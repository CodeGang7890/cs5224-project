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


# --- Services, their providers and the providers' weekly availability ---------------------------

SLOT_MINUTES = 15  # every block of a weekly availability is 15 minutes
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 96
DAYS_PER_WEEK = 7
AVAILABILITY_LENGTH = SLOTS_PER_DAY * DAYS_PER_WEEK  # 672
# One letter per block of a provider's week. The business opens (O) or closes (U) blocks; the
# bookings (checkout_app.ScheduleItem) set them to H or X themselves, and only they can (see
# checkout_app.schedule): H while a booking is pending payment, X once it's paid or completed.
SLOT_AVAILABLE = 'O'  # open: customers can book it
SLOT_UNAVAILABLE = 'U'  # not open for booking
SLOT_ON_HOLD = 'H'  # booked, payment pending
SLOT_BOOKED = 'X'  # booked and paid (or done)
SLOT_LETTERS = (SLOT_AVAILABLE, SLOT_UNAVAILABLE, SLOT_ON_HOLD, SLOT_BOOKED)
BOOKED_LETTERS = (SLOT_ON_HOLD, SLOT_BOOKED)  # taken by a booking
# Exactly AVAILABILITY_LENGTH letters, written as days of blocks: PostgreSQL rejects repeat counts
# over 255 (so `[OUHX]{672}` fails on every insert there, while SQLite's Python regex allows it).
AVAILABILITY_PATTERN = rf'^([{"".join(SLOT_LETTERS)}]{{{SLOTS_PER_DAY}}}){{{DAYS_PER_WEEK}}}$'
UNAVAILABLE_WEEK = SLOT_UNAVAILABLE * AVAILABILITY_LENGTH

SERVICE_PROVIDER_NAME_MAX_LENGTH = 150
SERVICE_PROVIDER_DESCRIPTION_MAX_LENGTH = 300
SERVICE_NAME_MAX_LENGTH = PRODUCT_NAME_MAX_LENGTH
SERVICE_DESCRIPTION_MAX_LENGTH = PRODUCT_DESCRIPTION_MAX_LENGTH
SERVICE_INFORMATION_MAX_LENGTH = PRODUCT_INFORMATION_MAX_LENGTH
SERVICE_DURATION_MAX_MINUTES = 24 * 60
SERVICE_BUFFER_MAX_MINUTES = 24 * 60
# Bookings of a service start only every this many minutes, counted from midnight (local time):
# 30 → 9:00, 9:30, 10:00…; 60 → 9:00, 10:00…. The default, 15, is every block.
DEFAULT_START_INTERVAL_MINUTES = SLOT_MINUTES
SERVICE_START_INTERVAL_MAX_MINUTES = 24 * 60
START_INTERVAL_PRESETS = (15, 30, 60)  # offered first in the frontend (any multiple of 15 is allowed)


def default_availability() -> str:
    """A new week: nothing open until the business opens some blocks."""
    return UNAVAILABLE_WEEK


def block_index(weekday: int, minute_of_day: int) -> int:
    """The position in a week's availability of the block starting at `minute_of_day` (0–1439) on
    `weekday` (0 = Monday, as datetime.weekday())."""
    return weekday * SLOTS_PER_DAY + minute_of_day // SLOT_MINUTES


def validate_availability(value) -> None:
    """A week's availability: exactly AVAILABILITY_LENGTH letters, each O (available), U
    (unavailable), H (on hold) or X (booked); block 0 is Monday 00:00–00:15, block 96 Tuesday 00:00."""
    if not isinstance(value, str) or len(value) != AVAILABILITY_LENGTH:
        raise ValidationError(
            f'Must be exactly {AVAILABILITY_LENGTH} letters: one per {SLOT_MINUTES}-minute block of the week, '
            'from Monday 00:00.'
        )
    wrong = sorted(set(value) - set(SLOT_LETTERS))
    if wrong:
        raise ValidationError(
            f'Each block must be {SLOT_AVAILABLE} (available), {SLOT_UNAVAILABLE} (unavailable), {SLOT_ON_HOLD} '
            f'(on hold) or {SLOT_BOOKED} (booked); found {", ".join(repr(letter) for letter in wrong)}.'
        )


def validate_monday(value) -> None:
    """A week is identified by its Monday."""
    if value is not None and value.weekday() != 0:
        raise ValidationError('Must be a Monday: the first day of the week.')


def validate_slot_minutes(value) -> None:
    """Durations and buffers fit whole 15-minute blocks."""
    if value is not None and value % SLOT_MINUTES:
        raise ValidationError(f'Must be a multiple of {SLOT_MINUTES} minutes.')


