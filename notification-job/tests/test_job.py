"""The notification job's reminders (app/job.py), on SQLite (tables created here for the tests only)."""

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import job
from app.models import Base, BusinessConfiguration, ChatSession, OrderItem, ScheduleItem

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


if __name__ == '__main__':
    unittest.main()
