import copy
import re

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from .constants import (
    BLOCK_TYPES,
    DEFAULT_DETAIL_FIELDS,
    DETAIL_FIELD_TYPES,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_TEXT,
    DETAILS_COLLECTION_BLOCK,
    MESSAGE_SENDERS,
    SEND_MESSAGE_BLOCK,
    START_BLOCK,
)

BLOCK_FIELDS = {'id', 'next_block_id', 'block_type', 'position_x', 'position_y'}
# Extra block keys, and the block type each is allowed on. `message` is required on its type.
OPTIONAL_BLOCK_FIELDS = {'fields': DETAILS_COLLECTION_BLOCK, 'message': SEND_MESSAGE_BLOCK}

# --- DETAILS_COLLECTION_BLOCK `fields`: the customer details it asks for --------------------
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
    DETAIL_TYPE_TEXT: {'description', 'max_length'},
    DETAIL_TYPE_NUMBER: {'description', 'min_value', 'max_value'},
}
DETAIL_FIELD_OPTIONAL_KEYS_DEFAULT = {'description'}  # email, phone


def block_detail_fields(block: dict) -> list[dict]:
    """The customer details a DETAILS_COLLECTION_BLOCK asks for: its `fields`, or the defaults."""
    return block.get('fields') or copy.deepcopy(DEFAULT_DETAIL_FIELDS)


def _is_number(value) -> bool:
    # bool is a subclass of int, but True/False aren't valid coordinates.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_valid_block_id(value) -> bool:
    """Block IDs can be any int or non-blank string (e.g. a UUID)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and value.strip() != '')


def validate_chat_config(value) -> None:
    """Validate a ChatConfiguration.config_json: a list of flow blocks.

    Each block is ``{id, next_block_id, block_type, position_x, position_y}``, plus an optional
    ``fields`` on a DETAILS_COLLECTION_BLOCK (see ``_detail_field_errors``) and a required
    ``message`` on a SEND_MESSAGE_BLOCK (a non-blank string of at most CHAT_MESSAGE_MAX_LENGTH
    characters: what it sends the customer). Rules:
    - ``id`` is an int or non-blank string (e.g. a UUID), unique across blocks.
    - ``next_block_id`` is null or the ``id`` of another block in the list.
    - ``block_type`` is one of ``BLOCK_TYPES``; there must be exactly one ``START_BLOCK``.
    - ``position_x`` / ``position_y`` are numbers.

    Raises a ``ValidationError`` listing every problem found.
    """
    if not isinstance(value, list):
        raise ValidationError('Chat configuration must be a list of blocks.')

    errors = []
    ids = set()
    blocks = []  # (index, block) pairs that passed the per-block checks
    for index, block in enumerate(value):
        prefix = f'Block {index}'
        if not isinstance(block, dict):
            errors.append(f'{prefix}: must be an object.')
            continue
        missing = BLOCK_FIELDS - block.keys()
        unknown = block.keys() - BLOCK_FIELDS - OPTIONAL_BLOCK_FIELDS.keys()
        if missing:
            errors.append(f'{prefix}: missing field(s) {", ".join(sorted(missing))}.')
        if unknown:
            errors.append(f'{prefix}: unknown field(s) {", ".join(sorted(unknown))}.')
        if missing:
            continue
        for key, allowed_type in OPTIONAL_BLOCK_FIELDS.items():
            if key in block and block['block_type'] != allowed_type:
                errors.append(f'{prefix}: {key} is only allowed on a {allowed_type}.')
        if 'fields' in block and block['block_type'] == DETAILS_COLLECTION_BLOCK:
            errors.extend(_detail_field_errors(block['fields'], prefix))
        if block['block_type'] == SEND_MESSAGE_BLOCK:
            message = block.get('message')
            if not isinstance(message, str) or not message.strip():
                errors.append(f'{prefix}: a {SEND_MESSAGE_BLOCK} needs a non-blank message.')
            elif len(message) > CHAT_MESSAGE_MAX_LENGTH:
                errors.append(f'{prefix}: message must be at most {CHAT_MESSAGE_MAX_LENGTH} characters.')

        block_id = block['id']
        if not is_valid_block_id(block_id):
            errors.append(f'{prefix}: id must be an integer or a non-blank string.')
        elif block_id in ids:
            errors.append(f'{prefix}: duplicate id {block_id!r}.')
        else:
            ids.add(block_id)

        next_id = block['next_block_id']
        if next_id is not None and not is_valid_block_id(next_id):
            errors.append(f'{prefix}: next_block_id must be null, an integer or a non-blank string.')

        if block['block_type'] not in BLOCK_TYPES:
            errors.append(
                f'{prefix}: block_type must be one of {", ".join(BLOCK_TYPES)} '
                f'(got {block["block_type"]!r}).'
            )
        for field in ('position_x', 'position_y'):
            if not _is_number(block[field]):
                errors.append(f'{prefix}: {field} must be a number.')
        blocks.append((index, block))

    # Checked after the loop, so next_block_id can point at a block further down the list.
    for index, block in blocks:
        next_id = block['next_block_id']
        if next_id is None or not is_valid_block_id(next_id):
            continue
        if next_id == block['id']:
            errors.append(f'Block {index}: next_block_id must not point at the block itself.')
        elif next_id not in ids:
            errors.append(f'Block {index}: next_block_id {next_id!r} does not match any block id.')

    start_count = sum(1 for _, block in blocks if block['block_type'] == START_BLOCK)
    if start_count != 1:
        errors.append(f'There must be exactly one {START_BLOCK} (found {start_count}).')

    if errors:
        raise ValidationError(errors)


def _detail_field_errors(fields, prefix: str) -> list[str]:
    """Errors in a DETAILS_COLLECTION_BLOCK's `fields`: the customer details it asks for.

    A list of 1 to DETAIL_FIELDS_MAX fields, each ``{key, label, type}`` plus optional keys:
    - ``key``: lowercase letters, digits and underscores, starting with a letter (e.g.
      ``postal_code``), unique in the block. It's the key in chat_state_data['details'].
    - ``label``: non-blank, what the customer is asked for (e.g. "Postal code").
    - ``type``: one of DETAIL_FIELD_TYPES.
    - ``description`` (any type): a hint for the assistant, e.g. "6 digits".
    - ``max_length`` (text only): 1 to DETAIL_TEXT_MAX_LENGTH.
    - ``min_value`` / ``max_value`` (number only): numbers, min ≤ max.
    """
    if not isinstance(fields, list):
        return [f'{prefix}: fields must be a list.']
    if not 1 <= len(fields) <= DETAIL_FIELDS_MAX:
        return [f'{prefix}: fields must have between 1 and {DETAIL_FIELDS_MAX} items.']

    errors = []
    keys = set()
    for index, item in enumerate(fields):
        where = f'{prefix}, field {index}'
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

STATE_DATA_FIELDS = {'items', 'items_confirmed', 'details', 'completed', 'order_id'}
STATE_ITEM_FIELDS = {'product_id', 'name', 'unit_price', 'quantity'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
    - ``completed``: true once the customer confirmed and the flow reached its last block.
    - ``order_id``: the checkout_app OrderItem placed when the customer confirmed.

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

    for flag in ('items_confirmed', 'completed'):
        if not isinstance(value.get(flag, False), bool):
            errors.append(f'{flag} must be true or false.')
    if 'order_id' in value and (not _is_int(value['order_id']) or value['order_id'] < 1):
        errors.append('order_id must be a positive integer.')

    if errors:
        raise ValidationError(errors)
