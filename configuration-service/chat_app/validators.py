from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from .constants import BLOCK_TYPES, MESSAGE_SENDERS, START_BLOCK

BLOCK_FIELDS = {'id', 'next_block_id', 'block_type', 'position_x', 'position_y'}


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

    Each block is ``{id, next_block_id, block_type, position_x, position_y}``. Rules:
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
        unknown = block.keys() - BLOCK_FIELDS
        if missing:
            errors.append(f'{prefix}: missing field(s) {", ".join(sorted(missing))}.')
        if unknown:
            errors.append(f'{prefix}: unknown field(s) {", ".join(sorted(unknown))}.')
        if missing:
            continue

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

STATE_DATA_FIELDS = {'items', 'details', 'completed'}
STATE_ITEM_FIELDS = {'product_id', 'name', 'unit_price', 'quantity'}
STATE_DETAIL_FIELDS = {'name', 'email'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_chat_state_data(value) -> None:
    """Validate a ChatSession.chat_state_data: what the chat flow has collected so far.

    Every key is optional (an empty object means nothing collected yet):
    - ``items``: the products the customer chose, each ``{product_id, name, unit_price, quantity}``
      (``name`` / ``unit_price`` are a snapshot taken when chosen; ``unit_price`` is a decimal string
      like ``"5.50"``; ``quantity`` is at least 1).
    - ``details``: ``{name?, email?}``, non-blank strings.
    - ``completed``: true once the customer confirmed and the flow reached its last block.

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
        unknown = details.keys() - STATE_DETAIL_FIELDS
        if unknown:
            errors.append(f'details: unknown field(s) {", ".join(sorted(unknown))}.')
        for field in STATE_DETAIL_FIELDS & details.keys():
            if not isinstance(details[field], str) or not details[field].strip():
                errors.append(f'details: {field} must be a non-blank string.')

    if not isinstance(value.get('completed', False), bool):
        errors.append('completed must be true or false.')

    if errors:
        raise ValidationError(errors)
