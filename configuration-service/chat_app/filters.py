import django_filters
from django.db.models import Q

from .models import ChatSession


class StableOrderingFilter(django_filters.OrderingFilter):
    """`?ordering=` that always adds `-id` last, so rows with equal values keep a fixed order
    across pages. Without `ordering`, the view's default order is kept."""

    def filter(self, qs, value):
        qs = super().filter(qs, value)
        if value:
            qs = qs.order_by(*qs.query.order_by, '-id')
        return qs


class ChatSessionFilter(django_filters.FilterSet):
    """Filters and sorting for GET /api/chat/sessions/. All parameters are optional and combine (AND)."""

    phone_number = django_filters.CharFilter(help_text='Exact phone number, e.g. `+6591234567` (URL-encode `+` as `%2B`).')
    search = django_filters.CharFilter(
        method='filter_search',
        help_text='Case-insensitive text in the display name or phone number.',
    )
    display_name = django_filters.CharFilter(lookup_expr='icontains', help_text='Case-insensitive text in the display name.')
    chat_state_id = django_filters.CharFilter(
        method='filter_chat_state_id',
        help_text='ID of the chat flow block the customer is at, e.g. `2` (a number is matched as a number).',
    )
    # A choice filter rather than BooleanFilter, which silently ignores values like "maybe".
    has_messages = django_filters.ChoiceFilter(
        choices=[('true', 'true'), ('false', 'false')],
        method='filter_has_messages',
        help_text='`true`: only chats with at least one message; `false`: only empty chats.',
    )
    created_time = django_filters.IsoDateTimeFromToRangeFilter(
        help_text='Use `created_time_after` / `created_time_before` (ISO 8601, inclusive).',
    )
    last_chat_time = django_filters.IsoDateTimeFromToRangeFilter(
        help_text='Use `last_chat_time_after` / `last_chat_time_before` (ISO 8601, inclusive).',
    )
    ordering = StableOrderingFilter(
        fields=('last_chat_time', 'created_time', 'display_name', 'phone_number', 'id'),
        help_text=(
            'Sort by one or more comma-separated fields; prefix with `-` for descending, e.g. '
            '`-last_chat_time` (the default) or `display_name,-created_time`.'
        ),
    )

    class Meta:
        model = ChatSession
        fields = ['phone_number', 'display_name', 'chat_state_id', 'created_time', 'last_chat_time']

    def filter_search(self, queryset, name, value):
        return queryset.filter(Q(display_name__icontains=value) | Q(phone_number__icontains=value))

    def filter_chat_state_id(self, queryset, name, value):
        # Block ids are ints or strings, and "2" must match block 2 (an int in the JSON).
        state_id = int(value) if value.lstrip('-').isdigit() else value
        return queryset.filter(chat_state_id=state_id)

    def filter_has_messages(self, queryset, name, value):
        empty = Q(chat_message_json=[])
        return queryset.exclude(empty) if value == 'true' else queryset.filter(empty)
