"""Meta's WhatsApp webhook: one Callback URL per business, /webhook/<business_id>.

- GET: Meta's subscription handshake when the owner saves the webhook in Meta (or, with Embedded
  Signup, when configuration-service points the business's WhatsApp account at it).
- POST: incoming events. The signature is checked, then each customer message is published.

/webhook (no ID) is our Meta app's own Callback URL, which Embedded Signup needs (App Dashboard →
WhatsApp → Configuration). It only gets account-level events; businesses' messages go to their own
URLs. It checks the handshake and signature and publishes nothing: account_update events are handed to
configuration-service (which marks the connections disconnected or banned), the rest only logged.

The checks are done by configuration-service (verification.py); this service holds no secrets.
Routes are plain `def`s: FastAPI runs them in a thread pool, so the blocking HTTP and Pub/Sub
calls don't stall the event loop.
"""

import json
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import PlainTextResponse

from . import config
from .parsing import parse_account_updates, parse_webhook
from .publisher import Publisher, PublishError, PubSubPublisher
from .schemas import AppWebhookAck, ErrorResponse, ValidationErrorResponse, WebhookAck
from .verification import BusinessNotConnectedError, ConfigurationServiceClient, ConfigurationServiceUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(tags=['webhook'])

@lru_cache
def get_verifier() -> ConfigurationServiceClient:
    return ConfigurationServiceClient()


@lru_cache
def get_publisher() -> Publisher:
    return PubSubPublisher()


async def raw_body(request: Request) -> bytes:
    """The exact bytes Meta sent: the signature is computed over them, so never re-serialize."""
    return await request.body()


BusinessId = Annotated[int, Path(description='The business ID from the Callback URL.')]
Verifier = Annotated[ConfigurationServiceClient, Depends(get_verifier)]

def _check(call, not_found: str = 'This business has not connected WhatsApp.'):
    """Runs a configuration-service call, mapping its failures to HTTP errors: 404 `not_found`, or 503
    (so Meta retries)."""
    try:
        return call()
    except BusinessNotConnectedError as exc:
        raise HTTPException(status_code=404, detail=not_found) from exc
    except ConfigurationServiceUnavailableError as exc:
        logger.error('configuration-service unavailable: %s', exc)
        raise HTTPException(status_code=503, detail='Could not verify the request right now; try again later.') from exc


# --- Routes -------------------------------------------------------------------------------


@router.get(
    '/webhook/{business_id}',
    summary="Meta's webhook verification handshake",
    response_class=PlainTextResponse,
    responses={
        200: {'content': {'text/plain': {'example': '1158201444'}}, 'description': 'The `hub.challenge`, echoed.'},
        403: {'model': ErrorResponse, 'description': 'Wrong `hub.mode` or `hub.verify_token`.'},
        404: {'model': ErrorResponse, 'description': 'This business has not connected WhatsApp.'},
        422: {'model': ValidationErrorResponse, 'description': 'Missing query parameters.'},
        503: {'model': ErrorResponse, 'description': 'configuration-service is unreachable.'},
    },
)
def verify_subscription(
    business_id: BusinessId,
    verifier: Verifier,
    mode: Annotated[str, Query(alias='hub.mode')],
    verify_token: Annotated[str, Query(alias='hub.verify_token')],
    challenge: Annotated[str, Query(alias='hub.challenge')],
) -> PlainTextResponse:
    """Asks configuration-service to check the verify token. Yes -> returns Meta's challenge. No -> 403.
    Any error -> 503 (Meta retries).
    """
    if mode != 'subscribe':
        raise HTTPException(status_code=403, detail='hub.mode must be "subscribe".')
    verification = _check(lambda: verifier.verify_token(business_id, verify_token))
    if not verification.valid:
        logger.warning('Webhook verification for business %s failed: wrong verify token', business_id)
        raise HTTPException(status_code=403, detail='Wrong verify token.')
    logger.info('Webhook verified for business %s', business_id)
    return PlainTextResponse(challenge)


