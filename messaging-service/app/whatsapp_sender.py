"""Sending a reply to a customer on WhatsApp: through configuration-service's internal send
endpoint, which holds the business's access token and calls Meta's Graph API (locally,
mock_whatsapp's fake one). Later this can go through an outbound queue (retries, rate limits)."""

import httpx

from . import config


RETRYABLE_4XX = (401, 403, 408, 429)


class SendError(Exception):
    """The message wasn't sent (configuration-service or Meta refused it, or couldn't be reached).
    `status_code`: configuration-service's answer (None: no answer). A 4xx is permanent (400 a bad
    request, 404 the business isn't connected any more): retrying won't help. Except 401 / 403 (our
    internal API key is wrong: a deployment mistake, fixed by redeploying, so keep retrying), 408
    and 429 (a timeout, too many requests)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def permanent(self) -> bool:
        return self.status_code is not None and 400 <= self.status_code < 500 and self.status_code not in RETRYABLE_4XX


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
        raise SendError(f'Not sent ({response.status_code}): {detail or response.text[:200]}', response.status_code)
    return body['message_id']
