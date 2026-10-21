"""The Xendit payment link for a just-confirmed order / booking.

Once the chat flow has saved an order or booking (order_flow.commit_turn), this module asks
payment-ingester for the Xendit payment link (payment_client.create_payment), stores Xendit's
payment id and the link on the order / booking's row, and puts the link on the turn: the
confirmation message ends with it, and the customer pays on Xendit's own page. The result comes
back later through Xendit's webhook (payment-ingester → Pub/Sub → processing-service), which
updates the order / booking's status.

If no link can be created (payment-ingester down, Xendit refused, or the chat didn't collect the
customer's name or email), the order / booking stays pending payment with no link: the
confirmation message carries a note instead, and the reason goes on the turn (the Chat Sandbox's
debug panel shows it).
"""

import logging
import re
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from .. import payment_client
from ..models import OrderItem, ScheduleItem
from .order_flow import Turn

logger = logging.getLogger(__name__)


def _customer_details(details: dict) -> tuple[str, str] | None:
    """The customer's name and email, from the details collected in the chat (the fields with
    the keys `name` and `email`). None if Xendit can't be given them: a non-blank name with at
    least one letter or digit, and an email within Xendit's 50-character limit."""
    given_name = details.get('name')
    email = details.get('email')
    if not (isinstance(given_name, str) and isinstance(email, str)):
        return None
    given_name, email = given_name.strip(), email.strip()
    if not given_name or not re.search(r'[0-9A-Za-z]', given_name):
        return None
    if not email or len(email) > 50:
        return None
    return given_name, email


def _amount(data: dict, booking: bool) -> Decimal:
    """What the customer pays: the service's price for a booking, the items' total for an order."""
    if booking:
        return Decimal(data['service']['price'])
    items = data.get('items', [])
    return sum((Decimal(item['unit_price']) * item['quantity'] for item in items), Decimal('0.00'))


def store_payment_for_placed(sessions: sessionmaker, turn: Turn, business) -> None:
    """After commit_turn() saved an order / booking: create the Xendit payment link, store it on
    the row, and put it on the turn (turn.payment_link). A failure goes on turn.payment_error
    (and is logged): the confirmation message carries the note instead of a link."""
    if turn.placed_order_id is not None:
        kind, item_id, model = 'order', turn.placed_order_id, OrderItem
    elif turn.placed_booking_id is not None:
        kind, item_id, model = 'booking', turn.placed_booking_id, ScheduleItem
    else:
        return

    booking = kind == 'booking'
    data = turn.confirmation or {}
    customer = _customer_details(data.get('details', {}) or {})
    if customer is None:
        turn.payment_error = 'The customer name or email was not collected.'
        logger.warning('%s #%s: no payment link (no customer name or email in the details)', kind, item_id)
        return

    with sessions() as db:
        reference = db.get(model, item_id).payment_reference

    description = f"{'Order' if not booking else 'Booking'} #{item_id} with {business.business_name}"
    try:
        result = payment_client.create_payment(
            kind,
            item_id,
            _amount(data, booking),
            reference,
            {'given_name': customer[0], 'email': customer[1]},
            description=description,
        )
    except payment_client.PaymentClientError as exc:
        turn.payment_error = str(exc)
        logger.error('%s #%s: could not create the Xendit payment: %s', kind, item_id, exc)
        return

    with sessions.begin() as db:
        item = db.get(model, item_id)
        item.xendit_payment_id = result['xendit_payment_id']
        item.payment_link = result['payment_url']

    turn.payment_link = result['payment_url']
