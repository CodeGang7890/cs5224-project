import django_filters

from chat_app.filters import SANDBOX_EXCLUDE, SANDBOX_INCLUDE, SANDBOX_ONLY, StableOrderingFilter

from .models import OrderItem, OrderStatus, ScheduleItem


class OrderItemFilter(django_filters.FilterSet):
    """Filters and sorting for GET /api/orders/. All parameters are optional and combine (AND).

    Unlike chat sessions, sandbox (test) orders are included by default: they reserve real stock.
    """

    order_status = django_filters.ChoiceFilter(choices=OrderStatus.choices, help_text='Only orders with this status.')
    payment_reference = django_filters.CharFilter(
        field_name='payment_reference', lookup_expr='iexact', help_text='Only the order with this payment reference.',
    )
    sandbox = django_filters.ChoiceFilter(
        choices=[(SANDBOX_INCLUDE, SANDBOX_INCLUDE), (SANDBOX_EXCLUDE, SANDBOX_EXCLUDE), (SANDBOX_ONLY, SANDBOX_ONLY)],
        method='filter_sandbox',
        help_text='Sandbox (test) orders: `include` (the default), `exclude` or `only`.',
    )
    created_time = django_filters.IsoDateTimeFromToRangeFilter(
        help_text='Use `created_time_after` / `created_time_before` (ISO 8601, inclusive).',
    )
    ordering = StableOrderingFilter(
        fields=('created_time', 'order_status', 'id'),
        help_text='Sort by `created_time`, `order_status` or `id`; prefix with `-` for descending. Default: `-created_time`.',
    )

    class Meta:
        model = OrderItem
        fields = ['order_status', 'payment_reference', 'created_time']

    def filter_sandbox(self, queryset, name, value):
        if value == SANDBOX_ONLY:
            return queryset.filter(is_sandbox=True)
        if value == SANDBOX_EXCLUDE:
            return queryset.filter(is_sandbox=False)
        return queryset


class ScheduleItemFilter(django_filters.FilterSet):
    """Filters and sorting for GET /api/schedules/. All parameters are optional and combine (AND).

    Sandbox (test) bookings are included by default, like orders: they take up real time.
    """

    order_status = django_filters.ChoiceFilter(choices=OrderStatus.choices, help_text='Only bookings with this status.')
    payment_reference = django_filters.CharFilter(
        field_name='payment_reference', lookup_expr='iexact', help_text='Only the booking with this payment reference.',
    )
    sandbox = django_filters.ChoiceFilter(
        choices=[(SANDBOX_INCLUDE, SANDBOX_INCLUDE), (SANDBOX_EXCLUDE, SANDBOX_EXCLUDE), (SANDBOX_ONLY, SANDBOX_ONLY)],
        method='filter_sandbox',
        help_text='Sandbox (test) bookings: `include` (the default), `exclude` or `only`.',
    )
    service = django_filters.NumberFilter(field_name='service_id', help_text='Only bookings of this service (ID).')
    service_provider = django_filters.NumberFilter(
        field_name='service_provider_id', help_text='Only bookings with this service provider (ID).'
    )
    start_time = django_filters.IsoDateTimeFromToRangeFilter(
        help_text='Use `start_time_after` / `start_time_before` (ISO 8601, inclusive).',
    )
    created_time = django_filters.IsoDateTimeFromToRangeFilter(
        help_text='Use `created_time_after` / `created_time_before` (ISO 8601, inclusive).',
    )
    ordering = StableOrderingFilter(
        fields=('start_time', 'created_time', 'order_status', 'id'),
        help_text=(
            'Sort by `start_time`, `created_time`, `order_status` or `id`; prefix with `-` for descending. '
            'Default: `-start_time`.'
        ),
    )

    class Meta:
        model = ScheduleItem
        fields = ['order_status', 'payment_reference', 'start_time', 'created_time']

    filter_sandbox = OrderItemFilter.filter_sandbox
