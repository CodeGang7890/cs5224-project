from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .constants import (
    CUSTOM_STYLE_MAX_LENGTH,
    DEFAULT_REPLY_STYLE,
    DETAIL_FIELD_TYPES,
    MESSAGE_SENDERS,
    REPLY_STYLE_CUSTOM,
    REPLY_STYLES,
    WELCOME_MESSAGE_MAX_LENGTH,
)
from .llm import CHAT_PROMPT_MAX_LENGTH, OLLAMA_MODEL, OLLAMA_OPTIONS
from product_app.models import FAQ_QUESTION_MAX_LENGTH

from .models import PHONE_NUMBER_MAX_LENGTH, ChatConfiguration, ChatSession, UnansweredQuestion, phone_number_validator
from .questions import ANSWER_MAX_LENGTH
from .validators import (
    CHAT_MESSAGE_MAX_LENGTH,
    DETAIL_DESCRIPTION_MAX_LENGTH,
    DETAIL_FIELDS_MAX,
    DETAIL_KEY_MAX_LENGTH,
    DETAIL_LABEL_MAX_LENGTH,
    DETAIL_TEXT_DEFAULT_MAX_LENGTH,
    DETAIL_TEXT_MAX_LENGTH,
    validate_detail_fields,
)


class ChatRequestSerializer(serializers.Serializer):
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only prompts.
    prompt = serializers.CharField(
        max_length=CHAT_PROMPT_MAX_LENGTH,
        help_text=f'Your message to the assistant (max {CHAT_PROMPT_MAX_LENGTH} characters).',
    )


class ChatResponseSerializer(serializers.Serializer):
    reply = serializers.CharField(help_text="The model's answer.")
    model = serializers.CharField(help_text=f'The Ollama model used, e.g. `{OLLAMA_MODEL}`.')
    options = serializers.DictField(
        help_text=f'Sampling hyperparameters sent to Ollama (hardcoded): `{OLLAMA_OPTIONS}`.',
    )


# --- Chat configuration -------------------------------------------------------------------
# detail_fields is stored and validated as plain JSON (validate_detail_fields). The serializer
# below only describes its shape in the Swagger docs.

class ChatDetailFieldSerializer(serializers.Serializer):
    """One customer detail the Details collection step asks for."""

    key = serializers.RegexField(
        r'^[a-z][a-z0-9_]*$',
        max_length=DETAIL_KEY_MAX_LENGTH,
        help_text='Unique, e.g. `postal_code`: the key in `chat_state_data.details`.',
    )
    label = serializers.CharField(max_length=DETAIL_LABEL_MAX_LENGTH, help_text='What the customer is asked for.')
    type = serializers.ChoiceField(choices=DETAIL_FIELD_TYPES)
    description = serializers.CharField(
        required=False, max_length=DETAIL_DESCRIPTION_MAX_LENGTH, help_text='Optional hint for the assistant.'
    )
    required = serializers.BooleanField(
        required=False,
        default=True,
        help_text='False for an optional detail (asked for, but not needed to move on). At least one must be required.',
    )
    max_length = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=DETAIL_TEXT_MAX_LENGTH,
        help_text=f'`text` only (default {DETAIL_TEXT_DEFAULT_MAX_LENGTH}).',
    )
    min_value = serializers.FloatField(required=False, help_text='`number` only.')
    max_value = serializers.FloatField(required=False, help_text='`number` only; at least `min_value`.')


@extend_schema_field(ChatDetailFieldSerializer(many=True))
class DetailFieldsJSONField(serializers.JSONField):
    pass


class ChatConfigurationSerializer(serializers.ModelSerializer):
    # Null while the business hasn't saved its configuration (GET returns the defaults).
    id = serializers.IntegerField(read_only=True, allow_null=True)
    last_updated = serializers.DateTimeField(read_only=True, allow_null=True)
    detail_fields = DetailFieldsJSONField(
        validators=[validate_detail_fields],
        help_text=(
            f'The customer details the Details collection step asks for (1 to {DETAIL_FIELDS_MAX}). '
            'See the detail field schema for the rules.'
        ),
    )

    class Meta:
        model = ChatConfiguration
        fields = ['id', 'business', 'detail_fields', 'welcome_message', 'reply_style', 'custom_style', 'last_updated']
        read_only_fields = ['id', 'business', 'last_updated']
        extra_kwargs = {
            'welcome_message': {
                'help_text': (
                    f"Sent word for word as the reply to a chat's first message (at most {WELCOME_MESSAGE_MAX_LENGTH} "
                    'characters; blank: no welcome message). The only placeholder is {business_name}. Optional on PUT '
                    '(kept as saved).'
                ),
            },
            'reply_style': {
                'help_text': (
                    f'How the assistant writes: one of {", ".join(REPLY_STYLES)} (see GET /api/chat/configuration/reply-styles/). '
                    'Optional on PUT (kept as saved).'
                ),
            },
            'custom_style': {
                'help_text': (
                    f'With reply_style "custom" (then required): how the assistant should write, in your own words, at '
                    f'most {CUSTOM_STYLE_MAX_LENGTH} characters. Optional on PUT (kept as saved).'
                ),
            },
        }

    def validate(self, attrs):
        style = attrs.get('reply_style', getattr(self.instance, 'reply_style', DEFAULT_REPLY_STYLE))
        custom = attrs.get('custom_style', getattr(self.instance, 'custom_style', ''))
        if style == REPLY_STYLE_CUSTOM and not custom.strip():
            raise serializers.ValidationError(
                {'custom_style': ['Describe the style you want (or choose one of the presets).']}
            )
        return attrs


