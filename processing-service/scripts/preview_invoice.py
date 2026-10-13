"""Writes sample invoices as PDFs to look at, with no database or cloud: `python scripts/preview_invoice.py`.

Writes sample_order_invoice.pdf and sample_booking_invoice.pdf in the current directory.
"""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import invoice

COMMON = dict(
    issued_at=datetime.now(UTC),
    payment_reference='0123456789abcdef0123456789abcdef',
    business_name='Kopi & Toast',
    business_location='1 Raffles Place, Singapore',
    customer_name='Hong Gildong',
    customer_phone='+6591234567',
    currency='SGD',
)

ORDER = invoice.Invoice(
    number='INV-O-000002',
    kind=invoice.ORDER,
    details=(('Email', 'gildong@mail.com'), ('Pickup time', 'Saturday 9am')),
    lines=(
        invoice.InvoiceLine('Kopi C', 20, Decimal('1.80')),
        invoice.InvoiceLine('Kaya Toast Set (with soft-boiled eggs and a very long description to see if it is wrapped in the invoice)', 10, Decimal('5.50')),
    ),
    **COMMON,
)
BOOKING = invoice.Invoice(
    number='INV-B-000028',
    kind=invoice.BOOKING,
    details=(('Email', 'gildong@example.com'),),
    lines=(invoice.InvoiceLine('Portrait shoot', 1, Decimal('180.00')),),
    booking=invoice.Booking('Portrait shoot', 'John Doe', datetime(2026, 10, 12, 2, tzinfo=UTC), datetime(2026, 10, 12, 3, tzinfo=UTC)),
    **COMMON,
)

if __name__ == '__main__':
    for name, sample in (('sample_order_invoice.pdf', ORDER), ('sample_booking_invoice.pdf', BOOKING)):
        Path(name).write_bytes(invoice.render_pdf(sample))
        print(f'Wrote {Path(name).resolve()}')