@router.post(
    '/webhook/{business_id}',
    summary='Receive WhatsApp events from Meta',
    responses={
        400: {'model': ErrorResponse, 'description': 'The (correctly signed) body is not JSON.'},
        401: {'model': ErrorResponse, 'description': 'Missing or wrong `X-Hub-Signature-256`.'},
        404: {'model': ErrorResponse, 'description': 'This business has not connected WhatsApp.'},
        503: {'model': ErrorResponse, 'description': 'configuration-service or Pub/Sub is unavailable; Meta retries.'},
    },
)
def receive_webhook(
    business_id: BusinessId,
    verifier: Verifier,
    publisher: Annotated[Publisher, Depends(get_publisher)],
    body: Annotated[bytes, Depends(raw_body)],
    signature: Annotated[str | None, Header(alias=config.SIGNATURE_HEADER)] = None,
) -> WebhookAck:
    """Forwards Meta's exact body and signature header to configuration-service for verification.
    If valid, parses the customer messages for the business's own number only, delivery/read receipts are ignored,
    publishes them to Pub/Sub and waits until Pub/Sub confirms the publication.
    """
    verification = _check(lambda: verifier.verify_signature(business_id, body, signature))
    if not verification.valid:
        logger.warning('Rejected a webhook for business %s: bad signature', business_id)
        raise HTTPException(status_code=401, detail='Missing or invalid signature.')
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='The body is not valid JSON.') from exc

    result = parse_webhook(payload, business_id, verification.phone_number_id)
    try:
        publisher.publish(result.messages)
    except PublishError as exc:
        logger.error('Publishing for business %s failed: %s', business_id, exc)
        raise HTTPException(status_code=503, detail='Could not publish the messages; try again later.') from exc
    return WebhookAck(published=len(result.messages))



# --- Our Meta app's default webhook (Embedded Signup) ---------------------------------------

@router.get(
    '/webhook',
    summary="Meta's handshake for our app's webhook",
    response_class=PlainTextResponse,
    responses={
        200: {'content': {'text/plain': {'example': '1158201444'}}, 'description': 'The `hub.challenge`, echoed.'},
        403: {'model': ErrorResponse, 'description': 'Wrong `hub.mode` or `hub.verify_token`.'},
        404: {'model': ErrorResponse, 'description': 'Our app webhook is not configured.'},
        422: {'model': ValidationErrorResponse, 'description': 'Missing query parameters.'},
        503: {'model': ErrorResponse, 'description': 'configuration-service is unreachable.'},
    },
)
def verify_app_subscription(
    verifier: Verifier,
    mode: Annotated[str, Query(alias='hub.mode')],
    verify_token: Annotated[str, Query(alias='hub.verify_token')],
    challenge: Annotated[str, Query(alias='hub.challenge')],
) -> PlainTextResponse:
    """When our Callback URL is saved in the App Dashboard: checks META_APP_WEBHOOK_VERIFY_TOKEN."""
    if mode != 'subscribe':
        raise HTTPException(status_code=403, detail='hub.mode must be "subscribe".')
    if not _check(lambda: verifier.verify_app_token(verify_token), 'Our app webhook is not configured.').valid:
        logger.warning('App webhook verification failed: wrong verify token')
        raise HTTPException(status_code=403, detail='Wrong verify token.')
    logger.info('App webhook verified')
    return PlainTextResponse(challenge)


@router.post(
    '/webhook',
    summary="Receive events for our app's webhook",
    responses={
        400: {'model': ErrorResponse, 'description': 'The (correctly signed) body is not JSON.'},
        401: {'model': ErrorResponse, 'description': 'Missing or wrong `X-Hub-Signature-256`.'},
        404: {'model': ErrorResponse, 'description': 'Our app webhook is not configured.'},
        503: {'model': ErrorResponse, 'description': 'configuration-service is unavailable; Meta retries.'},
    },
)
def receive_app_webhook(
    verifier: Verifier,
    body: Annotated[bytes, Depends(raw_body)],
    signature: Annotated[str | None, Header(alias=config.SIGNATURE_HEADER)] = None,
) -> AppWebhookAck:
    """Checks the signature (our App Secret), hands the account_update events to configuration-service
    (which marks connections disconnected or banned; if it's unavailable → 503, so Meta retries) and logs
    the rest. Customer messages shouldn't arrive here (each business's are overridden to its own URL);
    any that do are logged, not published."""
    if not _check(lambda: verifier.verify_app_signature(body, signature), 'Our app webhook is not configured.').valid:
        logger.warning('Rejected an app webhook: bad signature')
        raise HTTPException(status_code=401, detail='Missing or invalid signature.')
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='The body is not valid JSON.') from exc

    entries = payload.get('entry') if isinstance(payload, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        changes = entry.get('changes') if isinstance(entry, dict) else None
        for item in changes if isinstance(changes, list) else []:
            if not isinstance(item, dict):
                continue
            field = item.get('field')
            value = item.get('value') if isinstance(item.get('value'), dict) else {}
            if field == 'messages' and value.get('messages'):
                metadata = value.get('metadata') if isinstance(value.get('metadata'), dict) else {}
                logger.warning(
                    'App webhook got messages for phone number %s (its webhook override is missing); not published',
                    metadata.get('phone_number_id'),
                )
            else:
                logger.info('App webhook event %s for account %s', field, entry.get('id'))

    updates = parse_account_updates(payload)
    changed = _check(lambda: verifier.report_account_updates(updates), 'Our app webhook is not configured.') if updates else 0
    if updates:
        logger.info('Handed %d account_update event(s) to configuration-service: %d changed', len(updates), changed)
    return AppWebhookAck(account_updates=len(updates), changed=changed)
