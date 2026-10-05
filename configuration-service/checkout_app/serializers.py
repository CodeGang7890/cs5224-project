from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import OrderItem

# order_data is stored and validated as plain JSON (validate_order_data). The serializers below
# only describe its shape in the Swagger docs.


class OrderLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField(help_text='Product name when it was ordered.')
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text='Price when it was ordered.')
    quantity = serializers.IntegerField(min_value=1)


class OrderDataSerializer(serializers.Serializer):
    items = OrderLineSerializer(many=True, help_text='What was ordered: one line per product.')
    details = serializers.DictField(
        help_text='Customer details collected in the chat, by field key (strings or numbers), e.g. `{"name": "Alice"}`.',
    )


@extend_schema_field(OrderDataSerializer)
class OrderDataJSONField(serializers.JSONField):
    pass


class OrderItemSerializer(serializers.ModelSerializer):
    """An order, read only (orders are created by the chat flow when a customer confirms)."""

    order_data = OrderDataJSONField(read_only=True)
    total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, help_text='Sum of unit_price × quantity.'
    )

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'business',
            'chat_session',
            'is_sandbox',
            'order_status',
            'order_data',
            'total',
            'created_time',
            'updated_time',
        ]
        read_only_fields = fields
