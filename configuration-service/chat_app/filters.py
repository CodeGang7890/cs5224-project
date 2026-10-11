import django_filters
from django.db.models import Q

from .constants import CHAT_STEPS, STEP_LABELS
from .models import ChatSession, QuestionStatus, UnansweredQuestion


class StableOrderingFilter(django_filters.OrderingFilter):
    """`?ordering=` that always adds `-id` last, so rows with equal values keep a fixed order
    across pages. Without `ordering`, the view's default order is kept."""

    def filter(self, qs, value):
        qs = super().filter(qs, value)
        if value:
            qs = qs.order_by(*qs.query.order_by, '-id')
        return qs


SANDBOX_EXCLUDE = 'exclude'
SANDBOX_INCLUDE = 'include'
SANDBOX_ONLY = 'only'


class ChatSessionFilter(django_filters.FilterSet):
    """Filters and sorting for GET /api/chat/sessions/. All parameters are optional and combine (AND).

    Sandbox (test) sessions are left out unless `sandbox=include` or `sandbox=only`.
    """

    sandbox = django_filters.ChoiceFilter(
        choices=[(SANDBOX_EXCLUDE, SANDBOX_EXCLUDE), (SANDBOX_INCLUDE, SANDBOX_INCLUDE), (SANDBOX_ONLY, SANDBOX_ONLY)],
        method='filter_sandbox',
        help_text=(
            'Sandbox (test) chats: `exclude` (the default: real customer chats only), `include` '
            '(real and sandbox chats) or `only` (sandbox chats only).'
        ),
    )

    phone_number = django_filters.CharFilter(help_text='Exact phone number, e.g. `+6591234567` (URL-encode `+` as `%2B`).')
    search = django_filters.CharFilter(
        method='filter_search',
        help_text='Case-insensitive text in the display name or phone number.',
    )
    display_name = django_filters.CharFilter(lookup_expr='icontains', help_text='Case-insensitive text in the display name.')
    chat_state_id = django_filters.ChoiceFilter(
        choices=[(step, STEP_LABELS[step]) for step in CHAT_STEPS],
        help_text='The chat flow step the customer is at, e.g. `details_collection`.',
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

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        # No `sandbox` parameter: same as `sandbox=exclude`.
        if not self.form.cleaned_data.get('sandbox'):
            queryset = queryset.filter(is_sandbox=False)
        return queryset

    def filter_sandbox(self, queryset, name, value):
        if value == SANDBOX_ONLY:
            return queryset.filter(is_sandbox=True)
        if value == SANDBOX_EXCLUDE:
            return queryset.filter(is_sandbox=False)
        return queryset  # include

    def filter_search(self, queryset, name, value):
        return queryset.filter(Q(display_name__icontains=value) | Q(phone_number__icontains=value))

    def filter_has_messages(self, queryset, name, value):
        empty = Q(chat_message_json=[])
        return queryset.exclude(empty) if value == 'true' else queryset.filter(empty)


class UnansweredQuestionFilter(django_filters.FilterSet):
    """Filters for GET /api/chat/questions/. All parameters are optional and combine (AND).

    Questions from sandbox (test) chats are included by default, so the Chat Sandbox can be used
    to try the whole loop.
    """

    status = django_filters.ChoiceFilter(
        choices=QuestionStatus.choices, help_text='Only questions with this status, e.g. `open` (the alert).'
    )
    sandbox = django_filters.ChoiceFilter(
        choices=[(SANDBOX_INCLUDE, SANDBOX_INCLUDE), (SANDBOX_EXCLUDE, SANDBOX_EXCLUDE), (SANDBOX_ONLY, SANDBOX_ONLY)],
        method='filter_sandbox',
        help_text='Questions from sandbox (test) chats: `include` (the default), `exclude` or `only`.',
    )
    ordering = StableOrderingFilter(
        fields=('created_time', 'answered_time', 'id'),
        help_text='Sort by `created_time`, `answered_time` or `id`; prefix with `-` for descending. Default: `-created_time`.',
    )

    class Meta:
        model = UnansweredQuestion
        fields = ['status']

    def filter_sandbox(self, queryset, name, value):
        if value == SANDBOX_ONLY:
            return queryset.filter(chat_session__is_sandbox=True)
        if value == SANDBOX_EXCLUDE:
            return queryset.filter(chat_session__is_sandbox=False)
        return queryset
