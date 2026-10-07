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
