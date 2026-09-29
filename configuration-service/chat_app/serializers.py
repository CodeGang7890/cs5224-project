from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .constants import BLOCK_TYPES, MESSAGE_SENDERS, START_BLOCK
from .llm import CHAT_PROMPT_MAX_LENGTH, OLLAMA_MODEL, OLLAMA_OPTIONS
from .models import PHONE_NUMBER_MAX_LENGTH, ChatConfiguration, ChatSession, phone_number_validator
from .validators import CHAT_MESSAGE_MAX_LENGTH, validate_chat_config


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


class ChatBlockSerializer(serializers.Serializer):
    id = _BlockIdSchemaField(help_text='Integer or non-blank string (e.g. a UUID), unique in the list.')
    next_block_id = _NextBlockIdSchemaField(help_text='`id` of the next block, or null for the last one.')
    block_type = serializers.ChoiceField(
        choices=BLOCK_TYPES, help_text=f'Exactly one block must be a `{START_BLOCK}`.'
    )
    position_x = serializers.FloatField()
    position_y = serializers.FloatField()


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


class SandboxMessageRequestSerializer(serializers.Serializer):
    # trim_whitespace + allow_blank=False rejects empty and whitespace-only messages.
    message = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        help_text=f'Your message, as the pretend customer (max {CHAT_MESSAGE_MAX_LENGTH} characters).',
    )
