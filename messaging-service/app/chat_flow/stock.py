"""How much of each product is tied up in orders: a port of configuration-service's
checkout_app/stock.py and Product.quantity_* (product_app.models).

A product only stores its `total_quantity`. Everything else comes from the orders:
- on hold: the quantities in orders still being paid for or fulfilled (HOLD_STATUSES);
- sold: the quantities in completed orders (SOLD_STATUSES);
- available: total_quantity - on hold - sold.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import OrderItem, Product
from .schedule import ORDER_COMPLETED, PAYMENT_RECEIVED, PENDING_PAYMENT

HOLD_STATUSES = (PENDING_PAYMENT, PAYMENT_RECEIVED)
SOLD_STATUSES = (ORDER_COMPLETED,)


@dataclass(frozen=True)
class Stock:
    """One product's quantities in orders."""

    on_hold: int = 0
    sold: int = 0

    @property
    def committed(self) -> int:
        return self.on_hold + self.sold


def ordered_quantities(db: Session, business_ids: Iterable[int], product_ids: Iterable[int] | None = None) -> dict[int, Stock]:
    """Product id → Stock, summed over the businesses' orders (one query)."""
    wanted = None if product_ids is None else set(product_ids)
    on_hold: dict[int, int] = {}
    sold: dict[int, int] = {}
    orders = db.execute(
        select(OrderItem.order_status, OrderItem.order_data).where(
            OrderItem.business_id.in_(set(business_ids)), OrderItem.order_status.in_([*HOLD_STATUSES, *SOLD_STATUSES])
        )
    ).all()
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


def quantities_available(db: Session, products: Iterable[Product]) -> dict[int, int]:
    """Product id → quantity_available (total − on hold − sold; Product.load_stock: one query)."""
    products = list(products)
    stock = ordered_quantities(db, {p.business_id for p in products}, [p.id for p in products])
    return {p.id: p.total_quantity - stock.get(p.id, Stock()).committed for p in products}
