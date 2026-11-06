"""What the customer is told (app/notifications.py), with fake senders: the invoice and the receipt each
have their own wording."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

from app import notifications
from app.documents import BOOKING, INVOICE, ORDER, RECEIPT, Booking, Document, DocumentLine
from app.email_sender import EmailError
from app.whatsapp_sender import SendError

PAY_URL = 'https://checkout.xendit.example/pay/abc123'


def make_document(kind=ORDER, doc_type=RECEIPT, phone='+6591234567', email='daniel@example.com', is_sandbox=False, payment_url=''):
    prefix = 'INV' if doc_type == INVOICE else 'RCT'
    return Document(
        number=f'{prefix}-O-000012' if kind == ORDER else f'{prefix}-B-000028', doc_type=doc_type, kind=kind,
        issued_at=datetime(2026, 10, 1, tzinfo=UTC), payment_reference='a' * 32, business_name='Kopi & Toast',
        business_location='', customer_name='Daniel', customer_phone=phone, details=(),
        lines=(DocumentLine('Kopi C', 2, Decimal('1.80')),), currency='SGD',
        customer_email=email, is_sandbox=is_sandbox, payment_url=payment_url,
        booking=Booking('Portrait shoot', 'Bob', datetime(2026, 10, 12, 2, tzinfo=UTC), datetime(2026, 10, 12, 3, tzinfo=UTC))
        if kind == BOOKING else None,
    )


def make_invoice(**kwargs):
    return make_document(doc_type=INVOICE, payment_url=kwargs.pop('payment_url', PAY_URL), **kwargs)


class InvoiceWordingTests(unittest.TestCase):
    """The invoice: you've placed it, here is what to pay."""

    def test_the_whatsapp_message_has_the_amount_to_pay_and_where(self):
        text = notifications.message_text(make_invoice(), 'pending_payment', 'https://signed/inv.pdf')
        for wanted in ('Hi Daniel', 'your invoice INV-O-000012', 'Order: 2 × Kopi C', 'Amount to pay: SGD 3.60',
                       f'Pay here: {PAY_URL}', 'Invoice (PDF): https://signed/inv.pdf', "We'll send you a receipt once"):
            self.assertIn(wanted, text)
        self.assertNotIn('we received your payment', text)
        self.assertNotIn('Your receipt', text)

    def test_without_a_payment_link_or_pdf_link_those_lines_are_left_out(self):
        text = notifications.message_text(make_invoice(payment_url=''), 'pending_payment')
        self.assertNotIn('Pay here', text)
        self.assertNotIn('Invoice (PDF)', text)
        self.assertIn('Amount to pay: SGD 3.60', text)

    def test_a_booking_says_what_and_when_in_local_time(self):
        text = notifications.message_text(make_invoice(kind=BOOKING), 'pending_payment')
        self.assertIn('Booking: Portrait shoot with Bob, Monday, 12 October 2026, 10:00 to 11:00', text)  # Singapore time
        self.assertIn('thank you for your booking with Kopi & Toast', text)

    def test_a_long_order_is_summarised(self):
        document = make_invoice()
        lines = tuple(DocumentLine(f'Item {i}', 1, Decimal('1.00')) for i in range(8))
        text = notifications.message_text(Document(**{**document.__dict__, 'lines': lines}), 'pending_payment')
        self.assertIn('Item 4, and 3 more', text)

    def test_the_email(self):
        subject, text = notifications.email_subject_and_text(make_invoice())
        self.assertEqual(subject, 'Invoice for your order with Kopi & Toast: SGD 3.60 to pay')
        for wanted in ('Hi Daniel,', 'Your invoice (INV-O-000012) is attached to this email as a PDF', 'Order: 2 × Kopi C',
                       'Amount to pay: SGD 3.60', f'Pay online: {PAY_URL}', "Once we receive your payment, we'll send you a receipt"):
            self.assertIn(wanted, text)
        self.assertNotIn('has received your payment', text)
        self.assertNotIn('Your receipt', text)

    def test_the_email_without_a_payment_link(self):
        _, text = notifications.email_subject_and_text(make_invoice(payment_url=''))
        self.assertNotIn('Pay online', text)


class ReceiptWordingTests(unittest.TestCase):
    """The receipt: your payment is received."""

    def test_the_whatsapp_message(self):
        text = notifications.message_text(make_document(), 'payment_received', 'https://signed/rct.pdf')
        for wanted in ('Hi Daniel', 'we received your payment of SGD 3.60 for your order', 'Your receipt: RCT-O-000012',
                       'Receipt (PDF): https://signed/rct.pdf'):
            self.assertIn(wanted, text)
        for unwanted in ('invoice', 'Amount to pay', 'Pay here'):
            self.assertNotIn(unwanted, text.lower() if unwanted == 'invoice' else text)

    def test_received_without_a_link_has_no_dangling_pdf_line(self):
        text = notifications.message_text(make_document(), 'payment_received', None)
        self.assertIn('Your receipt: RCT-O-000012', text)
        self.assertNotIn('Receipt (PDF)', text)

    def test_a_booking_says_booking(self):
        self.assertIn('your booking', notifications.message_text(make_document(BOOKING), 'payment_received'))

    def test_the_email(self):
        subject, text = notifications.email_subject_and_text(make_document())
        self.assertEqual(subject, 'Payment received: your order with Kopi & Toast')
        for wanted in ('Hi Daniel,', 'Kopi & Toast has received your payment of SGD 3.60 for your order.',
                       'Your receipt (RCT-O-000012) is attached'):
            self.assertIn(wanted, text)
        for unwanted in ('invoice', 'Amount to pay', 'Pay online'):
            self.assertNotIn(unwanted, text.lower() if unwanted == 'invoice' else text)

    def test_a_booking_email_says_what_and_when_in_local_time(self):
        subject, text = notifications.email_subject_and_text(make_document(BOOKING))
        self.assertIn('your booking with Kopi & Toast', subject)
        self.assertIn('Your booking: Portrait shoot with Bob, Monday, 12 October 2026, 10:00 to 11:00.', text)


