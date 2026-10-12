"""Placing orders and bookings, safely under concurrency: a port of configuration-service's
checkout_app/services.py (place_order / place_booking), checkout_app/validators.py and the model
checks Django's full_clean() runs (OrderItem / ScheduleItem.clean), to SQLAlchemy.

Rows are inserted with every column set (Django's defaults don't run here): a new random
payment_reference, created / updated times, and pending payment.
"""

import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ChatSession, OrderItem, Product, ScheduleItem, Service
from . import dates, schedule
from .errors import ValidationError
from .schedule import PENDING_PAYMENT
from .stock import quantities_available
from .validators import DETAIL_KEY_PATTERN

# product_app.models
PRICE_MAX_DIGITS = 10  # up to 99,999,999.99
PRICE_DECIMAL_PLACES = 2
QUANTITY_MAX = 1_000_000
# checkout_app.models: a random 128-bit reference the payment is made under (32 hex characters).
PAYMENT_REFERENCE_BITS = 128


def new_payment_reference() -> str:
    """checkout_app.models.new_payment_reference: not checked for duplicates (negligible odds)."""
    return secrets.token_hex(PAYMENT_REFERENCE_BITS // 8)


# --- checkout_app/validators.py -----------------------------------------------------------------

ORDER_DATA_FIELDS = {'items', 'details'}
ORDER_ITEM_FIELDS = {'product_id', 'name', 'unit_price', 'quantity'}
SCHEDULE_DATA_FIELDS = {'service', 'details'}
SCHEDULE_SERVICE_FIELDS = {'service_id', 'name', 'price', 'duration_minutes', 'buffer_minutes'}


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


def validate_details(details, errors: list[str]) -> None:
    """Customer details collected in a chat, by field key: non-blank strings or numbers."""
    if not isinstance(details, dict):
        errors.append('details must be an object.')
        return
    for key, detail in details.items():
        if not DETAIL_KEY_PATTERN.match(key):
            errors.append(f'details: invalid key {key!r}.')
        elif not (_is_number(detail) or (isinstance(detail, str) and detail.strip())):
            errors.append(f'details: {key} must be a non-blank string or a number.')


def validate_order_data(value) -> None:
    """checkout_app.validators.validate_order_data: `{"items": [...], "details": {...}}`."""
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
    validate_details(value.get('details', {}), errors)
    if errors:
        raise ValidationError(errors)


def validate_schedule_data(value) -> None:
    """checkout_app.validators.validate_schedule_data: `{"service": {...}, "details": {...}}`."""
    if not isinstance(value, dict):
        raise ValidationError('Schedule data must be an object.')
    errors = []
    missing = SCHEDULE_DATA_FIELDS - value.keys()
    unknown = value.keys() - SCHEDULE_DATA_FIELDS
    if missing:
        errors.append(f'Missing field(s) {", ".join(sorted(missing))}.')
    if unknown:
        errors.append(f'Unknown field(s) {", ".join(sorted(unknown))}.')
    service = value.get('service', {})
    if not isinstance(service, dict) or service.keys() != SCHEDULE_SERVICE_FIELDS:
        errors.append(f'service must be an object with exactly {", ".join(sorted(SCHEDULE_SERVICE_FIELDS))}.')
    else:
        if not _is_int(service['service_id']):
            errors.append('service: service_id must be an integer.')
        if not isinstance(service['name'], str) or not service['name'].strip():
            errors.append('service: name must be a non-blank string.')
        if not _is_price(service['price']):
            errors.append('service: price must be a decimal string of at least 0, e.g. "180.00".')
        if not _is_int(service['duration_minutes']) or service['duration_minutes'] < 1:
            errors.append('service: duration_minutes must be a positive integer.')
        if not _is_int(service['buffer_minutes']) or service['buffer_minutes'] < 0:
            errors.append('service: buffer_minutes must be an integer of at least 0.')
    validate_details(value.get('details', {}), errors)
    if errors:
        raise ValidationError(errors)


# --- checkout_app/services.py -------------------------------------------------------------------

class OrderError(Exception):
    """The order can't be placed, e.g. a product sold out since the customer chose it.

    `problems` are short sentences to explain to the customer.
    """

    def __init__(self, problems: list[str]):
        super().__init__(' '.join(problems))
        self.problems = problems


def place_order(
    db: Session, business, items: list[dict], details: dict, *, chat_session: ChatSession | None = None,
    is_sandbox: bool = False,
) -> OrderItem:
    """Creates a PENDING_PAYMENT order, all or nothing, if every product has enough available.

    Call inside a transaction (the caller's: order_flow.commit_turn); raising rolls it back.
    `items` are `{product_id, name, unit_price, quantity}` (the snapshot the customer confirmed;
    the price isn't re-read). Products store only their total_quantity, and their on hold / sold /
    available quantities are derived from the orders, so creating the order puts them on hold.

    Concurrency: the products' rows are locked with SELECT ... FOR UPDATE, in id order (so two
    orders can't deadlock), before the quantities are checked (the same lock configuration-service
    takes). After the order is added, the quantities are checked again with it counted, so a
    product can never be oversold even without row locks (SQLite). Raises OrderError.
    """
    merged: dict[int, dict] = {}
    for item in items:
        line = merged.setdefault(item['product_id'], {**item, 'quantity': 0})
        line['quantity'] += item['quantity']
    if not merged:
        raise OrderError(['The order has no items.'])
    quantities = {product_id: line['quantity'] for product_id, line in merged.items()}
    names = {product_id: line['name'] for product_id, line in merged.items()}

    locked = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.business_id == business.id, Product.id.in_(list(quantities)))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    available = quantities_available(db, locked.values())
    problems = []
    for product_id, quantity in quantities.items():
        product = locked.get(product_id)
        if product is None or not product.is_active:
            problems.append(f'{names[product_id]} is no longer available.')
        elif available[product_id] < quantity:
            left = max(available[product_id], 0)
            problems.append(f'Only {left} {product.name} {"is" if left == 1 else "are"} left.')
    if problems:
        raise OrderError(problems)

    order_data = {'items': list(merged.values()), 'details': details}
    validate_order_data(order_data)  # Django's full_clean()
    now = dates.now()
    order = OrderItem(
        business_id=business.id,
        chat_session_id=chat_session.id if chat_session is not None else None,
        is_sandbox=is_sandbox,
        order_data=order_data,
        order_status=PENDING_PAYMENT,
        payment_reference=new_payment_reference(),
        created_time=now,
        updated_time=now,
    )
    db.add(order)
    db.flush()

    # Counted again, with this order: only if the lock didn't hold could another order have taken
    # the stock in between. Then the caller's transaction is rolled back.
    available = quantities_available(db, locked.values())
    oversold = [names[product_id] for product_id in locked if available[product_id] < 0]
    if oversold:
        raise OrderError([f'{name} just sold out.' for name in oversold])
    return order


