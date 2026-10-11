from datetime import time, timedelta
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from auth_app.business_scope import OTHER_BUSINESS_MESSAGE, BusinessOwnedSerializerMixin
from checkout_app.schedule import WEEKS_CHANGED_MAX

from .models import (
    AVAILABILITY_LENGTH,
    BOOKED_LETTERS,
    FAQ,
    SLOT_MINUTES,
    Product,
    Service,
    ServiceProvider,
    WeeklyAvailability,
    total_quantity_error,
    validate_monday,
)

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


def _check_letters(new: str, old: str | None) -> None:
    """The business can only open (O) or close (U) blocks; H / X are set by bookings.

    `old`: the week's letters before (None for a new week). Raises a ValidationError if a booked
    block (H / X) would change, or a block would be set to H / X.
    """
    problems = []
    if old is None:
        if any(letter in BOOKED_LETTERS for letter in new):
            problems.append('Only O (available) and U (unavailable) can be set: H and X come from bookings.')
    else:
        booked = sum(1 for a, b in zip(old, new) if a in BOOKED_LETTERS and a != b)
        made_booked = sum(1 for a, b in zip(old, new) if a not in BOOKED_LETTERS and b in BOOKED_LETTERS)
        if booked:
            problems.append(f"{booked} booked block{'s' if booked != 1 else ''} (H / X) can't be changed: cancel the booking instead.")
        if made_booked:
            problems.append('Only O (available) and U (unavailable) can be set: H and X come from bookings.')
    if problems:
        raise serializers.ValidationError({'availability': problems})


class ServiceProviderSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    services = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True, help_text='The services this provider does (set on each service).'
    )

    class Meta:
        model = ServiceProvider
        fields = ('id', 'business', 'name', 'description', 'is_active', 'services')
        read_only_fields = ('id',)


