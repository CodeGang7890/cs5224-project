from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from auth_app.business_scope import BusinessOwnedSerializerMixin

from .models import FAQ, Product, total_quantity_error

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
