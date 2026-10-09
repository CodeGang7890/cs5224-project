"""Placing orders and bookings, safely under concurrency: place_order() creates the OrderItem,
which puts its products on hold; place_booking() creates the ScheduleItem, which takes up its time."""

from django.db import transaction

from product_app.models import Product, Service

from . import schedule
from .models import OrderItem, OrderStatus, ScheduleItem


class OrderError(Exception):
    """The order can't be placed, e.g. a product sold out since the customer chose it.

    `problems` are short sentences to explain to the customer.
    """

    def __init__(self, problems: list[str]):
        super().__init__(' '.join(problems))
        self.problems = problems


def place_order(
    business, items: list[dict], details: dict, *, chat_session=None, is_sandbox: bool = False
) -> OrderItem:
    """Creates a PENDING_PAYMENT order, all or nothing, if every product has enough available.

    `items` are `{product_id, name, unit_price, quantity}` (the snapshot the customer confirmed;
    the price isn't re-read, so the customer pays what they were shown). Products store only their
    total_quantity, and their on hold / sold / available quantities are derived from the orders
    (checkout_app.stock), so creating the order is what puts its quantities on hold.

    Concurrency: everything runs in one transaction. The products' rows are locked with
    SELECT ... FOR UPDATE, in id order (so two orders can't deadlock), before the quantities are
    checked; the same lock guards changes to total_quantity (ProductSerializer.update). After the
    order is saved, the quantities are checked again with it counted, so a product can never be
    oversold even on a database without row locks (SQLite locks the whole database instead).
    Raises OrderError (and changes nothing) if a product isn't on sale or doesn't have enough.
    """
    # One line per product (the same product chosen twice is merged).
    merged: dict[int, dict] = {}
    for item in items:
        line = merged.setdefault(item['product_id'], {**item, 'quantity': 0})
        line['quantity'] += item['quantity']
    if not merged:
        raise OrderError(['The order has no items.'])
    quantities = {product_id: line['quantity'] for product_id, line in merged.items()}
    names = {product_id: line['name'] for product_id, line in merged.items()}

    with transaction.atomic():
        locked = {
            product.pk: product
            for product in Product.objects.select_for_update()
            .filter(business=business, pk__in=quantities)
            .order_by('pk')
        }
        Product.load_stock(locked.values())
        problems = []
        for product_id, quantity in quantities.items():
            product = locked.get(product_id)
            if product is None or not product.is_active:
                problems.append(f'{names[product_id]} is no longer available.')
            elif product.quantity_available < quantity:
                left = max(product.quantity_available, 0)
                problems.append(f'Only {left} {product.name} {"is" if left == 1 else "are"} left.')
        if problems:
            raise OrderError(problems)

        order = OrderItem(
            business=business,
            chat_session=chat_session,
            is_sandbox=is_sandbox,
            order_data={'items': list(merged.values()), 'details': details},
            order_status=OrderStatus.PENDING_PAYMENT,
        )
        order.full_clean()
        order.save()

        # Counted again, with this order: only if the lock didn't hold (e.g. no row locks) could
        # another order have taken the stock in between. Then roll everything back.
        oversold = [
            names[product.pk] for product in Product.load_stock(locked.values()) if product.quantity_available < 0
        ]
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


def place_booking(
    business, service_id: int, start, details: dict, *, price: str | None = None, chat_session=None,
    is_sandbox: bool = False, now=None,
) -> ScheduleItem:
    """Books `start` for the service, all or nothing: a PENDING_PAYMENT ScheduleItem, in the first
    of the service's weekly availabilities (in pk order) that's free then (checkout_app.schedule).

    `price` is the price the customer was shown (a decimal string; default: the service's current
    price), like an order's snapshot unit_price. The duration and buffer are the service's current ones.

    Concurrency: one transaction; the service's availabilities are locked with SELECT ... FOR
    UPDATE, in pk order, before checking for overlapping bookings, then the overlap is checked again
    with the new booking saved (protects databases without row locks, like SQLite). Raises
    BookingError (and changes nothing) if the service isn't bookable or the time isn't free.
    """
    with transaction.atomic():
        service = Service.objects.filter(business=business, pk=service_id).first()
        if service is None:
            raise BookingError(['That service is no longer available.'])
        availabilities = schedule.service_availabilities(service, lock=True)
        problem = schedule.start_problem(service, start, now)
        if problem:
            raise BookingError([problem])
        times = schedule.booking_times(service, start)
        bookings = list(schedule.bookings_between([a.pk for a in availabilities], times.start, times.blocked_until))
        availability = schedule.free_availability(service, start, availabilities, bookings)
        if availability is None:  # start_problem() already checked this; kept as a safety net
            raise BookingError([f'{schedule.format_slot(start)} is not available for {service.name}.'])

        booking = ScheduleItem(
            business=business,
            chat_session=chat_session,
            is_sandbox=is_sandbox,
            service=service,
            weekly_availability=availability,
            start_time=times.start,
            end_time=times.end,
            blocked_until=times.blocked_until,
            schedule_data={
                'service': {
                    'service_id': service.pk,
                    'name': service.name,
                    'price': price if price is not None else str(service.price),
                    'duration_minutes': service.duration_minutes,
                    'buffer_minutes': service.buffer_minutes,
                },
                'details': details,
            },
            order_status=OrderStatus.PENDING_PAYMENT,
        )
        booking.full_clean()
        booking.save()

        # Checked again, with this booking saved: only if the lock didn't hold could another
        # booking have taken the time in between. Then roll everything back.
        clash = schedule.bookings_between([availability.pk], times.start, times.blocked_until).exclude(pk=booking.pk)
        if clash.exists():
            raise BookingError([f'{schedule.format_slot(start)} was just booked by someone else.'])
    return booking
