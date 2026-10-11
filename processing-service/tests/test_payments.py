"""The payment flow (app/payments.py), a draft: a couple of cases on in-memory SQLite."""

import unittest
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import UNAVAILABLE_WEEK, Base, OrderItem, ScheduleItem, WeeklyAvailability
from app.payments import PaymentNotFoundError, apply_payment

ORDER_REFERENCE = 'a' * 32
BOOKING_REFERENCE = 'b' * 32
MONDAY = date(2026, 10, 12)
# Monday 10:00–11:00 (Singapore) is H (the booking), 11:00–11:30 its buffer (H), the rest of the
# morning open (O). Blocks are 15 minutes from Monday 00:00: 10:00 is block 40.
LETTERS = UNAVAILABLE_WEEK[:36] + 'OOOO' + 'HHHH' + 'HH' + 'OO' + UNAVAILABLE_WEEK[48:]


class PaymentFlowTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)  # tests only: configuration-service owns the real schema
        self.sessions = sessionmaker(engine)
        now = datetime(2026, 10, 1, tzinfo=UTC)
        with self.sessions.begin() as session:
            session.add(OrderItem(id=1, business_id=1, order_status='pending_payment', payment_reference=ORDER_REFERENCE, updated_time=now))
            session.add(ScheduleItem(
                id=1, business_id=4, service_provider_id=1, order_status='pending_payment', payment_reference=BOOKING_REFERENCE,
                start_time=datetime(2026, 10, 12, 2, tzinfo=UTC),  # 10:00 in Singapore
                end_time=datetime(2026, 10, 12, 3, tzinfo=UTC),
                blocked_until=datetime(2026, 10, 12, 3, 30, tzinfo=UTC),
                updated_time=now,
            ))
            session.add(WeeklyAvailability(id=1, service_provider_id=1, week=MONDAY, availability=LETTERS))

    def test_a_paid_booking_takes_its_time_and_a_failed_order_frees_its_stock(self):
        with self.sessions() as session:
            booking = apply_payment(session, BOOKING_REFERENCE, 'success')
            order = apply_payment(session, ORDER_REFERENCE, 'fail')
        self.assertEqual((booking.kind, booking.new_status), ('booking', 'payment_received'))
        self.assertEqual((order.kind, order.new_status), ('order', 'payment_failed'))
        with self.sessions() as session:
            self.assertEqual(session.get(ScheduleItem, 1).order_status, 'payment_received')
            self.assertEqual(session.get(OrderItem, 1).order_status, 'payment_failed')  # its stock is derived: freed
            letters = session.get(WeeklyAvailability, 1).availability
        self.assertEqual(letters[36:48], 'OOOO' + 'XXXX' + 'XX' + 'OO')  # duration and buffer H → X

    def test_an_unknown_payment_reference_is_an_error(self):
        with self.sessions() as session, self.assertRaises(PaymentNotFoundError):
            apply_payment(session, 'c' * 32, 'success')


if __name__ == '__main__':
    unittest.main()