class BookingError(Exception):
    """The time can't be booked, e.g. someone else booked it since the customer chose it.

    `problems` are short sentences to explain to the customer.
    """

    def __init__(self, problems: list[str]):
        super().__init__(' '.join(problems))
        self.problems = problems


def _check_booking(booking: ScheduleItem, service: Service, provider, chat_session) -> None:
    """ScheduleItem.clean(): the times match the snapshot, and everything is the same business's."""
    errors = []
    snapshot = booking.schedule_data['service']
    if booking.end_time != booking.start_time + timedelta(minutes=snapshot['duration_minutes']):
        errors.append('end_time: Must be start_time plus the service duration.')
    if booking.blocked_until != booking.end_time + timedelta(minutes=snapshot['buffer_minutes']):
        errors.append('blocked_until: Must be end_time plus the service buffer.')
    for name, related in (('service', service), ('service provider', provider), ('chat session', chat_session)):
        if related is not None and related.business_id != booking.business_id:
            errors.append(f"The {name} must belong to the booking's business.")
    if errors:
        raise ValidationError(errors)


def place_booking(
    db: Session, business, service_id: int, start, details: dict, *, price: str | None = None,
    chat_session: ChatSession | None = None, is_sandbox: bool = False, now=None,
) -> ScheduleItem:
    """Books `start` for the service, all or nothing: a PENDING_PAYMENT ScheduleItem with the first
    of the service's active providers (in pk order) who is free then, written into the provider's
    week (its blocks O → H; schedule.sync_booking, which Django runs from a signal).

    Call inside a transaction (the caller's: order_flow.commit_turn); raising rolls it back.
    `price` is the price the customer was shown (default: the service's current price). The
    duration and buffer are the service's current ones.

    Concurrency: the service's providers and their weeks are locked with SELECT ... FOR UPDATE, in pk
    order, before checking (configuration-service's set_slots / copy_week / week edits take the same
    provider lock), then the time is checked again with the new booking added. Raises BookingError.
    """
    service = db.scalars(select(Service).where(Service.business_id == business.id, Service.id == service_id)).first()
    if service is None:
        raise BookingError(['That service is no longer available.'])
    providers = schedule.service_providers(db, service, lock=True)
    problem = schedule.start_problem(db, service, start, now, lock=True)
    if problem:
        raise BookingError([problem])
    times = schedule.booking_times(service, start)
    ids = [p.pk for p in providers]
    weeks = schedule.load_weeks(db, ids, times.start, times.blocked_until, lock=True)
    bookings = list(schedule.bookings_between(db, ids, times.start, times.blocked_until))
    provider = schedule.free_provider(service, start, providers, weeks, bookings)
    if provider is None:  # start_problem() already checked this; kept as a safety net
        raise BookingError([f'{schedule.format_slot(start)} is not available for {service.name}.'])

    schedule_data = {
        'service': {
            'service_id': service.pk,
            'name': service.name,
            'price': price if price is not None else str(service.price),
            'duration_minutes': service.duration_minutes,
            'buffer_minutes': service.buffer_minutes,
        },
        'details': details,
    }
    validate_schedule_data(schedule_data)  # Django's full_clean()
    created = dates.now()
    booking = ScheduleItem(
        business_id=business.id,
        chat_session_id=chat_session.id if chat_session is not None else None,
        is_sandbox=is_sandbox,
        service_id=service.id,
        service_provider_id=provider.id,
        start_time=times.start,
        end_time=times.end,
        blocked_until=times.blocked_until,
        schedule_data=schedule_data,
        order_status=PENDING_PAYMENT,
        payment_reference=new_payment_reference(),
        created_time=created,
        updated_time=created,
    )
    _check_booking(booking, service, provider, chat_session)
    db.add(booking)
    db.flush()
    schedule.sync_booking(db, booking)  # its blocks on hold (Django: checkout_app.signals)

    # Checked again, with this booking added: only if the lock didn't hold could another booking
    # have taken the time in between. Then the caller's transaction is rolled back.
    if schedule.bookings_between(db, [provider.pk], times.start, times.blocked_until, exclude_id=booking.id):
        raise BookingError([f'{schedule.format_slot(start)} was just booked by someone else.'])
    return booking
