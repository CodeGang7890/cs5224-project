import copy
import re

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from .constants import (
    DEFAULT_DETAIL_FIELDS,
    DETAIL_FIELD_TYPES,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_TEXT,
    MESSAGE_SENDERS,
    WELCOME_MESSAGE_MAX_LENGTH,
    WELCOME_PLACEHOLDERS,
)

# --- ChatConfiguration.detail_fields: the customer details the Details collection step asks for
DETAIL_FIELDS_MAX = 20
DETAIL_KEY_MAX_LENGTH = 40
DETAIL_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')  # e.g. postal_code
DETAIL_LABEL_MAX_LENGTH = 100
DETAIL_DESCRIPTION_MAX_LENGTH = 300
DETAIL_TEXT_MAX_LENGTH = 2000  # the most a text field's max_length can be
DETAIL_TEXT_DEFAULT_MAX_LENGTH = 500  # when a text field has no max_length
DETAIL_FIELD_KEYS = {'key', 'label', 'type'}
# Optional keys of a field, by type.
DETAIL_FIELD_OPTIONAL_KEYS = {
    DETAIL_TYPE_TEXT: {'description', 'required', 'max_length'},
    DETAIL_TYPE_NUMBER: {'description', 'required', 'min_value', 'max_value'},
}
DETAIL_FIELD_OPTIONAL_KEYS_DEFAULT = {'description', 'required'}  # email, phone


def is_required_detail(detail_field: dict) -> bool:
    """Whether the chat must get this detail before moving on (`required`, true when missing)."""
    return detail_field.get('required', True) is not False


def default_detail_fields() -> list[dict]:
    """ChatConfiguration.detail_fields' default: name and email (a fresh copy each time)."""
    return copy.deepcopy(DEFAULT_DETAIL_FIELDS)


def _is_number(value) -> bool:
    # bool is a subclass of int, but True/False aren't valid numbers here.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_chat_config(value) -> None:
    """Legacy: validated ChatConfiguration.config_json, the user-built block graph that migration
    0007 replaced with the fixed flow + detail_fields. Kept only because migration 0001 refers to it."""


def validate_detail_fields(value) -> None:
    """Validate a ChatConfiguration.detail_fields: the customer details the Details collection step
    asks for (see ``detail_field_errors``). Raises a ``ValidationError`` listing every problem."""
    errors = detail_field_errors(value)
    if errors:
        raise ValidationError(errors)


