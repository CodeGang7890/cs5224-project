from django.core.exceptions import ValidationError

from .constants import BLOCK_TYPES, START_BLOCK

BLOCK_FIELDS = {'id', 'next_block_id', 'block_type', 'position_x', 'position_y'}


def _is_number(value) -> bool:
    # bool is a subclass of int, but True/False aren't valid coordinates.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_valid_id(value) -> bool:
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
        if not _is_valid_id(block_id):
            errors.append(f'{prefix}: id must be an integer or a non-blank string.')
        elif block_id in ids:
            errors.append(f'{prefix}: duplicate id {block_id!r}.')
        else:
            ids.add(block_id)

        next_id = block['next_block_id']
        if next_id is not None and not _is_valid_id(next_id):
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
        if next_id is None or not _is_valid_id(next_id):
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
