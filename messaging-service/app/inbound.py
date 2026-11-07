"""A customer's WhatsApp message, from the Pub/Sub topic `whatsapp-inbound-messages` (published by
messaging-ingester; the consumer is app/consumer.py), answered by the chat flow: the same flow as
the Chat Sandbox and POST /api/chat/sessions/messages/ (app/chat_flow/flow.py).

handle_inbound(sessions, payload) for one message:
1. Only for a business that exists. A message that isn't text (a photo, document, voice message,
   …) isn't read for now: answer_unsupported() saves it in the chat as a placeholder (e.g.
   "[Photo]") with a short reply asking for text (UNSUPPORTED_REPLY), in one transaction with its
   InboundMessage (`replied`) and the outbox, then sends it (steps 3 and 5, without the chat flow).
   Every type that isn't text gets it (the user asked), reactions and system notices too.
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
4. The chat flow runs (router, order / booking steps, FAQ, order status, the reply). The
   transaction saving its messages also marks the row `replied` and puts every message of the
   turn (a welcome message, the reply) in the outbox (chat_app.OutboundMessage, `pending`), so a
   reply can't be lost. If another worker answered the same message meanwhile (a duplicate), that
   save is rolled back and nothing is sent (unless this turn placed an order or booking: its
   confirmation is kept).
   Messages sent close together get one reply (the user asked): a turn answers every customer
   message in the chat since the business's last one (the subscription has no message ordering, so
   a customer's messages are handled in parallel, each saved as it arrives, in the order they were
   sent: flow.add_message with Meta's timestamp). So that save marks
   every `received` InboundMessage of the chat `replied`, not only this one: the chat's version
   check means the turn saw them all (one saved after the turn read the chat makes it run again,
   with it). A turn whose message is `replied` by then stops before its next attempt
   (stop_if_answered), without an LLM call.
5. The outbox sends them (app/outbox.py, through configuration-service's internal send endpoint,
   which holds the access token), in order. A failed send stays `pending` and is retried by the
   consumer's sweeper with a backoff, then marked `failed`; the turn never runs again for it.

An LLM failure (or any error) is raised: the consumer nacks the message, so Pub/Sub redelivers it.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import latency, outbox
from .chat_flow import dates, flow
from .chat_flow.constants import (
    SENT_BY_BUSINESS_AUTOMATED,
    SENT_BY_CUSTOMER,
    STEP_START,
    UNSUPPORTED_LABELS,
    UNSUPPORTED_REPLY,
)
from .chat_flow.validators import CHAT_MESSAGE_MAX_LENGTH
from .models import BusinessConfiguration, ChatSession, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

RECEIVED, REPLIED = 'received', 'replied'  # chat_app.InboundMessageStatus
DISPLAY_NAME_MAX_LENGTH = 150  # chat_app.models



class AlreadyReplied(Exception):
    """The message was answered by another worker while this one was working on it."""


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


def unsupported_placeholder(message_type: str) -> str:
    """What the chat shows for a message that isn't text, e.g. "[Photo]"."""
    return f'[{UNSUPPORTED_LABELS.get(message_type, "Message")}]'


def queue_reply(db: Session, session: ChatSession, record: InboundMessage, text: str, now) -> None:
    """Puts a message for the customer in the outbox (to send once the transaction commits)."""
    db.add(OutboundMessage(
        business_id=session.business_id, chat_session_id=session.id, inbound_message_id=record.id,
        text=text, status=outbox.PENDING, attempts=0, next_attempt_time=now,
        last_error='', meta_message_id='', created_time=now, sent_time=None,
    ))
    db.flush()  # one at a time: ids in the order they're sent


def send_replies(sessions: sessionmaker, session_id: int) -> None:
    """Sends the chat's queued replies. A failed send stays in the outbox, retried by the consumer's
    sweeper; so does everything if sending can't even start (e.g. the database just went away): the
    message was answered, so it isn't nacked."""
    try:
        outbox.send_due(sessions, chat_session_id=session_id)
    except Exception:
        logger.exception('Sending the replies in chat %s failed; the sweeper will retry', session_id)


