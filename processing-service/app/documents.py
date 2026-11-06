"""The two PDFs a customer gets, never to be mixed up:

- an INVOICE (`INV-O-000012`) when they place an order / booking: what they ordered and the
  amount to pay, with the link to pay it online. Made for an order / booking that is pending payment.
- a RECEIPT (`RCT-O-000012`) once the payment is received: the same details, as paid.

Two steps, so each can be tested on its own:
1. build_document(session, item, doc_type): reads what the document shows (the business, the
   customer, the lines) from the order / booking and the rows it points to, into a Document.
2. render_pdf(document): the PDF, as bytes. No database, no files: the caller decides where it goes
   (object storage; a local file in scripts/preview_documents.py).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.orm import Session

from . import config
from .models import BusinessConfiguration, ChatSession, OrderItem, ScheduleItem, ServiceProvider

ORDER, BOOKING = 'order', 'booking'  # the kind of item
INVOICE, RECEIPT = 'invoice', 'receipt'  # the type of document
NUMBER_PREFIX = {INVOICE: 'INV', RECEIPT: 'RCT'}
TITLE = {INVOICE: 'INVOICE', RECEIPT: 'RECEIPT'}


@dataclass(frozen=True)
class DocumentLine:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Booking:
    service: str
    provider: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Document:
    number: str
    doc_type: str  # INVOICE or RECEIPT
    kind: str  # ORDER or BOOKING
    issued_at: datetime
    payment_reference: str
    business_name: str
    business_location: str
    customer_name: str
    customer_phone: str
    details: tuple[tuple[str, str], ...]
    lines: tuple[DocumentLine, ...]
    currency: str
    booking: Booking | None = None
    is_sandbox: bool = False
    customer_email: str = ''  # from the chat's `email` detail, '' if none or it doesn't look like an address
    payment_url: str = ''  # where to pay (an invoice only), '' if there is no link

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal('0.00'))


EMAIL_ADDRESS = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')  # roughly an address; the mail server has the final say


def document_number(doc_type: str, kind: str, item_id: int) -> str:
    """INV-O-000012 / RCT-O-000012 for order #12, INV-B-000028 / RCT-B-000028 for booking #28:
    stable, so a repeated event gives the same document."""
    return f'{NUMBER_PREFIX[doc_type]}-{kind[0].upper()}-{item_id:06d}'


def aware(moment: datetime) -> datetime:
    """PostgreSQL returns aware datetimes, SQLite (tests) naive ones, which are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def detail_label(key: str) -> str:
    """'pickup_time' → 'Pickup time'."""
    return key.replace('_', ' ').strip().capitalize()


def build_document(
    session: Session,
    item: OrderItem | ScheduleItem,
    doc_type: str,
    issued_at: datetime | None = None,
    payment_url: str = '',
) -> Document:
    """The invoice or receipt for this order / booking. `issued_at` defaults to when the order was
    placed (an invoice) or when the payment was applied (a receipt: its updated_time)."""
    kind = ORDER if isinstance(item, OrderItem) else BOOKING
    data = (item.order_data if kind == ORDER else item.schedule_data) or {}
    details = dict(data.get('details') or {})

    business = session.get(BusinessConfiguration, item.business_id)
    chat = session.get(ChatSession, item.chat_session_id) if item.chat_session_id else None
    customer_name = str(details.pop('name', '') or (chat.display_name if chat else '') or 'Customer')

    booking = None
    if kind == ORDER:
        lines = tuple(
            DocumentLine(str(line['name']), int(line['quantity']), Decimal(str(line['unit_price'])))
            for line in data.get('items', [])
        )
    else:
        service = data.get('service') or {}
        name = str(service.get('name') or 'Booking')
        provider = session.get(ServiceProvider, item.service_provider_id) if item.service_provider_id else None
        booking = Booking(name, provider.name if provider else '', aware(item.start_time), aware(item.end_time))
        lines = (DocumentLine(name, 1, Decimal(str(service.get('price', '0.00')))),)

    email = next((str(value).strip() for key, value in details.items() if key.lower() == 'email'), '')
    default_time = item.created_time if doc_type == INVOICE else item.updated_time

    return Document(
        number=document_number(doc_type, kind, item.id),
        doc_type=doc_type,
        kind=kind,
        issued_at=aware(issued_at or default_time),
        payment_reference=item.payment_reference,
        business_name=business.business_name if business else f'Business #{item.business_id}',
        business_location=business.location if business else '',
        customer_name=customer_name,
        customer_phone=chat.phone_number if chat else '',
        details=tuple((detail_label(key), str(value)) for key, value in details.items()),
        lines=lines,
        currency=config.INVOICE_CURRENCY,  # the currency of both documents
        booking=booking,
        is_sandbox=item.is_sandbox,
        customer_email=email if EMAIL_ADDRESS.match(email) else '',
        payment_url=payment_url if doc_type == INVOICE else '',
    )

# Generating the pdf
TYPOGRAPHY = str.maketrans({'–': '-', '—': '-', '‘': "'", '’': "'", '“': '"', '”': '"', '…': '...', '•': '-'})
GREY = (110, 110, 110)
LIGHT = (242, 242, 242)
BLACK = (0, 0, 0)


