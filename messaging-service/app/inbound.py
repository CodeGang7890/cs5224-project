"""A customer's WhatsApp message, from the Pub/Sub topic `whatsapp-inbound-messages` (published by
messaging-ingester; the consumer is app/consumer.py), answered by the chat flow: the same flow as
the Chat Sandbox and POST /api/chat/sessions/messages/ (app/chat_flow/flow.py).

handle_inbound(sessions, payload) for one message:
1. Only text messages are answered (images, audio, … are skipped for now), and only for a
   business that exists.
2. The customer's chat: the business's real (not sandbox) ChatSession with that phone number, or a
   new one (as configuration-service creates them: at `start`, no messages; the WhatsApp profile
   name as its display_name).
3. One transaction, with the chat row locked: an InboundMessage row for Meta's message id
   (chat_app.InboundMessage, the schema is configuration-service's) is created together with the
   customer message in the chat, so they can't disagree:
   - already `replied`: a duplicate (Pub/Sub delivers at least once, Meta retries webhooks), skipped;
   - already `received`: a delivery after a failed attempt: the message is in the chat already, so
     the turn runs again without saving it twice;
   - new: saved now.
4. The chat flow runs (router, order / booking steps, FAQ, order status, the reply) and saves the
   reply; the row becomes `replied`.
5. TODO: send the reply to the customer on WhatsApp (e.g. an outbound messages queue). For now it's
   logged; it is saved in the chat either way.

An LLM failure (or any error) is raised: the consumer nacks the message, so Pub/Sub redelivers it.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .chat_flow import dates, flow
from .chat_flow.constants import SENT_BY_CUSTOMER, STEP_START
from .chat_flow.validators import CHAT_MESSAGE_MAX_LENGTH
from .models import BusinessConfiguration, ChatSession, InboundMessage

logger = logging.getLogger(__name__)

RECEIVED, REPLIED = 'received', 'replied'  # chat_app.InboundMessageStatus
DISPLAY_NAME_MAX_LENGTH = 150  # chat_app.models


@dataclass(frozen=True)
class InboundResult:
    outcome: str  # 'replied' or 'skipped'
    reason: str = ''
    chat_session_id: int | None = None
    reply: str | None = None


def customer_session(db: Session, business: BusinessConfiguration, phone_number: str, display_name: str | None) -> ChatSession:
    """The business's real chat with this customer, or a new one (locked: call inside a transaction)."""
    query = select(ChatSession).where(
        ChatSession.business_id == business.id, ChatSession.phone_number == phone_number, ChatSession.is_sandbox.is_(False)
    )
    session = db.scalars(query.with_for_update()).first()
    if session is not None:
        return session
    now = dates.now()
    try:
        with db.begin_nested():  # another worker may create it at the same time (unique per business + phone)
            session = ChatSession(
                business_id=business.id, phone_number=phone_number, is_sandbox=False,
                display_name=(display_name or '').strip()[:DISPLAY_NAME_MAX_LENGTH],
                created_time=now, last_chat_time=now, chat_message_json=[], chat_state_id=STEP_START, chat_state_data={},
            )
            db.add(session)
            db.flush()
    except IntegrityError:
        session = db.scalars(query.with_for_update()).one()
    return session


def handle_inbound(sessions: sessionmaker, payload: dict) -> InboundResult:
    """Answers one inbound WhatsApp message (see the module docstring)."""
    message_id = payload['message_id']
    text = payload.get('text') if isinstance(payload.get('text'), str) else ''
    text = text.strip()[:CHAT_MESSAGE_MAX_LENGTH]
    if payload.get('type') != 'text' or not text:
        return InboundResult('skipped', f'not a text message ({payload.get("type")})')

    try:
        with sessions.begin() as db:
            business = db.get(BusinessConfiguration, payload['business_id'])
            if business is None:
                return InboundResult('skipped', f'no business {payload["business_id"]}')
            session = customer_session(db, business, payload['from'], payload.get('display_name'))
            record = db.scalars(
                select(InboundMessage).where(InboundMessage.message_id == message_id).with_for_update()
            ).first()
            if record is not None and record.status == REPLIED:
                return InboundResult('skipped', 'already replied (a duplicate)', session.id)
            if record is None:
                flow.append_in_transaction(db, session.id, text, SENT_BY_CUSTOMER)
                db.add(InboundMessage(
                    business_id=business.id, chat_session_id=session.id, message_id=message_id, status=RECEIVED,
                    received_time=dates.now(), replied_time=None,
                ))
            session_id = session.id
    except IntegrityError:
        # The same message was claimed by another worker at the same moment: it answers it.
        return InboundResult('skipped', 'being answered by another worker (a duplicate)')

    result = flow.handle_customer_message(sessions, session_id, text, save_message=False)
    with sessions.begin() as db:
        record = db.scalars(select(InboundMessage).where(InboundMessage.message_id == message_id)).one()
        record.status, record.replied_time = REPLIED, dates.now()
    for sent in result.messages:
        # TODO: send it to the customer on WhatsApp (an outbound messages queue → the WhatsApp API).
        logger.info('TODO: send to %s on WhatsApp (chat %s): %s', payload['from'], session_id, sent['message'])
    return InboundResult('replied', chat_session_id=session_id, reply=result.reply['message'])
