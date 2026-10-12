"""Sending a reply to a customer on WhatsApp: through configuration-service's internal send
endpoint, which holds the business's access token and calls Meta's Graph API (locally,
mock_whatsapp's fake one). Later this can go through an outbound queue (retries, rate limits)."""

import httpx

from . import config


class SendError(Exception):
    """The message wasn't sent (configuration-service or Meta refused it, or couldn't be reached)."""


def send_text(business_id: int, to: str, text: str, transport: httpx.BaseTransport | None = None) -> str:
    """Sends `text` to `to` (E.164) from the business's WhatsApp number; returns Meta's message id."""
    url = f'{config.CONFIGURATION_SERVICE_URL}/internal/whatsapp/{business_id}/send/'
    try:
        with httpx.Client(timeout=config.WHATSAPP_SEND_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(url, json={'to': to, 'text': text}, headers={'X-Internal-Api-Key': config.INTERNAL_API_KEY})
    except httpx.HTTPError as exc:
        raise SendError(f'Could not reach configuration-service: {exc}') from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not isinstance(body, dict) or not body.get('message_id'):
        detail = body.get('detail') if isinstance(body, dict) else None
        raise SendError(f'Not sent ({response.status_code}): {detail or response.text[:200]}')
    return body['message_id']
