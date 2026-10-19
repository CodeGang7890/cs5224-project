import unittest
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import invoice
from app.models import Base, BusinessConfiguration, ChatSession, OrderItem, ScheduleItem, ServiceProvider

NOW = datetime(2026, 10, 1, 4, 5, tzinfo=UTC)
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


class InvoiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.session = sessionmaker(engine)()
        self.addCleanup(self.session.close)
        self.session.add_all([
            BusinessConfiguration(id=1, business_name='Kopi & Toast', location='1 Raffles Place'),
            ChatSession(id=1, phone_number='+6591234567', display_name='Daniel'),
            ServiceProvider(id=1, name='Mei Lin'),
            OrderItem(id=12, business_id=1, chat_session_id=1, is_sandbox=False, order_data=ORDER_DATA,
                      order_status='payment_received', payment_reference='a' * 32, updated_time=NOW),
            ScheduleItem(id=28, business_id=1, chat_session_id=1, is_sandbox=True, service_provider_id=1,
                         start_time=datetime(2026, 10, 12, 2, tzinfo=UTC), end_time=datetime(2026, 10, 12, 3, tzinfo=UTC),
                         blocked_until=datetime(2026, 10, 12, 3, 15, tzinfo=UTC), schedule_data=SCHEDULE_DATA,
                         order_status='payment_received', payment_reference='b' * 32, updated_time=NOW),
        ])
        self.session.commit()

    def test_an_order_invoice(self):
        built = invoice.build_invoice(self.session, self.session.get(OrderItem, 12))
        self.assertEqual(built.number, 'INV-O-000012')
        self.assertEqual(built.total, Decimal('14.60'))
        self.assertEqual(built.customer_name, 'Daniel <b>Ong</b> & Co')  # `name` in the details wins
        self.assertEqual(built.details, (('Pickup time', '8:45am'),))  # and isn't repeated
        self.assertEqual((built.business_name, built.customer_phone), ('Kopi & Toast', '+6591234567'))
        self.assertIsNone(built.booking)

    def test_a_booking_invoice(self):
        built = invoice.build_invoice(self.session, self.session.get(ScheduleItem, 28))
        self.assertEqual(built.number, 'INV-B-000028')
        self.assertEqual(built.total, Decimal('180.00'))
        self.assertEqual(built.customer_name, 'Daniel')  # no `name` detail: the chat's display name
        self.assertEqual((built.booking.service, built.booking.provider), ('Portrait shoot', 'Mei Lin'))
        self.assertTrue(built.is_sandbox)

    def test_the_customer_email_comes_from_the_email_detail(self):
        order = self.session.get(OrderItem, 12)
        for details, expected in [
            ({'name': 'Daniel', 'email': 'daniel@example.com'}, 'daniel@example.com'),
            ({'Email': ' daniel@example.com '}, 'daniel@example.com'),
            ({'email': 'not an address'}, ''),
            ({'email': 'a@b.com\r\nBcc: x@y.z'}, ''),
            ({'pickup_time': '8:45am'}, ''),
        ]:
            with self.subTest(details=details):
                order.order_data = {**ORDER_DATA, 'details': details}
                self.assertEqual(invoice.build_invoice(self.session, order).customer_email, expected)

    def test_a_deleted_chat_and_provider_are_fine(self):
        order = self.session.get(OrderItem, 12)
        order.chat_session_id = None
        booking = self.session.get(ScheduleItem, 28)
        booking.chat_session_id, booking.service_provider_id = None, None
        built = invoice.build_invoice(self.session, booking)
        self.assertEqual((built.customer_name, built.customer_phone, built.booking.provider), ('Customer', '', ''))
        self.assertEqual(invoice.build_invoice(self.session, order).customer_phone, '')

    def test_renders_a_pdf_for_both_kinds(self):
        for item in (self.session.get(OrderItem, 12), self.session.get(ScheduleItem, 28)):
            self.assertTrue(invoice.render_pdf(invoice.build_invoice(self.session, item)).startswith(b'%PDF'))

    def test_text_outside_latin_1_does_not_break_the_pdf(self):
        self.assertEqual(invoice.pdf_text('Café “Kopi” – 咖啡 😀'), 'Café "Kopi" - ?? ?')
        order = self.session.get(OrderItem, 12)
        order.order_data = {**ORDER_DATA, 'details': {'name': '李小龍 😀'}}
        self.assertTrue(invoice.render_pdf(invoice.build_invoice(self.session, order)).startswith(b'%PDF'))

    def test_many_and_long_lines_still_render(self):
        built = invoice.build_invoice(self.session, self.session.get(OrderItem, 12))
        lines = tuple(invoice.InvoiceLine(f'Item {i} ' + 'very long description ' * 6, 1, Decimal('1.00')) for i in range(80))
        pdf = invoice.render_pdf(invoice.Invoice(**{**built.__dict__, 'lines': lines}))
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_the_object_name_is_per_payment(self):
        self.assertEqual(invoice.object_name('a' * 32), f'invoices/{"a" * 32}.pdf')
