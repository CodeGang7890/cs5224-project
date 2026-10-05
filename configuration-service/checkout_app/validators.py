from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from chat_app.validators import DETAIL_KEY_PATTERN
from product_app.models import PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS, QUANTITY_MAX

ORDER_DATA_FIELDS = {'items', 'details'}
ORDER_ITEM_FIELDS = {'product_id', 'name', 'unit_price', 'quantity'}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_price(value) -> bool:
    """A decimal string like "5.50": at least 0, at most 2 decimal places, fits Product.price."""
    if not isinstance(value, str):
        return False
    try:
        price = Decimal(value)
    except InvalidOperation:
        return False
    if not price.is_finite() or price < 0:
        return False
    sign, digits, exponent = price.as_tuple()
    decimals = max(-exponent, 0)
    return decimals <= PRICE_DECIMAL_PLACES and len(digits) - decimals <= PRICE_MAX_DIGITS - PRICE_DECIMAL_PLACES


def validate_order_data(value) -> None:
    """Validate an OrderItem.order_data: what was ordered, and the customer's details.

    ``{"items": [...], "details": {...}}``, both required:
    - ``items``: at least one ``{product_id, name, unit_price, quantity}``, one per product
      (``product_id`` unique). ``name`` and ``unit_price`` are a snapshot from when the customer
      chose it: ``name`` non-blank, ``unit_price`` a decimal string like ``"5.50"`` (≥0, at most
      2 decimal places). ``quantity`` is an integer from 1 to QUANTITY_MAX.
    - ``details``: the details collected in the chat's Details collection phase, by field key
      (e.g. ``{"name": "Alice", "postal_code": 238801}``): non-blank strings or numbers. Can be
      empty, for a chat flow without a Details collection block.

    Raises a ``ValidationError`` listing every problem found.
    """
    if not isinstance(value, dict):
        raise ValidationError('Order data must be an object.')

    errors = []
    missing = ORDER_DATA_FIELDS - value.keys()
    unknown = value.keys() - ORDER_DATA_FIELDS
    if missing:
        errors.append(f'Missing field(s) {", ".join(sorted(missing))}.')
    if unknown:
        errors.append(f'Unknown field(s) {", ".join(sorted(unknown))}.')

    items = value.get('items', [])
    if not isinstance(items, list):
        errors.append('items must be a list.')
        items = []
    elif 'items' in value and not items:
        errors.append('items must have at least one item.')
    product_ids = set()
    for index, item in enumerate(items):
        prefix = f'Item {index}'
        if not isinstance(item, dict) or item.keys() != ORDER_ITEM_FIELDS:
            errors.append(f'{prefix}: must be an object with exactly {", ".join(sorted(ORDER_ITEM_FIELDS))}.')
            continue
        if not _is_int(item['product_id']):
            errors.append(f'{prefix}: product_id must be an integer.')
        elif item['product_id'] in product_ids:
            errors.append(f'{prefix}: product {item["product_id"]} is listed more than once.')
        else:
            product_ids.add(item['product_id'])
        if not isinstance(item['name'], str) or not item['name'].strip():
            errors.append(f'{prefix}: name must be a non-blank string.')
        if not _is_price(item['unit_price']):
            errors.append(f'{prefix}: unit_price must be a decimal string of at least 0, e.g. "5.50".')
        if not _is_int(item['quantity']) or not 1 <= item['quantity'] <= QUANTITY_MAX:
            errors.append(f'{prefix}: quantity must be an integer from 1 to {QUANTITY_MAX:,}.')

    details = value.get('details', {})
    if not isinstance(details, dict):
        errors.append('details must be an object.')
    else:
        for key, detail in details.items():
            if not DETAIL_KEY_PATTERN.match(key):
                errors.append(f'details: invalid key {key!r}.')
            elif not (_is_number(detail) or (isinstance(detail, str) and detail.strip())):
                errors.append(f'details: {key} must be a non-blank string or a number.')

    if errors:
        raise ValidationError(errors)
