"""The customer's past orders and bookings, for the chat's order status branch (the router's
`order_status` intent; flow.check_order_status).

The branch has no states and no tools: an LLM call only extracts what the customer asks about
(order / booking, and any numbers: prompts.ORDER_STATUS_SCHEMA), then lookup() here, plain code,
finds them among the customer's own orders and bookings, and a second LLM call rewrites what was
found for the customer (prompts.build_order_status_prompt), checked by reply_is_grounded().

"The customer" is everyone chatting with the same business from the same phone number: real
chats only see real orders, and sandbox chats only sandbox ones. Sandbox chats without a phone
number count as one customer (the business testing), so an order made in one test chat can be
checked from another. A number that isn't the customer's is "not found", exactly like a number
that doesn't exist, so nothing about other customers' orders is ever revealed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from checkout_app.models import OrderItem, OrderStatus, ScheduleItem
from checkout_app.schedule import local

from .models import ChatSession

# At most this many orders / bookings in a list (the newest first).
LIST_MAX = 10
# At most this many numbers looked up from one message.
NUMBERS_MAX = 5

KIND_ORDER = 'order'
KIND_BOOKING = 'booking'
KIND_ANY = 'any'
KINDS = [KIND_ORDER, KIND_BOOKING, KIND_ANY]

# Each status, as the customer is told it, and what it means.
STATUS_LABELS = {
    OrderStatus.PENDING_PAYMENT: 'Payment pending',
    OrderStatus.PAYMENT_RECEIVED: 'Payment received',
    OrderStatus.ORDER_COMPLETED: 'Completed',
}
ORDER_STATUS_MEANINGS = {
    OrderStatus.PENDING_PAYMENT: 'the order is placed, but the business has not received the payment yet',
    OrderStatus.PAYMENT_RECEIVED: 'the business has received the payment; the order is not completed yet',
    OrderStatus.ORDER_COMPLETED: 'the order is completed',
}
BOOKING_STATUS_MEANINGS = {
    OrderStatus.PENDING_PAYMENT: 'the time is held for the customer, but the business has not received the payment yet',
    OrderStatus.PAYMENT_RECEIVED: 'the business has received the payment; the booking is confirmed',
    OrderStatus.ORDER_COMPLETED: 'the booking is completed (the service has been done)',
}


def customer_sessions(session: ChatSession):
    """The chats of the same customer as `session`: same business, same phone number, and real or
    sandbox like it. Real chats always have a phone number; sandbox chats without one share theirs."""
    return ChatSession.objects.filter(
        business_id=session.business_id, is_sandbox=session.is_sandbox, phone_number=session.phone_number
    )


def when(moment: datetime) -> str:
    """A date and time for customers, in the business's local time, e.g. "Sat 12 Sep 2026, 10:30am"."""
    moment = local(moment)
    return f'{moment:%a} {moment.day} {moment:%b %Y}, {_clock(moment)}'


def _clock(moment: datetime) -> str:
    return f'{moment.hour % 12 or 12}:{moment.minute:02d}{"am" if moment.hour < 12 else "pm"}'


def _orders(session: ChatSession):
    return OrderItem.objects.filter(
        business_id=session.business_id, chat_session__in=customer_sessions(session)
    ).order_by('-created_time', '-id')


def _bookings(session: ChatSession):
    return ScheduleItem.objects.filter(
        business_id=session.business_id, chat_session__in=customer_sessions(session)
    ).select_related('service_provider').order_by('-start_time', '-id')


def order_record(order: OrderItem) -> dict:
    """What the customer may be told about one of their orders."""
    return {
        'number': order.pk,
        'placed': when(order.created_time),
        'items': ', '.join(f'{item["quantity"]} × {item["name"]}' for item in order.order_data.get('items', [])),
        'total': str(order.total),
        'status': STATUS_LABELS.get(order.order_status, order.order_status),
        'status_meaning': ORDER_STATUS_MEANINGS.get(order.order_status, ''),
    }


def booking_record(booking: ScheduleItem, now: datetime) -> dict:
    """What the customer may be told about one of their bookings."""
    return {
        'number': booking.pk,
        'service': booking.schedule_data['service']['name'],
        'time': f'{when(booking.start_time)} to {_clock(local(booking.end_time))}',
        'upcoming': booking.start_time > now,
        'with': booking.service_provider.name if booking.service_provider else None,
        'total': str(booking.total),
        'status': STATUS_LABELS.get(booking.order_status, booking.order_status),
        'status_meaning': BOOKING_STATUS_MEANINGS.get(booking.order_status, ''),
    }


