from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

PRODUCT_NAME_MAX_LENGTH = 150
# The description is the short summary the assistant gives customers; the information is the long
# extra context (details, FAQs about the product) it looks up only when a question needs it.
PRODUCT_DESCRIPTION_MAX_LENGTH = 300
PRODUCT_INFORMATION_MAX_LENGTH = 5000
PRICE_MAX_DIGITS = 10  # up to 99,999,999.99
PRICE_DECIMAL_PLACES = 2
QUANTITY_MAX = 1_000_000

FAQ_QUESTION_MAX_LENGTH = 300
FAQ_ANSWER_MAX_LENGTH = 10000


class Product(models.Model):
    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='products',
    )
    name = models.CharField(max_length=PRODUCT_NAME_MAX_LENGTH)
    # Django doesn't enforce max_length on TextField at the model level, hence the explicit validator.
    description = models.TextField(
        max_length=PRODUCT_DESCRIPTION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(PRODUCT_DESCRIPTION_MAX_LENGTH)],
        help_text='A short summary of the product, which the assistant tells customers when they ask what it is.',
    )
    information = models.TextField(
        max_length=PRODUCT_INFORMATION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(PRODUCT_INFORMATION_MAX_LENGTH)],
        help_text=(
            'Extra details about the product (ingredients, sizes, options, allergens, FAQs, etc.). Not shown '
            'to customers as is: the assistant looks it up to answer specific questions.'
        ),
    )
    price = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    # The only stored quantity. On hold, sold and available are derived from the orders (see
    # `stock` below). PositiveIntegerField rejects negatives in validation and at the database level.
    total_quantity = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(QUANTITY_MAX)],
        help_text=(
            'How many the business has in total, including those on hold or sold in orders. It can '
            'go down only as far as on hold + sold, so the quantity available is never negative.'
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['business', 'name']
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name='product_price_non_negative'),
            models.CheckConstraint(condition=~Q(name=''), name='product_name_not_empty'),
            models.UniqueConstraint(
                fields=['business', 'name'],
                name='product_name_unique_per_business',
                violation_error_message='This business already has a product with this name.',
            ),
        ]

    def __str__(self) -> str:
        return self.name

    # --- Quantities derived from orders (checkout_app.stock) -----------------------------

    @classmethod
    def load_stock(cls, products) -> list['Product']:
        """Loads (or reloads) the order quantities of `products` in one query; returns them as a list.

        Use it before reading the quantities of many products, to avoid a query per product.
        """
        # Imported here: checkout_app imports this module.
        from checkout_app.stock import Stock, ordered_quantities

        products = list(products)
        saved = [product for product in products if product.pk is not None]
        stocks = ordered_quantities({p.business_id for p in saved}, {p.pk for p in saved}) if saved else {}
        for product in products:
            product._stock = stocks.get(product.pk, Stock())
        return products

    @property
    def stock(self):
        """This product's quantities in orders (checkout_app.stock.Stock), loaded on first use."""
        if '_stock' not in self.__dict__:
            Product.load_stock([self])
        return self._stock

    @property
    def quantity_on_hold(self) -> int:
        """In orders that are pending payment or have been paid, but aren't completed yet."""
        return self.stock.on_hold

    @property
    def quantity_sold(self) -> int:
        """In completed orders."""
        return self.stock.sold

    @property
    def quantity_available(self) -> int:
        """What can still be ordered: total_quantity - on hold - sold."""
        return self.total_quantity - self.stock.committed

    def refresh_from_db(self, *args, **kwargs):
        self.__dict__.pop('_stock', None)  # the orders may have changed too
        super().refresh_from_db(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.pk is not None and self.total_quantity is not None:
            Product.load_stock([self])  # fresh: orders may have changed since it was loaded
            if self.total_quantity < self.stock.committed:
                raise ValidationError({'total_quantity': total_quantity_error(self.stock)})


def total_quantity_error(stock) -> str:
    """Why a total_quantity below on hold + sold (checkout_app.stock.Stock) is rejected."""
    return (
        f'Must be at least {stock.committed} ({stock.on_hold} on hold and {stock.sold} sold in orders), '
        'so the quantity available is not negative.'
    )


class FAQ(models.Model):
    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='faqs',
    )
    question = models.CharField(max_length=FAQ_QUESTION_MAX_LENGTH)
    answer = models.TextField(
        max_length=FAQ_ANSWER_MAX_LENGTH,
        validators=[MaxLengthValidator(FAQ_ANSWER_MAX_LENGTH)],
    )

    class Meta:
        ordering = ['business', 'question']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'
        constraints = [
            models.CheckConstraint(condition=~Q(question=''), name='faq_question_not_empty'),
            models.CheckConstraint(condition=~Q(answer=''), name='faq_answer_not_empty'),
            models.UniqueConstraint(
                fields=['business', 'question'],
                name='faq_question_unique_per_business',
                violation_error_message='This business already has an FAQ with this question.',
            ),
        ]

    def __str__(self) -> str:
        return self.question


