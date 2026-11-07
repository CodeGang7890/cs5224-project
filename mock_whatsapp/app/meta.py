"""What Meta does when a customer messages a business: a POST to the business's webhook
(messaging-ingester's /webhook/{business_id}) with Meta's payload, signed with the App Secret.

The body, as Meta sends it (WhatsApp Cloud API, "messages" webhook):

    {"object": "whatsapp_business_account",
     "entry": [{"id": "<WhatsApp Business Account id>",
                "changes": [{"field": "messages",
                             "value": {"messaging_product": "whatsapp",
                                       "metadata": {"display_phone_number": "6588323212",
                                                    "phone_number_id": "100000000000001"},
                                       "contacts": [{"profile": {"name": "Alice Tan"}, "wa_id": "6591234567"}],
                                       "messages": [{"from": "6591234567", "id": "wamid.…",
                                                     "timestamp": "1760000000", "type": "text",
                                                     "text": {"body": "Hi!"}}]}}]}]}

and the header X-Hub-Signature-256: sha256=<HMAC-SHA256 of the exact body bytes, keyed by the App Secret>.
A photo or document (app/media.py) is `"type": "image"` / `"document"` with, in place of "text",
`"image": {"caption"?, "mime_type", "sha256", "id"}` / `"document": {"caption"?, "filename", "mime_type", "sha256", "id"}`.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

import httpx

from . import config

SIGNATURE_HEADER = 'X-Hub-Signature-256'


def new_wamid() -> str:
    """A WhatsApp message id in Meta's style ("wamid." + base64)."""
    return 'wamid.' + base64.b64encode(b'\x15\x02\x00\x11\x18\x12' + secrets.token_bytes(18)).decode().rstrip('=')


def message_content(text: str, attachment: dict | None = None) -> dict:
    """The message's type and content, as Meta sends them: text, or a photo / document (the text is its caption)."""
    if attachment is None:
        return {'type': 'text', 'text': {'body': text}}
    kind = attachment['kind']
    content = {'caption': text} if text else {}
    if kind == 'document':
        content['filename'] = attachment['filename']
    content.update(mime_type=attachment['mime_type'], sha256=attachment['sha256'], id=attachment['id'])
    return {'type': kind, kind: content}


def webhook_payload(
    business: dict, wa_id: str, name: str, wamid: str, text: str, timestamp: int | None = None, attachment: dict | None = None,
) -> dict:
    return {
        'object': 'whatsapp_business_account',
        'entry': [{
            'id': business['waba_id'],
            'changes': [{
                'field': 'messages',
                'value': {
                    'messaging_product': 'whatsapp',
                    'metadata': {
                        'display_phone_number': business['display_phone_number'].replace('+', '').replace(' ', ''),
                        'phone_number_id': business['phone_number_id'],
                    },
                    'contacts': [{'profile': {'name': name}, 'wa_id': wa_id}],
                    'messages': [{
                        'from': wa_id,
                        'id': wamid,
                        'timestamp': str(timestamp if timestamp is not None else int(time.time())),
                        **message_content(text, attachment),
                    }],
                },
            }],
        }],
    }


def signature(app_secret: str, body: bytes) -> str:
    return 'sha256=' + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookError(Exception):
    """The webhook call failed (the ingester refused it, or couldn't be reached)."""


def send_to_webhook(business: dict, payload: dict, transport: httpx.BaseTransport | None = None) -> None:
    """POSTs the payload to the business's webhook, signed like Meta signs it."""
    body = json.dumps(payload, separators=(',', ':')).encode()  # the exact bytes that are signed
    url = f'{config.INGESTER_URL}/webhook/{business["business_id"]}'
    headers = {'Content-Type': 'application/json', SIGNATURE_HEADER: signature(business['app_secret'], body)}
    try:
        with httpx.Client(timeout=config.INGESTER_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise WebhookError(f'Could not reach messaging-ingester at {config.INGESTER_URL}: {exc}') from exc
    if response.status_code != 200:
        raise WebhookError(f'The webhook answered {response.status_code}: {response.text[:300]}')
