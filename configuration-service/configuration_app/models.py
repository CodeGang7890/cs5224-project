import secrets
from datetime import datetime, timedelta

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
# How long before its access token expires the owner is warned to reconnect (notification-job's
# alerts start then too: keep them in sync).
ACCESS_TOKEN_EXPIRY_WARNING = timedelta(days=7)
WHATSAPP_STATUS_EVENT_MAX_LENGTH = 64  # Meta's account_update event names, e.g. "PARTNER_APP_UNINSTALLED"

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
    MANUAL = 'manual', 'Entered manually'  # the owner's own Meta app: its token, App Secret and webhook
    EMBEDDED_SIGNUP = 'embedded_signup', 'Embedded Signup'  # through our Meta app (embedded_signup.py)


class WhatsAppConnectionStatus(models.TextChoices):
    """What Meta last reported about the connection (account_update webhooks, account_updates.py)."""

    CONNECTED = 'connected', 'Connected'
    DISCONNECTED = 'disconnected', 'Disconnected'  # access removed, or the account / number is gone
    BANNED = 'banned', 'Banned'  # Meta disabled the WhatsApp Business account


# What to tell the owner, by the account_update event that set the status (status_event).
STATUS_REASONS = {
    'PARTNER_APP_UNINSTALLED': "Our app's access to your WhatsApp Business account was removed in Meta.",
    'PARTNER_REMOVED': 'Your WhatsApp Business account is no longer shared with us in Meta.',
    'ACCOUNT_DELETED': 'Your WhatsApp Business account was deleted.',
    'ACCOUNT_OFFBOARDED': (
        'Your number was taken off the WhatsApp Cloud API: it was registered again, or moved to another device.'
    ),
    'DISABLED_UPDATE': (
        'Meta disabled your WhatsApp Business account for breaking its policies or terms. '
        'You can request a review in WhatsApp Manager.'
    ),
}
DEFAULT_STATUS_REASONS = {
    WhatsAppConnectionStatus.DISCONNECTED.value: 'Meta reported that your WhatsApp Business account was disconnected.',
    WhatsAppConnectionStatus.BANNED.value: 'Meta disabled your WhatsApp Business account.',
}


class AccessTokenStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'  # doesn't expire within ACCESS_TOKEN_EXPIRY_WARNING (or never)
    EXPIRING_SOON = 'expiring_soon', 'Expiring soon'  # reconnect before it lapses
    EXPIRED = 'expired', 'Expired'  # Meta refuses it: replies can't be sent until the owner reconnects


class WhatsAppConfiguration(models.Model):
    """A business's WhatsApp Business (Cloud API) connection, entered by the owner from their Meta app.

    Only what's needed to receive and reply to messages (the user asked to keep it minimal): the
    number's Phone Number ID, the app's App Secret and an access token (the WABA ID is only needed
    for templates/account management). They're checked with Meta before saving, which also gives
    the read-only `display_phone_number` and `verified_name` shown to the owner.

    The messaging-ingester reads it (internal API) to verify Meta's webhook calls: `verify_token`
    for the subscription handshake and `app_secret` for each payload's X-Hub-Signature-256.
    `access_token` is for sending replies. Both secrets are encrypted at rest (crypto.py) and are
    never returned by the owner-facing API.
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
        error_messages={'unique': 'This phone number ID is already connected to another business.'},
        help_text='"Phone number ID" from Meta/Whatsapp API. Identifies the phone number in webhooks.',
    )
    access_token = EncryptedTextField(
        validators=[MaxLengthValidator(WHATSAPP_ACCESS_TOKEN_MAX_LENGTH), no_whitespace_validator],
        help_text='User\'s Meta/Whatsapp API access token, used to send messages on behalf of user. Stored encrypted.',
    )
    app_secret = EncryptedTextField(
        validators=[MaxLengthValidator(WHATSAPP_APP_SECRET_MAX_LENGTH), no_whitespace_validator],
        help_text='The Meta app\'s App Secret, used to check webhook signatures. Stored encrypted.',
    )
    # Filled in from Meta when the credentials are checked (meta_api.check_credentials), read only.
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
    status_event = models.CharField(
        max_length=WHATSAPP_STATUS_EVENT_MAX_LENGTH,
        blank=True,
        editable=False,
        help_text="Meta's account_update event that set the status, e.g. PARTNER_APP_UNINSTALLED.",
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
                condition=~Q(phone_number_id='') & ~Q(access_token='') & ~Q(app_secret='') & ~Q(verify_token=''),
                name='whatsapp_configuration_all_fields_not_empty',
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
        return STATUS_REASONS.get(self.status_event) or DEFAULT_STATUS_REASONS[self.status]

    def access_token_status(self, now: datetime | None = None) -> str:
        """An AccessTokenStatus: whether the owner needs to reconnect (soon) to renew the token."""
        expires = self.access_token_expires_time
        if expires is None:
            return AccessTokenStatus.ACTIVE
        now = now or timezone.now()
        if expires <= now:
            return AccessTokenStatus.EXPIRED
        if expires - now <= ACCESS_TOKEN_EXPIRY_WARNING:
            return AccessTokenStatus.EXPIRING_SOON
        return AccessTokenStatus.ACTIVE