def pdf_text(text: str) -> str:
    return str(text).translate(TYPOGRAPHY).encode('latin-1', 'replace').decode('latin-1')


def money(amount: Decimal, currency: str) -> str:
    return f'{currency} {amount:,.2f}'


def local(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(config.SCHEDULE_TIME_ZONE))


class _DocumentPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*GREY)
        self.cell(0, 5, f'Page {self.page_no()}', align='C')


def render_pdf(document: Document) -> bytes:
    is_invoice = document.doc_type == INVOICE
    title = TITLE[document.doc_type]
    pdf = _DocumentPDF(format='A4')
    pdf.set_title(pdf_text(f'{title.capitalize()} {document.number}'))
    pdf.set_author(pdf_text(document.business_name))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    width = pdf.epw

    def line(text: str, size: float = 10, style: str = '', color=BLACK, align: str = 'L', height: float = 5):
        pdf.set_font('Helvetica', style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(width, height, pdf_text(text), align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Header: the business on the left, the document's title, number and date on the right
    top = pdf.get_y()
    line(document.business_name, size=16, style='B', height=8)
    if document.business_location:
        line(document.business_location, size=9, color=GREY)
    after_business = pdf.get_y()
    pdf.set_xy(pdf.l_margin, top)
    line(title, size=16, style='B', align='R', height=8)
    line(document.number, size=9, color=GREY, align='R')
    when = 'Issued' if is_invoice else 'Paid'
    line(f'{when} {local(document.issued_at):%d %b %Y, %H:%M}', size=9, color=GREY, align='R')
    pdf.set_y(max(after_business, pdf.get_y()) + 6)

    if document.is_sandbox:
        line(f'TEST {title}: placed in the Chat Sandbox, not a real payment.', size=9, style='B', color=(180, 0, 0))
        pdf.ln(3)

    # Bill to
    line('BILLED TO', size=8, style='B', color=GREY)
    line(document.customer_name, size=11, style='B', height=6)
    if document.customer_phone:
        line(document.customer_phone, size=9)
    for label, value in document.details:
        line(f'{label}: {value}', size=9)
    pdf.ln(4)

    # Booking: what and when
    if document.booking:
        booking = document.booking
        start, end = local(booking.start), local(booking.end)
        line('BOOKING', size=8, style='B', color=GREY)
        line(booking.service, size=10, style='B')
        if booking.provider:
            line(f'With {booking.provider}', size=9)
        line(f'{start:%A, %d %B %Y}, {start:%H:%M} to {end:%H:%M}', size=9)
        pdf.ln(4)

    # The lines
    columns = (('Description', width * 0.52, 'L'), ('Qty', width * 0.10, 'R'), ('Unit price', width * 0.19, 'R'), ('Amount', width * 0.19, 'R'))
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*BLACK)
    pdf.set_fill_color(*LIGHT)
    for title, column_width, align in columns:
        pdf.cell(column_width, 7, title, align=align, fill=True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 9)
    for item in document.lines:
        values = (item.description, str(item.quantity), money(item.unit_price, document.currency), money(item.amount, document.currency))
        # A long description wraps onto more rows; the numbers stay on its first row.
        description = pdf_text(values[0])
        rows = len(pdf.multi_cell(columns[0][1], 6, description, dry_run=True, output='LINES'))
        if pdf.will_page_break(6 * rows):
            pdf.add_page()
        y = pdf.get_y()
        pdf.multi_cell(columns[0][1], 6, description, new_x=XPos.RIGHT, new_y=YPos.TOP)
        for value, (_, column_width, align) in zip(values[1:], columns[1:]):
            pdf.cell(column_width, 6, value, align=align)
        pdf.set_xy(pdf.l_margin, y + 6 * rows)
        pdf.set_draw_color(*LIGHT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())

    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(width * 0.81, 8, 'Amount due' if is_invoice else 'Total paid', align='R')
    pdf.cell(width * 0.19, 8, money(document.total, document.currency), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)

    if is_invoice:
        # How to pay, and what comes next: this is not a receipt yet.
        line('HOW TO PAY', size=8, style='B', color=GREY)
        if document.payment_url:
            pdf.set_font('Helvetica', 'U', 9)
            pdf.set_text_color(0, 0, 200)
            pdf.write(5, pdf_text(document.payment_url), link=document.payment_url)
            pdf.ln(7)
        else:
            line('Please contact the business to arrange payment.', size=9)
        line('This is an invoice, not a receipt. You will get a receipt once your payment is received.', size=9)
        pdf.ln(4)
    line(f'Payment reference: {document.payment_reference}', size=8, color=GREY)
    if not is_invoice:
        line(f'Thank you for your {document.kind}!', size=9)

    return bytes(pdf.output())


def object_name(doc_type: str, payment_reference: str) -> str:
    """Where the PDF goes in object storage: invoices/<reference>.pdf or receipts/<reference>.pdf, one
    of each per payment, so a repeated event overwrites it."""
    return f'{doc_type}s/{payment_reference}.pdf'
