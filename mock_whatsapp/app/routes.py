"""The page (server-rendered with Jinja2) and the small JSON API its JavaScript uses."""

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Literal

from pydantic import BaseModel, Field

from . import config, db, media, meta

router = APIRouter()
templates = Jinja2Templates(directory=config.BASE_DIR / 'templates')
TEXT_MAX_LENGTH = 4096  # WhatsApp's limit
# Added to the CSS / JS URLs (?v=), so a browser doesn't keep using an old copy after a change.
STATIC_VERSION = str(int(max(path.stat().st_mtime for path in (config.BASE_DIR / 'static').iterdir())))


def format_number(wa_id: str) -> str:
    """6591234567 → +65 9123 4567 (Singapore); other numbers just get a "+"."""
    if re.fullmatch(r'65\d{8}', wa_id):
        return f'+65 {wa_id[2:6]} {wa_id[6:]}'
    return f'+{wa_id}'


templates.env.filters['number'] = format_number
templates.env.filters['hue'] = lambda name: sum(map(ord, name or '?')) * 47 % 360  # an avatar colour per name


def with_media(message: dict | None) -> dict | None:
    """The message, with its attachment's metadata (`media`, from memory; None if it's text, or unknown
    after a restart) and a one-line `preview` for the chat list."""
    if message is None:
        return None
    attachment = media.get(message['wamid'])
    if attachment is None:
        preview = message['text'] or '📎 Attachment'
    elif attachment['kind'] == media.IMAGE:
        preview = f'📷 {message["text"] or "Photo"}'
    else:
        preview = f'📄 {attachment["filename"]}'
    return {**message, 'media': attachment, 'preview': preview}


def chats(wa_id: str) -> list[dict]:
    """The businesses, with this customer's last message to / from each."""
    last = db.last_messages(wa_id)
    return [{**business, 'last': with_media(last.get(business['phone_number_id']))} for business in config.businesses()]


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
        'messages': [with_media(m) for m in db.messages(current['wa_id'], business['phone_number_id'])],
        'ingester_url': config.INGESTER_URL,
        'graph_url': f'http://<this machine>:{config.PORT}/{config.GRAPH_API_VERSION}',
        'static_version': STATIC_VERSION,
        'prefix': config.PUBLIC_PATH_PREFIX,
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
    return [with_media(m) for m in db.messages(request.query_params.get('as', ''), chat, after)]


class Attachment(BaseModel):
    """A photo or document's metadata: the file itself isn't sent (see app/media.py)."""

    kind: Literal['image', 'document']
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(default='application/octet-stream', min_length=1, max_length=255)
    size: int = Field(default=0, ge=0, description='In bytes.')


class NewMessage(BaseModel):
    wa_id: str  # the customer sending it
    phone_number_id: str  # the business they send it to
    text: str = Field(default='', max_length=TEXT_MAX_LENGTH, description="The message, or the attachment's caption.")
    attachment: Attachment | None = None


@router.post('/api/messages', summary='Send a message, photo or document as the customer (calls the webhook, like Meta)')
def send_message(body: NewMessage) -> dict:
    customer = db.customer(body.wa_id)
    business = config.business_by_phone_number_id(body.phone_number_id)
    if customer is None or business is None:
        raise HTTPException(404, 'Unknown customer or business.')
    text = body.text.strip()
    if not text and body.attachment is None:
        raise HTTPException(400, 'Type a message.')
    wamid = meta.new_wamid()
    attachment = None
    if body.attachment is not None:
        attachment = media.add(wamid, **body.attachment.model_dump())
    message = db.add_message(wamid, customer['wa_id'], business['phone_number_id'], from_customer=True, text=text, status='sending')
    payload = meta.webhook_payload(business, customer['wa_id'], customer['name'], wamid, text, attachment=attachment)
    try:
        meta.send_to_webhook(business, payload)
    except meta.WebhookError as exc:
        return with_media(db.set_status(message['id'], 'failed', str(exc)))
    return with_media(db.set_status(message['id'], 'sent'))


@router.post('/api/reset', summary='Delete every message (the customers stay)')
def reset() -> dict:
    db.reset()
    media.clear()
    return {'reset': True}
