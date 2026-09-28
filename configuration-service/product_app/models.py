from decimal import Decimal

from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db import models
from django.db.models import Q

PRODUCT_NAME_MAX_LENGTH = 150
PRODUCT_DESCRIPTION_MAX_LENGTH = 5000
PRICE_MAX_DIGITS = 10  # up to 99,999,999.99
PRICE_DECIMAL_PLACES = 2

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
    )
    price = models.DecimalField(
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    # PositiveIntegerField rejects negatives in validation and at the database level.
    quantity_available = models.PositiveIntegerField(default=0)
    quantity_on_hold = models.PositiveIntegerField(default=0)
    quantity_sold = models.PositiveIntegerField(default=0)
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
