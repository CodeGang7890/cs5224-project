"""The invoice and the receipt (app/documents.py): their data from the rows, and their PDFs. SQLite in memory."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

from fpdf import FPDF
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import documents
from app.documents import INVOICE, RECEIPT
from app.models import Base, BusinessConfiguration, ChatSession, OrderItem, ScheduleItem, ServiceProvider, WhatsAppConfiguration

PLACED = datetime(2026, 9, 30, 4, 5, tzinfo=UTC)  # when the order was placed (the invoice's date)
PAID = datetime(2026, 10, 1, 4, 5, tzinfo=UTC)  # when it was paid (the receipt's date)
ORDER_DATA = {
    'items': [
        {'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2},
        {'product_id': 2, 'name': 'Kaya Toast Set', 'unit_price': '5.50', 'quantity': 2},
    ],
    'details': {'name': 'Daniel <b>Ong</b> & Co', 'pickup_time': '8:45am'},
}
SCHEDULE_DATA = {
    'service': {'service_id': 1, 'name': 'Portrait shoot', 'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 15},
    'details': {'email': 'alice@example.com'},
}
PAY_URL = 'https://checkout.xendit.example/pay/abc123'


def pdf_texts(document) -> str:
    """Every piece of text drawn on the PDF (its content streams are compressed, so record the calls)."""
    drawn = []

    def recording(original, text_position):
        def wrapper(self, *args, **kwargs):
            text = kwargs.get('text', args[text_position] if len(args) > text_position else '')
            drawn.append(str(text))
            return original(self, *args, **kwargs)
        return wrapper

    with mock.patch.object(FPDF, 'multi_cell', recording(FPDF.multi_cell, 2)), \
            mock.patch.object(FPDF, 'cell', recording(FPDF.cell, 2)), \
            mock.patch.object(FPDF, 'write', recording(FPDF.write, 1)):
        documents.render_pdf(document)
    return '\n'.join(drawn)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)  # tests only: configuration-service owns the real schema
        self.session = sessionmaker(engine)()
        self.addCleanup(self.session.close)
        self.session.add_all([
            BusinessConfiguration(id=1, business_name='Kopi & Toast', location='1 Raffles Place'),
            BusinessConfiguration(id=2, business_name='No WhatsApp Yet', location=''),
            WhatsAppConfiguration(id=1, business_id=1, display_phone_number='+65 9123 4567'),
            ChatSession(id=1, phone_number='+6591234567', display_name='Daniel'),
            ServiceProvider(id=1, name='Mei Lin'),
            OrderItem(id=12, business_id=1, chat_session_id=1, is_sandbox=False, order_data=ORDER_DATA,
                      order_status='pending_payment', payment_reference='a' * 32, created_time=PLACED, updated_time=PAID),
            ScheduleItem(id=28, business_id=1, chat_session_id=1, is_sandbox=True, service_provider_id=1,
                         start_time=datetime(2026, 10, 12, 2, tzinfo=UTC), end_time=datetime(2026, 10, 12, 3, tzinfo=UTC),
                         blocked_until=datetime(2026, 10, 12, 3, 15, tzinfo=UTC), schedule_data=SCHEDULE_DATA,
                         order_status='pending_payment', payment_reference='b' * 32, created_time=PLACED, updated_time=PAID),
        ])
        self.session.commit()
        self.order = self.session.get(OrderItem, 12)
        self.booking = self.session.get(ScheduleItem, 28)

    def build(self, item, doc_type=RECEIPT, **kwargs):
        return documents.build_document(self.session, item, doc_type, **kwargs)

    # --- what each document is called, and dated --------------------------------------------------

    def test_an_invoice_and_a_receipt_have_their_own_numbers_and_dates(self):
        for doc_type, order_number, booking_number, issued in (
            (INVOICE, 'INV-O-000012', 'INV-B-000028', PLACED),
            (RECEIPT, 'RCT-O-000012', 'RCT-B-000028', PAID),
        ):
            with self.subTest(doc_type):
                order, booking = self.build(self.order, doc_type), self.build(self.booking, doc_type)
                self.assertEqual((order.number, booking.number), (order_number, booking_number))
                self.assertEqual(order.issued_at, issued)  # an invoice: when it was placed; a receipt: when it was paid
                self.assertEqual(order.doc_type, doc_type)

    def test_only_an_invoice_carries_the_payment_link(self):
        self.assertEqual(self.build(self.order, INVOICE, payment_url=PAY_URL).payment_url, PAY_URL)
        self.assertEqual(self.build(self.order, RECEIPT, payment_url=PAY_URL).payment_url, '')

    def test_the_object_name_is_per_document_and_payment(self):
        self.assertEqual(documents.object_name(INVOICE, 7, 'a' * 32), f'invoices/7/{"a" * 32}.pdf')
        self.assertEqual(documents.object_name(RECEIPT, 7, 'a' * 32), f'receipts/7/{"a" * 32}.pdf')

    # --- the data ---------------------------------------------------------------------------------

    def test_an_order(self):
        built = self.build(self.order)
        self.assertEqual(built.total, Decimal('14.60'))
        self.assertEqual(built.customer_name, 'Daniel <b>Ong</b> & Co')  # `name` in the details wins
        self.assertEqual(built.details, (('Pickup time', '8:45am'),))  # and isn't repeated
        self.assertEqual((built.business_name, built.customer_phone), ('Kopi & Toast', '+6591234567'))
        self.assertIsNone(built.booking)

    def test_the_business_whatsapp_number_is_read_when_it_has_a_connection(self):
        self.assertEqual(self.build(self.order).business_whatsapp, '+65 9123 4567')
        self.order.business_id = 2  # a business that never connected WhatsApp
        self.assertEqual(self.build(self.order).business_whatsapp, '')

    def test_a_booking(self):
        built = self.build(self.booking)
        self.assertEqual(built.total, Decimal('180.00'))
        self.assertEqual(built.customer_name, 'Daniel')  # no `name` detail: the chat's display name
        self.assertEqual((built.booking.service, built.booking.provider), ('Portrait shoot', 'Mei Lin'))
        self.assertTrue(built.is_sandbox)

    def test_the_customer_email_comes_from_the_email_detail(self):
        for details, expected in [
            ({'name': 'Daniel', 'email': 'daniel@example.com'}, 'daniel@example.com'),
            ({'Email': ' daniel@example.com '}, 'daniel@example.com'),
            ({'email': 'not an address'}, ''),
            ({'email': 'a@b.com\r\nBcc: x@y.z'}, ''),
            ({'pickup_time': '8:45am'}, ''),
        ]:
            with self.subTest(details=details):
                self.order.order_data = {**ORDER_DATA, 'details': details}
                self.assertEqual(self.build(self.order).customer_email, expected)

    def test_a_deleted_chat_and_provider_are_fine(self):
        self.order.chat_session_id = None
        self.booking.chat_session_id, self.booking.service_provider_id = None, None
        built = self.build(self.booking)
        self.assertEqual((built.customer_name, built.customer_phone, built.booking.provider), ('Customer', '', ''))
        self.assertEqual(self.build(self.order).customer_phone, '')

    # --- the PDFs ---------------------------------------------------------------------------------

    def test_renders_a_pdf_for_every_kind_and_type(self):
        for item in (self.order, self.booking):
            for doc_type in (INVOICE, RECEIPT):
                with self.subTest(item=type(item).__name__, doc_type=doc_type):
                    pdf = documents.render_pdf(self.build(item, doc_type, payment_url=PAY_URL))
                    self.assertTrue(pdf.startswith(b'%PDF'))

    def test_the_invoice_pdf_says_invoice_and_what_to_pay(self):
        text = pdf_texts(self.build(self.order, INVOICE, payment_url=PAY_URL))
        for wanted in ('INVOICE', 'INV-O-000012', 'Issued 30 Sep 2026', 'Amount due', 'SGD 14.60', 'HOW TO PAY', PAY_URL,
                       'This is an invoice, not a receipt'):
            self.assertIn(wanted, text)
        for unwanted in ('RECEIPT', 'RCT-', 'Total paid', 'Paid '):
            self.assertNotIn(unwanted, text)

    def test_the_receipt_pdf_says_receipt_and_paid(self):
        text = pdf_texts(self.build(self.order, RECEIPT, payment_url=PAY_URL))
        for wanted in ('RECEIPT', 'RCT-O-000012', 'Paid 01 Oct 2026', 'Total paid', 'SGD 14.60', 'Thank you for your order'):
            self.assertIn(wanted, text)
        for unwanted in ('INVOICE', 'INV-', 'Amount due', 'HOW TO PAY', PAY_URL):
            self.assertNotIn(unwanted, text)

    def test_an_invoice_without_a_payment_link_says_to_contact_the_business(self):
        text = pdf_texts(self.build(self.order, INVOICE))
        self.assertIn('Please contact the business to arrange payment.', text)

    def test_a_sandbox_document_says_it_is_a_test_of_its_own_kind(self):
        self.assertIn('TEST INVOICE', pdf_texts(self.build(self.booking, INVOICE)))
        self.assertIn('TEST RECEIPT', pdf_texts(self.build(self.booking, RECEIPT)))

    def test_text_outside_latin_1_does_not_break_the_pdf(self):
        self.assertEqual(documents.pdf_text('Café “Kopi” – 咖啡 😀'), 'Café "Kopi" - ?? ?')
        self.order.order_data = {**ORDER_DATA, 'details': {'name': '李小龍 😀'}}
        for doc_type in (INVOICE, RECEIPT):
            self.assertTrue(documents.render_pdf(self.build(self.order, doc_type)).startswith(b'%PDF'))

    def test_many_and_long_lines_still_render(self):
        built = self.build(self.order, INVOICE, payment_url=PAY_URL)
        lines = tuple(documents.DocumentLine(f'Item {i} ' + 'very long description ' * 6, 1, Decimal('1.00')) for i in range(80))
        pdf = documents.render_pdf(documents.Document(**{**built.__dict__, 'lines': lines}))
        self.assertTrue(pdf.startswith(b'%PDF'))
