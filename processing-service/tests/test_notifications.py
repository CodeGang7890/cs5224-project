"""The customer's WhatsApp message (app/notifications.py), with a fake sender."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

from app import notifications
from app.email_sender import EmailError
from app.invoice import BOOKING, ORDER, Booking, Invoice, InvoiceLine
from app.whatsapp_sender import SendError


def make_invoice(kind=ORDER, phone='+6591234567', email='daniel@example.com', is_sandbox=False):
    return Invoice(
        number='INV-O-000012' if kind == ORDER else 'INV-B-000028', kind=kind, issued_at=datetime(2026, 10, 1, tzinfo=UTC),
        payment_reference='a' * 32, business_name='Kopi & Toast', business_location='', customer_name='Daniel',
        customer_phone=phone, details=(), lines=(InvoiceLine('Kopi C', 2, Decimal('1.80')),), currency='SGD',
        customer_email=email, is_sandbox=is_sandbox,
        booking=Booking('Portrait shoot', 'Bob', datetime(2026, 10, 12, 2, tzinfo=UTC), datetime(2026, 10, 12, 3, tzinfo=UTC))
        if kind == BOOKING else None,
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


class MessageCustomerTests(unittest.TestCase):
    def test_sends_to_the_customers_number_from_their_business(self):
        with mock.patch('app.whatsapp_sender.send_text', return_value='wamid.1') as send:
            self.assertTrue(notifications.message_customer(7, make_invoice(), 'payment_received', 'https://l'))
        business_id, to, text = send.call_args.args
        self.assertEqual((business_id, to), (7, '+6591234567'))
        self.assertIn('https://l', text)

    def test_no_phone_number_means_nothing_is_sent(self):
        with mock.patch('app.whatsapp_sender.send_text') as send:
            self.assertFalse(notifications.message_customer(7, make_invoice(phone=''), 'payment_received'))
        send.assert_not_called()

    def test_a_refusal_is_logged_not_raised(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('window closed', retryable=False)):
            self.assertFalse(notifications.message_customer(7, make_invoice(), 'payment_received'))

    def test_a_temporary_failure_is_raised_so_the_event_is_redelivered(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('down', retryable=True)), \
                self.assertRaises(SendError):
            notifications.message_customer(7, make_invoice(), 'payment_received')


class EmailTextTests(unittest.TestCase):
    def test_an_order(self):
        subject, text = notifications.email_subject_and_text(make_invoice())
        self.assertEqual(subject, 'Payment received: your order with Kopi & Toast')
        self.assertIn('Hi Daniel,', text)
        self.assertIn('Kopi & Toast has received your payment of SGD 3.60 for your order.', text)
        self.assertIn('Your invoice (INV-O-000012) is attached', text)
        self.assertNotIn('Your booking', text)

    def test_a_booking_says_what_and_when_in_local_time(self):
        subject, text = notifications.email_subject_and_text(make_invoice(BOOKING))
        self.assertIn('your booking with Kopi & Toast', subject)
        self.assertIn('Your booking: Portrait shoot with Bob, Monday, 12 October 2026, 10:00 to 11:00.', text)  # Singapore time


class EmailCustomerTests(unittest.TestCase):
    def email(self, invoice=None, status='payment_received', pdf=b'%PDF-x', **send_kwargs):
        with mock.patch('app.email_sender.send_email', **send_kwargs) as send:
            result = notifications.email_customer(invoice or make_invoice(), status, pdf)
        return result, send

    def test_sends_the_invoice_attached(self):
        sent, send = self.email(return_value=True)
        self.assertTrue(sent)
        subject, text, to = send.call_args.args
        attachment = send.call_args.kwargs['attachments'][0]
        self.assertEqual(to, 'daniel@example.com')
        self.assertEqual((attachment.filename, attachment.data, attachment.mime_type), ('INV-O-000012.pdf', b'%PDF-x', 'application/pdf'))

    def test_email_switched_off_is_not_sent(self):
        sent, send = self.email(return_value=False)
        self.assertFalse(sent)
        send.assert_called_once()

    def test_when_nothing_is_emailed(self):
        cases = {
            'a failed payment': dict(status='payment_failed'),
            'no invoice PDF': dict(pdf=None),
            'no email address': dict(invoice=make_invoice(email='')),
            'a sandbox customer': dict(invoice=make_invoice(is_sandbox=True)),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                sent, send = self.email(**kwargs)
                self.assertFalse(sent)
                send.assert_not_called()

    def test_a_refusal_is_logged_not_raised(self):
        sent, _ = self.email(side_effect=EmailError('mailbox does not exist', retryable=False))
        self.assertFalse(sent)

    def test_a_temporary_failure_is_raised_so_the_event_is_redelivered(self):
        with mock.patch('app.email_sender.send_email', side_effect=EmailError('relay down', retryable=True)), \
                self.assertRaises(EmailError):
            notifications.email_customer(make_invoice(), 'payment_received', b'%PDF-x')


class NotifyCustomerTests(unittest.TestCase):
    def tell(self, whatsapp=None, email=None):
        with mock.patch('app.whatsapp_sender.send_text', **(whatsapp or {'return_value': 'wamid.1'})) as send_text, \
                mock.patch('app.email_sender.send_email', **(email or {'return_value': True})) as send_email:
            try:
                notifications.notify_customer(7, make_invoice(), 'payment_received', 'https://l', b'%PDF-x')
            finally:
                self.send_text, self.send_email = send_text, send_email

    def test_both_channels(self):
        self.tell()
        self.send_text.assert_called_once()
        self.send_email.assert_called_once()

    def test_a_whatsapp_failure_does_not_stop_the_email_but_is_raised_afterwards(self):
        with self.assertRaises(SendError):
            self.tell(whatsapp={'side_effect': SendError('down', retryable=True)})
        self.send_email.assert_called_once()

    def test_an_email_failure_does_not_stop_whatsapp_but_is_raised_afterwards(self):
        with self.assertRaises(EmailError):
            self.tell(email={'side_effect': EmailError('relay down', retryable=True)})
        self.send_text.assert_called_once()

    def test_refusals_on_both_channels_are_not_raised(self):
        self.tell(whatsapp={'side_effect': SendError('window closed', retryable=False)},
                  email={'side_effect': EmailError('no such mailbox', retryable=False)})