class FailedPaymentTests(unittest.TestCase):
    def test_whatsapp_says_it_failed_and_has_no_links(self):
        text = notifications.message_text(make_document(), 'payment_failed', 'https://ignored')
        self.assertIn("didn't go through", text)
        self.assertNotIn('https://', text)


class MessageCustomerTests(unittest.TestCase):
    def test_sends_to_the_customers_number_from_their_business(self):
        with mock.patch('app.whatsapp_sender.send_text', return_value='wamid.1') as send:
            self.assertTrue(notifications.message_customer(7, make_invoice(), 'pending_payment', 'https://l'))
        business_id, to, text = send.call_args.args
        self.assertEqual((business_id, to), (7, '+6591234567'))
        self.assertIn('Amount to pay', text)

    def test_no_phone_number_means_nothing_is_sent(self):
        with mock.patch('app.whatsapp_sender.send_text') as send:
            self.assertFalse(notifications.message_customer(7, make_invoice(phone=''), 'pending_payment'))
        send.assert_not_called()

    def test_a_refusal_is_logged_not_raised(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('window closed', retryable=False)):
            self.assertFalse(notifications.message_customer(7, make_document(), 'payment_received'))

    def test_a_temporary_failure_is_raised_so_the_event_is_redelivered(self):
        with mock.patch('app.whatsapp_sender.send_text', side_effect=SendError('down', retryable=True)), \
                self.assertRaises(SendError):
            notifications.message_customer(7, make_document(), 'payment_received')


class EmailCustomerTests(unittest.TestCase):
    def email(self, document=None, status='payment_received', pdf=b'%PDF-x', **send_kwargs):
        with mock.patch('app.email_sender.send_email', **send_kwargs) as send:
            result = notifications.email_customer(document or make_document(), status, pdf)
        return result, send

    def test_the_receipt_is_sent_attached(self):
        sent, send = self.email(return_value=True)
        self.assertTrue(sent)
        subject, text, to = send.call_args.args
        attachment = send.call_args.kwargs['attachments'][0]
        self.assertEqual((to, subject), ('daniel@example.com', 'Payment received: your order with Kopi & Toast'))
        self.assertEqual((attachment.filename, attachment.data, attachment.mime_type), ('RCT-O-000012.pdf', b'%PDF-x', 'application/pdf'))

    def test_the_invoice_is_sent_attached(self):
        sent, send = self.email(make_invoice(), 'pending_payment', return_value=True)
        self.assertTrue(sent)
        subject, text, to = send.call_args.args
        attachment = send.call_args.kwargs['attachments'][0]
        self.assertTrue(subject.startswith('Invoice for your order'))
        self.assertEqual(attachment.filename, 'INV-O-000012.pdf')

    def test_email_switched_off_is_not_sent(self):
        sent, send = self.email(return_value=False)  # send_email logs and returns False when EMAIL_ENABLED is off
        self.assertFalse(sent)
        send.assert_called_once()

    def test_when_nothing_is_emailed(self):
        cases = {
            'a failed payment': dict(status='payment_failed'),
            'no PDF': dict(pdf=None),
            'no email address': dict(document=make_document(email='')),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                sent, send = self.email(**kwargs)
                self.assertFalse(sent)
                send.assert_not_called()

    def test_a_chat_sandbox_customer_is_emailed_too(self):
        for document, status in ((make_invoice(is_sandbox=True, phone=''), 'pending_payment'),
                                 (make_document(is_sandbox=True, phone=''), 'payment_received')):
            with self.subTest(status):
                sent, send = self.email(document, status, return_value=True)
                self.assertTrue(sent)
                self.assertEqual(send.call_args.args[2], 'daniel@example.com')

    def test_a_refusal_is_logged_not_raised(self):
        sent, _ = self.email(side_effect=EmailError('mailbox does not exist', retryable=False))
        self.assertFalse(sent)

    def test_a_temporary_failure_is_raised_so_the_event_is_redelivered(self):
        with mock.patch('app.email_sender.send_email', side_effect=EmailError('relay down', retryable=True)), \
                self.assertRaises(EmailError):
            notifications.email_customer(make_document(), 'payment_received', b'%PDF-x')


class NotifyCustomerTests(unittest.TestCase):
    def tell(self, whatsapp=None, email=None, document=None, status='payment_received'):
        with mock.patch('app.whatsapp_sender.send_text', **(whatsapp or {'return_value': 'wamid.1'})) as send_text, \
                mock.patch('app.email_sender.send_email', **(email or {'return_value': True})) as send_email:
            try:
                notifications.notify_customer(7, document or make_document(), status, 'https://l', b'%PDF-x')
            finally:
                self.send_text, self.send_email = send_text, send_email

    def test_both_channels_for_a_receipt(self):
        self.tell()
        self.send_text.assert_called_once()
        self.send_email.assert_called_once()
        self.assertIn('we received your payment', self.send_text.call_args.args[2])
        self.assertTrue(self.send_email.call_args.args[0].startswith('Payment received'))

    def test_both_channels_for_an_invoice(self):
        self.tell(document=make_invoice(), status='pending_payment')
        self.assertIn('Amount to pay', self.send_text.call_args.args[2])
        self.assertTrue(self.send_email.call_args.args[0].startswith('Invoice for your order'))

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
