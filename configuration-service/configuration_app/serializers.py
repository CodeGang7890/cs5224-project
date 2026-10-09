from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import APIException

from . import meta_api

from .models import (
    WHATSAPP_ACCESS_TOKEN_MAX_LENGTH,
    WHATSAPP_APP_SECRET_MAX_LENGTH,
    WHATSAPP_VERIFY_TOKEN_MAX_LENGTH,
    WhatsAppConfiguration,
    no_whitespace_validator,
)

SECRET_REQUIRED_MESSAGE = 'This field is required when connecting WhatsApp for the first time.'


class MetaUnavailable(APIException):
    status_code = 503
    default_detail = "Couldn't reach Meta to check these details. Nothing was saved; please try again."
    default_code = 'meta_unavailable'


class RandomNumberSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=1, max_value=10)


def webhook_url(business_id: int) -> str:
    """The Callback URL a business enters in Meta's webhook settings."""
    return f'{settings.MESSAGING_INGESTER_PUBLIC_URL}/webhook/{business_id}'


class WhatsAppConfigurationSerializer(serializers.ModelSerializer):
    """The owner's view of their WhatsApp connection. Secrets are write-only.

    `access_token` and `app_secret` are required when creating. When updating, leaving them out
    or blank keeps the saved value, so the owner doesn't have to re-enter them for every change.
    Every save is checked with Meta first (`_check_with_meta`).
    """

    access_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=WHATSAPP_ACCESS_TOKEN_MAX_LENGTH,
        validators=[no_whitespace_validator],
        help_text='User\'s Meta/Whatsapp API access token, used to send messages on behalf of user. Write-only; blank on update keeps the saved one.',
    )
    app_secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=WHATSAPP_APP_SECRET_MAX_LENGTH,
        validators=[no_whitespace_validator],
        help_text="The Meta app's App Secret. Write-only; blank on update keeps the saved one.",
    )
    webhook_url = serializers.SerializerMethodField(
        help_text="Callback URL to enter in Meta's webhook settings by user.",
    )

    class Meta:
        model = WhatsAppConfiguration
        fields = (
            'phone_number_id',
            'access_token',
            'app_secret',
            'display_phone_number',
            'verified_name',
            'webhook_url',
            'verify_token',
            'created_time',
            'last_updated',
        )
        read_only_fields = ('display_phone_number', 'verified_name', 'verify_token', 'created_time', 'last_updated')

    def get_webhook_url(self, obj: WhatsAppConfiguration) -> str:
        return webhook_url(obj.business_id)

    def validate(self, attrs):
        missing = {}
        for field in ('access_token', 'app_secret'):
            if attrs.get(field):
                continue
            attrs.pop(field, None)  # blank or missing: keep the saved value
            if self.instance is None:
                missing[field] = [SECRET_REQUIRED_MESSAGE]
        if missing:
            raise serializers.ValidationError(missing)
        attrs.update(self._check_with_meta(attrs))
        return attrs

    def _check_with_meta(self, attrs) -> dict:
        """Checks the credentials with Meta (new values, or the saved ones being kept), so wrong or
        expired ones are rejected now rather than failing later on webhooks or replies. Runs only
        after every field passed its own checks. Returns Meta's read-only details to save.
        """
        def value(field):
            return attrs[field] if field in attrs else getattr(self.instance, field)

        try:
            info = meta_api.check_credentials(value('phone_number_id'), value('access_token'), value('app_secret'))
        except meta_api.MetaCredentialsError as exc:
            raise serializers.ValidationError({exc.field: [exc.message]}) from exc
        except meta_api.MetaUnavailableError as exc:
            raise MetaUnavailable() from exc
        return {'display_phone_number': info.display_phone_number, 'verified_name': info.verified_name}


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