class WeeklyAvailabilitySerializer(serializers.ModelSerializer):
    """One provider's week. `service_provider` and `week` can't change once created; the letters
    can only go between O and U (booked blocks, H / X, are set by bookings and stay as they are)."""

    service_provider = serializers.PrimaryKeyRelatedField(
        queryset=ServiceProvider.objects.all(), help_text='One of your service providers (ID).'
    )

    class Meta:
        model = WeeklyAvailability
        fields = ('id', 'service_provider', 'week', 'availability')
        read_only_fields = ('id',)
        extra_kwargs = {'availability': {'required': False, 'min_length': AVAILABILITY_LENGTH}}

    def validate_service_provider(self, provider):
        if provider.business_id != self.context['request'].user.business_id:
            raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
        if self.instance is not None and provider.pk != self.instance.service_provider_id:
            raise serializers.ValidationError("Can't be changed: create a week for the other provider instead.")
        return provider

    def validate_week(self, week):
        if self.instance is not None and week != self.instance.week:
            raise serializers.ValidationError("Can't be changed: create (or copy to) the other week instead.")
        return week

    def create(self, validated_data):
        if 'availability' in validated_data:
            _check_letters(validated_data['availability'], None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Checked and saved with the provider locked (like place_booking), against the week's
        current letters, so a booking made at the same moment is never overwritten."""
        if 'availability' not in validated_data:
            return super().update(instance, validated_data)
        with transaction.atomic():
            ServiceProvider.objects.select_for_update().filter(pk=instance.service_provider_id).first()
            instance.availability = WeeklyAvailability.objects.select_for_update().get(pk=instance.pk).availability
            _check_letters(validated_data['availability'], instance.availability)
            return super().update(instance, validated_data)


class ServiceSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    service_providers = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=ServiceProvider.objects.all(),
        help_text='IDs of your service providers (e.g. photographers) who can do this service.',
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
            'start_interval_minutes',
            'service_providers',
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
        others = [p.pk for p in attrs.get('service_providers', []) if business and p.business_id != business.pk]
        if others:
            raise serializers.ValidationError(
                {'service_providers': [f"Not your business's service provider: {', '.join(map(str, others))}."]}
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


class SlotsSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    slots = serializers.ListField(
        child=serializers.DateTimeField(), help_text='Start times at which the service can be booked.'
    )


class CalendarQuerySerializer(serializers.Serializer):
    """Query parameters of GET /api/service-providers/{id}/calendar/."""

    week = serializers.DateField(help_text='Any day of the week to show (local date, YYYY-MM-DD).')


class CalendarBookingSerializer(serializers.Serializer):
    """A booking in a provider's week: who booked it and its status (for clicking a block)."""

    id = serializers.IntegerField()
    service = serializers.CharField(help_text='The service name (from the booking).')
    customer = serializers.CharField(allow_null=True, help_text="The customer's name (a `name` detail), else null.")
    details = serializers.DictField(help_text='The customer details collected in the chat.')
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    blocked_until = serializers.DateTimeField(help_text='end_time + the buffer.')
    order_status = serializers.CharField(
        help_text='`pending_payment` (H), `payment_received` / `order_completed` (X); bookings whose payment failed take up no time and are not listed.'
    )
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_sandbox = serializers.BooleanField()
    chat_session = serializers.IntegerField(allow_null=True)
    start_block = serializers.IntegerField(
        help_text="Index in this week's letters of the block start_time is in (negative if it started the week before)."
    )
    end_block = serializers.IntegerField(help_text='Index of the block end_time is in (the buffer starts there; may be ≥ 672).')
    until_block = serializers.IntegerField(
        help_text='Index of the first block after blocked_until, rounded up (may be ≥ 672 if it runs into the next week).'
    )


class WeekCalendarSerializer(serializers.Serializer):
    service_provider = serializers.IntegerField()
    week = serializers.DateField(help_text='The Monday of the week.')
    time_zone = serializers.CharField(help_text='The time zone the blocks are in (e.g. Asia/Singapore).')
    id = serializers.IntegerField(allow_null=True, help_text="The week's WeeklyAvailability ID; null if it has none yet.")
    availability = serializers.CharField(help_text='The 672 letters (all U if the week has no WeeklyAvailability yet).')
    bookings = CalendarBookingSerializer(many=True)


class SetSlotsSerializer(serializers.Serializer):
    """Body of POST /api/service-providers/{id}/slots/: open or close blocks over a range of days."""

    date_from = serializers.DateField(help_text='First day (YYYY-MM-DD).')
    date_to = serializers.DateField(help_text='Last day, inclusive; at most 26 weeks after date_from.')
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), min_length=1, max_length=7,
        help_text='The days of the week to change: 0 = Monday … 6 = Sunday.',
    )
    time_from = serializers.TimeField(help_text='From (local time, HH:MM, on the quarter hour).')
    time_to = serializers.CharField(help_text='Until (HH:MM on the quarter hour, after time_from), or 24:00.')
    available = serializers.BooleanField(
        default=True, help_text='true: open the blocks (O); false: close them (U). Booked blocks are left alone.'
    )

    def validate(self, attrs):
        errors = {}
        if attrs['date_to'] < attrs['date_from']:
            errors['date_to'] = ['Must not be before date_from.']
        elif (attrs['date_to'] - attrs['date_from']).days >= 7 * WEEKS_CHANGED_MAX:
            errors['date_to'] = [f'At most {WEEKS_CHANGED_MAX} weeks at once.']
        if attrs['time_from'].minute % SLOT_MINUTES or attrs['time_from'].second:
            errors['time_from'] = [f'Must be on the quarter hour (every {SLOT_MINUTES} minutes).']
        raw = attrs['time_to'].strip()
        to = None
        if raw != '24:00':
            try:
                to = time.fromisoformat(raw)
            except ValueError:
                errors['time_to'] = ['Must be HH:MM, or 24:00.']
        if to is not None and (to.minute % SLOT_MINUTES or to.second):
            errors['time_to'] = [f'Must be on the quarter hour (every {SLOT_MINUTES} minutes).']
        elif 'time_to' not in errors and to is not None and to <= attrs['time_from']:
            errors['time_to'] = ['Must be after time_from.']
        if errors:
            raise serializers.ValidationError(errors)
        attrs['time_to'] = to  # None: midnight
        attrs['weekdays'] = sorted(set(attrs['weekdays']))
        return attrs


class CopyWeekSerializer(serializers.Serializer):
    """Body of POST /api/service-providers/{id}/copy-week/."""

    source_week = serializers.DateField(help_text='The week to copy: its Monday.', validators=[validate_monday])
    target_week = serializers.DateField(
        required=False, validators=[validate_monday], help_text='The first week to copy to: a Monday (default: the next week).'
    )
    weeks = serializers.IntegerField(
        default=1, min_value=1, max_value=WEEKS_CHANGED_MAX, help_text='How many weeks to copy to, from target_week.'
    )

    def validate(self, attrs):
        attrs.setdefault('target_week', attrs['source_week'] + timedelta(weeks=1))
        if attrs['target_week'] == attrs['source_week']:
            raise serializers.ValidationError({'target_week': ['Must not be the week being copied.']})
        return attrs


class WeeksChangeSerializer(serializers.Serializer):
    weeks = WeeklyAvailabilitySerializer(many=True, help_text='Every week changed or created.')
    changed = serializers.IntegerField(help_text='Blocks that changed.')
    skipped = serializers.IntegerField(help_text='Blocks left alone because they are booked (H / X).')
