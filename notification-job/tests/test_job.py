"""The notification job's reminders (app/job.py), on SQLite (tables created here for the tests only)."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job
from app.email_sender import EmailError
from app.whatsapp_sender import SendError
from app.models import (
    Base,
    BusinessConfiguration,
    BusinessUser,
    ChatSession,
    OrderItem,
    ScheduleItem,
    WhatsAppConfiguration,
)

# A run at 9:11:30 pm Singapore time (13:11:30 UTC): "the hour" is 9 pm (13:00 UTC).
NOW = datetime(2026, 10, 12, 13, 11, 30, tzinfo=UTC)
HOUR = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)
ORDER_DATA = {
    'items': [{'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2}],
    'details': {'name': 'Alice'},
}
SCHEDULE_DATA = {
    'service': {'service_id': 1, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 60, 'buffer_minutes': 0},
    'details': {'name': 'Priya'},
}


class JobTestCase(unittest.TestCase):
    def setUp(self):
        # Never a real WhatsApp message or email, whatever the environment running the tests has set.
        for target, name, answer in (('app.whatsapp_sender.send_text', 'send_text', 'wamid.1'), ('app.email_sender.send_email', 'send_email', True)):
            patcher = mock.patch(target, return_value=answer)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(engine, expire_on_commit=False)
        self.next_id = 1
        with self.sessions.begin() as session:
            session.add(BusinessConfiguration(id=1, business_name='Snap Studio', description='', location='Singapore'))
            session.add(ChatSession(id=1, business_id=1, phone_number='+6591234567', display_name='', is_sandbox=False))
            session.add(ChatSession(id=2, business_id=1, phone_number='', display_name='Test', is_sandbox=True))

    def order(self, created_time, status='pending_payment', chat=1, details=None, payment_link=None):
        order_data = {**ORDER_DATA, 'details': details or ORDER_DATA['details']}
        with self.sessions.begin() as session:
            order = OrderItem(
                id=self.next_id, business_id=1, chat_session_id=chat, is_sandbox=chat == 2, order_data=order_data,
                order_status=status, payment_reference=f'{self.next_id:032x}', payment_link=payment_link,
                created_time=created_time,
            )
            session.add(order)
        self.next_id += 1
        return order.id

    def booking(self, start_time, created_time=None, status='pending_payment', chat=1, details=None, payment_link=None):
        schedule_data = {**SCHEDULE_DATA, 'details': details or SCHEDULE_DATA['details']}
        with self.sessions.begin() as session:
            booking = ScheduleItem(
                id=self.next_id, business_id=1, chat_session_id=chat, is_sandbox=chat == 2, start_time=start_time,
                end_time=start_time + timedelta(hours=1), schedule_data=schedule_data, order_status=status,
                payment_reference=f'{self.next_id:032x}', payment_link=payment_link,
                created_time=created_time or HOUR - timedelta(days=3),
            )
            session.add(booking)
        self.next_id += 1
        return booking.id

    def run_job(self):
        with self.assertLogs('app.job', level='INFO') as logs:
            result = job.run(self.sessions, now=NOW)
        return result, logs.output


class HourTests(unittest.TestCase):
    def test_rounded_down_to_the_hour(self):
        self.assertEqual(job.floor_to_hour(NOW), HOUR)
        self.assertEqual(job.floor_to_hour(HOUR), HOUR)


class PaymentReminderTests(JobTestCase):
    def test_pending_orders_and_bookings_made_1_to_2_hours_before_the_hour(self):
        reminded = [
            self.order(HOUR - timedelta(hours=1)),  # exactly 1 h: included
            self.order(HOUR - timedelta(minutes=90)),
            self.order(HOUR - timedelta(hours=2) + timedelta(seconds=1)),
            self.booking(HOUR + timedelta(days=2), created_time=HOUR - timedelta(minutes=75)),
        ]
        self.order(HOUR - timedelta(hours=2))  # exactly 2 h: the previous run reminded it
        self.order(HOUR - timedelta(minutes=59))  # under 1 h: the next run will
        self.order(HOUR - timedelta(minutes=90), status='payment_received')
        self.order(HOUR - timedelta(minutes=90), status='payment_failed')
        result, _ = self.run_job()
        self.assertEqual(result.hour, HOUR)
        self.assertEqual(
            [r.item for r in result.payment_reminders],
            [f'order #{reminded[2]}', f'order #{reminded[1]}', f'order #{reminded[0]}', f'booking #{reminded[3]}'],
        )

    PAY_LINK = 'https://checkout.xendit.example/pay/abc123'

    def test_the_messages_have_the_payment_link(self):
        order = self.order(HOUR - timedelta(minutes=90), details={'name': 'Alice', 'email': 'alice@example.com'}, payment_link=self.PAY_LINK)
        reminder, = self.run_job()[0].payment_reminders
        self.assertEqual(reminder.phone_number, '+6591234567')
        self.assertEqual(
            reminder.message,
            f'Hi Alice, this is Snap Studio. Your order #{order} (2 × Kopi C, SGD 3.60) is still waiting for payment. '
            f'Please complete it here: {self.PAY_LINK}\n\nReply here if you need any help.',
        )
        self.assertEqual(reminder.email, 'alice@example.com')
        self.assertEqual(reminder.email_subject, 'Reminder: your order with Snap Studio is waiting for payment')
        self.assertEqual(
            reminder.email_text,
            '\n'.join([
                'Hi Alice,',
                '',
                'Your order with Snap Studio is still waiting for payment.',
                '',
                'Order: 2 × Kopi C',
                'Amount to pay: SGD 3.60',
                '',
                f'Pay online: {self.PAY_LINK}',
                '',
                "If you've already paid, please ignore this email. If you need any help, just message Snap Studio in your WhatsApp chat.",
                '',
                'Thank you,',
                'Snap Studio',
            ]),
        )

    def test_a_booking_says_what_and_when_and_to_keep_the_time(self):
        booking = self.booking(HOUR - timedelta(minutes=90), created_time=HOUR - timedelta(minutes=90), payment_link=self.PAY_LINK,
                               details={'name': 'Priya', 'email': 'priya@example.com'})
        # A booking made 90 minutes ago, for a time days ahead (the default start is the hour − 3 days: use a later one).
        with self.sessions.begin() as session:
            session.get(ScheduleItem, booking).start_time = datetime(2026, 10, 20, 12, 30, tzinfo=UTC)  # 8:30pm SGT
        reminder = next(r for r in self.run_job()[0].payment_reminders if r.item == f'booking #{booking}')
        self.assertIn('Your booking #%d (Family Shoot on Tue 20 Oct, 8:30pm, SGD 250.00) is still waiting for payment.' % booking, reminder.message)
        self.assertIn(f'Please complete it here to keep your time: {self.PAY_LINK}', reminder.message)
        self.assertIn('Booking: Family Shoot on Tue 20 Oct, 8:30pm', reminder.email_text)
        self.assertIn(f'Pay online to keep your time: {self.PAY_LINK}', reminder.email_text)

    def test_without_a_payment_link_it_offers_help_instead_of_a_reference(self):
        order = self.order(HOUR - timedelta(minutes=90), payment_link=None)  # the Xendit link was never created
        reminder, = self.run_job()[0].payment_reminders
        self.assertEqual(
            reminder.message,
            f'Hi Alice, this is Snap Studio. Your order #{order} (2 × Kopi C, SGD 3.60) is still waiting for payment. '
            'Reply here if you need any help completing it.',
        )
        self.assertNotIn('Pay online', reminder.email_text)
        self.assertNotIn(f'{order:032x}', reminder.message)  # a reference means nothing to a customer

    def test_a_long_order_is_summarised(self):
        many = {**ORDER_DATA, 'items': [{'product_id': n, 'name': f'Item {n}', 'unit_price': '1.00', 'quantity': 1} for n in range(8)]}
        with self.sessions.begin() as session:
            session.add(OrderItem(
                id=99, business_id=1, chat_session_id=1, is_sandbox=False, order_data=many, order_status='pending_payment',
                payment_reference='9' * 32, created_time=HOUR - timedelta(minutes=90),
            ))
        reminder, = self.run_job()[0].payment_reminders
        self.assertIn('1 × Item 0, 1 × Item 1, 1 × Item 2, 1 × Item 3, 1 × Item 4, and 3 more', reminder.message)
        self.assertIn('SGD 8.00', reminder.message)

    def test_a_chat_without_a_phone_number(self):
        self.order(HOUR - timedelta(minutes=90), chat=2, details={'name': 'Test', 'email': 'test@example.com'})
        self.order(HOUR - timedelta(minutes=90), chat=None)
        result, logs = self.run_job()
        self.assertEqual([r.phone_number for r in result.payment_reminders], [None, None])
        self.send_text.assert_not_called()
        self.assertTrue(any('no phone number for WhatsApp' in line for line in logs))
        self.send_email.assert_called_once()  # the sandbox customer gave an email address; the other order has none


class AppointmentReminderTests(JobTestCase):
    def test_bookings_starting_23_to_24_hours_after_the_hour(self):
        reminded = [
            self.booking(HOUR + timedelta(hours=23)),  # exactly 23 h: included
            self.booking(HOUR + timedelta(hours=23, minutes=30), status='payment_received'),
        ]
        self.booking(HOUR + timedelta(hours=24))  # exactly 24 h: the next run
        self.booking(HOUR + timedelta(hours=22, minutes=59))  # the previous run reminded it
        self.booking(HOUR + timedelta(hours=23, minutes=30), status='payment_failed')  # holds no time
        result, _ = self.run_job()
        self.assertEqual([r.item for r in result.appointment_reminders], [f'booking #{n}' for n in reminded])

    def test_the_messages(self):
        booking = self.booking(
            datetime(2026, 10, 13, 12, 30, tzinfo=UTC), status='payment_received',  # 8:30pm SGT
            details={'name': 'Priya', 'email': 'priya@example.com'},
        )
        result, _ = self.run_job()
        reminder, = result.appointment_reminders
        self.assertEqual(reminder.phone_number, '+6591234567')
        self.assertEqual(
            reminder.message,
            f'Hi Priya, a reminder from Snap Studio: your Family Shoot (booking #{booking}) starts in about 24 hours, '
            'on Tue 13 Oct, 8:30pm. See you tomorrow! Reply here if you need to change anything.',
        )
        self.assertEqual(reminder.email, 'priya@example.com')
        self.assertEqual(reminder.email_subject, 'Reminder: your Family Shoot with Snap Studio starts in about 24 hours')
        self.assertEqual(
            reminder.email_text,
            '\n'.join([
                'Hi Priya,',
                '',
                f'This is a reminder from Snap Studio: your Family Shoot (booking #{booking}) starts in about 24 hours.',
                '',
                'Time: Tue 13 Oct, 8:30pm',
                'Location: Singapore',
                '',
                'If you need to change anything, just message Snap Studio in your WhatsApp chat.',
                '',
                'See you soon,',
                'Snap Studio',
            ]),
        )

    def test_a_pending_booking_is_also_asked_to_pay(self):
        booking = self.booking(HOUR + timedelta(hours=23))
        reminder, = self.run_job()[0].appointment_reminders
        self.assertIn(f'please pay with reference {booking:032x}', reminder.message)
        self.assertIn(f'please pay with reference {booking:032x} to keep your time', reminder.email_text)


class AppointmentSendingTests(JobTestCase):
    """The appointment reminders are sent, on WhatsApp and by email (the senders are faked)."""

    DETAILS = {'name': 'Priya', 'email': 'priya@example.com'}

    def test_sent_on_whatsapp_and_by_email(self):
        booking = self.booking(HOUR + timedelta(hours=23), details=self.DETAILS)
        result, _ = self.run_job()
        reminder, = result.appointment_reminders
        self.send_text.assert_called_once_with(1, '+6591234567', reminder.message)  # from business #1's number
        self.send_email.assert_called_once_with(reminder.email_subject, reminder.email_text, 'priya@example.com')
        self.assertIn('Family Shoot', reminder.message)
        self.assertEqual(result.failed_reminders, [])
        self.assertIn(f'booking #{booking}', reminder.item)

    def test_without_an_email_detail_it_is_only_on_whatsapp(self):
        for details in ({'name': 'Priya'}, {'name': 'Priya', 'email': 'not an address'}, {'email': 'a@b.com\r\nBcc: x@y.z'}):
            with self.subTest(details=details):
                self.send_text.reset_mock()
                self.send_email.reset_mock()
                self.booking(HOUR + timedelta(hours=23), details=details)
                self.run_job()
                self.send_text.assert_called_once()
                self.send_email.assert_not_called()
                with self.sessions.begin() as session:
                    session.query(ScheduleItem).delete()

    def test_a_sandbox_booking_has_no_phone_number_but_is_emailed(self):
        self.booking(HOUR + timedelta(hours=23), chat=2, details=self.DETAILS)
        result, _ = self.run_job()
        self.send_text.assert_not_called()
        self.send_email.assert_called_once()
        self.assertEqual(result.failed_reminders, [])

    def test_a_booking_without_a_chat_is_still_emailed(self):
        self.booking(HOUR + timedelta(hours=23), chat=None, details=self.DETAILS)
        self.run_job()
        self.send_text.assert_not_called()
        self.send_email.assert_called_once()

    def test_a_refusal_is_logged_and_the_run_still_succeeds(self):
        self.send_text.side_effect = SendError('Meta: the 24-hour window has closed', retryable=False)
        self.send_email.side_effect = EmailError('no such mailbox', retryable=False)
        self.booking(HOUR + timedelta(hours=23), details=self.DETAILS)
        with self.assertLogs('app.job', level='ERROR'):
            result = job.run(self.sessions, now=NOW)
        self.assertEqual(result.failed_reminders, [])  # retrying would never help: no non-zero exit

    def test_a_temporary_failure_fails_the_run_but_not_the_other_reminders_or_channel(self):
        self.send_text.side_effect = [SendError('configuration-service is down', retryable=True), 'wamid.2']
        first = self.booking(HOUR + timedelta(hours=23), details=self.DETAILS)
        second = self.booking(HOUR + timedelta(hours=23, minutes=30), details=self.DETAILS)
        with self.assertLogs('app.job', level='WARNING'):
            result = job.run(self.sessions, now=NOW)
        self.assertEqual([r.item for r in result.failed_reminders], [f'booking #{first}'])
        self.assertEqual(self.send_text.call_count, 2)  # the second reminder was still sent
        self.assertEqual(self.send_email.call_count, 2)  # and the first one's email was not held up by WhatsApp
        self.assertEqual(second, first + 1)

    def test_an_email_that_could_not_be_sent_yet_fails_the_run_too(self):
        self.send_email.side_effect = EmailError('the mail relay is down', retryable=True)
        self.booking(HOUR + timedelta(hours=23), details=self.DETAILS)
        with self.assertLogs('app.job', level='WARNING'):
            result = job.run(self.sessions, now=NOW)
        self.assertEqual(len(result.failed_reminders), 1)
        self.send_text.assert_called_once()  # WhatsApp went out

    def test_the_payment_reminders_are_sent_too(self):
        self.order(HOUR - timedelta(minutes=90), details={'name': 'Alice', 'email': 'alice@example.com'}, payment_link='https://pay.example/x')
        result, _ = self.run_job()
        reminder, = result.payment_reminders
        self.send_text.assert_called_once_with(1, '+6591234567', reminder.message)
        self.send_email.assert_called_once_with(reminder.email_subject, reminder.email_text, 'alice@example.com')
        self.assertEqual(result.failed_reminders, [])

    def test_a_temporary_failure_on_a_payment_reminder_fails_the_run(self):
        self.send_text.side_effect = SendError('configuration-service is down', retryable=True)
        self.order(HOUR - timedelta(minutes=90))
        with self.assertLogs('app.job', level='WARNING'):
            result = job.run(self.sessions, now=NOW)
        self.assertEqual([r.kind for r in result.failed_reminders], ['payment'])


class ContactNumberTests(JobTestCase):
    """The emails tell the customer how to reach the business: its WhatsApp number, when it has one."""

    def connect_whatsapp(self, display_phone_number='+65 9123 4567'):
        with self.sessions.begin() as session:
            session.add(WhatsAppConfiguration(
                id=1, business_id=1, phone_number_id='100000000000001', display_phone_number=display_phone_number,
                status='connected', access_token_expires_time=None,
            ))

    def emails(self):
        order = self.order(HOUR - timedelta(minutes=90), details={'name': 'Alice', 'email': 'alice@example.com'})
        booking = self.booking(HOUR + timedelta(hours=23), details={'name': 'Priya', 'email': 'priya@example.com'})
        result, _ = self.run_job()
        return result.payment_reminders[0].email_text, result.appointment_reminders[0].email_text

    def test_the_number_is_in_both_emails(self):
        self.connect_whatsapp()
        payment, appointment = self.emails()
        self.assertIn("If you need any help, just message Snap Studio on WhatsApp at +65 9123 4567.", payment)
        self.assertIn('If you need to change anything, just message Snap Studio on WhatsApp at +65 9123 4567.', appointment)
        self.assertNotIn('in your WhatsApp chat', payment + appointment)

    def test_without_a_connection_it_says_in_your_whatsapp_chat(self):
        payment, appointment = self.emails()
        self.assertIn('If you need any help, just message Snap Studio in your WhatsApp chat.', payment)
        self.assertIn('If you need to change anything, just message Snap Studio in your WhatsApp chat.', appointment)

    def test_a_connection_without_a_number_says_in_your_whatsapp_chat(self):
        self.connect_whatsapp(display_phone_number='')  # Meta hasn't reported it
        payment, appointment = self.emails()
        self.assertIn('just message Snap Studio in your WhatsApp chat.', payment)
        self.assertIn('just message Snap Studio in your WhatsApp chat.', appointment)

    def test_the_whatsapp_messages_are_unchanged(self):
        self.connect_whatsapp()
        self.order(HOUR - timedelta(minutes=90))
        reminder, = self.run_job()[0].payment_reminders
        self.assertNotIn('+65 9123 4567', reminder.message)  # they are already in the chat: "Reply here"
        self.assertIn('Reply here', reminder.message)


class ReconnectAlertTests(JobTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions.begin() as session:
            session.add(BusinessConfiguration(id=2, business_name='Bloom', description='', location='Singapore'))
            for user_id, business_id, email, active in (
                (1, 1, 'owner@snap.example', True),
                (2, 1, 'staff@snap.example', True),
                (3, 1, '', True),  # no address
                (4, 1, 'left@snap.example', False),  # deactivated
                (5, 2, 'owner@bloom.example', True),
            ):
                session.add(BusinessUser(id=user_id, business_id=business_id, username=f'user{user_id}', email=email,
                                         is_active=active))

    def connection(self, expires, business=1, display_phone_number='+65 9123 4567', status='connected'):
        with self.sessions.begin() as session:
            session.add(WhatsAppConfiguration(
                id=self.next_id, business_id=business, phone_number_id=f'10000000000000{self.next_id}',
                display_phone_number=display_phone_number, status=status, access_token_expires_time=expires,
            ))
        self.next_id += 1

    def test_7_days_1_day_and_at_expiry(self):
        self.connection(HOUR + timedelta(days=7))  # exactly 7 days after the hour: included
        self.connection(HOUR + timedelta(days=1) - timedelta(minutes=30), business=2)
        self.connection(HOUR - timedelta(minutes=59))  # expired during the last hour
        self.connection(HOUR + timedelta(days=7, seconds=1))  # the next run
        self.connection(HOUR + timedelta(days=7) - timedelta(hours=1))  # the previous run alerted it
        self.connection(HOUR - timedelta(hours=1))  # expired before: the previous run alerted it
        self.connection(HOUR + timedelta(days=3))  # between the alerts
        self.connection(None)  # never expires (e.g. manual connections)
        self.assertEqual(
            [alert.business for alert in self.run_job()[0].reconnect_alerts],
            ['business #1 (Snap Studio)', 'business #2 (Bloom)', 'business #1 (Snap Studio)'],
        )

    def test_not_for_connections_meta_reported_disconnected_or_banned(self):
        self.connection(HOUR + timedelta(days=7), status='disconnected')
        self.connection(HOUR + timedelta(days=1), business=2, status='banned')
        self.assertEqual(self.run_job()[0].reconnect_alerts, [])

    def test_sent_to_the_business_s_active_users_with_an_email(self):
        self.connection(HOUR + timedelta(days=1))
        self.connection(HOUR + timedelta(days=7), business=2)
        result, logs = self.run_job()
        self.assertEqual(
            [alert.emails for alert in result.reconnect_alerts],
            [['owner@bloom.example'], ['owner@snap.example', 'staff@snap.example']],
        )
        self.assertIn(
            'TODO: send whatsapp_reconnect alert for business #1 (Snap Studio) to owner@snap.example, staff@snap.example',
            logs[-1],
        )

    def test_the_draft_messages(self):
        self.connection(datetime(2026, 10, 13, 12, 30, tzinfo=UTC))  # 1 day ahead, 8:30pm SGT
        self.connection(HOUR - timedelta(minutes=10), display_phone_number='')
        expiring, expired = self.run_job()[0].reconnect_alerts
        self.assertEqual(
            expiring.message,
            'Hi Snap Studio, your WhatsApp connection (+65 9123 4567) expires on Tue 13 Oct, 8:30pm. Reconnect it '
            'with Facebook on the Home page of Ansera Business Admin before then, or your assistant won\'t be able '
            'to reply to customers on WhatsApp.',
        )
        self.assertEqual(
            expired.message,
            "Hi Snap Studio, your WhatsApp connection (phone number ID 100000000000002) has expired, so your "
            "assistant can't reply to customers on WhatsApp. Reconnect it with Facebook on the Home page of "
            'Ansera Business Admin.',
        )

    def test_a_business_without_email_addresses(self):
        self.connection(HOUR + timedelta(days=7), business=2)
        with self.sessions.begin() as session:
            session.get(BusinessUser, 5).email = ''
        result, logs = self.run_job()
        self.assertEqual(result.reconnect_alerts[0].emails, [])
        self.assertIn('to no email address', logs[-1])


if __name__ == '__main__':
    unittest.main()