# --- Services and their weekly availability -------------------------------------------------

SLOT_MINUTES = 15  # every block of a weekly availability is 15 minutes
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96
DAYS_PER_WEEK = 7
AVAILABILITY_LENGTH = SLOTS_PER_DAY * DAYS_PER_WEEK  # 672
# One letter per block. In a WeeklyAvailability as stored (the recurring weekly template the
# business edits), only O blocks can be booked. In a week's calendar (checkout_app.schedule.week_calendar),
# bookings are drawn over the template: pending payment as H, paid or completed as X.
SLOT_AVAILABLE = 'O'
SLOT_TAKEN = 'X'
SLOT_ON_HOLD = 'H'
SLOT_LETTERS = (SLOT_AVAILABLE, SLOT_TAKEN, SLOT_ON_HOLD)
AVAILABILITY_PATTERN = rf'^[{"".join(SLOT_LETTERS)}]{{{AVAILABILITY_LENGTH}}}$'
NOT_AVAILABLE_WEEK = SLOT_TAKEN * AVAILABILITY_LENGTH

WEEKLY_AVAILABILITY_NAME_MAX_LENGTH = 150
SERVICE_NAME_MAX_LENGTH = PRODUCT_NAME_MAX_LENGTH
SERVICE_DESCRIPTION_MAX_LENGTH = PRODUCT_DESCRIPTION_MAX_LENGTH
SERVICE_INFORMATION_MAX_LENGTH = PRODUCT_INFORMATION_MAX_LENGTH
SERVICE_DURATION_MAX_MINUTES = 24 * 60
SERVICE_BUFFER_MAX_MINUTES = 24 * 60


def default_availability() -> str:
    """A new WeeklyAvailability: nothing bookable until the business opens some blocks."""
    return NOT_AVAILABLE_WEEK


def block_index(weekday: int, minute_of_day: int) -> int:
    """The position in a weekly availability of the block starting at `minute_of_day` (0–1439) on
    `weekday` (0 = Monday, as datetime.weekday())."""
    return weekday * SLOTS_PER_DAY + minute_of_day // SLOT_MINUTES


def validate_availability(value) -> None:
    """A weekly availability: exactly AVAILABILITY_LENGTH letters, each O (available), X (taken)
    or H (on hold); block 0 is Monday 00:00–00:15, block 96 Tuesday 00:00, and so on."""
    if not isinstance(value, str) or len(value) != AVAILABILITY_LENGTH:
        raise ValidationError(
            f'Must be exactly {AVAILABILITY_LENGTH} letters: one per {SLOT_MINUTES}-minute block of the week, '
            'from Monday 00:00.'
        )
    wrong = sorted(set(value) - set(SLOT_LETTERS))
    if wrong:
        raise ValidationError(
            f'Each block must be {SLOT_AVAILABLE} (available), {SLOT_TAKEN} (taken) or {SLOT_ON_HOLD} (on hold); '
            f'found {", ".join(repr(letter) for letter in wrong)}.'
        )


def validate_slot_minutes(value) -> None:
    """Durations and buffers fit whole 15-minute blocks."""
    if value is not None and value % SLOT_MINUTES:
        raise ValidationError(f'Must be a multiple of {SLOT_MINUTES} minutes.')


