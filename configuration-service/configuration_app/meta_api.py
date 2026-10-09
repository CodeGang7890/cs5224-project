"""Client for Meta's Graph API (WhatsApp Cloud API): checks a business's WhatsApp credentials.

One call checks all three values together:

    GET {META_GRAPH_API_URL}/{phone_number_id}?fields=display_phone_number,verified_name
        &appsecret_proof=<HMAC-SHA256 of the access token, keyed by the App Secret>
    Authorization: Bearer <access token>

- a bad or expired access token → Meta error 190
- a wrong App Secret (it isn't the secret of the app that issued the token) → "Invalid appsecret_proof"
- a wrong Phone Number ID, or one the token can't access → Meta error 100

Outbound calls to Meta live here (not in messaging-ingester), because the secrets never leave this
service. Sending replies will use the same client.
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
