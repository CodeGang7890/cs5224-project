"""The payment flow (app/payments.py), a draft: a couple of cases on in-memory SQLite."""

import unittest
from datetime import UTC, date, datetime
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import UNAVAILABLE_WEEK, Base, BusinessConfiguration, ChatSession, OrderItem, ScheduleItem, WeeklyAvailability
from app.payments import PaymentEventError, PaymentNotFoundError, apply_payment
from app.whatsapp_sender import SendError

ORDER_REFERENCE = 'a' * 32
BOOKING_REFERENCE = 'b' * 32
CHAT_ORDER_REFERENCE = 'd' * 32
ORDER_TOTAL = 3.60  # 2 × 1.80
BOOKING_TOTAL = 180.00
MONDAY = date(2026, 10, 12)
# Monday 10:00–11:00 (Singapore) is H (the booking), 11:00–11:30 its buffer (H), the rest of the
# morning open (O). Blocks are 15 minutes from Monday 00:00: 10:00 is block 40.
LETTERS = UNAVAILABLE_WEEK[:36] + 'OOOO' + 'HHHH' + 'HH' + 'OO' + UNAVAILABLE_WEEK[48:]
ORDER_DATA = {
    'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
    'details': {'name': 'Daniel Ong'},
}
SCHEDULE_DATA = {
    'service': {'service_id': 1, 'name': 'Portrait shoot', 'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 30},
    'details': {'name': 'Alice'},
}


class PaymentFlowTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)  # tests only: configuration-service owns the real schema
        self.sessions = sessionmaker(engine)
        now = datetime(2026, 10, 1, tzinfo=UTC)
        with self.sessions.begin() as session:
            session.add(BusinessConfiguration(id=1, business_name='Kopi & Toast', location='1 Raffles Place'))
            session.add(BusinessConfiguration(id=4, business_name='Studio', location='2 Orchard Road'))
            session.add(ChatSession(id=1, phone_number='+6591234567', display_name='Daniel'))
            session.add(OrderItem(id=2, business_id=1, chat_session_id=1, is_sandbox=False, order_data=ORDER_DATA, order_status='pending_payment', payment_reference=CHAT_ORDER_REFERENCE, updated_time=now))
            session.add(OrderItem(id=1, business_id=1, is_sandbox=False, order_data=ORDER_DATA, order_status='pending_payment', payment_reference=ORDER_REFERENCE, updated_time=now))
            session.add(ScheduleItem(
                id=1, business_id=4, is_sandbox=False, service_provider_id=1, schedule_data=SCHEDULE_DATA, order_status='pending_payment', payment_reference=BOOKING_REFERENCE,
                start_time=datetime(2026, 10, 12, 2, tzinfo=UTC),  # 10:00 in Singapore
                end_time=datetime(2026, 10, 12, 3, tzinfo=UTC),
                blocked_until=datetime(2026, 10, 12, 3, 30, tzinfo=UTC),
                updated_time=now,
            ))
            session.add(WeeklyAvailability(id=1, service_provider_id=1, week=MONDAY, availability=LETTERS))

    def test_a_paid_booking_takes_its_time_and_a_failed_order_frees_its_stock(self):
        with self.sessions() as session:
            booking = apply_payment(session, BOOKING_REFERENCE, 'success', BOOKING_TOTAL)
            order = apply_payment(session, ORDER_REFERENCE, 'fail', ORDER_TOTAL)
        self.assertEqual((booking.kind, booking.new_status), ('booking', 'payment_received'))
        self.assertEqual((order.kind, order.new_status), ('order', 'payment_failed'))
        with self.sessions() as session:
            self.assertEqual(session.get(ScheduleItem, 1).order_status, 'payment_received')
            self.assertEqual(session.get(OrderItem, 1).order_status, 'payment_failed')  # its stock is derived: freed
            letters = session.get(WeeklyAvailability, 1).availability
        self.assertEqual(letters[36:48], 'OOOO' + 'XXXX' + 'XX' + 'OO')  # duration and buffer H → X

    def test_a_paid_order_gets_its_invoice_uploaded(self):
        with mock.patch('app.storage.upload_invoice', return_value='gs://bucket/x.pdf') as upload, \
                mock.patch('app.storage.invoice_link', return_value='https://signed') as link, \
                self.sessions() as session:
            result = apply_payment(session, ORDER_REFERENCE, 'success', ORDER_TOTAL)
        pdf, object_name = upload.call_args.args
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(object_name, f'invoices/{ORDER_REFERENCE}.pdf')
        link.assert_called_once_with(f'invoices/{ORDER_REFERENCE}.pdf')
        self.assertEqual((result.invoice_uri, result.invoice_link), ('gs://bucket/x.pdf', 'https://signed'))

    def test_a_paid_booking_gets_its_invoice_uploaded(self):
        with mock.patch('app.storage.upload_invoice', return_value=None) as upload, self.sessions() as session:
            result = apply_payment(session, BOOKING_REFERENCE, 'success', BOOKING_TOTAL)
        self.assertEqual(upload.call_args.args[1], f'invoices/{BOOKING_REFERENCE}.pdf')
        self.assertIsNone(result.invoice_link)  # nothing uploaded (no bucket): nothing to link

    def test_a_failed_payment_makes_no_invoice(self):
        with mock.patch('app.storage.upload_invoice') as upload, self.sessions() as session:
            apply_payment(session, ORDER_REFERENCE, 'fail', ORDER_TOTAL)
        upload.assert_not_called()

    def test_a_successful_payment_without_an_amount_is_rejected(self):
        with self.sessions() as session, self.assertRaises(PaymentEventError):
            apply_payment(session, ORDER_REFERENCE, 'success')
        with self.sessions() as session:
            self.assertEqual(session.get(OrderItem, 1).order_status, 'pending_payment')

    def test_a_successful_payment_with_the_wrong_amount_is_rejected(self):
        with self.sessions() as session, self.assertRaises(PaymentEventError):
            apply_payment(session, ORDER_REFERENCE, 'success', 99.99)
        with self.sessions() as session:
            self.assertEqual(session.get(OrderItem, 1).order_status, 'pending_payment')

    def test_a_failed_payment_with_the_wrong_amount_is_rejected(self):
        with self.sessions() as session, self.assertRaises(PaymentEventError):
            apply_payment(session, BOOKING_REFERENCE, 'fail', 99.99)
        with self.sessions() as session:
            self.assertEqual(session.get(ScheduleItem, 1).order_status, 'pending_payment')
            self.assertEqual(session.get(WeeklyAvailability, 1).availability[36:48], 'OOOO' + 'HHHH' + 'HH' + 'OO')

    def test_a_failed_payment_may_omit_its_amount(self):
        with self.sessions() as session:
            result = apply_payment(session, ORDER_REFERENCE, 'fail')
        self.assertEqual(result.new_status, 'payment_failed')

    def test_a_repeated_event_makes_the_invoice_again_after_a_failed_upload(self):
        with mock.patch('app.storage.upload_invoice', side_effect=[RuntimeError('GCS down'), 'gs://b/x.pdf']) as upload:
            with self.sessions() as session, self.assertRaises(RuntimeError):
                apply_payment(session, ORDER_REFERENCE, 'success', ORDER_TOTAL)
            with self.sessions() as session:
                self.assertEqual(session.get(OrderItem, 1).order_status, 'payment_received')  # the payment stood
            with self.sessions() as session:
                result = apply_payment(session, ORDER_REFERENCE, 'success', ORDER_TOTAL)  # Pub/Sub redelivers
        self.assertFalse(result.changed)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(result.invoice_uri, 'gs://b/x.pdf')

    def test_the_customer_is_told_a_payment_was_received_with_the_invoice_link(self):
        with mock.patch('app.storage.upload_invoice', return_value='gs://b/x.pdf'), \
                mock.patch('app.storage.invoice_link', return_value='https://signed/x.pdf'), \
                mock.patch('app.whatsapp_sender.send_text', return_value='wamid.1') as send, self.sessions() as session:
            apply_payment(session, CHAT_ORDER_REFERENCE, 'success', ORDER_TOTAL)
        business_id, to, text = send.call_args.args
        self.assertEqual((business_id, to), (1, '+6591234567'))
        self.assertIn('received your payment', text)
        self.assertIn('https://signed/x.pdf', text)

    def test_the_customer_is_told_a_payment_failed(self):
        with mock.patch('app.whatsapp_sender.send_text', return_value='wamid.1') as send, self.sessions() as session:
            apply_payment(session, CHAT_ORDER_REFERENCE, 'fail', ORDER_TOTAL)
        self.assertIn("didn't go through", send.call_args.args[2])

    def test_a_sandbox_or_deleted_chat_is_not_messaged(self):
        with mock.patch('app.whatsapp_sender.send_text') as send, self.sessions() as session:
            apply_payment(session, ORDER_REFERENCE, 'fail', ORDER_TOTAL)
        send.assert_not_called()

    def test_a_message_that_could_not_be_sent_yet_is_retried_with_the_event(self):
        down = SendError('configuration-service is down', retryable=True)
        with mock.patch('app.whatsapp_sender.send_text', side_effect=[down, 'wamid.1']) as send:
            with self.sessions() as session, self.assertRaises(SendError):
                apply_payment(session, CHAT_ORDER_REFERENCE, 'fail', ORDER_TOTAL)
            with self.sessions() as session:
                self.assertEqual(session.get(OrderItem, 2).order_status, 'payment_failed')  # the payment stood
            with self.sessions() as session:
                apply_payment(session, CHAT_ORDER_REFERENCE, 'fail', ORDER_TOTAL)  # Pub/Sub redelivers
        self.assertEqual(send.call_count, 2)

    def test_a_refused_message_does_not_fail_the_payment(self):
        refused = SendError('the 24-hour window has closed', retryable=False)
        with mock.patch('app.whatsapp_sender.send_text', side_effect=refused), self.sessions() as session:
            result = apply_payment(session, CHAT_ORDER_REFERENCE, 'fail')
        self.assertEqual(result.new_status, 'payment_failed')

    def test_an_unknown_payment_reference_is_an_error(self):
        with self.sessions() as session, self.assertRaises(PaymentNotFoundError):
            apply_payment(session, 'c' * 32, 'success')


if __name__ == '__main__':
    unittest.main()
