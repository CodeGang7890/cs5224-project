from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from .validators import validate_order_data


class OrderStatus(models.TextChoices):
    # The chat flow creates orders as PENDING_PAYMENT; the other two are set later (payment service).
    PENDING_PAYMENT = 'pending_payment', 'Pending payment'
    PAYMENT_RECEIVED = 'payment_received', 'Payment received'
    ORDER_COMPLETED = 'order_completed', 'Order completed'


ORDER_STATUS_MAX_LENGTH = 32


class OrderItem(models.Model):
    """An order a customer confirmed in a chat: what they ordered and their details (`order_data`).

    Created by checkout_app.services.place_order(), which also reserves the stock: each product's
    quantity moves from `quantity_available` to `quantity_on_hold` while payment is pending.
    """

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='order_items',
    )
    # Kept (as null) if the chat is deleted, e.g. a sandbox chat.
    chat_session = models.ForeignKey(
        'chat_app.ChatSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items',
        help_text='The chat the order was placed in.',
    )
    is_sandbox = models.BooleanField(
        default=False,
        help_text='Placed in a Chat Sandbox test chat rather than by a real customer.',
    )
    order_data = models.JSONField(
        validators=[validate_order_data],
        help_text='The items ordered (product, price, quantity) and the customer details collected.',
    )
    order_status = models.CharField(
        max_length=ORDER_STATUS_MAX_LENGTH,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
    )
    # Not auto_now_add, so fixtures and tests can set it (like ChatSession.created_time).
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_time', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(order_status__in=OrderStatus.values),
                name='order_item_status_valid',
            ),
        ]

    def __str__(self) -> str:
        return f'Order #{self.pk} ({self.business})'

    @property
    def total(self) -> Decimal:
        """Sum of unit_price × quantity over the items."""
        items = self.order_data.get('items', []) if isinstance(self.order_data, dict) else []
        return sum((Decimal(item['unit_price']) * item['quantity'] for item in items), Decimal('0.00'))
