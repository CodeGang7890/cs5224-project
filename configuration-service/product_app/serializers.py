from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from auth_app.business_scope import BusinessOwnedSerializerMixin

from .models import AVAILABILITY_LENGTH, FAQ, Product, Service, WeeklyAvailability, total_quantity_error

# Derived from the orders (checkout_app.stock), so they can't be written.
DERIVED_QUANTITY_FIELDS = ('quantity_available', 'quantity_on_hold', 'quantity_sold')
DERIVED_QUANTITY_ERROR = 'This field is read-only: it is derived from the orders. Change total_quantity instead.'


class ProductListSerializer(serializers.ListSerializer):
    """Loads every product's order quantities in one query, instead of one per product."""

    def to_representation(self, data):
        products = data.all() if hasattr(data, 'all') else data
        return super().to_representation(Product.load_stock(products))


class ProductSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    quantity_on_hold = serializers.IntegerField(
        read_only=True,
        help_text='Derived: the quantity in orders that are pending payment or have been paid (not completed yet).',
    )
    quantity_sold = serializers.IntegerField(read_only=True, help_text='Derived: the quantity in completed orders.')
    quantity_available = serializers.IntegerField(
        read_only=True, help_text=(
            'Derived: total_quantity - quantity_on_hold - quantity_sold. The API keeps it from going '
            'negative (only orders created outside the chat, e.g. in Django Admin, could make it so).'
        ),
    )

    class Meta:
        model = Product
        fields = (
            'id',
            'business',
            'name',
            'description',
            'information',
            'price',
            'total_quantity',
            'quantity_available',
            'quantity_on_hold',
            'quantity_sold',
            'is_active',
        )
        read_only_fields = ('id',)
        list_serializer_class = ProductListSerializer
        extra_kwargs = {
            # Decimals are sent as strings, so Swagger can't show a numeric minimum; say it in the help text.
            'price': {
                'min_value': Decimal('0.00'),
                'help_text': 'Price as a decimal string, e.g. "12.50". Must be ≥ 0, max 2 decimal places.',
            },
            'total_quantity': {
                'help_text': (
                    'How many you have in total, including those on hold or sold in orders. Add stock by '
                    'raising it; lower it at most down to quantity_on_hold + quantity_sold (otherwise 400).'
                ),
            },
        }

    def to_internal_value(self, data):
        # DRF silently ignores read-only fields; reject the derived quantities explicitly so clients
        # notice, reported together with any other field errors.
        errors = {}
        try:
            value = super().to_internal_value(data)
        except serializers.ValidationError as exc:
            errors = dict(exc.detail)
        for field in DERIVED_QUANTITY_FIELDS:
            if field in data:
                errors[field] = [DERIVED_QUANTITY_ERROR]
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def update(self, instance, validated_data):
        """A new total_quantity can't go below what's on hold or sold in orders.

        Checked with the product's row locked (the same lock checkout_app.services.place_order takes),
        so an order placed at the same moment can't make the quantity available negative.
        """
        if 'total_quantity' not in validated_data:
            return super().update(instance, validated_data)
        with transaction.atomic():
            Product.objects.select_for_update().get(pk=instance.pk)  # the lock
            Product.load_stock([instance])
            if validated_data['total_quantity'] < instance.stock.committed:
                raise serializers.ValidationError({'total_quantity': [total_quantity_error(instance.stock)]})
            return super().update(instance, validated_data)


class FAQSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ('id', 'business', 'question', 'answer')
        read_only_fields = ('id',)


class WeeklyAvailabilitySerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    services = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True, help_text='The services this availability can do (set on each service).'
    )

    class Meta:
        model = WeeklyAvailability
        fields = ('id', 'business', 'name', 'availability', 'services')
        read_only_fields = ('id',)
        extra_kwargs = {'availability': {'required': False, 'min_length': AVAILABILITY_LENGTH}}


class ServiceSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    weekly_availability = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=WeeklyAvailability.objects.all(),
        help_text='IDs of your weekly availabilities (e.g. photographers) that can do this service.',
    )

    class Meta:
        model = Service
        fields = (
            'id',
            'business',
            'name',
            'description',
            'information',
            'price',
            'duration_minutes',
            'buffer_minutes',
            'weekly_availability',
            'is_active',
        )
        read_only_fields = ('id',)
        extra_kwargs = {
            'price': {
                'min_value': Decimal('0.00'),
                'help_text': 'Price as a decimal string, e.g. "180.00". Must be ≥ 0, max 2 decimal places.',
            },
        }

    def validate(self, attrs):
        business = attrs.get('business') or (self.instance.business if self.instance else None)
        others = [a.pk for a in attrs.get('weekly_availability', []) if business and a.business_id != business.pk]
        if others:
            raise serializers.ValidationError(
                {'weekly_availability': [f'Not your business\'s weekly availability: {", ".join(map(str, others))}.']}
            )
        return attrs


class SlotQuerySerializer(serializers.Serializer):
    """Query parameters of GET /api/services/{id}/slots/."""

    date_from = serializers.DateField(help_text='First day (local date, YYYY-MM-DD).')
    date_to = serializers.DateField(
        required=False, help_text='Last day, inclusive (default: date_from). At most 31 days are searched.'
    )

    def validate(self, attrs):
        attrs.setdefault('date_to', attrs['date_from'])
        if attrs['date_to'] < attrs['date_from']:
            raise serializers.ValidationError({'date_to': ['Must not be before date_from.']})
        return attrs


class CalendarQuerySerializer(serializers.Serializer):
    """Query parameters of GET /api/weekly-availabilities/{id}/calendar/."""

    week = serializers.DateField(help_text='Any day of the week to show (local date, YYYY-MM-DD).')


class CalendarBookingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    service = serializers.CharField(help_text='The service name (from the booking).')
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    blocked_until = serializers.DateTimeField()
    order_status = serializers.CharField()


class WeekCalendarSerializer(serializers.Serializer):
    week_start = serializers.DateField(help_text='The Monday of the week.')
    availability = serializers.CharField(
        help_text=(
            'The weekly template with that week\'s bookings drawn over it: H where a booking is pending '
            'payment, X where it is paid or completed (including its buffer).'
        ),
    )
    bookings = CalendarBookingSerializer(many=True)


class SlotsSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    slots = serializers.ListField(
        child=serializers.DateTimeField(), help_text='Start times at which the service can be booked.'
    )
