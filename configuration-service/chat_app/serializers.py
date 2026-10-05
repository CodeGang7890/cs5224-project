from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .constants import (
    BLOCK_TYPES,
    DETAIL_FIELD_TYPES,
    DETAILS_COLLECTION_BLOCK,
    MESSAGE_SENDERS,
    SEND_MESSAGE_BLOCK,
    START_BLOCK,
)
from .llm import CHAT_PROMPT_MAX_LENGTH, OLLAMA_MODEL, OLLAMA_OPTIONS
from .models import PHONE_NUMBER_MAX_LENGTH, ChatConfiguration, ChatSession, phone_number_validator
from .validators import (
    CHAT_MESSAGE_MAX_LENGTH,
    DETAIL_DESCRIPTION_MAX_LENGTH,
    DETAIL_FIELDS_MAX,
    DETAIL_KEY_MAX_LENGTH,
    DETAIL_LABEL_MAX_LENGTH,
    DETAIL_TEXT_DEFAULT_MAX_LENGTH,
    DETAIL_TEXT_MAX_LENGTH,
    validate_chat_config,
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
# config_json is stored and validated as plain JSON (validate_chat_config). The serializers
# below only describe its shape in the Swagger docs.

BLOCK_ID_SCHEMA = {'oneOf': [{'type': 'integer'}, {'type': 'string'}]}


@extend_schema_field(BLOCK_ID_SCHEMA)
class _BlockIdSchemaField(serializers.JSONField):
    pass


@extend_schema_field({**BLOCK_ID_SCHEMA, 'nullable': True})
class _NextBlockIdSchemaField(serializers.JSONField):
    pass


class ChatDetailFieldSerializer(serializers.Serializer):
    """One customer detail a DETAILS_COLLECTION_BLOCK asks for."""

    key = serializers.RegexField(
        r'^[a-z][a-z0-9_]*$',
        max_length=DETAIL_KEY_MAX_LENGTH,
        help_text='Unique in the block, e.g. `postal_code`: the key in `chat_state_data.details`.',
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


class ChatBlockSerializer(serializers.Serializer):
    id = _BlockIdSchemaField(help_text='Integer or non-blank string (e.g. a UUID), unique in the list.')
    next_block_id = _NextBlockIdSchemaField(help_text='`id` of the next block, or null for the last one.')
    block_type = serializers.ChoiceField(
        choices=BLOCK_TYPES, help_text=f'Exactly one block must be a `{START_BLOCK}`.'
    )
    position_x = serializers.FloatField()
    position_y = serializers.FloatField()
    fields = ChatDetailFieldSerializer(
        many=True,
        required=False,
        help_text=(
            f'`{DETAILS_COLLECTION_BLOCK}` only: the customer details it asks for (1 to '
            f'{DETAIL_FIELDS_MAX}). Without it, the block asks for name and email.'
        ),
    )
    message = serializers.CharField(
        required=False,
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        help_text=f'`{SEND_MESSAGE_BLOCK}` only, and required there: the message it sends the customer.',
    )


@extend_schema_field(ChatBlockSerializer(many=True))
class ChatConfigJSONField(serializers.JSONField):
    pass


class ChatConfigurationSerializer(serializers.ModelSerializer):
    config_json = ChatConfigJSONField(
        validators=[validate_chat_config],
        help_text='The chat flow: a list of blocks. See the block schema for the rules.',
    )

    class Meta:
        model = ChatConfiguration
        fields = ['id', 'business', 'config_json', 'last_updated']
        read_only_fields = ['id', 'business', 'last_updated']


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
    completed = serializers.BooleanField(
        required=False, help_text='True once the customer confirmed and the flow reached its last block.'
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
    chat_state_id = _NextBlockIdSchemaField(
        read_only=True, help_text='`id` of the chat flow block the customer is at.'
    )
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
        read_only_fields = ['id', 'business', 'created_time', 'last_chat_time', 'is_sandbox']

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


class SandboxMessageResponseSerializer(ChatMessageSerializer):
    """The assistant's reply in a sandbox chat, plus what happened inside the turn (flow.py)."""

    debug = serializers.JSONField(
        help_text=(
            'For debugging, not stored: `before` / `after` (`chat_state_id`, `chat_state_data`), '
            '`steps` (per block: `block_id`, `block_type`, `system_prompt`, `extracted` (the LLM\'s '
            'JSON), `complete`, `go_back`, `missing`, `issues`, `chat_state_data`), `stop_reason`, '
            '`finished`, `missing`, `issues`, `reply_system_prompt` and `tool_calls` (`name`, `arguments`).'
        ),
    )


class SandboxMessageRequestSerializer(serializers.Serializer):
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only messages.
    message = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        help_text=f'Your message, as the pretend customer (max {CHAT_MESSAGE_MAX_LENGTH} characters).',
    )
