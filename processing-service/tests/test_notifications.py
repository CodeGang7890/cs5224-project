"""The customer's WhatsApp message (app/notifications.py), with a fake sender."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

from app import notifications
from app.invoice import BOOKING, ORDER, Invoice, InvoiceLine
from app.whatsapp_sender import SendError


def make_invoice(kind=ORDER, phone='+6591234567'):
    return Invoice(
        number='INV-O-000012' if kind == ORDER else 'INV-B-000028', kind=kind, issued_at=datetime(2026, 10, 1, tzinfo=UTC),
        payment_reference='a' * 32, business_name='Kopi & Toast', business_location='', customer_name='Daniel',
        customer_phone=phone, details=(), lines=(InvoiceLine('Kopi C', 2, Decimal('1.80')),), currency='SGD',
    )


class MessageTextTests(unittest.TestCase):
    def test_received_with_the_invoice_link(self):
        text = notifications.message_text(make_invoice(), 'payment_received', 'https://signed/x.pdf')
        self.assertIn('Hi Daniel', text)
        self.assertIn('SGD 3.60', text)
        self.assertIn('INV-O-000012', text)
        self.assertTrue(text.endswith('Your invoice: https://signed/x.pdf'))

    def test_received_without_a_link_has_no_dangling_invoice_line(self):
        self.assertNotIn('invoice:', notifications.message_text(make_invoice(), 'payment_received', None))

    def test_a_booking_says_booking(self):
        self.assertIn('your booking', notifications.message_text(make_invoice(BOOKING), 'payment_received'))

    def test_failed(self):
        text = notifications.message_text(make_invoice(), 'payment_failed', 'https://ignored')
        self.assertIn("didn't go through", text)
        self.assertNotIn('https://', text)


class NotifyCustomerTests(unittest.TestCase):
    def test_sends_to_the_customers_number_from_their_business(self):
        with mock.patch('app.whatsapp_sender.send_text', return_value='wamid.1') as send:
            self.assertTrue(notifications.notify_customer(7, make_invoice(), 'payment_received', 'https://l'))
        business_id, to, text = send.call_args.args
        self.assertEqual((business_id, to), (7, '+6591234567'))
        self.assertIn('https://l', text)

    def test_no_phone_number_means_nothing_is_sent(self):
        with mock.patch('app.whatsapp_sender.send_text') as send:
            self.assertFalse(notifications.notify_customer(7, make_invoice(phone=''), 'payment_received'))
        send.assert_not_called()

    def test_a_refusal_is_logged_not_raised(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('window closed', retryable=False)):
            self.assertFalse(notifications.notify_customer(7, make_invoice(), 'payment_received'))

    def test_a_temporary_failure_is_raised_so_the_event_is_redelivered(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('down', retryable=True)), \
                self.assertRaises(SendError):
            notifications.notify_customer(7, make_invoice(), 'payment_received')
