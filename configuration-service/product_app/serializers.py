from decimal import Decimal

from rest_framework import serializers

from auth_app.business_scope import BusinessOwnedSerializerMixin

from .models import FAQ, Product


class ProductSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            'id',
            'business',
            'name',
            'description',
            'price',
            'quantity_available',
            'quantity_on_hold',
            'quantity_sold',
            'is_active',
        )
        # quantity_sold is managed by the system (e.g. future order processing), not edited by users.
        read_only_fields = ('id', 'quantity_sold')
        extra_kwargs = {
            # Decimals are sent as strings, so Swagger can't show a numeric minimum; say it in the help text.
            'price': {
                'min_value': Decimal('0.00'),
                'help_text': 'Price as a decimal string, e.g. "12.50". Must be ≥ 0, max 2 decimal places.',
            },
            'quantity_sold': {'help_text': 'Read-only. Managed by the system; sending it returns 400.'},
        }

    def to_internal_value(self, data):
        # DRF silently ignores read-only fields; reject quantity_sold explicitly so clients notice,
        # reported together with any other field errors.
        errors = {}
        try:
            value = super().to_internal_value(data)
        except serializers.ValidationError as exc:
            errors = dict(exc.detail)
        if 'quantity_sold' in data:
            errors['quantity_sold'] = ['This field is read-only.']
        if errors:
            raise serializers.ValidationError(errors)
        return value


class FAQSerializer(BusinessOwnedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ('id', 'business', 'question', 'answer')
        read_only_fields = ('id',)
