from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .validators import validate_order_data, validate_schedule_data


class OrderStatus(models.TextChoices):
    # The chat flow creates orders as PENDING_PAYMENT; the other two are set later (payment service).
    PENDING_PAYMENT = 'pending_payment', 'Pending payment'
    PAYMENT_RECEIVED = 'payment_received', 'Payment received'
    ORDER_COMPLETED = 'order_completed', 'Order completed'
    # The payment didn't go through (set by the payment service, later). Holds no stock and no time.
    PAYMENT_FAILED = 'payment_failed', 'Payment failed'


ORDER_STATUS_MAX_LENGTH = 32


class OrderItem(models.Model):
    """An order a customer confirmed in a chat: what they ordered and their details (`order_data`).

    Created by checkout_app.services.place_order(). Products' on hold / sold / available
    quantities are derived from the orders (checkout_app.stock): an order's quantities are on hold
    while it's pending payment or paid, and sold once it's completed.
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


class ScheduleItem(models.Model):
    """A time slot a customer booked for a service in a chat (`schedule_data`: the service and
    their details). Like OrderItem, but for product_app.Service.

    Created by checkout_app.services.place_booking(). It takes up its service provider's time from
    `start_time` until `blocked_until` (the end of the service plus its buffer), and writes that
    into the provider's WeeklyAvailability: on hold (H) while pending payment, booked (X) once paid
    or completed, and available (O) again if it's deleted (checkout_app.schedule.sync_booking, run
    by the signals in checkout_app/signals.py whenever a booking is saved or deleted).
    """

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='schedule_items',
    )
    chat_session = models.ForeignKey(
        'chat_app.ChatSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedule_items',
        help_text='The chat the booking was made in.',
    )
    is_sandbox = models.BooleanField(
        default=False,
        help_text='Booked in a Chat Sandbox test chat rather than by a real customer.',
    )
    # Kept (as null) if the service or provider is deleted: schedule_data has the snapshot.
    service = models.ForeignKey(
        'product_app.Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedule_items',
    )
    service_provider = models.ForeignKey(
        'product_app.ServiceProvider',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedule_items',
        help_text='Who it is booked with (e.g. which photographer).',
    )
    start_time = models.DateTimeField(help_text='When the service starts.')
    end_time = models.DateTimeField(help_text='When the service ends: start_time + its duration.')
    blocked_until = models.DateTimeField(
        help_text="When the calendar is free again: end_time + the service's buffer."
    )
    schedule_data = models.JSONField(
        validators=[validate_schedule_data],
        help_text='The service booked (name, price, duration, buffer) and the customer details collected.',
    )
    order_status = models.CharField(
        max_length=ORDER_STATUS_MAX_LENGTH,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
    )
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time', '-id']
        indexes = [models.Index(fields=['service_provider', 'start_time'], name='schedule_item_provider_time')]
        constraints = [
            models.CheckConstraint(
                condition=Q(order_status__in=OrderStatus.values),
                name='schedule_item_status_valid',
            ),
            models.CheckConstraint(condition=Q(end_time__gt=F('start_time')), name='schedule_item_ends_after_start'),
            models.CheckConstraint(
                condition=Q(blocked_until__gte=F('end_time')), name='schedule_item_blocked_after_end'
            ),
        ]

    def __str__(self) -> str:
        return f'Booking #{self.pk} ({self.business})'

    @property
    def total(self) -> Decimal:
        """The service's price (from the snapshot)."""
        service = self.schedule_data.get('service', {}) if isinstance(self.schedule_data, dict) else {}
        return Decimal(service.get('price', '0.00'))

    def clean(self):
        super().clean()
        errors = {}
        service = self.schedule_data.get('service') if isinstance(self.schedule_data, dict) else None
        if self.start_time and self.end_time and self.blocked_until and isinstance(service, dict):
            duration, buffer = service.get('duration_minutes'), service.get('buffer_minutes')
            if isinstance(duration, int) and self.end_time != self.start_time + timedelta(minutes=duration):
                errors['end_time'] = 'Must be start_time plus the service duration.'
            if isinstance(buffer, int) and self.blocked_until != self.end_time + timedelta(minutes=buffer):
                errors['blocked_until'] = 'Must be end_time plus the service buffer.'
        for field in ('service', 'service_provider', 'chat_session'):
            related = getattr(self, field) if getattr(self, f'{field}_id') else None
            if related is not None and self.business_id and related.business_id != self.business_id:
                errors[field] = f"The {field.replace('_', ' ')} must belong to the booking's business."
        if errors:
            raise ValidationError(errors)
