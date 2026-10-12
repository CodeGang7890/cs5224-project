"""The page (server-rendered with Jinja2) and the small JSON API its JavaScript uses."""

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import config, db, meta

router = APIRouter()
templates = Jinja2Templates(directory=config.BASE_DIR / 'templates')
TEXT_MAX_LENGTH = 4096  # WhatsApp's limit


def format_number(wa_id: str) -> str:
    """6591234567 → +65 9123 4567 (Singapore); other numbers just get a "+"."""
    if re.fullmatch(r'65\d{8}', wa_id):
        return f'+65 {wa_id[2:6]} {wa_id[6:]}'
    return f'+{wa_id}'


templates.env.filters['number'] = format_number
templates.env.filters['hue'] = lambda name: sum(map(ord, name or '?')) * 47 % 360  # an avatar colour per name


def chats(wa_id: str) -> list[dict]:
    """The businesses, with this customer's last message to / from each."""
    last = db.last_messages(wa_id)
    return [{**business, 'last': last.get(business['phone_number_id'])} for business in config.businesses()]


@router.get('/', response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, chat: str | None = None):
    """?as=<customer wa_id> (who you chat as) and ?chat=<business phone_number_id> (the open chat)."""
    customers = db.customers()
    current = next((c for c in customers if c['wa_id'] == request.query_params.get('as')), customers[0])
    businesses = config.businesses()
    business = next((b for b in businesses if b['phone_number_id'] == chat), businesses[0])
    return templates.TemplateResponse(request, 'index.html', {
        'customers': customers,
        'customer': current,
        'chats': chats(current['wa_id']),
        'business': business,
        'messages': db.messages(current['wa_id'], business['phone_number_id']),
        'ingester_url': config.INGESTER_URL,
        'graph_url': f'http://<this machine>:{config.PORT}/{config.GRAPH_API_VERSION}',
    })


class NewCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    wa_id: str | None = Field(default=None, description='Digits only, e.g. 6591234567 (default: a random Singapore number).')


@router.post('/api/customers', summary='Add a customer to chat as')
def add_customer(body: NewCustomer) -> dict:
    wa_id = body.wa_id.replace('+', '').replace(' ', '') if body.wa_id else None
    if wa_id is not None and not re.fullmatch(r'[1-9]\d{6,14}', wa_id):
        raise HTTPException(400, 'The number must be in international format, e.g. +65 9123 4567.')
    if wa_id is not None and db.customer(wa_id):
        raise HTTPException(400, 'That number is already one of the customers.')
    return db.add_customer(body.name, wa_id)


@router.get('/api/chats', summary="A customer's chats (the businesses, with the last message)")
def get_chats(request: Request) -> list[dict]:
    return chats(request.query_params.get('as', ''))


@router.get('/api/messages', summary='Messages of one chat (after a message id, for polling)')
def get_messages(request: Request, chat: str, after: int = 0) -> list[dict]:
    return db.messages(request.query_params.get('as', ''), chat, after)


class NewMessage(BaseModel):
    wa_id: str  # the customer sending it
    phone_number_id: str  # the business they send it to
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)


@router.post('/api/messages', summary='Send a message as the customer (calls the webhook, like Meta)')
def send_message(body: NewMessage) -> dict:
    customer = db.customer(body.wa_id)
    business = config.business_by_phone_number_id(body.phone_number_id)
    if customer is None or business is None:
        raise HTTPException(404, 'Unknown customer or business.')
    text = body.text.strip()
    if not text:
        raise HTTPException(400, 'Type a message.')
    wamid = meta.new_wamid()
    message = db.add_message(wamid, customer['wa_id'], business['phone_number_id'], from_customer=True, text=text, status='sending')
    payload = meta.webhook_payload(business, customer['wa_id'], customer['name'], wamid, text)
    try:
        meta.send_to_webhook(business, payload)
    except meta.WebhookError as exc:
        return db.set_status(message['id'], 'failed', str(exc))
    return db.set_status(message['id'], 'sent')


@router.post('/api/reset', summary='Delete every message (the customers stay)')
def reset() -> dict:
    db.reset()
    return {'reset': True}
