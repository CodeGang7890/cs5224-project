"""The outbox: sending the WhatsApp replies saved with the chat (chat_app.OutboundMessage).

A reply is saved as `pending` in the same transaction as the chat (app/inbound.py), so it can't be
lost: if sending fails, or the worker dies before sending, it's still there to send. send_due()
sends what's due through configuration-service's internal send endpoint (app/whatsapp_sender.py):
- one message at a time, each in its own transaction with its row locked (`FOR UPDATE SKIP
  LOCKED`): workers sending at the same time never send the same message;
- in order within a chat: a message waits while an earlier one of its chat is still pending (being
  retried); once that one is `failed`, the next ones go;
- sent → `sent`, with Meta's message id; a failure → attempts + 1 and retried after
  OUTBOX_RETRY_DELAYS_SECONDS, then `failed` after OUTBOX_ATTEMPTS_MAX attempts (logged as an error);
  a permanent refusal (configuration-service's 4xx, e.g. 404: the business isn't connected any
  more; see SendError.permanent) → `failed` at once, so it doesn't hold back the rest of the chat.

It runs right after a turn (for that chat) and from the consumer's sweeper (every chat). Sending is
at least once: a worker dying after Meta accepted a message but before saving `sent`, or a send that
timed out after reaching Meta, sends it again.
The row stays locked while it's sent (at most WHATSAPP_SEND_TIMEOUT_SECONDS).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased, sessionmaker

from . import config, latency, whatsapp_sender
from .chat_flow import dates
from .models import ChatSession, OutboundMessage

logger = logging.getLogger(__name__)

PENDING, SENT, FAILED = 'pending', 'sent', 'failed'  # chat_app.OutboundMessageStatus
LAST_ERROR_MAX_LENGTH = 1000
META_MESSAGE_ID_MAX_LENGTH = 255  # chat_app.models.WHATSAPP_MESSAGE_ID_MAX_LENGTH


@dataclass
class SendRound:
    """What one send_due() call did."""

    sent: int = 0
    retrying: int = 0  # failed this time; to retry later
    failed: int = 0  # failed for the last time: given up


def retry_delay(attempts: int) -> timedelta:
    """How long to wait after the `attempts`-th failed attempt."""
    delays = config.OUTBOX_RETRY_DELAYS_SECONDS
    return timedelta(seconds=delays[min(attempts, len(delays)) - 1])


def due_query(now: datetime, chat_session_id: int | None = None):
    """The next message to send: pending, due, and with no earlier pending message in its chat."""
    earlier = aliased(OutboundMessage)
    query = (
        select(OutboundMessage)
        .where(OutboundMessage.status == PENDING, OutboundMessage.next_attempt_time <= now)
        .where(~exists().where(
            earlier.chat_session_id == OutboundMessage.chat_session_id,
            earlier.status == PENDING,
            earlier.id < OutboundMessage.id,
        ))
        .order_by(OutboundMessage.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if chat_session_id is not None:
        query = query.where(OutboundMessage.chat_session_id == chat_session_id)
    return query


def send_due(sessions: sessionmaker, chat_session_id: int | None = None, now: datetime | None = None) -> SendRound:
    """Sends the messages due (only `chat_session_id`'s, if given), oldest first. See the module docstring."""
    now = now or dates.now()
    done = SendRound()
    for _ in range(config.OUTBOX_BATCH_MAX):
        if not _send_next(sessions, chat_session_id, now, done):
            break
    return done


def _send_next(sessions: sessionmaker, chat_session_id: int | None, now: datetime, done: SendRound) -> bool:
    """Sends one due message (False: none is due), and records how it went."""
    with sessions.begin() as db:
        item = db.scalars(due_query(now, chat_session_id)).first()
        if item is None:
            return False
        to = db.get(ChatSession, item.chat_session_id).phone_number
        try:
            with latency.timed('SEND', outbox=item.id, attempt=item.attempts + 1):
                meta_message_id = whatsapp_sender.send_text(item.business_id, to, item.text)
        except Exception as exc:  # a SendError, or anything unexpected: never retried forever
            if not isinstance(exc, whatsapp_sender.SendError):
                logger.exception('Sending outbox message %s failed unexpectedly', item.id)
            item.attempts += 1
            item.last_error = str(exc)[:LAST_ERROR_MAX_LENGTH]
            permanent = isinstance(exc, whatsapp_sender.SendError) and exc.permanent
            if permanent or item.attempts >= config.OUTBOX_ATTEMPTS_MAX:
                item.status = FAILED
                done.failed += 1
                logger.error(
                    'Reply %s in chat %s not sent to %s after %d attempt(s), given up%s: %s',
                    item.id, item.chat_session_id, to, item.attempts, ' (refused: no retry)' if permanent else '', exc,
                )
            else:
                # From the current time, not the round's (a round's sends can take a while).
                item.next_attempt_time = dates.now() + retry_delay(item.attempts)
                done.retrying += 1
                logger.warning(
                    'Reply %s in chat %s not sent to %s (attempt %d of %d), retrying at %s: %s',
                    item.id, item.chat_session_id, to, item.attempts, config.OUTBOX_ATTEMPTS_MAX,
                    item.next_attempt_time.isoformat(), exc,
                )
        else:
            # Cut to the column's length: a save failing after Meta accepted it would send it again.
            item.status, item.sent_time, item.meta_message_id = SENT, dates.now(), str(meta_message_id)[:META_MESSAGE_ID_MAX_LENGTH]
            item.attempts += 1
            item.last_error = ''
            done.sent += 1
            logger.info('Reply %s in chat %s sent to %s on WhatsApp (%s)', item.id, item.chat_session_id, to, meta_message_id)
    return True
