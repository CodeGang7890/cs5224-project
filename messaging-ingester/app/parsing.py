"""Meta webhook payload → the messages we publish (one per customer message).

A WhatsApp Cloud API webhook looks like this (several entries/changes/messages may come at once):

    {"object": "whatsapp_business_account",
     "entry": [{"id": "<WABA ID>", "changes": [{"field": "messages", "value": {
         "metadata": {"display_phone_number": "15550001234", "phone_number_id": "1065..."},
         "contacts": [{"wa_id": "6591234567", "profile": {"name": "Alice"}}],
         "messages": [{"from": "6591234567", "id": "wamid.X", "timestamp": "1700000000",
                       "type": "text", "text": {"body": "Hi"}}],
         "statuses": [...]   # delivery/read receipts for messages we sent: ignored
     }}]}]}

The payload is only parsed after its signature was verified, but it's still read defensively:
anything with an unexpected shape is skipped, never a crash.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundMessage:
    """One customer message, as published to Pub/Sub (see `to_dict` for the JSON contract)."""

    business_id: int
    phone_number_id: str
    message_id: str  # Meta's "wamid…" id: unique, use it to drop duplicates (Meta can redeliver)
    from_number: str  # the customer, E.164 (e.g. +6591234567), like ChatSession.phone_number
    display_name: str | None  # the customer's WhatsApp profile name, if Meta sent it
    type: str  # "text", "image", "audio", "location", ...
    text: str | None  # the message text for "text" messages, otherwise None
    timestamp: str  # when the customer sent it, ISO 8601 UTC

    def to_dict(self) -> dict:
        return {
            'business_id': self.business_id,
            'phone_number_id': self.phone_number_id,
            'message_id': self.message_id,
            'from': self.from_number,
            'display_name': self.display_name,
            'type': self.type,
            'text': self.text,
            'timestamp': self.timestamp,
        }


@dataclass
class ParseResult:
    messages: list[InboundMessage] = field(default_factory=list)
    skipped: int = 0  # message items not published (another number, unexpected shape)


def to_e164(wa_id: str) -> str:
    """Meta sends numbers as digits without "+" (e.g. "6591234567")."""
    return wa_id if wa_id.startswith('+') else f'+{wa_id}'


def to_iso_timestamp(unix_seconds) -> str | None:
    try:
        return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def parse_webhook(payload, business_id: int, phone_number_id: str) -> ParseResult:
    """Extracts the customer messages sent to `phone_number_id` (the business's number).
    Changes for another number are skipped: a Meta app can serve several numbers, and only this
    business's number belongs to this business. Statuses (receipts) are ignored.

    The result contains the messages to publish and a count of skipped items.
    """
    result = ParseResult()
    for entry in _list(_dict(payload).get('entry')):
        for change in _list(_dict(entry).get('changes')):
            change = _dict(change)
            if change.get('field') != 'messages':
                continue
            value = _dict(change.get('value'))
            messages = _list(value.get('messages'))
            if not messages:
                continue  # e.g. skip statuses only
            change_number = _dict(value.get('metadata')).get('phone_number_id')
            if change_number != phone_number_id:
                logger.warning(
                    'Skipping %d message(s) for phone_number_id %r: business %s uses %r',
                    len(messages), change_number, business_id, phone_number_id,
                )
                result.skipped += len(messages)
                continue
            names = {
                _dict(contact).get('wa_id'): _dict(_dict(contact).get('profile')).get('name')
                for contact in _list(value.get('contacts'))
            }
            for item in messages:
                message = _parse_message(_dict(item), business_id, phone_number_id, names)
                if message is None:
                    logger.warning('Skipping a message with an unexpected shape for business %s', business_id)
                    result.skipped += 1
                else:
                    result.messages.append(message)
    return result


def _parse_message(item: dict, business_id: int, phone_number_id: str, names: dict) -> InboundMessage | None:
    sender, message_id, message_type = item.get('from'), item.get('id'), item.get('type')
    timestamp = to_iso_timestamp(item.get('timestamp'))
    if not all(isinstance(v, str) and v for v in (sender, message_id, message_type)) or timestamp is None:
        return None
    text = _dict(item.get('text')).get('body') if message_type == 'text' else None
    name = names.get(sender)
    return InboundMessage(
        business_id=business_id,
        phone_number_id=phone_number_id,
        message_id=message_id,
        from_number=to_e164(sender),
        display_name=name if isinstance(name, str) and name else None,
        type=message_type,
        text=text if isinstance(text, str) else None,
        timestamp=timestamp,
    )
