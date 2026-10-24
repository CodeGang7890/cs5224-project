"""Client for Meta's Graph API (WhatsApp Cloud API): checks a business's WhatsApp credentials.

One call checks all three values together:

    GET {META_GRAPH_API_URL}/{phone_number_id}?fields=display_phone_number,verified_name
        &appsecret_proof=<HMAC-SHA256 of the access token, keyed by the App Secret>
    Authorization: Bearer <access token>

- a bad or expired access token → Meta error 190
- a wrong App Secret (it isn't the secret of the app that issued the token) → "Invalid appsecret_proof"
- a wrong Phone Number ID, or one the token can't access → Meta error 100

Outbound calls to Meta live here (not in messaging-ingester), because the secrets never leave this
service. send_text_message() sends a reply (the internal send endpoint, called by messaging-service):

    POST {META_GRAPH_API_URL}/{phone_number_id}/messages?appsecret_proof=…
    {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "6591234567",
     "type": "text", "text": {"preview_url": false, "body": "…"}}
    → {"messaging_product": "whatsapp", "contacts": [...], "messages": [{"id": "wamid.…"}]}

Locally, META_GRAPH_API_URL can point at mock_whatsapp's fake Graph API.

Embedded Signup (embedded_signup.py) uses our app's ID and App Secret (settings.META_APP_*):

    GET  oauth/access_token?client_id=…&client_secret=…&code=…   → the business's token (exchange_code)
    GET  debug_token?input_token=…&access_token=<app id>|<App Secret>   → when it expires (token_expiry)
    POST {phone_number_id}/register {"messaging_product": "whatsapp", "pin": "123456"}   (register_phone_number)
    POST {waba_id}/subscribed_apps [{"override_callback_uri": …, "verify_token": …}]   (subscribe_app)
    DELETE {waba_id}/subscribed_apps   (unsubscribe_app)
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

META_TIMEOUT_SECONDS = 10

INVALID_TOKEN_MESSAGE = 'Meta rejected this access token: it is invalid or has expired.'
TOKEN_PERMISSION_MESSAGE = (
    "This access token doesn't have permission for this phone number. Give the System User the "
    'whatsapp_business_messaging and whatsapp_business_management permissions.'
)
INVALID_APP_SECRET_MESSAGE = "This App Secret doesn't belong to the Meta app that issued the access token."
UNKNOWN_PHONE_NUMBER_ID_MESSAGE = "Meta doesn't know this Phone Number ID, or the access token can't access it."


@dataclass(frozen=True)
class PhoneNumberInfo:
    display_phone_number: str  # e.g. "+65 9123 4567"
    verified_name: str  # the business name Meta verified for the number


@dataclass(frozen=True)
class BusinessToken:
    access_token: str
    # When Meta stops accepting it; None if it never expires (or Meta didn't say). Whether a token
    # expires (e.g. after 60 days) is set by our Facebook Login for Business configuration.
    expires_time: datetime | None


class MetaCredentialsError(Exception):
    """Meta rejected the credentials. `field` is the form field to show `message` under."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class MetaUnavailableError(Exception):
    """Meta couldn't be reached or didn't answer usefully (network, timeout, 5xx, rate limit)."""


class MetaSendError(Exception):
    """Meta refused to send the message (e.g. a bad number, or the 24-hour window has closed)."""


class MetaSignupError(Exception):
    """Meta refused a step of Embedded Signup. The message is for the business owner."""


# Graph API error codes worth retrying: Meta-side problems and rate limits.
RETRYABLE_ERROR_CODES = (1, 2, 4, 17, 32, 613)
# Registering a number that already has a different two-step verification PIN, i.e. it's registered.
PIN_MISMATCH_ERROR_CODE = 133005
EXPIRED_CODE_MESSAGE = 'The Facebook login expired or was already used. Please click Connect with Facebook again.'