class WeeklyAvailability(models.Model):
    """When someone (e.g. one photographer) can take bookings, every week: a calendar of
    15-minute blocks (see validate_availability). Services list which availabilities can do them."""

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='weekly_availabilities',
    )
    name = models.CharField(
        max_length=WEEKLY_AVAILABILITY_NAME_MAX_LENGTH,
        help_text='Whose calendar this is, e.g. "Photographer: Mei" (not shown to customers).',
    )
    availability = models.CharField(
        max_length=AVAILABILITY_LENGTH,
        default=default_availability,
        validators=[validate_availability],
        help_text=(
            f'{AVAILABILITY_LENGTH} letters, one per {SLOT_MINUTES}-minute block of the week from Monday 00:00 '
            f'(local time): {SLOT_AVAILABLE} = available, {SLOT_TAKEN} = taken, {SLOT_ON_HOLD} = on hold. Only '
            f'{SLOT_AVAILABLE} blocks can be booked.'
        ),
    )

    class Meta:
        ordering = ['business', 'name']
        verbose_name_plural = 'weekly availabilities'
        constraints = [
            models.CheckConstraint(condition=~Q(name=''), name='weekly_availability_name_not_empty'),
            models.CheckConstraint(
                condition=Q(availability__regex=AVAILABILITY_PATTERN), name='weekly_availability_valid'
            ),
            models.UniqueConstraint(
                fields=['business', 'name'],
                name='weekly_availability_name_unique_per_business',
                violation_error_message='This business already has a weekly availability with this name.',
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def block(self, weekday: int, minute_of_day: int) -> str:
        """The letter of the block starting at `minute_of_day` on `weekday` (0 = Monday)."""
        return self.availability[block_index(weekday, minute_of_day)]


class Service(models.Model):
    """Something a customer books a time for (e.g. a photoshoot), done by the people whose weekly
    availabilities it lists. Booked as checkout_app.ScheduleItem."""

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='services',
    )
    # Which calendars can take a booking for this service: e.g. one photographer does every
    # service, another only some. They must be the same business's (checked by the serializer and admin).
    weekly_availability = models.ManyToManyField(
        WeeklyAvailability,
        blank=True,
        related_name='services',
        help_text='The weekly availabilities (e.g. photographers) that can do this service.',
    )
    name = models.CharField(max_length=SERVICE_NAME_MAX_LENGTH)
    description = models.TextField(
        max_length=SERVICE_DESCRIPTION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(SERVICE_DESCRIPTION_MAX_LENGTH)],
        help_text='A short summary of the service, which the assistant tells customers when they ask what it is.',
    )
    information = models.TextField(
        max_length=SERVICE_INFORMATION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(SERVICE_INFORMATION_MAX_LENGTH)],
        help_text=(
            "Extra details (what's included, what to bring, locations, FAQs, etc.). Not shown to customers "
            'as is: the assistant looks it up to answer specific questions.'
        ),
    )
    price = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    duration_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(SLOT_MINUTES), MaxValueValidator(SERVICE_DURATION_MAX_MINUTES), validate_slot_minutes],
        help_text=f'How long the service itself takes, with the customer: a multiple of {SLOT_MINUTES} minutes.',
    )
    buffer_minutes = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(SERVICE_BUFFER_MAX_MINUTES), validate_slot_minutes],
        help_text=(
            'Time blocked after each booking (e.g. to clean up or travel), without the customer, so '
            f'the next booking can only start after it: a multiple of {SLOT_MINUTES} minutes.'
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['business', 'name']
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name='service_price_non_negative'),
            models.CheckConstraint(condition=~Q(name=''), name='service_name_not_empty'),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=SLOT_MINUTES, duration_minutes__lte=SERVICE_DURATION_MAX_MINUTES),
                name='service_duration_in_range',
            ),
            models.CheckConstraint(
                condition=Q(buffer_minutes__lte=SERVICE_BUFFER_MAX_MINUTES), name='service_buffer_in_range'
            ),
            models.UniqueConstraint(
                fields=['business', 'name'],
                name='service_name_unique_per_business',
                violation_error_message='This business already has a service with this name.',
            ),
        ]

    def __str__(self) -> str:
        return self.name
