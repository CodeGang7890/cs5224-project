"""Client for Meta's Graph API (WhatsApp Cloud API). Outbound calls to Meta live here (not in
messaging-ingester), because the secrets never leave this service. Every call goes through _call():
the business's token as `Authorization: Bearer`, plus `appsecret_proof` (HMAC-SHA256 of the token,
keyed by the App Secret).

- phone_number_info(): which number Embedded Signup connected (its display number and verified name):

    GET {META_GRAPH_API_URL}/{phone_number_id}?fields=display_phone_number,verified_name

- send_text_message(): a reply (the internal send endpoint, called by messaging-service):

    POST {phone_number_id}/messages
    {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "6591234567",
     "type": "text", "text": {"preview_url": false, "body": "…"}}
    → {"messaging_product": "whatsapp", "contacts": [...], "messages": [{"id": "wamid.…"}]}

- Embedded Signup (embedded_signup.py), with our app's ID and App Secret (settings.META_APP_*):

    GET  oauth/access_token?client_id=…&client_secret=…&code=…   → the business's token (exchange_code)
    POST {phone_number_id}/register {"messaging_product": "whatsapp", "pin": "123456"}   (register_phone_number)
    POST {waba_id}/subscribed_apps [{"override_callback_uri": …, "verify_token": …}]   (subscribe_app)
    DELETE {waba_id}/subscribed_apps   (unsubscribe_app)

Locally, META_GRAPH_API_URL can point at mock_whatsapp's fake Graph API.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

META_TIMEOUT_SECONDS = 10
# Embedded Signup's calls can take Meta longer (registering a number, or overriding the webhook, which
# Meta checks against messaging-ingester before answering): a 10-second limit sometimes cut them off.
SIGNUP_TIMEOUT_SECONDS = 30


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


class MetaUnavailableError(Exception):
    """Meta couldn't be reached or didn't answer usefully (network, timeout, 5xx, rate limit)."""


class MetaSendError(Exception):
    """Meta refused to send the message (e.g. a bad number, or the 24-hour window has closed)."""


class MetaSignupError(Exception):
    """Meta refused a step of Embedded Signup. The message is for the business owner."""


# Graph API error codes worth retrying: Meta-side problems and rate limits.
RETRYABLE_ERROR_CODES = (1, 2, 4, 17, 32, 613)
# Sending also has WhatsApp's own rate limits (account, spam, pair rate): worth retrying too.
SEND_RETRYABLE_ERROR_CODES = (*RETRYABLE_ERROR_CODES, 130429, 131048, 131056)
# Registering a number that already has a different two-step verification PIN, i.e. it's registered.
PIN_MISMATCH_ERROR_CODE = 133005
EXPIRED_CODE_MESSAGE = 'The Facebook login expired or was already used. Please click Connect with Facebook again.'


def appsecret_proof(access_token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()


def _call(
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    app_secret: str | None = None,
    params: dict | None = None,
    json: dict | None = None,
    retryable: tuple[int, ...] = RETRYABLE_ERROR_CODES,
    timeout: float = META_TIMEOUT_SECONDS,
    transport: httpx.BaseTransport | None = None,  # tests pass an httpx.MockTransport
) -> tuple[int, dict]:
    """One Graph API call. Returns (status, JSON object); raises MetaUnavailableError if Meta can't be
    reached, answers 5xx or one of the `retryable` error codes, or doesn't answer with a JSON object.
    Its message names the call (e.g. `POST 123/register`), so the logs show which one failed."""
    params = dict(params or {})
    headers = {}
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
        params['appsecret_proof'] = appsecret_proof(access_token, app_secret or '')
    call = f'{method} {path}'
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.request(
                method, f'{settings.META_GRAPH_API_URL}/{path}', params=params, json=json, headers=headers
            )
    except httpx.HTTPError as exc:
        raise MetaUnavailableError(f'Could not reach Meta ({call}): {type(exc).__name__} {exc}') from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise MetaUnavailableError(f'Meta answered {response.status_code} without JSON ({call}).') from exc
    if not isinstance(data, dict):
        raise MetaUnavailableError(f'Unexpected answer from Meta ({call}, {response.status_code}).')
    error = data.get('error') if isinstance(data.get('error'), dict) else {}
    if response.status_code >= 500 or error.get('code') in retryable:
        raise MetaUnavailableError(
            f'Meta answered {response.status_code} ({call}): {error.get("message") or "no details"}'
        )
    return response.status_code, data


def _error_message(data: dict) -> str:
    error = data.get('error') if isinstance(data.get('error'), dict) else {}
    return str(error.get('error_user_msg') or error.get('message') or 'no details')


def phone_number_info(
    phone_number_id: str, access_token: str, app_secret: str, transport: httpx.BaseTransport | None = None
) -> PhoneNumberInfo:
    """The number's display number and verified name, which also proves the token can use it. Raises
    MetaSignupError (a message for the owner) if Meta refuses."""
    status, data = _call(
        'GET',
        phone_number_id,
        access_token=access_token,
        app_secret=app_secret,
        params={'fields': 'display_phone_number,verified_name'},
        timeout=SIGNUP_TIMEOUT_SECONDS,
        transport=transport,
    )
    if status != 200:
        raise MetaSignupError(f"Meta didn't give us access to this phone number: {_error_message(data)}")
    return PhoneNumberInfo(
        display_phone_number=str(data.get('display_phone_number') or ''),
        verified_name=str(data.get('verified_name') or ''),
    )


def send_text_message(
    phone_number_id: str,
    access_token: str,
    app_secret: str,
    to: str,
    text: str,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Sends `text` to the customer `to` (E.164, e.g. +6591234567) from the business's number.
    Returns Meta's message id (wamid…). Raises MetaSendError if Meta refuses it, MetaUnavailableError
    if Meta can't be reached (worth retrying)."""
    body = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to.removeprefix('+'),  # Meta's wa_id: the number without "+"
        'type': 'text',
        'text': {'preview_url': False, 'body': text},
    }
    status, data = _call(
        'POST',
        f'{phone_number_id}/messages',
        access_token=access_token,
        app_secret=app_secret,
        json=body,
        retryable=SEND_RETRYABLE_ERROR_CODES,
        transport=transport,
    )
    if status != 200:
        raise MetaSendError(f'Meta refused the message ({status}): {_error_message(data)}')
    messages = data.get('messages')
    if isinstance(messages, list) and messages and isinstance(messages[0], dict) and messages[0].get('id'):
        return str(messages[0]['id'])
    raise MetaUnavailableError('Meta answered 200 without a message id.')


# --- Embedded Signup ----------------------------------------------------------------------


def exchange_code(code: str, transport: httpx.BaseTransport | None = None) -> BusinessToken:
    """Swaps the code from the Embedded Signup popup (valid for 30 seconds, single use) for the
    business's token: a business integration system user token for our app, with when it expires
    (Meta's `expires_in`; None if it doesn't say)."""
    status, data = _call(
        'GET',
        'oauth/access_token',
        params={'client_id': settings.META_APP_ID, 'client_secret': settings.META_APP_SECRET, 'code': code},
        timeout=SIGNUP_TIMEOUT_SECONDS,
        transport=transport,
    )
    token = data.get('access_token')
    if status != 200 or not isinstance(token, str) or not token:
        logger.warning('Embedded Signup code exchange failed (%s): %s', status, _error_message(data))
        raise MetaSignupError(EXPIRED_CODE_MESSAGE)
    expires_in = data.get('expires_in')
    if isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in > 0:
        return BusinessToken(token, timezone.now() + timedelta(seconds=expires_in))
    return BusinessToken(token, None)


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
        timeout=SIGNUP_TIMEOUT_SECONDS,
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
        timeout=SIGNUP_TIMEOUT_SECONDS,
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
