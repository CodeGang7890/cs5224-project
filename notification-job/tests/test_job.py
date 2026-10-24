"""The notification job's reminders (app/job.py), on SQLite (tables created here for the tests only)."""

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job
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
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        self.sessions = sessionmaker(engine, expire_on_commit=False)
        self.next_id = 1
        with self.sessions.begin() as session:
            session.add(BusinessConfiguration(id=1, business_name='Snap Studio', description='', location='Singapore'))
            session.add(ChatSession(id=1, business_id=1, phone_number='+6591234567', display_name='', is_sandbox=False))
            session.add(ChatSession(id=2, business_id=1, phone_number='', display_name='Test', is_sandbox=True))

    def order(self, created_time, status='pending_payment', chat=1):
        with self.sessions.begin() as session:
            order = OrderItem(
                id=self.next_id, business_id=1, chat_session_id=chat, is_sandbox=chat == 2, order_data=ORDER_DATA,
                order_status=status, payment_reference=f'{self.next_id:032x}', created_time=created_time,
            )
            session.add(order)
        self.next_id += 1
        return order.id

    def booking(self, start_time, created_time=None, status='pending_payment', chat=1):
        with self.sessions.begin() as session:
            booking = ScheduleItem(
                id=self.next_id, business_id=1, chat_session_id=chat, is_sandbox=chat == 2, start_time=start_time,
                end_time=start_time + timedelta(hours=1), schedule_data=SCHEDULE_DATA, order_status=status,
                payment_reference=f'{self.next_id:032x}', created_time=created_time or HOUR - timedelta(days=3),
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

    def test_logs_the_phone_number_and_a_draft_message(self):
        order = self.order(HOUR - timedelta(minutes=90))
        result, logs = self.run_job()
        reminder, = result.payment_reminders
        self.assertEqual(reminder.phone_number, '+6591234567')
        self.assertEqual(
            reminder.message,
            f'Hi Alice, this is Snap Studio. Your order #{order} (total $3.60) is still waiting for payment. Please '
            f'complete it with payment reference {order:032x}, or reply here if you need any help.',
        )
        self.assertIn(f'TODO: send payment reminder for order #{order} to +6591234567: Hi Alice', logs[-1])

    def test_a_chat_without_a_phone_number(self):
        self.order(HOUR - timedelta(minutes=90), chat=2)
        self.order(HOUR - timedelta(minutes=90), chat=None)
        result, logs = self.run_job()
        self.assertEqual([r.phone_number for r in result.payment_reminders], [None, None])
        self.assertIn('to no phone number', logs[-1])


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

    def test_the_draft_message(self):
        booking = self.booking(datetime(2026, 10, 13, 12, 30, tzinfo=UTC), status='payment_received')  # 8:30pm SGT
        result, logs = self.run_job()
        reminder, = result.appointment_reminders
        self.assertEqual(reminder.phone_number, '+6591234567')
        self.assertEqual(
            reminder.message,
            f'Hi Priya, a reminder from Snap Studio: your Family Shoot (booking #{booking}) is tomorrow, '
            'Tue 13 Oct, 8:30pm. See you then! Reply here if you need to change anything.',
        )
        self.assertIn(f'TODO: send appointment reminder for booking #{booking} to +6591234567', logs[-1])

    def test_a_pending_booking_is_also_asked_to_pay(self):
        booking = self.booking(HOUR + timedelta(hours=23))
        reminder, = self.run_job()[0].appointment_reminders
        self.assertIn(f'please pay with reference {booking:032x}', reminder.message)


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
