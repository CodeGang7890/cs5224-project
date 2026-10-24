import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.validators import MaxLengthValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .crypto import EncryptedTextField

BUSINESS_NAME_MAX_LENGTH = 150
LOCATION_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 2000

# WhatsApp configuration limits
WHATSAPP_ID_MAX_LENGTH = 32  # Meta's phone number IDs are numeric strings, ~15-17 digits today
WHATSAPP_ACCESS_TOKEN_MAX_LENGTH = 1000
WHATSAPP_APP_SECRET_MAX_LENGTH = 128
WHATSAPP_VERIFY_TOKEN_MAX_LENGTH = 64
WHATSAPP_DISPLAY_PHONE_NUMBER_MAX_LENGTH = 32  # as Meta formats it, e.g. "+65 9123 4567"
WHATSAPP_VERIFIED_NAME_MAX_LENGTH = 255
# How long before its access token expires the owner is warned to reconnect. notification-job's first
# alert (RECONNECT_ALERTS_BEFORE) uses the same 7 days: change both together.
ACCESS_TOKEN_EXPIRY_WARNING = timedelta(days=7)
PHONE_NUMBER_TAKEN_MESSAGE = 'This phone number ID is already connected to another business.'

class BusinessConfiguration(models.Model):
    """A business (tenant) using Ansera Business Admin. Other apps' data hangs off this."""

    business_name = models.CharField(max_length=BUSINESS_NAME_MAX_LENGTH)
    # Django doesn't enforce max_length on TextField at the model level, hence the explicit validator.
    description = models.TextField(
        max_length=DESCRIPTION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(DESCRIPTION_MAX_LENGTH)],
    )
    location = models.CharField(max_length=LOCATION_MAX_LENGTH)

    class Meta:
        verbose_name = 'Business Configuration'
        verbose_name_plural = 'Business Configurations'
        ordering = ['business_name']
        constraints = [
            models.CheckConstraint(
                condition=~Q(business_name=''),
                name='business_configuration_name_not_empty',
            ),
            models.CheckConstraint(
                condition=~Q(location=''),
                name='business_configuration_location_not_empty',
            ),
        ]

    def __str__(self) -> str:
        return self.business_name

meta_id_validator = RegexValidator(r'^\d+$', 'Must contain digits only.')
no_whitespace_validator = RegexValidator(r'^\S*$', 'Must not contain spaces.')

def new_verify_token() -> str:
    """A random token for Meta's webhook verification handshake (43 URL-safe characters)."""
    return secrets.token_urlsafe(32)


class WhatsAppConnectionMethod(models.TextChoices):
    MANUAL = 'manual'  # older connections made with the owner's own Meta app (e.g. the sample data)
    EMBEDDED_SIGNUP = 'embedded_signup'  # through our Meta app (embedded_signup.py)


class WhatsAppConnectionStatus(models.TextChoices):
    """What Meta last reported about the connection (account_update webhooks, account_updates.py)."""

    CONNECTED = 'connected', 'Connected'
    DISCONNECTED = 'disconnected', 'Disconnected'  # access removed, or the account / number is gone
    BANNED = 'banned', 'Banned'  # Meta disabled the WhatsApp Business account


# What to tell the owner when Meta reports the connection isn't working (status_reason).
STATUS_REASONS = {
    WhatsAppConnectionStatus.DISCONNECTED.value: (
        'Meta reported that your WhatsApp Business account was disconnected from us (for example, our app was '
        'removed in Meta, or the account or number was deleted or moved).'
    ),
    WhatsAppConnectionStatus.BANNED.value: (
        'Meta disabled your WhatsApp Business account for breaking its policies or terms. '
        'You can request a review in WhatsApp Manager.'
    ),
}


class ConnectionHealth(models.TextChoices):
    """One answer to "does the owner need to do something?", combining what Meta reported (`status`)
    with the access token's expiry. What Meta reported comes first: a disconnected or banned connection
    needs that fixed, whatever its token."""

    OK = 'ok', 'OK'
    EXPIRING_SOON = 'expiring_soon', 'Expiring soon'  # the token lapses within ACCESS_TOKEN_EXPIRY_WARNING
    EXPIRED = 'expired', 'Expired'  # Meta refuses the token: replies fail until the owner reconnects
    DISCONNECTED = 'disconnected', 'Disconnected'
    BANNED = 'banned', 'Banned'