def answer_unsupported(sessions: sessionmaker, payload: dict) -> InboundResult:
    """A message that isn't text: saved in the chat as a placeholder, answered with UNSUPPORTED_REPLY
    (see the module docstring). One transaction, so a redelivery finds it `replied` and skips it."""
    message_id, message_type = payload['message_id'], str(payload.get('type'))
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
            now = dates.now()
            if record is None:
                flow.add_message(session, unsupported_placeholder(message_type), SENT_BY_CUSTOMER, sent_time(payload))
                record = InboundMessage(
                    business_id=business.id, chat_session_id=session.id, message_id=message_id, status=REPLIED,
                    received_time=now, replied_time=now,
                )
                db.add(record)
                db.flush()
            else:
                record.status, record.replied_time = REPLIED, now
            flow.add_message(session, UNSUPPORTED_REPLY, SENT_BY_BUSINESS_AUTOMATED)
            queue_reply(db, session, record, UNSUPPORTED_REPLY, now)
            session_id = session.id
    except IntegrityError:
        # The same message was claimed by another worker at the same moment: it answers it.
        return InboundResult('skipped', 'being answered by another worker (a duplicate)')
    latency.add_fields(chat=session_id)
    send_replies(sessions, session_id)
    return InboundResult('replied', f'not a text message ({message_type})', session_id, UNSUPPORTED_REPLY)


def sent_time(payload: dict) -> datetime | None:
    """When the customer sent the message (Meta's timestamp, from the ingester), if it's valid."""
    moment = dates.parse_datetime(payload.get('timestamp'))
    return moment if moment is not None and dates.is_aware(moment) else None


def handle_inbound(sessions: sessionmaker, payload: dict) -> InboundResult:
    """Answers one inbound WhatsApp message (see the module docstring)."""
    message_id = payload['message_id']
    if payload.get('type') != 'text':
        return answer_unsupported(sessions, payload)
    text = payload.get('text') if isinstance(payload.get('text'), str) else ''
    text = text.strip()[:CHAT_MESSAGE_MAX_LENGTH]
    if not text:
        return InboundResult('skipped', 'an empty text message')

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
                flow.append_in_transaction(db, session.id, text, SENT_BY_CUSTOMER, sent_time(payload))
                db.add(InboundMessage(
                    business_id=business.id, chat_session_id=session.id, message_id=message_id, status=RECEIVED,
                    received_time=dates.now(), replied_time=None,
                ))
            session_id = session.id
    except IntegrityError:
        # The same message was claimed by another worker at the same moment: it answers it.
        return InboundResult('skipped', 'being answered by another worker (a duplicate)')

    latency.add_fields(chat=session_id)

    def stop_if_answered() -> None:
        """Before each attempt at the turn: stops it if its message was answered meanwhile (by a
        turn for a later message of the same chat, which saw this one too, or a duplicate's)."""
        with sessions() as db:
            status = db.scalar(select(InboundMessage.status).where(InboundMessage.message_id == message_id))
        if status == REPLIED:
            raise AlreadyReplied(message_id)

    def mark_replied_and_queue(db, session: ChatSession, messages: list[dict], placed: bool, saw_all: bool) -> None:
        """In the transaction saving the turn's messages (the chat row locked): every InboundMessage
        of the chat still `received` replied, as the turn saw them all (the module docstring, step 4),
        and every message of the turn in the outbox, to send. Not if the chat changed after the turn
        read it (`saw_all` false: a turn that placed an order / booking saves anyway): then a message
        that came in meanwhile wasn't seen, so only this one is replied, and the others get their
        own turns."""
        record = db.scalars(
            select(InboundMessage).where(InboundMessage.message_id == message_id).with_for_update()
        ).one()
        if record.status == REPLIED:
            if not placed:
                # Another worker answered this message while this one was working on it: keep its
                # reply only (rolls this save back).
                raise AlreadyReplied(message_id)
            # This turn placed an order / booking (saved already): its confirmation (and payment
            # link) must still go out, even though the message was answered meanwhile.
            logger.warning('Message %s was answered meanwhile; sending this turn\'s confirmation too', message_id)
        now = dates.now()
        if saw_all:
            answered = db.scalars(
                select(InboundMessage).where(
                    InboundMessage.chat_session_id == session.id, InboundMessage.status == RECEIVED,
                ).order_by(InboundMessage.id).with_for_update()
            ).all()  # this one too, unless it's `replied` already
        else:
            answered = [record] if record.status == RECEIVED else []
        for item in answered:
            item.status, item.replied_time = REPLIED, now
        if len(answered) > 1:
            logger.info('One reply for %d messages in chat %s (sent close together)', len(answered), session.id)
        for chat_message in messages:
            queue_reply(db, session, record, chat_message['message'], now)

    try:
        result = flow.handle_customer_message(
            sessions, session_id, text, save_message=False, on_saved=mark_replied_and_queue,
            before_attempt=stop_if_answered,
        )
    except AlreadyReplied:
        return InboundResult('skipped', 'answered meanwhile (with another message, or a duplicate)', session_id)
    send_replies(sessions, session_id)  # saved: now send
    return InboundResult('replied', chat_session_id=session_id, reply=result.reply['message'])