def detail_field_errors(fields) -> list[str]:
    """Errors in a list of detail fields.

    A list of 1 to DETAIL_FIELDS_MAX fields, each ``{key, label, type}`` plus optional keys:
    - ``key``: lowercase letters, digits and underscores, starting with a letter (e.g.
      ``postal_code``), unique. It's the key in chat_state_data['details'].
    - ``label``: non-blank, what the customer is asked for (e.g. "Postal code").
    - ``type``: one of DETAIL_FIELD_TYPES.
    - ``description`` (any type): a hint for the assistant, e.g. "6 digits".
    - ``required`` (any type): false for an optional detail (asked for, but not needed to move on).
      Missing means true. At least one field must be required.
    - ``max_length`` (text only): 1 to DETAIL_TEXT_MAX_LENGTH.
    - ``min_value`` / ``max_value`` (number only): numbers, min ≤ max.
    """
    if not isinstance(fields, list):
        return ['Details must be a list.']
    if not 1 <= len(fields) <= DETAIL_FIELDS_MAX:
        return [f'There must be between 1 and {DETAIL_FIELDS_MAX} details.']

    errors = []
    keys = set()
    for index, item in enumerate(fields):
        where = f'Detail {index}'
        if not isinstance(item, dict):
            errors.append(f'{where}: must be an object.')
            continue
        missing = DETAIL_FIELD_KEYS - item.keys()
        if missing:
            errors.append(f'{where}: missing {", ".join(sorted(missing))}.')
            continue

        key, label, field_type = item['key'], item['label'], item['type']
        if not isinstance(key, str) or not DETAIL_KEY_PATTERN.match(key) or len(key) > DETAIL_KEY_MAX_LENGTH:
            errors.append(
                f'{where}: key must be lowercase letters, digits and underscores, starting with a '
                f'letter (max {DETAIL_KEY_MAX_LENGTH} characters).'
            )
        elif key in keys:
            errors.append(f'{where}: duplicate key {key!r}.')
        else:
            keys.add(key)
        if not isinstance(label, str) or not label.strip() or len(label) > DETAIL_LABEL_MAX_LENGTH:
            errors.append(
                f'{where}: label must be a non-blank string of at most {DETAIL_LABEL_MAX_LENGTH} characters.'
            )
        if field_type not in DETAIL_FIELD_TYPES:
            errors.append(
                f'{where}: type must be one of {", ".join(DETAIL_FIELD_TYPES)} (got {field_type!r}).'
            )
            continue

        allowed = DETAIL_FIELD_OPTIONAL_KEYS.get(field_type, DETAIL_FIELD_OPTIONAL_KEYS_DEFAULT)
        unknown = item.keys() - DETAIL_FIELD_KEYS - allowed
        if unknown:
            errors.append(f'{where}: {", ".join(sorted(unknown))} not allowed for type {field_type}.')
        description = item.get('description')
        if description is not None and (
            not isinstance(description, str) or len(description) > DETAIL_DESCRIPTION_MAX_LENGTH
        ):
            errors.append(
                f'{where}: description must be a string of at most {DETAIL_DESCRIPTION_MAX_LENGTH} characters.'
            )
        if 'max_length' in item and 'max_length' in allowed:
            max_length = item['max_length']
            if not _is_int(max_length) or not 1 <= max_length <= DETAIL_TEXT_MAX_LENGTH:
                errors.append(f'{where}: max_length must be an integer from 1 to {DETAIL_TEXT_MAX_LENGTH}.')
        bounds = [item[k] for k in ('min_value', 'max_value') if k in item and k in allowed]
        if any(not _is_number(bound) for bound in bounds):
            errors.append(f'{where}: min_value and max_value must be numbers.')
        elif len(bounds) == 2 and bounds[0] > bounds[1]:
            errors.append(f'{where}: min_value must not be greater than max_value.')
        if 'required' in item and not isinstance(item['required'], bool):
            errors.append(f'{where}: required must be true or false.')
    # Otherwise Details collection would complete as soon as the chat reaches it, before asking anything.
    if not any(isinstance(item, dict) and is_required_detail(item) for item in fields):
        errors.append('At least one detail must be required.')
    return errors


# --- ChatSession.chat_message_json --------------------------------------------------------

MESSAGE_FIELDS = {'message', 'sent_by', 'message_time'}
CHAT_MESSAGE_MAX_LENGTH = 4096  # WhatsApp's limit for a text message


