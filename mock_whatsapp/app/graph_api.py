"""A fake of Meta's Graph API (WhatsApp Cloud API), for configuration-service to call instead of
Meta: point its META_GRAPH_API_URL at http://<this host>:9000/v26.0.

- POST /v26.0/{phone_number_id}/messages: send a message to a customer (configuration-service's
  internal send endpoint, i.e. the replies). Stored in the chat, as received by the customer.
- GET /v26.0/{phone_number_id}?fields=display_phone_number,verified_name: the credentials check
  configuration-service runs when an owner connects WhatsApp in the frontend.

Like Meta, both need `Authorization: Bearer <the business's access token>`, and a given
`appsecret_proof` must be the HMAC-SHA256 of the token keyed by the App Secret. Errors use Meta's
shape: {"error": {"message", "type", "code", "fbtrace_id"}}.
"""

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import config, db
from .meta import new_wamid

router = APIRouter(prefix=f'/{config.GRAPH_API_VERSION}', tags=['fake Graph API'])


def meta_error(status: int, code: int, message: str, kind: str = 'OAuthException') -> JSONResponse:
    return JSONResponse(
        {'error': {'message': message, 'type': kind, 'code': code, 'fbtrace_id': secrets.token_urlsafe(8)}},
        status_code=status,
    )


def authorize(request: Request, phone_number_id: str) -> tuple[dict | None, JSONResponse | None]:
    """The business of this phone number id, if the request carries its access token (else Meta's error)."""
    business = config.business_by_phone_number_id(phone_number_id)
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if business is None:
        return None, meta_error(
            400, 100, f"Unsupported request - method type: {request.method.lower()}. Object with ID '{phone_number_id}' "
            'does not exist, cannot be loaded due to missing permissions, or does not support this operation.',
            kind='GraphMethodException',
        )
    if not hmac.compare_digest(token.encode(), business['access_token'].encode()):
        return None, meta_error(401, 190, 'Invalid OAuth access token - Cannot parse access token')
    proof = request.query_params.get('appsecret_proof')
    expected = hmac.new(business['app_secret'].encode(), token.encode(), hashlib.sha256).hexdigest()
    if proof is not None and not hmac.compare_digest(proof, expected):
        return None, meta_error(400, 100, 'Invalid appsecret_proof provided in the API argument')
    return business, None


@router.post('/{phone_number_id}/messages', summary='Send a message (as the business)')
async def send_message(phone_number_id: str, request: Request):
    business, error = authorize(request, phone_number_id)
    if error:
        return error
    try:
        body = await request.json()
    except ValueError:
        return meta_error(400, 100, 'Invalid JSON in the request body', kind='GraphMethodException')
    to = str(body.get('to') or '').removeprefix('+') if isinstance(body, dict) else ''
    text = ((body.get('text') or {}).get('body') if isinstance(body, dict) and isinstance(body.get('text'), dict) else None)
    if body.get('messaging_product') != 'whatsapp' or body.get('type') != 'text' or not to.isdigit() or not text:
        return meta_error(400, 100, '(#100) Invalid parameter: send {messaging_product: whatsapp, to, type: text, text: {body}}')
    wamid = new_wamid()
    db.add_message(wamid, to, phone_number_id, from_customer=False, text=text, status='received')
    return {'messaging_product': 'whatsapp', 'contacts': [{'input': body['to'], 'wa_id': to}], 'messages': [{'id': wamid}]}


@router.get('/{phone_number_id}', summary="A phone number's details")
def phone_number(phone_number_id: str, request: Request):
    business, error = authorize(request, phone_number_id)
    if error:
        return error
    return {
        'display_phone_number': business['display_phone_number'],
        'verified_name': business['name'],
        'id': phone_number_id,
    }