class ServiceProvider(models.Model):
    """Who (or what) a service is booked with: one photographer, one teacher, one venue... Each
    has a calendar of WeeklyAvailability weeks, and does the Services that list it."""

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='service_providers',
    )
    name = models.CharField(
        max_length=SERVICE_PROVIDER_NAME_MAX_LENGTH,
        help_text='e.g. "Mei Lin" or "Studio A" (not shown to customers).',
    )
    description = models.CharField(
        max_length=SERVICE_PROVIDER_DESCRIPTION_MAX_LENGTH,
        blank=True,
        help_text='Optional note for the business, e.g. "Lead photographer".',
    )
    is_active = models.BooleanField(default=True, help_text='Inactive providers take no new bookings.')

    class Meta:
        ordering = ['business', 'name']
        constraints = [
            models.CheckConstraint(condition=~Q(name=''), name='service_provider_name_not_empty'),
            models.UniqueConstraint(
                fields=['business', 'name'],
                name='service_provider_name_unique_per_business',
                violation_error_message='This business already has a service provider with this name.',
            ),
        ]

    def __str__(self) -> str:
        return self.name


class WeeklyAvailability(models.Model):
    """One service provider's availability in one week (`week`: its Monday), in 15-minute blocks
    of local time (settings.SCHEDULE_TIME_ZONE); see validate_availability. A week without a row
    is all unavailable."""

    service_provider = models.ForeignKey(
        ServiceProvider,
        on_delete=models.CASCADE,
        related_name='weekly_availabilities',
    )
    week = models.DateField(validators=[validate_monday], help_text='The Monday of the week.')
    availability = models.CharField(
        max_length=AVAILABILITY_LENGTH,
        default=default_availability,
        validators=[validate_availability],
        help_text=(
            f'{AVAILABILITY_LENGTH} letters, one per {SLOT_MINUTES}-minute block from Monday 00:00 (local '
            f'time): {SLOT_AVAILABLE} = available, {SLOT_UNAVAILABLE} = unavailable, {SLOT_ON_HOLD} = on hold '
            f'(booked, payment pending), {SLOT_BOOKED} = booked. Bookings set {SLOT_ON_HOLD} and {SLOT_BOOKED}.'
        ),
    )

    class Meta:
        ordering = ['service_provider', 'week']
        verbose_name_plural = 'weekly availabilities'
        constraints = [
            models.UniqueConstraint(
                fields=['service_provider', 'week'],
                name='weekly_availability_unique_week',
                violation_error_message='This service provider already has an availability for this week.',
            ),
            models.CheckConstraint(
                condition=Q(availability__regex=AVAILABILITY_PATTERN), name='weekly_availability_letters_valid'
            ),
        ]

    def __str__(self) -> str:
        return f'{self.service_provider} – week of {self.week:%d %b %Y}' if self.week else str(self.service_provider)

    @property
    def business_id(self):
        return self.service_provider.business_id

    def block(self, weekday: int, minute_of_day: int) -> str:
        """The letter of the block starting at `minute_of_day` on `weekday` (0 = Monday)."""
        return self.availability[block_index(weekday, minute_of_day)]


class Service(models.Model):
    """Something a customer books a time for (e.g. a photoshoot), with one of the service providers
    it lists. Booked as checkout_app.ScheduleItem."""

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='services',
    )
    # Who can do it: e.g. one photographer does every service, another only some. They must be the
    # same business's (checked by the serializer and admin).
    service_providers = models.ManyToManyField(
        ServiceProvider,
        blank=True,
        related_name='services',
        help_text='The service providers (e.g. photographers) who can do this service.',
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
    start_interval_minutes = models.PositiveIntegerField(
        default=DEFAULT_START_INTERVAL_MINUTES,
        validators=[
            MinValueValidator(SLOT_MINUTES), MaxValueValidator(SERVICE_START_INTERVAL_MAX_MINUTES), validate_slot_minutes,
        ],
        help_text=(
            f'Bookings only start every this many minutes, counted from midnight: {SLOT_MINUTES} (any quarter hour, '
            f'the default), 30 (on the hour and half hour), 60 (on the hour), or any multiple of {SLOT_MINUTES}.'
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['business', 'name']
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name='service_price_non_negative'),
            models.CheckConstraint(
                condition=Q(
                    start_interval_minutes__gte=SLOT_MINUTES, start_interval_minutes__lte=SERVICE_START_INTERVAL_MAX_MINUTES
                ),
                name='service_start_interval_in_range',
            ),
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
