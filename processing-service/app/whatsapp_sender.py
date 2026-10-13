"""
Sending a WhatsApp message to a customer, through configuration-service's internal send endpoint
"""

import httpx
from . import config

class SendError(Exception):
    """The message wasn't sent.
    `retryable`: it could work later (configuration-service or Meta couldn't be reached).
    Otherwise it never will"""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def send_text(business_id: int, to: str, text: str, transport: httpx.BaseTransport | None = None) -> str:
    """Sends `text` to `to` from the business's WhatsApp number.
    Returns Meta's message id."""
    url = f'{config.CONFIGURATION_SERVICE_URL}/internal/whatsapp/{business_id}/send/'
    try:
        with httpx.Client(timeout=config.WHATSAPP_SEND_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(url, json={'to': to, 'text': text}, headers={'X-Internal-Api-Key': config.INTERNAL_API_KEY})
    except httpx.HTTPError as exc:
        raise SendError(f'Could not reach configuration-service: {exc}', retryable=True) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code == 200 and isinstance(body, dict) and body.get('message_id'):
        return body['message_id']
    detail = body.get('detail') if isinstance(body, dict) else None
    # 503: Meta couldn't be reached, 5xx other than 502: configuration-service failed
    # 502 (Meta refused), 404 (the business hasn't connected WhatsApp), 4xx: retrying won't change it
    retryable = response.status_code >= 500 and response.status_code != 502
    raise SendError(f'Not sent ({response.status_code}): {detail or response.text[:200]}', retryable=retryable)