def appsecret_proof(access_token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()


def check_credentials(
    phone_number_id: str,
    access_token: str,
    app_secret: str,
    transport: httpx.BaseTransport | None = None,  # tests pass an httpx.MockTransport
) -> PhoneNumberInfo:
    """Asks Meta about the phone number with these credentials; raises if any of them is wrong."""
    url = f'{settings.META_GRAPH_API_URL}/{phone_number_id}'
    params = {
        'fields': 'display_phone_number,verified_name',
        'appsecret_proof': appsecret_proof(access_token, app_secret),
    }
    try:
        with httpx.Client(timeout=META_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.get(url, params=params, headers={'Authorization': f'Bearer {access_token}'})
    except httpx.HTTPError as exc:
        raise MetaUnavailableError(f'Could not reach Meta: {exc}') from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise MetaUnavailableError(f'Meta answered {response.status_code} without JSON.') from exc
    if not isinstance(data, dict):
        raise MetaUnavailableError(f'Unexpected answer from Meta ({response.status_code}).')

    if response.status_code == 200:
        return PhoneNumberInfo(
            display_phone_number=str(data.get('display_phone_number') or ''),
            verified_name=str(data.get('verified_name') or ''),
        )
    raise _error_from(response.status_code, data.get('error'))


def _error_from(status_code: int, error) -> Exception:
    """Maps a Graph API error ({message, type, code, error_subcode}) to the field it's about."""
    error = error if isinstance(error, dict) else {}
    code, message = error.get('code'), str(error.get('message') or '')
    if status_code >= 500 or code in (1, 2, 4, 17, 32, 613):  # Meta-side problem or rate limit
        return MetaUnavailableError(f'Meta answered {status_code}: {message or "no details"}')
    if 'appsecret_proof' in message:
        return MetaCredentialsError('app_secret', INVALID_APP_SECRET_MESSAGE)
    if code == 190:
        return MetaCredentialsError('access_token', INVALID_TOKEN_MESSAGE)
    if code in (10, 200) or (isinstance(code, int) and 200 <= code < 300):
        return MetaCredentialsError('access_token', TOKEN_PERMISSION_MESSAGE)
    if code == 100:
        return MetaCredentialsError('phone_number_id', UNKNOWN_PHONE_NUMBER_ID_MESSAGE)
    return MetaCredentialsError('non_field_errors', f'Meta rejected these credentials: {message or status_code}')


def send_text_message(
    phone_number_id: str,
    access_token: str,
    app_secret: str,
    to: str,
    text: str,
    transport: httpx.BaseTransport | None = None,  # tests pass an httpx.MockTransport
) -> str:
    """Sends `text` to the customer `to` (E.164, e.g. +6591234567) from the business's number.
    Returns Meta's message id (wamid…). Raises MetaSendError if Meta refuses it, MetaUnavailableError
    if Meta can't be reached (worth retrying)."""
    url = f'{settings.META_GRAPH_API_URL}/{phone_number_id}/messages'
    body = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to.removeprefix('+'),  # Meta's wa_id: the number without "+"
        'type': 'text',
        'text': {'preview_url': False, 'body': text},
    }
    try:
        with httpx.Client(timeout=META_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(
                url, json=body, params={'appsecret_proof': appsecret_proof(access_token, app_secret)},
                headers={'Authorization': f'Bearer {access_token}'},
            )
    except httpx.HTTPError as exc:
        raise MetaUnavailableError(f'Could not reach Meta: {exc}') from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise MetaUnavailableError(f'Meta answered {response.status_code} without JSON.') from exc
    if response.status_code == 200 and isinstance(data, dict):
        messages = data.get('messages')
        if isinstance(messages, list) and messages and isinstance(messages[0], dict) and messages[0].get('id'):
            return str(messages[0]['id'])
        raise MetaUnavailableError('Meta answered 200 without a message id.')
    error = data.get('error') if isinstance(data, dict) else None
    error = error if isinstance(error, dict) else {}
    if response.status_code >= 500 or error.get('code') in (1, 2, 4, 17, 32, 613, 130429, 131048, 131056):
        raise MetaUnavailableError(f'Meta answered {response.status_code}: {error.get("message") or "no details"}')
    raise MetaSendError(f'Meta refused the message ({response.status_code}): {error.get("message") or "no details"}')


# --- Embedded Signup ----------------------------------------------------------------------


def _call(
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    app_secret: str | None = None,
    params: dict | None = None,
    json: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[int, dict]:
    """One Graph API call. Returns (status, JSON object); raises MetaUnavailableError if Meta can't be
    reached, answers with a retryable error, or doesn't answer with a JSON object."""
    params = dict(params or {})
    headers = {}
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
        params['appsecret_proof'] = appsecret_proof(access_token, app_secret or '')
    try:
        with httpx.Client(timeout=META_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.request(
                method, f'{settings.META_GRAPH_API_URL}/{path}', params=params, json=json, headers=headers
            )
    except httpx.HTTPError as exc:
        raise MetaUnavailableError(f'Could not reach Meta: {exc}') from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise MetaUnavailableError(f'Meta answered {response.status_code} without JSON.') from exc
    if not isinstance(data, dict):
        raise MetaUnavailableError(f'Unexpected answer from Meta ({response.status_code}).')
    error = data.get('error') if isinstance(data.get('error'), dict) else {}
    if response.status_code >= 500 or error.get('code') in RETRYABLE_ERROR_CODES:
        raise MetaUnavailableError(f'Meta answered {response.status_code}: {error.get("message") or "no details"}')
    return response.status_code, data


def _error_message(data: dict) -> str:
    error = data.get('error') if isinstance(data.get('error'), dict) else {}
    return str(error.get('error_user_msg') or error.get('message') or 'no details')


def exchange_code(code: str, transport: httpx.BaseTransport | None = None) -> BusinessToken:
    """Swaps the code from the Embedded Signup popup (valid for 30 seconds, single use) for the
    business's token: a business integration system user token for our app, with when it expires
    (Meta's `expires_in`, else asked with token_expiry; None if that fails: the connection still works)."""
    status, data = _call(
        'GET',
        'oauth/access_token',
        params={'client_id': settings.META_APP_ID, 'client_secret': settings.META_APP_SECRET, 'code': code},
        transport=transport,
    )
    token = data.get('access_token')
    if status != 200 or not isinstance(token, str) or not token:
        logger.warning('Embedded Signup code exchange failed (%s): %s', status, _error_message(data))
        raise MetaSignupError(EXPIRED_CODE_MESSAGE)
    expires_in = data.get('expires_in')
    if isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in > 0:
        return BusinessToken(token, timezone.now() + timedelta(seconds=expires_in))
    try:
        return BusinessToken(token, token_expiry(token, transport=transport))
    except (MetaSignupError, MetaUnavailableError) as exc:
        logger.warning("Couldn't find out when the Embedded Signup token expires: %s", exc)
        return BusinessToken(token, None)


def token_expiry(access_token: str, transport: httpx.BaseTransport | None = None) -> datetime | None:
    """When Meta stops accepting `access_token` (debug_token's `expires_at`), or None if it never
    expires (`expires_at` 0). Asked with our app's access token (`<app id>|<App Secret>`)."""
    status, data = _call(
        'GET',
        'debug_token',
        params={'input_token': access_token, 'access_token': f'{settings.META_APP_ID}|{settings.META_APP_SECRET}'},
        transport=transport,
    )
    info = data.get('data') if isinstance(data.get('data'), dict) else {}
    expires_at = info.get('expires_at')
    if status != 200 or not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise MetaSignupError(f"Meta couldn't describe the token: {_error_message(data)}")
    return datetime.fromtimestamp(expires_at, UTC) if expires_at > 0 else None


def register_phone_number(
    phone_number_id: str, access_token: str, app_secret: str, pin: str, transport: httpx.BaseTransport | None = None
) -> bool:
    """Registers the number for Cloud API, setting `pin` as its two-step verification PIN. Returns
    False if it is already registered with another PIN (left as it is, so `pin` wasn't set)."""
    status, data = _call(
        'POST',
        f'{phone_number_id}/register',
        access_token=access_token,
        app_secret=app_secret,
        json={'messaging_product': 'whatsapp', 'pin': pin},
        transport=transport,
    )
    if status == 200:
        return True
    error = data.get('error') if isinstance(data.get('error'), dict) else {}
    if error.get('code') == PIN_MISMATCH_ERROR_CODE:
        logger.info('Phone number %s is already registered (two-step PIN set); keeping it.', phone_number_id)
        return False
    raise MetaSignupError(f"Meta couldn't register your number for the WhatsApp Cloud API: {_error_message(data)}")


def subscribe_app(
    waba_id: str,
    access_token: str,
    app_secret: str,
    override_callback_uri: str | None = None,
    verify_token: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Subscribes our app to the WABA's webhooks. With `override_callback_uri`, its message webhooks go
    there instead of the app's callback URL; Meta checks it with `verify_token` (the handshake)."""
    body = None
    if override_callback_uri:
        body = {'override_callback_uri': override_callback_uri, 'verify_token': verify_token or ''}
    status, data = _call(
        'POST',
        f'{waba_id}/subscribed_apps',
        access_token=access_token,
        app_secret=app_secret,
        json=body,
        transport=transport,
    )
    if status == 200 and data.get('success') is True:
        return
    raise MetaSignupError(f"Meta couldn't set up your WhatsApp webhook: {_error_message(data)}")


def unsubscribe_app(
    waba_id: str, access_token: str, app_secret: str, transport: httpx.BaseTransport | None = None
) -> None:
    """Stops our app's webhooks for the WABA (disconnecting). Raises MetaSignupError if Meta refuses."""
    status, data = _call(
        'DELETE', f'{waba_id}/subscribed_apps', access_token=access_token, app_secret=app_secret, transport=transport
    )
    if status != 200 or data.get('success') is not True:
        raise MetaSignupError(f"Meta couldn't remove the webhook subscription: {_error_message(data)}")
