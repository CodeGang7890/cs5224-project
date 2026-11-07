"""Writes sample invoices and receipts as PDFs to look at, with no database or cloud:
`python scripts/preview_documents.py`.

Writes sample_{invoice,receipt}_{order,booking}.pdf in the current directory.
"""

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import documents  # noqa: E402
from app.documents import BOOKING, INVOICE, ORDER, RECEIPT  # noqa: E402

PAY_URL = 'https://checkout.xendit.co/web/6571ab0c0d9e4d3c9f2b'
COMMON = dict(
    issued_at=datetime.now(UTC),
    payment_reference='0123456789abcdef0123456789abcdef',
    business_name='Kopi & Toast',
    business_location='1 Raffles Place, Singapore',
    business_whatsapp='+65 9123 4567',
    customer_name='Mei Ling',
    customer_phone='+6591234567',
    customer_email='meiling@example.com',
    details=(('Email', 'meiling@example.com'), ('Pickup time', 'Saturday 9am')),
    currency='SGD',
)


def sample(kind: str, doc_type: str) -> documents.Document:
    number = documents.document_number(doc_type, kind, 2 if kind == ORDER else 28)
    payment_url = PAY_URL if doc_type == INVOICE else ''
    if kind == ORDER:
        lines = (
            documents.DocumentLine('Kopi C', 20, Decimal('1.80')),
            documents.DocumentLine('Kaya Toast Set (with soft-boiled eggs and a very long description to wrap)', 10, Decimal('5.50')),
        )
        return documents.Document(number=number, doc_type=doc_type, kind=kind, lines=lines, payment_url=payment_url, **COMMON)
    booking = documents.Booking('Portrait shoot', 'Mei Lin', datetime(2026, 10, 12, 2, tzinfo=UTC), datetime(2026, 10, 12, 3, tzinfo=UTC))
    lines = (documents.DocumentLine('Portrait shoot', 1, Decimal('180.00')),)
    return documents.Document(number=number, doc_type=doc_type, kind=kind, lines=lines, booking=booking, payment_url=payment_url, **COMMON)


if __name__ == '__main__':
    for doc_type in (INVOICE, RECEIPT):
        for kind in (ORDER, BOOKING):
            path = Path(f'sample_{doc_type}_{kind}.pdf')
            path.write_bytes(documents.render_pdf(sample(kind, doc_type)))
            print(f'Wrote {path.resolve()}')
