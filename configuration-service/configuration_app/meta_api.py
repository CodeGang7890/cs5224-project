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
"""

import hashlib
import hmac
from dataclasses import dataclass

import httpx
from django.conf import settings

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