def validate_chat_messages(value) -> None:
    """Validate a ChatSession.chat_message_json: the conversation, oldest message first.

    Each message is ``{message, sent_by, message_time}``. Rules:
    - ``message`` is a non-blank string of at most ``CHAT_MESSAGE_MAX_LENGTH`` characters.
    - ``sent_by`` is one of ``MESSAGE_SENDERS``.
    - ``message_time`` is an ISO 8601 date-time string with a timezone
      (e.g. ``2026-09-01T09:15:00+08:00``), and messages are in chronological order.
    An empty list (no messages yet) is valid.

    Raises a ``ValidationError`` listing every problem found.
    """
    if not isinstance(value, list):
        raise ValidationError('Chat messages must be a list.')

    errors = []
    previous_time = None
    for index, item in enumerate(value):
        prefix = f'Message {index}'
        if not isinstance(item, dict):
            errors.append(f'{prefix}: must be an object.')
            continue
        missing = MESSAGE_FIELDS - item.keys()
        unknown = item.keys() - MESSAGE_FIELDS
        if missing:
            errors.append(f'{prefix}: missing field(s) {", ".join(sorted(missing))}.')
        if unknown:
            errors.append(f'{prefix}: unknown field(s) {", ".join(sorted(unknown))}.')
        if missing:
            continue

        message = item['message']
        if not isinstance(message, str) or not message.strip():
            errors.append(f'{prefix}: message must be a non-blank string.')
        elif len(message) > CHAT_MESSAGE_MAX_LENGTH:
            errors.append(f'{prefix}: message must be at most {CHAT_MESSAGE_MAX_LENGTH} characters.')

        if item['sent_by'] not in MESSAGE_SENDERS:
            errors.append(
                f'{prefix}: sent_by must be one of {", ".join(MESSAGE_SENDERS)} (got {item["sent_by"]!r}).'
            )

        raw_time = item['message_time']
        try:
            message_time = parse_datetime(raw_time) if isinstance(raw_time, str) else None
        except ValueError:  # well-formed but impossible, e.g. month 13
            message_time = None
        if message_time is None:
            errors.append(f'{prefix}: message_time must be an ISO 8601 date-time string.')
        elif not is_aware(message_time):
            errors.append(f'{prefix}: message_time must include a timezone (e.g. "Z" or "+08:00").')
        else:
            if previous_time is not None and message_time < previous_time:
                errors.append(f'{prefix}: message_time is earlier than the previous message.')
            previous_time = message_time

    if errors:
        raise ValidationError(errors)


# --- ChatSession.chat_state_data ----------------------------------------------------------

