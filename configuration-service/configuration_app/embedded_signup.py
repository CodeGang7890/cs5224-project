"""WhatsApp Embedded Signup: a business connects WhatsApp through Meta's popup and OUR Meta app.

The frontend runs the popup (Facebook JS SDK, FB.login with our configuration ID) and sends what it
returns: a single-use code (valid for 30 seconds), the business's WhatsApp Business account (WABA) ID and
its phone number ID. connect() then, in this order:

1. swaps the code for the business's token (a business integration system user token for our app)
   and when it expires (reconnecting gives a new one: the owner is warned before it lapses);
2. checks the number with that token (meta_api.check_credentials), which also gives the number and name;
3. registers the number for Cloud API, with a random two-step verification PIN (kept encrypted, as it
   is needed to register the number again);
4. saves the connection: the token, our App Secret (it signs the webhooks), the WABA ID, the PIN;
5. subscribes our app to the WABA, overriding its message webhooks to the business's own Callback URL
   (MESSAGING_INGESTER_PUBLIC_URL/webhook/<business_id>) with its verify token. So messaging-ingester
   and the internal checks work exactly as for a manual connection. Meta checks the URL at once (the
   handshake asks this service for the verify token), which is why step 4 is saved first; if this
   step fails, step 4 is undone.

Meta only allows the popup on HTTPS pages of the domains set on our app, so it can't run locally:
there, the sample fixtures' (manual) connections are used with mock_whatsapp.
"""

import logging
import secrets

from django.conf import settings
from django.db import IntegrityError

from . import meta_api
from .models import BusinessConfiguration, WhatsAppConfiguration, WhatsAppConnectionMethod, WhatsAppConnectionStatus

logger = logging.getLogger(__name__)

# What connect() changes on an existing connection (restored if setting up the webhook fails).
SAVED_FIELDS = (
    'phone_number_id',
    'access_token',
    'access_token_expires_time',
    'app_secret',
    'waba_id',
    'connection_method',
    'two_step_pin',
    'status',
    'status_event',
    'status_updated_time',
    'display_phone_number',
    'verified_name',
)


class EmbeddedSignupNotConfigured(Exception):
    """META_APP_ID / META_APP_SECRET aren't set."""


class PhoneNumberTaken(Exception):
    """Another business has already connected this number."""


def webhook_url(business_id: int) -> str:
    """The business's own Callback URL on messaging-ingester, which its WABA's webhooks are overridden to."""
    return f'{settings.MESSAGING_INGESTER_PUBLIC_URL}/webhook/{business_id}'


def is_configured() -> bool:
    return bool(settings.META_APP_ID and settings.META_APP_SECRET)


def new_pin() -> str:
    """A random 6-digit two-step verification PIN for registering the number."""
    return f'{secrets.randbelow(10**6):06d}'


def connect(
    business: BusinessConfiguration, code: str, waba_id: str, phone_number_id: str
) -> tuple[WhatsAppConfiguration, bool]:
    """Connects the business's WhatsApp from the popup's results (see the module docstring). Returns
    the saved connection and whether it is new. Raises EmbeddedSignupNotConfigured, PhoneNumberTaken,
    meta_api.MetaSignupError (Meta refused a step: the message is for the owner) or
    meta_api.MetaUnavailableError (Meta couldn't be reached)."""
    if not is_configured():
        raise EmbeddedSignupNotConfigured
    app_secret = settings.META_APP_SECRET

    business_token = meta_api.exchange_code(code)
    token = business_token.access_token
    try:
        info = meta_api.check_credentials(phone_number_id, token, app_secret)
    except meta_api.MetaCredentialsError as exc:
        raise meta_api.MetaSignupError(f"Meta didn't give us access to this phone number: {exc.message}") from exc
    if WhatsAppConfiguration.objects.filter(phone_number_id=phone_number_id).exclude(business=business).exists():
        raise PhoneNumberTaken
    pin = new_pin()
    pin_set = meta_api.register_phone_number(phone_number_id, token, app_secret, pin)

    config = WhatsAppConfiguration.objects.filter(business=business).first()
    created = config is None
    previous = None if created else {field: getattr(config, field) for field in SAVED_FIELDS}
    if created:
        config = WhatsAppConfiguration(business=business)
    config.phone_number_id = phone_number_id
    config.access_token = token
    config.access_token_expires_time = business_token.expires_time
    config.app_secret = app_secret
    config.waba_id = waba_id
    config.connection_method = WhatsAppConnectionMethod.EMBEDDED_SIGNUP
    # Connected again (e.g. after Meta reported it disconnected): clear what Meta reported.
    config.status, config.status_event, config.status_updated_time = WhatsAppConnectionStatus.CONNECTED, '', None
    if pin_set:
        config.two_step_pin = pin
    elif previous is None or previous['phone_number_id'] != phone_number_id:
        config.two_step_pin = ''  # already registered with a PIN we don't know
    config.display_phone_number = info.display_phone_number
    config.verified_name = info.verified_name
    try:
        # Committed now (no surrounding transaction): Meta's webhook check below reads the verify token.
        config.save()
    except IntegrityError as exc:  # another business connected the number meanwhile
        raise PhoneNumberTaken from exc

    try:
        meta_api.subscribe_app(waba_id, token, app_secret)
        meta_api.subscribe_app(
            waba_id,
            token,
            app_secret,
            override_callback_uri=webhook_url(business.pk),
            verify_token=config.verify_token,
        )
    except Exception:
        if created:
            config.delete()
        else:
            for field, value in previous.items():
                setattr(config, field, value)
            config.save()
        raise

    if previous and previous['waba_id'] and previous['waba_id'] != waba_id:
        # Reconnected with another WhatsApp Business account: stop the old one's webhooks.
        unsubscribe(previous['waba_id'], previous['access_token'], previous['app_secret'])
    logger.info('Business %s connected WhatsApp %s through Embedded Signup', business.pk, phone_number_id)
    return config, created


def unsubscribe(waba_id: str, access_token: str, app_secret: str) -> None:
    """Best effort: stops our app's webhooks for a WABA we no longer use. Failures are only logged."""
    try:
        meta_api.unsubscribe_app(waba_id, access_token, app_secret)
    except (meta_api.MetaSignupError, meta_api.MetaUnavailableError) as exc:
        logger.warning('Could not unsubscribe from WABA %s: %s', waba_id, exc)
