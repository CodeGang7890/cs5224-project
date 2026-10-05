"""Placing orders: creates the OrderItem and reserves its stock, safely under concurrency."""

from django.db import transaction
from django.db.models import F

from product_app.models import Product

from .models import OrderItem, OrderStatus


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
    """Creates a PENDING_PAYMENT order and reserves its stock, all or nothing.

    `items` are `{product_id, name, unit_price, quantity}` (the snapshot the customer confirmed;
    the price isn't re-read, so the customer pays what they were shown). For each, the product's
    `quantity_available` goes down and `quantity_on_hold` goes up by the quantity.

    Concurrency: everything runs in one transaction. The products' rows are locked with
    SELECT ... FOR UPDATE, in id order (so two orders can't deadlock), before the stock is checked;
    the updates are also guarded with `quantity_available >= quantity`, so stock can never go
    negative even on a database without row locks (SQLite locks the whole database instead).
    Raises OrderError (and changes nothing) if a product isn't on sale or doesn't have enough stock.
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
        problems = []
        for product_id, quantity in quantities.items():
            product = locked.get(product_id)
            if product is None or not product.is_active:
                problems.append(f'{names[product_id]} is no longer available.')
            elif product.quantity_available < quantity:
                left = product.quantity_available
                problems.append(f'Only {left} {product.name} {"is" if left == 1 else "are"} left.')
        if problems:
            raise OrderError(problems)

        for product_id, quantity in sorted(quantities.items()):
            updated = Product.objects.filter(pk=product_id, quantity_available__gte=quantity).update(
                quantity_available=F('quantity_available') - quantity,
                quantity_on_hold=F('quantity_on_hold') + quantity,
            )
            if updated != 1:  # only if the lock didn't hold (e.g. no row locks): roll everything back
                raise OrderError([f'{names[product_id]} just sold out.'])

        order = OrderItem(
            business=business,
            chat_session=chat_session,
            is_sandbox=is_sandbox,
            order_data={'items': list(merged.values()), 'details': details},
            order_status=OrderStatus.PENDING_PAYMENT,
        )
        order.full_clean()
        order.save()
    return order