class ReplyStyleSerializer(serializers.Serializer):
    """One of the reply styles a business can choose (constants.REPLY_STYLE_PRESETS, plus custom)."""

    key = serializers.CharField(help_text='The value for ChatConfiguration.reply_style.')
    label = serializers.CharField()
    description = serializers.CharField(help_text='What the style is like, for the business.')
    instructions = serializers.CharField(
        allow_null=True, help_text='What the assistant is told (null for custom: your custom_style is used).'
    )


# --- Chat sessions ------------------------------------------------------------------------

class ChatMessageSerializer(serializers.Serializer):
    """One item of ChatSession.chat_message_json (see validate_chat_messages)."""

    message = serializers.CharField()
    sent_by = serializers.ChoiceField(choices=MESSAGE_SENDERS)
    message_time = serializers.DateTimeField(help_text='ISO 8601 with a timezone. Oldest message first.')


@extend_schema_field(ChatMessageSerializer(many=True))
class ChatMessagesJSONField(serializers.JSONField):
    pass


class ChatStateItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField(help_text='Product name when it was chosen.')
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text='Price when it was chosen.')
    quantity = serializers.IntegerField(min_value=1)


class ChatStateDataSerializer(serializers.Serializer):
    """ChatSession.chat_state_data (see validate_chat_state_data). Every key is optional."""

    items = ChatStateItemSerializer(many=True, required=False, help_text='The products the customer chose.')
    details = serializers.DictField(
        required=False,
        help_text="The customer's details collected so far, by field key (strings or numbers).",
    )
    items_confirmed = serializers.BooleanField(
        required=False, help_text='True once the customer said the items are everything they want.'
    )
    last_order_id = serializers.IntegerField(
        required=False, help_text='The last order placed in this chat (the chat then went back to the start).'
    )
    service = serializers.DictField(
        required=False,
        help_text='The service chosen for a booking: `{service_id, name, price, duration_minutes, buffer_minutes}`.',
    )
    slot = serializers.DateTimeField(required=False, help_text='The start time chosen for the booking.')
    slot_options = serializers.ListField(
        child=serializers.DateTimeField(), required=False,
        help_text='The free start times offered to the customer, numbered from 1 in this order.',
    )
    last_booking_id = serializers.IntegerField(
        required=False, help_text='The last booking (ScheduleItem) made in this chat.'
    )


@extend_schema_field(ChatStateDataSerializer)
class ChatStateDataJSONField(serializers.JSONField):
    pass


class ChatSessionSerializer(serializers.ModelSerializer):
    """A real customer's session. Create: only `phone_number` and `display_name` are writable;
    the rest is set by the backend."""

    # Required here, although the model allows it to be blank (for sandbox sessions only).
    phone_number = serializers.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        validators=[phone_number_validator],
        help_text="The customer's phone number, in international format (e.g. +6591234567).",
    )
    chat_message_json = ChatMessagesJSONField(read_only=True)
    chat_state_data = ChatStateDataJSONField(
        read_only=True, help_text='What the chat flow has collected so far.'
    )

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'business',
            'phone_number',
            'display_name',
            'created_time',
            'last_chat_time',
            'chat_message_json',
            'chat_state_id',
            'chat_state_data',
            'is_sandbox',
        ]
        read_only_fields = ['id', 'business', 'created_time', 'last_chat_time', 'chat_state_id', 'is_sandbox']

    def validate_phone_number(self, value: str) -> str:
        # `business` isn't a writable field, so DRF can't build the (business, phone_number)
        # unique validator itself; the view passes the business in the context.
        business = self.context['business']
        sessions = ChatSession.objects.filter(business=business, phone_number=value, is_sandbox=False)
        if self.instance is not None:
            sessions = sessions.exclude(pk=self.instance.pk)
        if sessions.exists():
            raise serializers.ValidationError('Your business already has a chat session with this phone number.')
        return value


