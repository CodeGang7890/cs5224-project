"""The Xendit payment link for a confirmed order / booking (app/chat_flow/payments.py).

payment-ingester's create endpoint is stubbed (ApiTestCase.create_payment_stub): these tests
check the link is requested with the order's / booking's details, stored on the row, and ends
the confirmation message — and that a failure (or a missing customer email) degrades to the note.
"""

import unittest
from datetime import timedelta
from decimal import Decimal

from app import payment_client
from app.chat_flow.prompts import PAYMENT_LINK_UNAVAILABLE_NOTE
from app.models import ChatSession, OrderItem, ScheduleItem

from .chat_helpers import ApiTestCase, FlowTestMixin
from .schedule_helpers import at, future_monday, open_week

WEEKDAYS = [(day, '09:00', '17:00') for day in range(5)]  # Mon–Fri 09:00–17:00


class OrderPaymentLinkTests(FlowTestMixin, ApiTestCase):
    """Confirming an order creates its Xendit payment link (stubbed) and ends the message with it."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café', 'Tiong Bahru')
        self.user = self.make.user(self.cafe, username='cafe')
        self.kopi = self.make.product(self.cafe, 'Kopi C', '1.80', total_quantity=10)
        self.session = self.make.session(
            self.cafe,
            is_sandbox=True,
            chat_state_id='confirmation',
            chat_state_data={
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 3}],
                'details': {'name': 'Alice', 'email': 'alice@example.com'},
            },
        )
        self.mock_llm()
        self.login(self.user)

    def test_link_requested_stored_and_in_the_message(self):
        response = self.send('Yes', {'decision': 'confirm'})
        order, = self.all(OrderItem)

        self.assertTrue(
            response.json()['message'].endswith(f'To pay, use this link: https://pay.xendit.co/test/{order.pk}')
        )
        self.assertEqual(order.xendit_payment_id, f'pay_test_{order.pk}')
        self.assertEqual(order.payment_link, f'https://pay.xendit.co/test/{order.pk}')

        args, kwargs = self.create_payment_stub.call_args
        self.assertEqual(
            args[:5],
            ('order', order.pk, Decimal('5.40'), order.payment_reference,
             {'given_name': 'Alice', 'email': 'alice@example.com'}),
        )
        self.assertEqual(kwargs['description'], f'Order #{order.pk} with Kopi Café')

    def test_creation_failure_degrades_to_the_note(self):
        self.create_payment_stub.side_effect = payment_client.PaymentClientError('payment-ingester is unreachable')
        response = self.send('Yes', {'decision': 'confirm'})
        order, = self.all(OrderItem)

        self.assertTrue(response.json()['message'].endswith(PAYMENT_LINK_UNAVAILABLE_NOTE))
        self.assertIsNone(order.xendit_payment_id)
        self.assertIsNone(order.payment_link)
        self.assertIsNone(response.json()['debug']['payment_link'])
        self.assertEqual(response.json()['debug']['payment_error'], 'payment-ingester is unreachable')

    def test_no_customer_email_means_no_link(self):
        with self.sessions.begin() as db:
            session = db.get(ChatSession, self.session.id)
            session.chat_state_data = {
                'items': [{'product_id': self.kopi.pk, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 1}],
                'details': {'name': 'Alice'},  # no email: Xendit needs one
            }
        self.session = self.get(ChatSession, self.session.id)

        response = self.send('Yes', {'decision': 'confirm'})
        order, = self.all(OrderItem)

        self.assertTrue(response.json()['message'].endswith(PAYMENT_LINK_UNAVAILABLE_NOTE))
        self.create_payment_stub.assert_not_called()
        self.assertEqual(response.json()['debug']['payment_error'], 'The customer name or email was not collected.')


class BookingPaymentLinkTests(FlowTestMixin, ApiTestCase):
    """Confirming a booking creates its Xendit payment link (stubbed)."""

    def setUp(self):
        super().setUp()
        self.studio = self.make.business('Snap Studio', description='Portrait and family photography.')
        self.user = self.make.user(self.studio, username='studio')
        self.mei = self.make.provider(self.studio, 'Mei')
        self.monday = future_monday()
        for weeks in range(3):
            open_week(self.sessions, self.mei, self.monday + timedelta(weeks=weeks), *WEEKDAYS)
        self.family = self.make.service(self.studio, 'Family Shoot', [self.mei], '250.00', duration_minutes=90, buffer_minutes=30)
        self.now = at(self.monday, '08:00')
        self.session = self.make.session(self.studio, is_sandbox=True)
        with self.sessions.begin() as db:
            session = db.get(ChatSession, self.session.id)
            session.chat_state_id = 'booking_confirmation'
            session.chat_state_data = {
                'service': {
                    'service_id': self.family.pk,
                    'name': 'Family Shoot',
                    'price': '250.00',
                    'duration_minutes': 90,
                    'buffer_minutes': 30,
                },
                'slot': (self.now + timedelta(days=1)).replace(hour=10, minute=0).isoformat(),
                'details': {'name': 'Priya', 'email': 'priya@example.com'},
            }
        self.session = self.get(ChatSession, self.session.id)
        self.mock_llm()
        self.login(self.user)
        patcher = unittest.mock.patch('app.chat_flow.flow.timezone.now', return_value=self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_booking_link_requested_stored_and_in_the_message(self):
        response = self.send('Yes', {'decision': 'confirm'})
        booking, = self.all(ScheduleItem)

        self.assertTrue(
            response.json()['message'].endswith(f'To pay, use this link: https://pay.xendit.co/test/{booking.pk}')
        )
        self.assertEqual(booking.xendit_payment_id, f'pay_test_{booking.pk}')
        self.assertEqual(booking.payment_link, f'https://pay.xendit.co/test/{booking.pk}')

        args, kwargs = self.create_payment_stub.call_args
        self.assertEqual(
            args[:5],
            ('booking', booking.pk, Decimal('250.00'), booking.payment_reference,
             {'given_name': 'Priya', 'email': 'priya@example.com'}),
        )
        self.assertEqual(kwargs['description'], f'Booking #{booking.pk} with Snap Studio')
