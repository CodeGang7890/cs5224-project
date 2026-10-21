"""Xendit webhook receiver for payment events.

Receives Xendit's payment webhooks, verifies the callback token, extracts the payment result,
and publishes it to Pub/Sub for processing-service.

Endpoints:
- POST /webhook: Receive Xendit payment webhooks
- POST /payments: Create the Xendit payment session (hosted link) for an order / booking
- GET /: Health check
"""

import hmac
import json
import logging

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import config, xendit_api
from .publisher import PublishError, Publisher, PubSubPublisher, ensure_emulator_resources
from .schemas import CreatePaymentRequest, CreatePaymentResponse
from .xendit_webhook import InvalidWebhookError, verify_signature, parse_webhook, create_webhook_response

logger = logging.getLogger(__name__)

app = FastAPI(
    title=config.API_TITLE,
    version=config.API_VERSION,
    docs_url='/docs',
    redoc_url=None,  # ReDoc off like messaging-ingester
)


@app.get('/', summary='Health check')
def index() -> dict[str, str]:
    """Health check endpoint."""
    return {'message': 'payment-ingester is running', 'status': 'healthy'}


def get_publisher() -> Publisher:
    """Get or create the Pub/Sub publisher singleton."""
    return PubSubPublisher()


@app.post('/webhook', summary='Receive Xendit payment webhooks', response_model=None)
async def receive_webhook(
    request: Request,
    x_callback_token: str | None = Header(None, alias='x-callback-token'),
) -> Response:
    """
    Receive Xendit payment webhooks.

    Xendit sends payment status updates as webhooks. This endpoint:
    1. Verifies the webhook token (x-callback-token)
    2. Parses the payment data
    3. Publishes to Pub/Sub for processing-service

    Response codes:
    - 200: Webhook received and published successfully (or ignored: not an event we act on)
    - 400: Invalid webhook payload
    - 401: Invalid or missing webhook token
    - 503: Pub/Sub unavailable (Xendit will retry)
    """
    # Verify the token before reading the body: a wrong token is rejected without processing.
    if not verify_signature(x_callback_token):
        logger.warning('Rejected webhook: invalid or missing x-callback-token')
        raise HTTPException(status_code=401, detail='Invalid or missing webhook token.')

    # Read the body (the token check doesn't need it, but the payload does).
    raw_body = await request.body()
    
    # Parse webhook payload
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error('Invalid JSON in webhook: %s', exc)
        raise HTTPException(status_code=400, detail='Invalid JSON in webhook body.') from exc
    
    # Extract payment data
    try:
        payment_event = parse_webhook(payload)
    except InvalidWebhookError as exc:
        logger.warning('Invalid webhook payload: %s', exc)
        # Don't return 400 - Xendit will retry. Just log and ignore.
        return JSONResponse(
            status_code=200,
            content={'status': 'ignored', 'reason': str(exc)}
        )
    
    # Publish to Pub/Sub
    publisher = get_publisher()
    try:
        publisher.publish([payment_event])
    except PublishError as exc:
        logger.error('Publishing payment event failed: %s', exc)
        raise HTTPException(
            status_code=503,
            detail='Could not publish the payment event; try again later.'
        ) from exc
    
    logger.info('Processed Xendit webhook for payment: %s', payment_event['payment_reference'])
    return JSONResponse(status_code=200, content=create_webhook_response())


@app.post(
    '/payments',
    status_code=201,
    response_model=CreatePaymentResponse,
    summary='Create a Xendit payment (link) for an order or booking',
)
def create_payment(
    request: CreatePaymentRequest,
    x_internal_api_key: str | None = Header(None, alias='X-Internal-Api-Key'),
) -> CreatePaymentResponse:
    """
    Create the payment session for a placed order or booking.

    Called by messaging-service right after the customer confirms (internal API key). Xendit
    creates a Payment Session with the customer's name and email, for the amount under our
    `payment_reference` (sent to Xendit as its `reference_id`); the customer pays on
    Xendit's hosted page and the result comes back through the webhook (POST /webhook).

    Response codes:
    - 201: The payment session was created (its Xendit ID and the hosted payment link)
    - 401: Invalid or missing internal API key
    - 403: Internal API disabled (INTERNAL_API_KEY not set)
    - 422: Invalid request
    - 502: Xendit refused (its detail in the response)
    - 503: Xendit unreachable or not configured
    """
    if not config.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail='Internal API is disabled (INTERNAL_API_KEY is not set).')
    if not hmac.compare_digest(config.INTERNAL_API_KEY, x_internal_api_key or ''):
        raise HTTPException(status_code=401, detail='Invalid or missing internal API key.')

    try:
        result = xendit_api.create_payment(
            amount=request.amount,
            external_reference=request.payment_reference,
            customer={'given_name': request.customer.given_name, 'email': request.customer.email},
            description=request.description,
        )
    except xendit_api.XenditUnavailableError as exc:
        logger.error('Could not create the Xendit payment for %s #%s: %s', request.kind, request.item_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except xendit_api.XenditApiError as exc:
        logger.error('Xendit refused the payment for %s #%s: %s', request.kind, request.item_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info('Created Xendit payment %s for %s #%s', result['xendit_payment_id'], request.kind, request.item_id)
    return CreatePaymentResponse(**result)


def create_app() -> FastAPI:
    """Create the FastAPI app (for Gunicorn)."""
    return app


@app.on_event('startup')
async def startup_event() -> None:
    """Set up Pub/Sub resources on startup (emulator only)."""
    ensure_emulator_resources()