STATE_DATA_FIELDS = {
    'items', 'items_confirmed', 'details', 'last_order_id',
    'service', 'slot', 'slot_options', 'last_booking_id', 'history_start',
}
STATE_SERVICE_FIELDS = {'service_id', 'name', 'price', 'duration_minutes', 'buffer_minutes'}
SLOT_OPTIONS_MAX = 10
STATE_ITEM_FIELDS = {'product_id', 'name', 'unit_price', 'quantity'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_aware_datetime(value) -> bool:
    try:
        moment = parse_datetime(value) if isinstance(value, str) else None
    except ValueError:
        return False
    return moment is not None and is_aware(moment)


def validate_chat_state_data(value) -> None:
    """Validate a ChatSession.chat_state_data: what the chat flow has collected so far.

    Every key is optional (an empty object means nothing collected yet):
    - ``items``: the products the customer chose, each ``{product_id, name, unit_price, quantity}``
      (``name`` / ``unit_price`` are a snapshot taken when chosen; ``unit_price`` is a decimal string
      like ``"5.50"``; ``quantity`` is at least 1).
    - ``items_confirmed``: true once the customer said the items are everything they want (cleared
      when the items change).
    - ``details``: the collected customer details, by field key (e.g. ``{"name": "Alice",
      "postal_code": 123456}``): non-blank strings or numbers.
    - ``last_order_id``: the checkout_app OrderItem placed by the last order confirmed in this chat
      (once placed, the chat goes back to the start, keeping only this and ``last_booking_id``).
    - ``service``: the service chosen for a booking, ``{service_id, name, price, duration_minutes,
      buffer_minutes}`` (a snapshot; ``price`` a decimal string).
    - ``slot``: the start time chosen for it, an ISO 8601 date-time with a timezone.
    - ``slot_options``: the start times offered to the customer, numbered from 1 in this order
      (ISO 8601 date-times, at most SLOT_OPTIONS_MAX).
    - ``last_booking_id``: the checkout_app ScheduleItem booked last in this chat.
    - ``history_start``: set when the customer cancels an order or booking: the index in
      chat_message_json of the message that cancelled it. The order / booking steps' extractions
      only read from there on, so a cancelled cart can't come back. Dropped when one is placed.

    Raises a ``ValidationError`` listing every problem found.
    """
    if not isinstance(value, dict):
        raise ValidationError('Chat state data must be an object.')

    errors = []
    unknown = value.keys() - STATE_DATA_FIELDS
    if unknown:
        errors.append(f'Unknown field(s) {", ".join(sorted(unknown))}.')

    items = value.get('items', [])
    if not isinstance(items, list):
        errors.append('items must be a list.')
        items = []
    for index, item in enumerate(items):
        prefix = f'Item {index}'
        if not isinstance(item, dict) or item.keys() != STATE_ITEM_FIELDS:
            errors.append(f'{prefix}: must be an object with exactly {", ".join(sorted(STATE_ITEM_FIELDS))}.')
            continue
        if not _is_int(item['product_id']):
            errors.append(f'{prefix}: product_id must be an integer.')
        if not isinstance(item['name'], str) or not item['name'].strip():
            errors.append(f'{prefix}: name must be a non-blank string.')
        if not isinstance(item['unit_price'], str):
            errors.append(f'{prefix}: unit_price must be a decimal string, e.g. "5.50".')
        if not _is_int(item['quantity']) or item['quantity'] < 1:
            errors.append(f'{prefix}: quantity must be an integer of at least 1.')

    details = value.get('details', {})
    if not isinstance(details, dict):
        errors.append('details must be an object.')
    else:
        for key, detail in details.items():
            if not DETAIL_KEY_PATTERN.match(key):
                errors.append(f'details: invalid key {key!r}.')
            elif not (_is_number(detail) or (isinstance(detail, str) and detail.strip())):
                errors.append(f'details: {key} must be a non-blank string or a number.')

    if not isinstance(value.get('items_confirmed', False), bool):
        errors.append('items_confirmed must be true or false.')
    for key in ('last_order_id', 'last_booking_id'):
        if key in value and (not _is_int(value[key]) or value[key] < 1):
            errors.append(f'{key} must be a positive integer.')
    if 'history_start' in value and (not _is_int(value['history_start']) or value['history_start'] < 0):
        errors.append('history_start must be a non-negative integer.')

    if 'service' in value:
        service = value['service']
        if not isinstance(service, dict) or service.keys() != STATE_SERVICE_FIELDS:
            errors.append(f'service must be an object with exactly {", ".join(sorted(STATE_SERVICE_FIELDS))}.')
        elif not (
            _is_int(service['service_id']) and isinstance(service['name'], str) and service['name'].strip()
            and isinstance(service['price'], str) and _is_int(service['duration_minutes'])
            and service['duration_minutes'] > 0 and _is_int(service['buffer_minutes']) and service['buffer_minutes'] >= 0
        ):
            errors.append('service: invalid service_id, name, price, duration_minutes or buffer_minutes.')
    if 'slot' in value and not _is_aware_datetime(value['slot']):
        errors.append('slot must be an ISO 8601 date-time with a timezone.')
    if 'slot_options' in value:
        options = value['slot_options']
        if not isinstance(options, list) or len(options) > SLOT_OPTIONS_MAX:
            errors.append(f'slot_options must be a list of at most {SLOT_OPTIONS_MAX} date-times.')
        elif not all(_is_aware_datetime(option) for option in options):
            errors.append('slot_options must be ISO 8601 date-times with a timezone.')

    if errors:
        raise ValidationError(errors)


# --- Welcome message (ChatConfiguration.welcome_message) ----------------------------------

_BRACES = re.compile(r'\{[^{}]*\}|[{}]')


def validate_welcome_message(value: str) -> None:
    """At most WELCOME_MESSAGE_MAX_LENGTH characters (the model field checks too), and no braces
    except the placeholders in WELCOME_PLACEHOLDERS (e.g. {business_name})."""
    if not isinstance(value, str):
        raise ValidationError('The welcome message must be text.')
    if len(value) > WELCOME_MESSAGE_MAX_LENGTH:
        raise ValidationError(f'The welcome message must be at most {WELCOME_MESSAGE_MAX_LENGTH} characters.')
    unknown = sorted({match for match in _BRACES.findall(value) if match not in WELCOME_PLACEHOLDERS})
    if unknown:
        raise ValidationError(
            f'Unknown placeholder {", ".join(unknown)}: the only one you can use is '
            f'{" or ".join(WELCOME_PLACEHOLDERS)} (no other curly braces).'
        )