class WhatsAppConfiguration(models.Model):
    """A business's WhatsApp Business (Cloud API) connection, made with Embedded Signup (embedded_signup.py)
    through our Meta app. Older `manual` rows (e.g. the sample fixtures) were made with a business's own
    Meta app and keep that app's App Secret; there's no API to create them any more.

    The messaging-ingester asks this service (internal API) to verify Meta's webhook calls: `verify_token`
    for the subscription handshake and `effective_app_secret` for each payload's X-Hub-Signature-256.
    `access_token` is for sending replies. The secrets are encrypted at rest (crypto.py) and are never
    returned by the owner-facing API. `display_phone_number` / `verified_name` come from Meta.
    """

    business = models.OneToOneField(
        BusinessConfiguration,
        on_delete=models.CASCADE,
        related_name='whatsapp_configuration',
    )
    phone_number_id = models.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH,
        unique=True,
        validators=[meta_id_validator],
        error_messages={'unique': PHONE_NUMBER_TAKEN_MESSAGE},
        help_text='"Phone number ID" from Meta/Whatsapp API. Identifies the phone number in webhooks.',
    )
    access_token = EncryptedTextField(
        validators=[MaxLengthValidator(WHATSAPP_ACCESS_TOKEN_MAX_LENGTH), no_whitespace_validator],
        help_text='User\'s Meta/Whatsapp API access token, used to send messages on behalf of user. Stored encrypted.',
    )
    # Only for manual connections (the business's own Meta app). Embedded Signup connections use our app's
    # secret, settings.META_APP_SECRET, so it isn't copied into every row: see effective_app_secret.
    app_secret = EncryptedTextField(
        blank=True,
        validators=[MaxLengthValidator(WHATSAPP_APP_SECRET_MAX_LENGTH), no_whitespace_validator],
        help_text="Manual connections only: their own Meta app's App Secret (signatures). Stored encrypted.",
    )
    # From Meta when the number is connected (meta_api.phone_number_info), read only.
    display_phone_number = models.CharField(
        max_length=WHATSAPP_DISPLAY_PHONE_NUMBER_MAX_LENGTH,
        blank=True,
        editable=False,
        help_text='The number as Meta shows it, e.g. "+65 9123 4567". Set from Meta.',
    )
    verified_name = models.CharField(
        max_length=WHATSAPP_VERIFIED_NAME_MAX_LENGTH,
        blank=True,
        editable=False,
        help_text="The business name Meta verified for the number. Set from Meta.",
    )
    verify_token = models.CharField(
        max_length=WHATSAPP_VERIFY_TOKEN_MAX_LENGTH,
        default=new_verify_token,
        editable=False,
        help_text="Generated by our system. Meta checks the business's webhook with it (set by Embedded Signup).",
    )
    # Embedded Signup: the business's WhatsApp Business account, which our app is subscribed to (with
    # its webhooks overridden to the business's Callback URL). Blank for connections made earlier with
    # a business's own Meta app (e.g. the sample data).
    waba_id = models.CharField(
        max_length=WHATSAPP_ID_MAX_LENGTH,
        blank=True,
        validators=[meta_id_validator],
        editable=False,
        help_text='WhatsApp Business account ID, from Embedded Signup. Blank for older connections.',
    )
    # The number's two-step verification PIN, set when Embedded Signup registers it for Cloud API (needed
    # to register it again). Blank if it was already registered with a PIN we don't know.
    two_step_pin = EncryptedTextField(
        blank=True,
        editable=False,
        help_text="The phone number's two-step verification PIN, set by Embedded Signup. Stored encrypted.",
    )
    # When Meta stops accepting access_token (Embedded Signup tokens can expire, e.g. after 60 days,
    # depending on our Facebook Login for Business configuration); reconnecting gives a new one.
    access_token_expires_time = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="When the access token expires, from Meta. Empty: it doesn't expire (or isn't known).",
    )
    connection_method = models.CharField(
        max_length=20,
        choices=WhatsAppConnectionMethod.choices,
        default=WhatsAppConnectionMethod.MANUAL,
        editable=False,
        help_text='How the business connected: its own Meta app (manual) or Embedded Signup through ours.',
    )
    # Set from Meta's account_update webhooks (our app's own webhook, Embedded Signup connections only);
    # connecting again with Embedded Signup sets it back to connected.
    status = models.CharField(
        max_length=20,
        choices=WhatsAppConnectionStatus.choices,
        default=WhatsAppConnectionStatus.CONNECTED,
        editable=False,
        help_text='What Meta last reported: connected, disconnected (e.g. our app was removed) or banned.',
    )
    status_updated_time = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text='When Meta reported it.',
    )
    created_time = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'WhatsApp Configuration'
        verbose_name_plural = 'WhatsApp Configurations'
        ordering = ['business']
        # Every field is needed for the connection to work, so none may be empty, even when saved
        # without validation (e.g. objects.create(), fixtures). NOT NULL alone still allows ''.
        constraints = [
            models.CheckConstraint(
                condition=~Q(phone_number_id='') & ~Q(access_token='') & ~Q(verify_token=''),
                name='whatsapp_configuration_required_fields_not_empty',
            ),
            # Manual connections keep their own app's App Secret; Embedded Signup ones use ours (settings).
            models.CheckConstraint(
                condition=(Q(connection_method=WhatsAppConnectionMethod.MANUAL) & ~Q(app_secret=''))
                | (Q(connection_method=WhatsAppConnectionMethod.EMBEDDED_SIGNUP) & Q(app_secret='')),
                name='whatsapp_configuration_app_secret_only_for_manual',
            ),
            models.CheckConstraint(
                condition=Q(connection_method__in=WhatsAppConnectionMethod.values),
                name='whatsapp_configuration_connection_method_valid',
            ),
            models.CheckConstraint(
                condition=Q(status__in=WhatsAppConnectionStatus.values),
                name='whatsapp_configuration_status_valid',
            ),
            # Embedded Signup always gives the WABA (our app is subscribed to it).
            models.CheckConstraint(
                condition=~Q(connection_method=WhatsAppConnectionMethod.EMBEDDED_SIGNUP) | ~Q(waba_id=''),
                name='whatsapp_configuration_embedded_signup_has_waba',
            ),
        ]

    def __str__(self) -> str:
        return f'WhatsApp {self.phone_number_id} ({self.business})'

    @property
    def status_reason(self) -> str:
        """Why it isn't connected, for the owner (empty while connected)."""
        if self.status == WhatsAppConnectionStatus.CONNECTED:
            return ''
        return STATUS_REASONS[self.status]

    @property
    def effective_app_secret(self) -> str:
        """The App Secret that signs this connection's webhooks and its appsecret_proof: our app's for
        Embedded Signup (so rotating META_APP_SECRET needs no data change), the stored one for manual."""
        if self.connection_method == WhatsAppConnectionMethod.EMBEDDED_SIGNUP:
            return settings.META_APP_SECRET
        return self.app_secret

    def health(self, now: datetime | None = None) -> str:
        """A ConnectionHealth: what (if anything) the owner must do. What Meta reported first, then the
        token's expiry (null: it doesn't expire, e.g. manual connections)."""
        if self.status == WhatsAppConnectionStatus.DISCONNECTED:
            return ConnectionHealth.DISCONNECTED
        if self.status == WhatsAppConnectionStatus.BANNED:
            return ConnectionHealth.BANNED
        expires = self.access_token_expires_time
        if expires is None:
            return ConnectionHealth.OK
        now = now or timezone.now()
        if expires <= now:
            return ConnectionHealth.EXPIRED
        if expires - now <= ACCESS_TOKEN_EXPIRY_WARNING:
            return ConnectionHealth.EXPIRING_SOON
        return ConnectionHealth.OK
