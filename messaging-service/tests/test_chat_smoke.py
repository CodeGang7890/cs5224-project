"""A first end-to-end turn through the ported flow (the full ports of the Django tests follow)."""

from app.models import OrderItem

from .chat_helpers import ApiTestCase, FlowTestMixin


class SmokeTests(FlowTestMixin, ApiTestCase):
    def setUp(self):
        super().setUp()
        self.cafe = self.make.business()
        self.user = self.make.user(self.cafe)
        self.kopi = self.make.product(self.cafe, 'Kopi C', '1.80', total_quantity=10)
        self.session = self.make.session(self.cafe)
        self.login(self.user)
        self.mock_llm()

    def test_an_order_from_start_to_placed(self):
        response = self.send('2 Kopi C please', {'items': [{'product_id': self.kopi.id, 'quantity': 2}], 'done_choosing': False}, intents=['order'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.session.chat_state_id, 'product_selection')
        self.send("That's all", {'items': [], 'done_choosing': True}, {'name': 'Alice', 'email': 'alice@example.com'})
        self.assertEqual(self.session.chat_state_id, 'confirmation')
        response = self.send('CONFIRM', {'decision': 'confirm'})
        body = response.json()
        self.assertEqual(body['debug']['reply_kind'], 'order_confirmed', body['debug']['stop_reason'])
        order, = self.all(OrderItem)
        self.assertEqual(order.order_data['items'][0]['quantity'], 2)
        self.assertRegex(order.payment_reference, r'^[0-9a-f]{32}$')
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('start', {'last_order_id': order.id}))
        self.assertEqual(self.session.display_name, 'Alice')
        self.assertIn(f'#{order.id}', body['message'])
        self.assertEqual(len(self.session.chat_message_json), 6)


class BookingSmokeTests(FlowTestMixin, ApiTestCase):
    def setUp(self):
        from datetime import date, datetime, timedelta
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        from app.chat_flow.schedule import SLOTS_PER_DAY, UNAVAILABLE_WEEK

        super().setUp()
        self.studio = self.make.business('Snap Studio', description='Portrait photography.')
        self.user = self.make.user(self.studio)
        self.mei = self.make.provider(self.studio, 'Mei')
        self.monday = date(2030, 1, 7)
        letters = list(UNAVAILABLE_WEEK)
        for day in range(5):  # Mon–Fri 09:00–17:00 open
            for block in range(day * SLOTS_PER_DAY + 36, day * SLOTS_PER_DAY + 68):
                letters[block] = 'O'
        self.week = self.make.week(self.mei, self.monday, ''.join(letters))
        self.family = self.make.service(self.studio, 'Family Shoot', [self.mei], '250.00', duration_minutes=90, buffer_minutes=30)
        self.session = self.make.session(self.studio)
        self.login(self.user)
        self.mock_llm()
        now = datetime(2030, 1, 7, 8, tzinfo=ZoneInfo('Asia/Singapore'))
        patcher = patch('app.chat_flow.flow.timezone.now', return_value=now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_booking_from_start_to_placed(self):
        from app.models import ScheduleItem, WeeklyAvailability

        nothing = {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None}
        response = self.send('Can I book a family shoot?', {'service_id': self.family.id}, nothing, intents=['booking'])
        body = response.json()
        self.assertEqual(body['debug']['reply_kind'], 'slot_options', body)
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        options = self.session.chat_state_data['slot_options']
        self.assertTrue(options[0].startswith('2030-01-07T09:00:00+08:00'), options)
        self.send('The first one', {**nothing, 'choice': 1}, {'name': 'Priya', 'email': 'priya@example.com'})
        self.assertEqual(self.session.chat_state_id, 'booking_confirmation')
        body = self.send('CONFIRM', {'decision': 'confirm'}).json()
        self.assertEqual(body['debug']['reply_kind'], 'booking_confirmed', body['debug']['stop_reason'])
        booking, = self.all(ScheduleItem)
        self.assertEqual((booking.service_provider_id, booking.order_status), (self.mei.id, 'pending_payment'))
        letters = self.get(WeeklyAvailability, self.week.id).availability
        self.assertEqual(letters[36:46], 'HHHHHHHHOO')  # 09:00–10:30 + buffer to 11:00 on hold
