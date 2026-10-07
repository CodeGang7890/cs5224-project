"""How much of each product is tied up in orders: the quantities derived from OrderItem.order_data.

A product only stores its `total_quantity`. Everything else comes from the orders:
- on hold: the quantities in orders still being paid for or fulfilled (HOLD_STATUSES);
- sold: the quantities in completed orders (SOLD_STATUSES);
- available: total_quantity - on hold - sold (see product_app.models.Product).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from .models import OrderItem, OrderStatus

HOLD_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_RECEIVED)
SOLD_STATUSES = (OrderStatus.ORDER_COMPLETED,)


@dataclass(frozen=True)
class Stock:
    """One product's quantities in orders."""

    on_hold: int = 0
    sold: int = 0

    @property
    def committed(self) -> int:
        """On hold + sold: the least the product's total_quantity can be."""
        return self.on_hold + self.sold


def ordered_quantities(business_ids: Iterable[int], product_ids: Iterable[int] | None = None) -> dict[int, Stock]:
    """Product id → Stock, summed over the businesses' orders (one query).

    `product_ids` limits the result to those products (others are skipped while summing); a
    product with no orders isn't in the result: use `.get(product_id, Stock())`.
    """
    wanted = None if product_ids is None else set(product_ids)
    on_hold: dict[int, int] = {}
    sold: dict[int, int] = {}
    orders = OrderItem.objects.filter(
        business_id__in=set(business_ids), order_status__in=[*HOLD_STATUSES, *SOLD_STATUSES]
    ).values_list('order_status', 'order_data')
    for status, order_data in orders:
        totals = sold if status in SOLD_STATUSES else on_hold
        for item in order_data.get('items', []) if isinstance(order_data, dict) else []:
            product_id = item.get('product_id')
            if wanted is None or product_id in wanted:
                totals[product_id] = totals.get(product_id, 0) + item.get('quantity', 0)
    return {
        product_id: Stock(on_hold=on_hold.get(product_id, 0), sold=sold.get(product_id, 0))
        for product_id in on_hold.keys() | sold.keys()
    }
