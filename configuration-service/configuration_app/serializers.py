from rest_framework import serializers
from rest_framework.exceptions import APIException

from .models import (
    WHATSAPP_ID_MAX_LENGTH,
    WHATSAPP_STATUS_EVENT_MAX_LENGTH,
    WHATSAPP_VERIFY_TOKEN_MAX_LENGTH,
    WhatsAppConfiguration,
    meta_id_validator,
)


class MetaUnavailable(APIException):
    status_code = 503
    default_detail = "Couldn't reach Meta. Nothing was saved; please try again."
    default_code = 'meta_unavailable'


class RandomNumberSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=1, max_value=10)


class WhatsAppConfigurationSerializer(serializers.ModelSerializer):
    """The owner's view of their WhatsApp connection, read only: businesses connect with Embedded
    Signup (EmbeddedSignupSerializer). The secrets (token, App Secret, two-step PIN) and the webhook
    details (set up automatically) are never returned. `status` is what Meta last reported (account_update
    webhooks): `disconnected` or `banned` with a `status_reason` for the owner; reconnecting resets it."""

    status_reason = serializers.CharField(
        read_only=True, help_text="Why it isn't connected, for the owner; empty while `status` is `connected`."
    )

    class Meta:
        model = WhatsAppConfiguration
        fields = (
            'phone_number_id',
            'display_phone_number',
            'verified_name',
            'waba_id',
            'connection_method',
            'status',
            'status_reason',
            'status_updated_time',
            'created_time',
            'last_updated',
        )
        read_only_fields = fields


class EmbeddedSignupSerializer(serializers.Serializer):
    """What Meta's Embedded Signup popup gives the frontend (FB.login's code and the FINISH event's IDs)."""

    code = serializers.CharField(
        max_length=2000,
        help_text="The code from FB.login's authResponse. Single use, valid for 30 seconds: send it at once.",
    )
    waba_id = serializers.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH,
        validators=[meta_id_validator],
        help_text='`data.waba_id` of the WA_EMBEDDED_SIGNUP FINISH message event.',
    )
    phone_number_id = serializers.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH,
        validators=[meta_id_validator],
        help_text='`data.phone_number_id` of the WA_EMBEDDED_SIGNUP FINISH message event.',
    )


class VerifyTokenRequestSerializer(serializers.Serializer):
    verify_token = serializers.CharField(
        allow_blank=True,
        trim_whitespace=False,
        max_length=WHATSAPP_VERIFY_TOKEN_MAX_LENGTH,  # anything longer can't match anyway
        help_text='The hub.verify_token Meta sent with its subscription handshake.',
    )


class VerificationResultSerializer(serializers.Serializer):
    valid = serializers.BooleanField(help_text='Whether the token or signature matches.')
    phone_number_id = serializers.CharField(
        allow_null=True,
        help_text=(
            "The business's Phone Number ID when `valid` (to check against the payload's "
            '`metadata.phone_number_id`), otherwise null.'
        ),
    )


class AccountUpdateSerializer(serializers.Serializer):
    """One account_update change from our app's webhook, as messaging-ingester extracts it."""

    waba_id = serializers.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH,
        validators=[meta_id_validator],
        help_text='The WhatsApp Business account: `value.waba_info.waba_id`, else the entry `id`.',
    )
    event = serializers.CharField(max_length=WHATSAPP_STATUS_EVENT_MAX_LENGTH, help_text='`value.event`.')
    ban_state = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default='',
        help_text='`value.ban_info.waba_ban_state` (DISABLED_UPDATE): DISABLE, REINSTATE or SCHEDULE_FOR_DISABLE.',
    )
    partner_app_id = serializers.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH, required=False, allow_blank=True, default='',
        help_text='`value.waba_info.partner_app_id` (PARTNER_APP_INSTALLED / UNINSTALLED).',
    )


class AccountUpdatesRequestSerializer(serializers.Serializer):
    updates = AccountUpdateSerializer(many=True, max_length=100)


class AccountUpdatesResultSerializer(serializers.Serializer):
    changed = serializers.IntegerField(help_text='How many connections changed status.')


WHATSAPP_TEXT_MAX_LENGTH = 4096  # WhatsApp's limit for a text message


class SendMessageRequestSerializer(serializers.Serializer):
    to = serializers.RegexField(
        r'^\+[1-9]\d{6,14}$', max_length=16,
        help_text="The customer's phone number, in international format (e.g. +6591234567).",
        error_messages={'invalid': 'Enter the phone number in international format, e.g. +6591234567.'},
    )
    text = serializers.CharField(max_length=WHATSAPP_TEXT_MAX_LENGTH, help_text='The message to send.')


class SendMessageResponseSerializer(serializers.Serializer):
    message_id = serializers.CharField(help_text="Meta's id of the message sent (wamid…).")