class SandboxChatSessionSerializer(ChatSessionSerializer):
    """A sandbox (test) session. Both writable fields are optional, and phone numbers needn't be unique."""

    phone_number = serializers.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        required=False,
        allow_blank=True,
        validators=[phone_number_validator],
        help_text='Optional mock phone number, in international format (e.g. +10000000000).',
    )

    def validate_phone_number(self, value: str) -> str:
        return value  # sandbox sessions may share a number


class CustomerMessageRequestSerializer(serializers.Serializer):
    business_id = serializers.IntegerField(min_value=1, help_text='ID of the business the customer is messaging.')
    phone_number = serializers.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        validators=[phone_number_validator],
        help_text="The customer's phone number, in international format (e.g. +6591234567).",
    )
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only messages.
    message = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        help_text=f"The customer's message (max {CHAT_MESSAGE_MAX_LENGTH} characters).",
    )


class CustomerMessageResponseSerializer(ChatMessageSerializer):
    """The assistant's reply (its last message this turn), and every message it sent."""

    messages = ChatMessageSerializer(
        many=True,
        help_text=(
            "Every message the assistant sent this turn, oldest first: on a chat's first message, the welcome "
            'message (if the business has one), then the reply (unless the welcome was the whole reply).'
        ),
    )


class SandboxMessageResponseSerializer(CustomerMessageResponseSerializer):
    """The assistant's reply in a sandbox chat, plus what happened inside the turn (flow.py)."""

    debug = serializers.JSONField(
        help_text=(
            'For debugging, not stored: `before` / `after` (`chat_state_id`, `chat_state_data`), '
            '`route` (the router\'s `intents`, `extracted` and `system_prompt`), `steps` (per order step: '
            '`step`, `system_prompt`, `extracted` (the LLM\'s JSON), `complete`, `go_back`, `go_back_to`, '
            '`missing`, `issues`, `chat_state_data`), `stop_reason`, `finished`, `confirmation` (Confirmation\'s or Booking confirmation\'s substage: '
            '`not_confirmed` / `confirmed` / null), `order_id` / `booking_id` (placed in this turn, or null), '
            '`missing`, `issues`, `question_check` (`kind`, `question`, `saved`, `system_prompt`; null unless the router '
            'found a question), `order_status` (`extracted`, `system_prompt`, `records`, `found`; null unless the router found an '
            'order status request), `welcome_message` (sent first this turn, or null), `reply_kind` (`llm`, `order_status` (the order status prompt), `order_status_fallback` / '
            '`order_status_not_found` (written by code), `welcome` (only the welcome message), or a fixed template: `confirmation_request`, '
            '`order_confirmed`, `slot_options`, `booking_confirmation_request`, `booking_confirmed`), `reply_system_prompt` (the aside prompt for templates; may be empty) and '
            '`tool_calls` (`name`, `arguments`).'
        ),
    )


class SandboxMessageRequestSerializer(serializers.Serializer):
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only messages.
    message = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        help_text=f'Your message, as the pretend customer (max {CHAT_MESSAGE_MAX_LENGTH} characters).',
    )


# --- Unanswered questions --------------------------------------------------------------------

class UnansweredQuestionSerializer(serializers.ModelSerializer):
    """A question the chat assistant couldn't answer, with who asked it (read only)."""

    display_name = serializers.CharField(source='chat_session.display_name', read_only=True)
    phone_number = serializers.CharField(source='chat_session.phone_number', read_only=True)
    is_sandbox = serializers.BooleanField(
        source='chat_session.is_sandbox', read_only=True, help_text='Asked in a sandbox (test) chat.'
    )
    answer = serializers.SerializerMethodField(help_text="The answer: the linked FAQ's (current) answer, if any.")

    class Meta:
        model = UnansweredQuestion
        fields = [
            'id', 'business', 'chat_session', 'display_name', 'phone_number', 'is_sandbox',
            'question', 'status', 'faq', 'answer', 'created_time', 'answered_time',
        ]
        read_only_fields = fields

    def get_answer(self, obj) -> str | None:
        return obj.faq.answer if obj.faq else None


class AnswerQuestionSerializer(serializers.Serializer):
    answer = serializers.CharField(
        max_length=ANSWER_MAX_LENGTH,
        help_text=(
            f'Your answer (max {ANSWER_MAX_LENGTH} characters). It is saved as an FAQ and sent to the customer '
            'in the chat as: Regarding your previous question about "<question>": <answer>'
        ),
    )
    question = serializers.CharField(
        max_length=FAQ_QUESTION_MAX_LENGTH,
        required=False,
        help_text="Optional: reworded question for the FAQ (and the chat message). Default: the customer's question.",
    )

