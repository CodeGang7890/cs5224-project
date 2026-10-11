"""Meta's WhatsApp webhook: one Callback URL per business, /webhook/<business_id>.

- GET: Meta's subscription handshake when the owner saves the webhook in Meta.
- POST: incoming events. The signature is checked, then each customer message is published.

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
from .parsing import parse_webhook
from .publisher import Publisher, PublishError, PubSubPublisher
from .schemas import ErrorResponse, ValidationErrorResponse, WebhookAck
from .verification import BusinessNotConnectedError, ConfigurationServiceClient, VerificationUnavailableError

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


def _check(call):
    """Runs a verification call, mapping its failures to HTTP errors."""
    try:
        return call()
    except BusinessNotConnectedError as exc:
        raise HTTPException(status_code=404, detail='This business has not connected WhatsApp.') from exc
    except VerificationUnavailableError as exc:
        logger.error('Verification unavailable: %s', exc)
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
