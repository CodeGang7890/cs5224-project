"""The invoice for a paid order or booking: its data, then a PDF.

Two steps, so each can be tested on its own:
1. build_invoice(session, item): reads what the invoice shows (the business, the customer, the
   lines) from the order / booking and the rows it points to, into an Invoice.
2. render_pdf(invoice): the PDF, as bytes. No database, no files: the caller decides where it goes
   (object storage, later; a local file in scripts/preview_invoice.py).

"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.orm import Session

from . import config
from .models import BusinessConfiguration, ChatSession, OrderItem, ScheduleItem, ServiceProvider

ORDER, BOOKING = 'order', 'booking'


@dataclass(frozen=True)
class InvoiceLine:
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
class Invoice:
    number: str
    kind: str  # ORDER or BOOKING
    issued_at: datetime
    payment_reference: str
    business_name: str
    business_location: str
    customer_name: str
    customer_phone: str
    details: tuple[tuple[str, str], ...]
    lines: tuple[InvoiceLine, ...]
    currency: str
    booking: Booking | None = None
    is_sandbox: bool = False

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal('0.00'))


def invoice_number(kind: str, item_id: int) -> str:
    """INV-O-000012 for order #12, INV-B-000028 for booking #28"""
    return f'INV-{kind[0].upper()}-{item_id:06d}'


def aware(moment: datetime) -> datetime:
    """PostgreSQL returns aware datetimes, SQLite (tests) naive ones, which are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def detail_label(key: str) -> str:
    """'pickup_time' → 'Pickup time'."""
    return key.replace('_', ' ').strip().capitalize()


def build_invoice(session: Session, item: OrderItem | ScheduleItem, issued_at: datetime | None = None) -> Invoice:
    """The invoice for this order / booking. `issued_at` defaults to its updated_time: when the
    payment was applied."""
    kind = ORDER if isinstance(item, OrderItem) else BOOKING
    data = (item.order_data if kind == ORDER else item.schedule_data) or {}
    details = dict(data.get('details') or {})

    business = session.get(BusinessConfiguration, item.business_id)
    chat = session.get(ChatSession, item.chat_session_id) if item.chat_session_id else None
    customer_name = str(details.pop('name', '') or (chat.display_name if chat else '') or 'Customer')

    booking = None
    if kind == ORDER:
        lines = tuple(
            InvoiceLine(str(line['name']), int(line['quantity']), Decimal(str(line['unit_price'])))
            for line in data.get('items', [])
        )
    else:
        service = data.get('service') or {}
        name = str(service.get('name') or 'Booking')
        provider = session.get(ServiceProvider, item.service_provider_id) if item.service_provider_id else None
        booking = Booking(name, provider.name if provider else '', aware(item.start_time), aware(item.end_time))
        lines = (InvoiceLine(name, 1, Decimal(str(service.get('price', '0.00')))),)

    return Invoice(
        number=invoice_number(kind, item.id),
        kind=kind,
        issued_at=aware(issued_at or item.updated_time),
        payment_reference=item.payment_reference,
        business_name=business.business_name if business else f'Business #{item.business_id}',
        business_location=business.location if business else '',
        customer_name=customer_name,
        customer_phone=chat.phone_number if chat else '',
        details=tuple((detail_label(key), str(value)) for key, value in details.items()),
        lines=lines,
        currency=config.INVOICE_CURRENCY,
        booking=booking,
        is_sandbox=item.is_sandbox,
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


class _InvoicePDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(*GREY)
        self.cell(0, 5, f'Page {self.page_no()}', align='C')


def render_pdf(invoice: Invoice) -> bytes:
    pdf = _InvoicePDF(format='A4')
    pdf.set_title(pdf_text(f'Invoice {invoice.number}'))
    pdf.set_author(pdf_text(invoice.business_name))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    width = pdf.epw

    def line(text: str, size: float = 10, style: str = '', color=BLACK, align: str = 'L', height: float = 5):
        pdf.set_font('Helvetica', style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(width, height, pdf_text(text), align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Header: the business on the left, the invoice's number and date on the right
    top = pdf.get_y()
    line(invoice.business_name, size=16, style='B', height=8)
    if invoice.business_location:
        line(invoice.business_location, size=9, color=GREY)
    after_business = pdf.get_y()
    pdf.set_xy(pdf.l_margin, top)
    line('INVOICE', size=16, style='B', align='R', height=8)
    line(invoice.number, size=9, color=GREY, align='R')
    line(f'Paid {local(invoice.issued_at):%d %b %Y, %H:%M}', size=9, color=GREY, align='R')
    pdf.set_y(max(after_business, pdf.get_y()) + 6)

    if invoice.is_sandbox:
        line('TEST INVOICE: placed in the Chat Sandbox, not a real payment.', size=9, style='B', color=(180, 0, 0))
        pdf.ln(3)

    # Bill to
    line('BILLED TO', size=8, style='B', color=GREY)
    line(invoice.customer_name, size=11, style='B', height=6)
    if invoice.customer_phone:
        line(invoice.customer_phone, size=9)
    for label, value in invoice.details:
        line(f'{label}: {value}', size=9)
    pdf.ln(4)

    # Booking: what and when
    if invoice.booking:
        booking = invoice.booking
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
    for item in invoice.lines:
        values = (item.description, str(item.quantity), money(item.unit_price, invoice.currency), money(item.amount, invoice.currency))
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
    pdf.cell(width * 0.81, 8, 'Total paid', align='R')
    pdf.cell(width * 0.19, 8, money(invoice.total, invoice.currency), align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)

    line(f'Payment reference: {invoice.payment_reference}', size=8, color=GREY)
    line(f'Thank you for your {invoice.kind}!', size=9)

    return bytes(pdf.output())


def object_name(payment_reference: str) -> str:
    """Where the PDF goes in object storage: one per payment, so a repeated event overwrites it."""
    return f'invoices/{payment_reference}.pdf'