@dataclass
class Lookup:
    """What lookup() found: only ever the customer's own orders and bookings."""

    kind: str  # what was asked about: order / booking / any
    numbers: list[int]  # the numbers asked about (empty: "my orders", "is my booking paid?")
    orders: list[dict] = field(default_factory=list)  # order_record()s
    bookings: list[dict] = field(default_factory=list)  # booking_record()s
    not_found: list[str] = field(default_factory=list)  # e.g. "booking #1": not one of theirs
    more_orders: bool = False  # the list was cut to LIST_MAX
    more_bookings: bool = False

    @property
    def numbers_found(self) -> set[int]:
        return {record['number'] for record in self.orders + self.bookings}

    def as_dict(self) -> dict:
        """For the Chat Sandbox's debug panel."""
        return {
            'kind': self.kind, 'numbers': self.numbers, 'orders': self.orders, 'bookings': self.bookings,
            'not_found': self.not_found, 'more_orders': self.more_orders, 'more_bookings': self.more_bookings,
        }


def clean_request(extracted: dict) -> tuple[str, list[int]]:
    """The extraction's kind and numbers, made safe: an unknown kind is "any"; numbers are positive
    integers (12, "12" or "#12"), once each, at most NUMBERS_MAX."""
    kind = extracted.get('kind') if extracted.get('kind') in KINDS else KIND_ANY
    numbers: list[int] = []
    raw = extracted.get('numbers')
    for value in raw if isinstance(raw, list) else []:
        if isinstance(value, str) and value.strip().lstrip('#').isdigit():
            value = int(value.strip().lstrip('#'))
        if isinstance(value, int) and not isinstance(value, bool) and value > 0 and value not in numbers:
            numbers.append(value)
    return kind, numbers[:NUMBERS_MAX]


def lookup(session: ChatSession, kind: str, numbers: list[int], now: datetime | None = None) -> Lookup:
    """Finds what the customer asks about, among their own orders and bookings only.

    With numbers: each one among their orders (kind order), bookings (kind booking) or both (any;
    and if it isn't of the kind asked, the other kind too: customers mix the words up). A number
    that isn't theirs is "not found", whether or not someone else has it. Without numbers: their
    orders and / or bookings, newest first (at most LIST_MAX each).
    """
    now = now or timezone.now()
    result = Lookup(kind=kind, numbers=numbers)
    want_orders, want_bookings = kind in (KIND_ORDER, KIND_ANY), kind in (KIND_BOOKING, KIND_ANY)
    if not numbers:
        if want_orders:
            orders = list(_orders(session)[: LIST_MAX + 1])
            result.orders, result.more_orders = [order_record(o) for o in orders[:LIST_MAX]], len(orders) > LIST_MAX
        if want_bookings:
            bookings = list(_bookings(session)[: LIST_MAX + 1])
            result.bookings = [booking_record(b, now) for b in bookings[:LIST_MAX]]
            result.more_bookings = len(bookings) > LIST_MAX
        return result
    orders = {o.pk: o for o in _orders(session).filter(pk__in=numbers)}
    bookings = {b.pk: b for b in _bookings(session).filter(pk__in=numbers)}
    for number in numbers:
        order = orders.get(number) if want_orders or number not in bookings else None
        booking = bookings.get(number) if want_bookings or number not in orders else None
        if order is not None:
            result.orders.append(order_record(order))
        if booking is not None:
            result.bookings.append(booking_record(booking, now))
        if order is None and booking is None:
            result.not_found.append(f'{kind} #{number}' if kind != KIND_ANY else f'#{number}')
    return result


# "#12", "order 12", "booking no. 12", "order number 12": numbers a reply gives as order / booking numbers.
_NUMBER_MENTIONS = re.compile(r'#\s*(\d+)|\b(?:order|booking)s?\s+(?:number\s+|no\.?\s*)?#?(\d+)\b', re.IGNORECASE)


# How a reply says it couldn't find something.
_NOT_FOUND_WORDING = re.compile(
    r"(?:could ?n[o']?t|can ?n?[o']?t|cannot|unable to|did ?n[o']?t|was ?n[o']?t able to) (?:find|locate|see)"
    r"|not (?:be )?found|no record|do ?n[o']?t have|does ?n[o']?t (?:match|exist)|not one of|check the number",
    re.IGNORECASE,
)


def _numbers_in(text: str) -> set[int]:
    return {int(a or b) for a, b in _NUMBER_MENTIONS.findall(text)}


def reply_is_grounded(reply: str, found: Lookup) -> bool:
    """Whether the reply only names what the lookup found. A reply that names any other order /
    booking number, or says anything but "not found" about a number that wasn't found (e.g.
    "booking #1 is pending" when #1 isn't theirs), made it up: it isn't sent."""
    if not _numbers_in(reply) <= found.numbers_found | set(found.numbers):
        return False
    missing = set(found.numbers) - found.numbers_found
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', reply):
        if _numbers_in(sentence) & missing and not _NOT_FOUND_WORDING.search(sentence):
            return False
    return True
