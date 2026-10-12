"""A port of configuration-service's chat_app/tests/test_booking_flow.py: booking a service end to
end through the sandbox message API (LLM mocked), the booking steps' checks, templates and prompts.
"""

import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import func, select, update

from app import config
from app.chat_flow.checkout import place_booking
from app.chat_flow.dates import parse_datetime
from app.chat_flow.errors import ValidationError
from app.chat_flow.order_flow import (
    DEFAULT_SLOT_DAYS,
    SLOT_OPTIONS_OFFERED,
    _parse_clock,
    check_service_selection,
    check_slot_selection,
    offer_slots,
)
from app.chat_flow.prompts import (
    booking_confirmed_message,
    booking_request_message,
    build_extraction_prompt,
    build_reply_prompt,
    build_router_prompt,
    slot_options_message,
)
from app.chat_flow.schedule import PENDING_PAYMENT, local
from app.chat_flow.validators import validate_chat_messages, validate_chat_state_data
from app.models import ChatSession, ScheduleItem, Service

from .chat_helpers import ApiTestCase, DatabaseTestCase, FlowTestMixin
from .schedule_helpers import at, book, day_letters, future_monday, open_week

WEEKDAYS = [(day, '09:00', '17:00') for day in range(5)]  # Mon–Fri 09:00–17:00
RAJ_DAYS = [(day, '10:00', '14:00') for day in range(6)]  # Mon–Sat 10:00–14:00


def iso(moment: datetime) -> str:
    return moment.isoformat()


def times(options: list[str]) -> list[str]:
    """Offered times as "Mon 09:00", for readable assertions."""
    return [local(parse_datetime(option)).strftime('%a %H:%M') for option in options]


def singapore_time(test):
    """override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')."""
    patcher = patch.object(config, 'SCHEDULE_TIME_ZONE', 'Asia/Singapore')
    patcher.start()
    test.addCleanup(patcher.stop)


class StudioTestData:
    """A photography studio: two photographers (with their next three weeks open) and services,
    "now" fixed on a Monday at 08:00. (Django's setUpTestData: here every test has its own DB.)"""

    def set_up_studio(self):
        self.studio = self.make.business('Snap Studio', description='Portrait and family photography.')
        self.user = self.make.user(self.studio, username='studio')
        self.mei = self.make.provider(self.studio, 'Mei')
        self.raj = self.make.provider(self.studio, 'Raj')
        self.monday = future_monday()
        for weeks in range(3):
            open_week(self.sessions, self.mei, self.monday + timedelta(weeks=weeks), *WEEKDAYS)
            open_week(self.sessions, self.raj, self.monday + timedelta(weeks=weeks), *RAJ_DAYS)
        self.family = self.make.service(
            self.studio, 'Family Shoot', [self.mei, self.raj], '250.00', duration_minutes=90, buffer_minutes=30,
            description='Up to 6 people, in the studio.', information='Bring up to 3 outfits. Pets welcome.',
        )
        self.portrait = self.make.service(self.studio, 'Portrait Session', [self.mei], '180.00', duration_minutes=60, buffer_minutes=15)
        self.retired = self.make.service(self.studio, 'Retired', price='1.00', duration_minutes=60, is_active=False)
        self.make.service(self.studio, 'Nobody Does It', price='1.00', duration_minutes=60)
        self.now = at(self.monday, '08:00')


class BookingAPIMixin(StudioTestData):
    """BookingFlowAPITests' setUp, at_step and family_data (shared with SeparateDetailFieldsFlowTests)."""

    def setUp(self):
        super().setUp()
        singapore_time(self)
        self.set_up_studio()
        self.session = self.make.session(self.studio, is_sandbox=True)
        self.mock_llm()
        self.login(self.user)
        patcher = patch('app.chat_flow.flow.timezone.now', return_value=self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def at_step(self, step, **data):
        with self.sessions.begin() as db:
            session = db.get(ChatSession, self.session.id)
            session.chat_state_id, session.chat_state_data = step, data
        self.session = self.get(ChatSession, self.session.id)

    def family_data(self, **extra):
        return {
            'service': {'service_id': self.family.pk, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30},
            **extra,
        }


class BookingFlowAPITests(BookingAPIMixin, FlowTestMixin, ApiTestCase):
    """Booking a service end to end, through the sandbox message API (LLM mocked)."""

    def test_full_booking_from_start_to_confirmed(self):
        # 1. Wants to book a family shoot: the service is chosen, and the free times are offered
        #    (a fixed message: no reply LLM call), spread out over the next days.
        response = self.send(
            'Hi, can I book a family shoot?',
            {'service_id': self.family.pk},
            {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None},
            intents=['booking'],
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        data = self.session.chat_state_data
        self.assertEqual(data['service']['name'], 'Family Shoot')
        self.assertEqual(times(data['slot_options']), ['Mon 09:00', 'Mon 10:30', 'Mon 12:00', 'Tue 09:00', 'Tue 10:30', 'Tue 12:00'])
        debug = response.json()['debug']
        self.assertEqual(debug['reply_kind'], 'slot_options')
        self.assertEqual(debug['route']['intents'], ['booking'])
        self.assertEqual([(s['step'], s['complete']) for s in debug['steps']], [('service_selection', True), ('slot_selection', False)])
        self.assertEqual(self.calls(structured=False), [])
        message = response.json()['message']
        self.assertTrue(message.startswith('Here are some available times for Family Shoot ($250.00, 1 h 30 min):\n1. Mon '))
        self.assertIn('\n2. Mon ', message)
        self.assertIn(', 10:30am\n', message)
        self.assertTrue(message.endswith('Please reply with the number of the time you would like, or tell me another day or time that suits you.'))
        # The slot extraction saw today's date, the next days and the service.
        slot_prompt = self.calls(structured=True)[1]['messages'][0]['content']
        self.assertIn(f'Today is Monday {self.monday.day} {self.monday:%B %Y} ({self.monday.isoformat()})', slot_prompt)
        self.assertIn(f'- {self.monday + timedelta(days=1):%a} {(self.monday + timedelta(days=1)).day} '
                      f'{self.monday + timedelta(days=1):%b} = {(self.monday + timedelta(days=1)).isoformat()}', slot_prompt)
        self.assertIn('The customer is choosing a time for: Family Shoot ($250.00, 1 h 30 min).', slot_prompt)

        # 2. Picks the 2nd time: on to the details (an LLM reply asks for them).
        response = self.send('The 2nd one please', {'choice': 2, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None},
                             {'name': None, 'email': None})
        self.assertEqual(self.session.chat_state_id, 'booking_details')
        self.assertEqual(self.session.chat_state_data['slot'], iso(at(self.monday, '10:30')))
        self.assertNotIn('slot_options', self.session.chat_state_data)
        prompt = self.reply_prompt()
        self.assertIn('Current step: Booking details', prompt)
        self.assertIn('Booking: Family Shoot ($250.00, 1 h 30 min), on Mon', prompt)
        self.assertIn('10:30am – 12pm.', prompt)
        self.assertIn('the booking is NOT confirmed yet', prompt)
        self.assertIn('## Still needed\n- Name\n- Email', prompt)
        self.assertEqual(response.json()['debug']['reply_kind'], 'llm')

        # 3. The details: on to the booking summary (a fixed message), nothing booked yet.
        response = self.send('Alice, alice@example.com', {'name': 'Alice', 'email': 'alice@example.com'})
        self.assertEqual(self.session.chat_state_id, 'booking_confirmation')
        self.assertEqual(response.json()['debug']['confirmation'], 'not_confirmed')
        self.assertEqual(response.json()['debug']['reply_kind'], 'booking_confirmation_request')
        self.assertEqual(
            response.json()['message'],
            'Here is your booking summary:\n'
            '- Family Shoot (1 h 30 min)\n'
            f'- Mon {self.monday.day} {self.monday:%b}, 10:30am – 12pm\n'
            'Price: $250.00\n\n'
            'Your details:\n- Name: Alice\n- Email: alice@example.com\n\n'
            'Please reply CONFIRM to book it, or tell me what you would like to change.',
        )
        self.assertFalse(self.all(ScheduleItem))
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '10:00', '13:00'), 'O' * 12)  # nothing on hold yet

        # 4. Confirms: the booking is saved first, then the customer is told, and back to the start.
        response = self.send('Confirm', {'decision': 'confirm'})
        booking, = self.all(ScheduleItem)
        self.assertEqual((booking.service_id, booking.service_provider_id, booking.chat_session_id), (self.family.id, self.mei.id, self.session.id))
        # Mei's week: 10:30–12:30 (the session and its buffer) went from O to H (pending payment).
        self.assertEqual(day_letters(self.sessions, self.mei, self.monday, '10:00', '13:00'), 'OO' + 'H' * 8 + 'OO')
        self.assertEqual((booking.start_time, booking.end_time, booking.blocked_until),
                         (at(self.monday, '10:30'), at(self.monday, '12:00'), at(self.monday, '12:30')))
        self.assertEqual((booking.order_status, booking.is_sandbox), (PENDING_PAYMENT, True))
        self.assertEqual(booking.schedule_data['details'], {'name': 'Alice', 'email': 'alice@example.com'})
        debug = response.json()['debug']
        self.assertEqual((debug['confirmation'], debug['booking_id'], debug['order_id'], debug['reply_kind']),
                         ('confirmed', booking.pk, None, 'booking_confirmed'))
        self.assertTrue(response.json()['message'].startswith(f'Thank you! Your booking #{booking.pk} with Snap Studio is confirmed.\n'))
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('start', {'last_booking_id': booking.pk}))
        self.assertEqual(self.session.display_name, 'Alice')
        validate_chat_messages(self.session.chat_message_json)
        validate_chat_state_data(self.session.chat_state_data)  # Django: self.session.full_clean()

        # 5. Afterwards: back at the start, the booking mentioned, and that time now taken.
        self.send('Thanks!')
        self.assertIn(f'Last booking made in this chat: #{booking.pk} (payment pending).', self.reply_prompt())
        self.assertIn(f'their last booking in this chat, #{booking.pk}, has been placed', self.router_call()['messages'][0]['content'])

    def test_an_exact_day_and_time(self):
        wednesday = self.monday + timedelta(days=2)
        self.at_step('slot_selection', **self.family_data())
        self.send('Wednesday at 2pm', {'choice': None, 'date': wednesday.isoformat(), 'date_to': None, 'time': '14:00', 'part_of_day': None},
                  {'name': None, 'email': None})
        self.assertEqual(self.session.chat_state_id, 'booking_details')
        self.assertEqual(self.session.chat_state_data['slot'], iso(at(wednesday, '14:00')))

    def test_a_taken_time_offers_others_that_day(self):
        wednesday = self.monday + timedelta(days=2)
        book(self.sessions, self.family, self.mei, at(wednesday, '14:00'))  # Raj doesn't work at 2pm
        self.at_step('slot_selection', **self.family_data())
        response = self.send('Wednesday at 2pm', {'choice': None, 'date': wednesday.isoformat(), 'date_to': None, 'time': '14:00', 'part_of_day': None})
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        self.assertNotIn('slot', self.session.chat_state_data)
        self.assertEqual(times(self.session.chat_state_data['slot_options']), ['Wed 09:00', 'Wed 10:30', 'Wed 12:00'])
        message = response.json()['message']
        self.assertTrue(message.startswith(f'Wed {wednesday.day} {wednesday:%b}, 2pm is not available for Family Shoot.\n\nHere are some'))

    def test_a_time_off_the_start_interval_is_explained_and_only_allowed_starts_are_offered(self):
        with self.sessions.begin() as db:
            db.get(Service, self.portrait.id).start_interval_minutes = 60
        tuesday = self.monday + timedelta(days=1)
        portrait = {'service_id': self.portrait.pk, 'name': 'Portrait Session', 'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 15}
        self.at_step('slot_selection', service=portrait)
        response = self.send('Tuesday at 9:30?', {'choice': None, 'date': tuesday.isoformat(), 'date_to': None, 'time': '09:30', 'part_of_day': None})
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        self.assertNotIn('slot', self.session.chat_state_data)
        message = response.json()['message']
        self.assertTrue(message.startswith('Portrait Session can only start every hour (for example 9am or 10am).'), message)
        offered = times(self.session.chat_state_data['slot_options'])
        self.assertTrue(offered)
        self.assertTrue(all(time.endswith(':00') for time in offered), offered)
        # An allowed start is taken.
        self.send('10am then', {'choice': None, 'date': tuesday.isoformat(), 'date_to': None, 'time': '10:00', 'part_of_day': None}, {'name': None, 'email': None})
        self.assertEqual(self.session.chat_state_data['slot'], iso(at(tuesday, '10:00')))

    def test_a_time_without_a_day_keeps_the_day_already_chosen(self):
        tuesday = self.monday + timedelta(days=1)
        self.at_step('booking_details', **self.family_data(slot=iso(at(tuesday, '09:00'))))
        self.send('Can we do 11am instead?', {'name': None, 'email': None, 'go_back_to': 'slot_selection'},
                  {'choice': None, 'date': None, 'date_to': None, 'time': '11:00', 'part_of_day': None},
                  {'name': None, 'email': None})
        self.assertEqual(self.session.chat_state_id, 'booking_details')
        self.assertEqual(self.session.chat_state_data['slot'], iso(at(tuesday, '11:00')))

    def test_part_of_the_day(self):
        tuesday = self.monday + timedelta(days=1)
        self.at_step('slot_selection', **self.family_data())
        self.send('Tuesday afternoon?', {'choice': None, 'date': tuesday.isoformat(), 'date_to': None, 'time': None, 'part_of_day': 'afternoon'})
        self.assertEqual(times(self.session.chat_state_data['slot_options']), ['Tue 12:00', 'Tue 13:30', 'Tue 15:00'])

    def test_a_closed_day_offers_the_next_free_days(self):
        sunday = self.monday + timedelta(days=6)
        self.at_step('slot_selection', **self.family_data())
        response = self.send('Sunday?', {'choice': None, 'date': sunday.isoformat(), 'date_to': None, 'time': None, 'part_of_day': None})
        self.assertEqual(times(self.session.chat_state_data['slot_options'])[:3], ['Mon 09:00', 'Mon 10:30', 'Mon 12:00'])
        self.assertEqual(local(parse_datetime(self.session.chat_state_data['slot_options'][0])).date(), sunday + timedelta(days=1))
        self.assertIn(f'There are no free times for Family Shoot on Sun {sunday.day} {sunday:%b}.', response.json()['message'])

    def test_a_past_day_or_a_wrong_number(self):
        self.at_step('slot_selection', **self.family_data(slot_options=[iso(at(self.monday, '09:00'))]))
        response = self.send('3', {'choice': 3, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None})
        self.assertIn('There is no time number 3: please pick one of the numbers listed.', response.json()['message'])
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        response = self.send('Last Friday', {'choice': None, 'date': (self.monday - timedelta(days=3)).isoformat(), 'date_to': None, 'time': None, 'part_of_day': None})
        self.assertIn('That day has already passed.', response.json()['message'])
        self.assertEqual(len(self.session.chat_state_data['slot_options']), SLOT_OPTIONS_OFFERED)

    def test_nothing_new_keeps_the_times_offered(self):
        offered = [iso(at(self.monday, '09:00')), iso(at(self.monday, '10:30'))]
        self.at_step('slot_selection', **self.family_data(slot_options=offered))
        response = self.send('Hmm let me think', {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None})
        self.assertEqual(self.session.chat_state_data['slot_options'], offered)
        self.assertIn('1. Mon ', response.json()['message'])

    def test_an_offered_time_taken_since(self):
        offered = [iso(at(self.monday, '09:00'))]
        book(self.sessions, self.family, self.mei, at(self.monday, '09:00'))
        book(self.sessions, self.family, self.raj, at(self.monday, '10:00'))  # Raj: 10:00–12:00, so 09:00 doesn't fit him either
        self.at_step('slot_selection', **self.family_data(slot_options=offered))
        response = self.send('1', {'choice': 1, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None})
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        self.assertIn('9am is not available for Family Shoot.', response.json()['message'])
        self.assertNotIn(iso(at(self.monday, '09:00')), self.session.chat_state_data['slot_options'])

    def test_changing_the_service_drops_the_time(self):
        self.at_step('slot_selection', **self.family_data(slot_options=[iso(at(self.monday, '09:00'))]))
        self.send(
            'Actually a portrait session',
            {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None, 'go_back_to': 'service_selection'},
            {'service_id': self.portrait.pk},
            {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None},
        )
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        data = self.session.chat_state_data
        self.assertEqual(data['service']['name'], 'Portrait Session')
        # Portrait is Mei's only, 60 min apart: Mon 09:00, 10:00, 11:00, then Tuesday.
        self.assertEqual(times(data['slot_options']), ['Mon 09:00', 'Mon 10:00', 'Mon 11:00', 'Tue 09:00', 'Tue 10:00', 'Tue 11:00'])

    def test_service_selection_asks_when_unclear(self):
        self.send('I want to book something', {'service_id': None}, intents=['booking'])
        self.assertEqual(self.session.chat_state_id, 'service_selection')
        prompt = self.reply_prompt()
        self.assertIn('Current step: Service selection', prompt)
        self.assertIn('## Services that can be booked\n', prompt)
        self.assertIn(f'- id {self.family.pk}: Family Shoot, $250.00 (1 h 30 min). Up to 6 people, in the studio.', prompt)
        self.assertNotIn('Retired', prompt)  # inactive
        self.assertNotIn('Nobody Does It', prompt)  # no service provider: can't be booked
        self.assertIn('Do not suggest or promise any dates or times', prompt)
        self.assertNotIn('## Products on sale', prompt)  # the studio sells no products
        extraction = self.calls(structured=True)[0]['messages'][0]['content']
        self.assertIn(f'- id {self.portrait.pk}: Portrait Session, $180.00 (1 h)', extraction)

    def test_an_unbookable_service_is_refused(self):
        retired = self.retired
        self.send('The retired one', {'service_id': retired.pk}, intents=['booking'])
        self.assertEqual(self.session.chat_state_id, 'service_selection')
        self.assertIn('The service the customer asked for cannot be booked.', self.reply_prompt())

    def test_not_confirming_resends_the_summary_and_change_goes_back(self):
        tuesday = self.monday + timedelta(days=1)
        data = self.family_data(slot=iso(at(tuesday, '09:00')), details={'name': 'Alice', 'email': 'a@b.co'})
        self.at_step('booking_confirmation', **data)
        response = self.send('Hmm', {'decision': 'none'})
        self.assertTrue(response.json()['message'].startswith('Here is your booking summary:'))
        self.assertFalse(self.all(ScheduleItem))
        # A different time from the summary: back to Time slot (the old time dropped), times offered.
        response = self.send(
            'Can I change the time?',
            {'decision': 'none', 'go_back_to': 'slot_selection'},
            {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None},
        )
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        self.assertNotIn('slot', self.session.chat_state_data)
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Alice', 'email': 'a@b.co'})
        self.assertEqual(response.json()['debug']['reply_kind'], 'slot_options')
        # The old time comes first (it can be picked again), then the next free times.
        self.assertEqual(times(self.session.chat_state_data['slot_options']),
                         ['Tue 09:00', 'Mon 09:00', 'Mon 10:30', 'Mon 12:00', 'Tue 10:30', 'Tue 12:00'])
        self.assertIn(
            '"slot_selection": Time slot, to choose a different day or time',
            self.calls(structured=True)[0]['messages'][0]['content'],
        )

    def test_change_at_booking_confirmation_passes_through_what_still_holds(self):
        tuesday = self.monday + timedelta(days=1)
        data = self.family_data(slot=iso(at(tuesday, '09:00')), details={'name': 'Alice', 'email': 'a@b.co'})
        self.at_step('booking_confirmation', **data)
        self.send(
            'Change my email to alice@work.com',
            {'decision': 'change'},
            {'service_id': None},
            {'choice': None, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None},
            {'name': None, 'email': 'alice@work.com'},
        )
        self.assertEqual(self.session.chat_state_id, 'booking_confirmation')
        self.assertEqual(self.session.chat_state_data['slot'], iso(at(tuesday, '09:00')))
        self.assertEqual(self.session.chat_state_data['details']['email'], 'alice@work.com')

    def test_taken_before_confirming_goes_back_to_time_slot(self):
        tuesday = self.monday + timedelta(days=1)
        self.at_step('booking_confirmation', **self.family_data(slot=iso(at(tuesday, '10:00')), details={'name': 'Alice', 'email': 'a@b.co'}))
        # Both photographers get booked at that time in the meantime.
        for _ in range(2):
            with self.sessions.begin() as db:
                place_booking(db, self.studio, self.family.pk, at(tuesday, '10:00'), {}, now=self.now)
        response = self.send('Confirm', {'decision': 'confirm'})
        self.assertEqual(len(self.all(ScheduleItem, ScheduleItem.chat_session_id == self.session.id)), 0)
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        data = self.session.chat_state_data
        self.assertNotIn('slot', data)
        self.assertEqual(data['details'], {'name': 'Alice', 'email': 'a@b.co'})
        self.assertTrue(data['slot_options'])
        debug = response.json()['debug']
        self.assertEqual((debug['confirmation'], debug['booking_id'], debug['reply_kind']), (None, None, 'slot_options'))
        self.assertIn('The booking could not be made', debug['stop_reason'])
        message = response.json()['message']
        self.assertIn('10am is not available for Family Shoot.', message)
        self.assertIn('The booking was not made: please choose another time.', message)
        self.assertIn('Here are some available times', message)

    def test_a_question_while_choosing_a_time_comes_before_the_times(self):
        self.at_step('slot_selection', **self.family_data())
        response = self.send(
            'Can I bring my dog? Any time Monday is fine',
            {'choice': None, 'date': self.monday.isoformat(), 'date_to': None, 'time': None, 'part_of_day': None},
            reply='Yes, pets are welcome!',
            intents=['booking', 'question'],
            question_check={'kind': 'answered', 'question': 'Can I bring my dog to the family shoot?'},
        )
        message = response.json()['message']
        self.assertTrue(message.startswith('Yes, pets are welcome!\n\nHere are some available times'))
        aside = response.json()['debug']['reply_system_prompt']
        self.assertIn('they are automatically sent the free times to choose from', aside)
        self.assertIn('never mention, suggest or promise any times yourself', aside)
        self.assertIn('## Details of Family Shoot\nBring up to 3 outfits. Pets welcome.', aside)  # the service's information
        self.assertIn('## Services that can be booked', aside)

    def test_the_router_knows_the_services_and_the_booking(self):
        self.at_step('slot_selection', **self.family_data())
        self.send('2', {'choice': None})
        prompt = self.router_call()['messages'][0]['content']
        self.assertIn('Services that can be booked: Family Shoot, Portrait Session', prompt)
        self.assertIn('The customer\'s order or booking: a booking is in progress, at the "Time slot" step.', prompt)
        self.assertIn('- "booking": the customer wants to book a time for one of the services', prompt)

    def test_a_booking_in_progress_runs_whatever_the_router_says(self):
        self.at_step('slot_selection', **self.family_data(slot_options=[iso(at(self.monday, '09:00'))]))
        self.send('1', {'choice': 1, 'date': None, 'date_to': None, 'time': None, 'part_of_day': None}, {'name': None, 'email': None}, intents=[])
        self.assertEqual(self.session.chat_state_id, 'booking_details')

    def test_two_bookings_in_one_chat(self):
        for start in ('09:00', '13:30'):
            self.at_step('booking_confirmation', **{
                **self.family_data(slot=iso(at(self.monday, start)), details={'name': 'Alice', 'email': 'a@b.co'}),
                **({'last_booking_id': self.session.chat_state_data['last_booking_id']} if 'last_booking_id' in self.session.chat_state_data else {}),
            })
            self.send('Confirm', {'decision': 'confirm'})
        self.assertEqual(len(self.all(ScheduleItem, ScheduleItem.chat_session_id == self.session.id)), 2)
        with self.sessions() as db:
            latest = db.scalar(select(func.max(ScheduleItem.id)))
        self.assertEqual(self.session.chat_state_data, {'last_booking_id': latest})

    def test_the_last_order_is_kept_after_a_booking(self):
        self.at_step('booking_confirmation', **self.family_data(slot=iso(at(self.monday, '09:00')), details={'name': 'A', 'email': 'a@b.co'}), last_order_id=3)
        self.send('Confirm', {'decision': 'confirm'})
        booking, = self.all(ScheduleItem)
        self.assertEqual(self.session.chat_state_data, {'last_order_id': 3, 'last_booking_id': booking.pk})


class SeparateDetailFieldsFlowTests(BookingAPIMixin, FlowTestMixin, ApiTestCase):
    """Bookings ask for the schedule details, orders for the product details: set independently."""

    BOOKING_FIELDS = [
        {'key': 'name', 'label': 'Name', 'type': 'text'},
        {'key': 'people', 'label': 'Number of people', 'type': 'number', 'min_value': 1, 'max_value': 12},
    ]
    ORDER_FIELDS = [
        {'key': 'name', 'label': 'Name', 'type': 'text'},
        {'key': 'pickup_time', 'label': 'Pickup time', 'type': 'text'},
    ]

    def setUp(self):
        super().setUp()
        self.make.chat_config(self.studio, product_detail_fields=self.ORDER_FIELDS, schedule_detail_fields=self.BOOKING_FIELDS)

    def test_booking_details_ask_for_the_schedule_details(self):
        tuesday = self.monday + timedelta(days=1)
        self.at_step('booking_details', **self.family_data(slot=iso(at(tuesday, '09:00'))))
        response = self.send('Priya, 4 of us', {'name': 'Priya', 'people': 4})
        extraction = self.calls(structured=True)[0]
        self.assertEqual(extraction['format']['required'], ['name', 'people', 'go_back_to'])
        self.assertNotIn('Pickup time', extraction['messages'][0]['content'])
        self.assertEqual(self.session.chat_state_id, 'booking_confirmation')
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Priya', 'people': 4})
        self.assertIn('- Number of people: 4', response.json()['message'])  # the summary uses their labels

    def test_orders_still_ask_for_the_product_details(self):
        kopi = self.make.product(self.studio, 'Prints', '15.00', total_quantity=10)
        self.at_step('details_collection', items=[{'product_id': kopi.pk, 'name': 'Prints', 'unit_price': '15.00', 'quantity': 1}], items_confirmed=True)
        self.send('Priya, at 5pm', {'name': 'Priya', 'pickup_time': '5pm'})
        extraction = self.calls(structured=True)[0]
        self.assertEqual(extraction['format']['required'], ['name', 'pickup_time', 'go_back_to'])
        self.assertEqual(self.session.chat_state_data['details'], {'name': 'Priya', 'pickup_time': '5pm'})
        self.assertEqual(self.session.chat_state_id, 'confirmation')


class StartingABookingTests(StudioTestData, FlowTestMixin, ApiTestCase):
    def setUp(self):
        super().setUp()
        self.set_up_studio()
        self.session = self.make.session(self.studio, is_sandbox=True)
        self.mock_llm()
        self.login(self.user)

    def test_no_bookable_services_means_no_booking(self):
        with self.sessions.begin() as db:
            db.execute(update(Service).where(Service.business_id == self.studio.id).values(is_active=False))
        response = self.send('Book me in!', intents=['booking'])
        self.assertEqual(self.session.chat_state_id, 'start')
        self.assertEqual(self.calls(structured=True), [])
        self.assertIn('no wish to order or book', response.json()['debug']['stop_reason'])

    def test_ordering_wins_when_its_both(self):
        self.make.product(self.studio, 'Photo Album', '60.00', total_quantity=10)
        self.send('An album, and book a shoot', {'items': []}, intents=['order', 'booking'])
        self.assertEqual(self.session.chat_state_id, 'product_selection')


class BookingCheckTests(StudioTestData, DatabaseTestCase):
    """The booking steps' deterministic checks, called directly."""

    def setUp(self):
        super().setUp()
        singapore_time(self)
        self.set_up_studio()

    def services(self):
        return [self.family, self.portrait]

    def test_service_selection(self):
        data = {}
        self.assertFalse(check_service_selection({'service_id': None}, data, self.services()).complete)
        result = check_service_selection({'service_id': self.family.pk}, data, self.services())
        self.assertTrue(result.complete)
        self.assertEqual(data['service'], {'service_id': self.family.pk, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30})
        # The same service again keeps the time; another one drops it.
        data['slot'] = iso(at(self.monday, '09:00'))
        check_service_selection({'service_id': self.family.pk}, data, self.services())
        self.assertIn('slot', data)
        check_service_selection({'service_id': self.portrait.pk}, data, self.services())
        self.assertNotIn('slot', data)
        # Not bookable any more (e.g. deactivated since): dropped, with the problem.
        result = check_service_selection({'service_id': None}, data, [self.family])
        self.assertFalse(result.complete)
        self.assertEqual(result.issues, ['Portrait Session cannot be booked any more.'])
        self.assertNotIn('service', data)
        self.assertEqual(check_service_selection({'service_id': True}, {}, self.services()).complete, False)  # not an id

    def test_slot_selection_without_a_bookable_service_goes_back(self):
        data = {'service': {'service_id': self.portrait.pk, 'name': 'Portrait Session', 'price': '180.00', 'duration_minutes': 60, 'buffer_minutes': 15}}
        result = check_slot_selection({}, data, [self.family], self.now, self.sessions)
        self.assertTrue(result.go_back)
        self.assertEqual(result.issues, ['Portrait Session cannot be booked any more.'])
        self.assertEqual(data, {})

    def test_slot_selection_choice_and_exact_time(self):
        data = {'service': {'service_id': self.family.pk, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30}}
        self.assertFalse(check_slot_selection({}, data, self.services(), self.now, self.sessions).complete)
        self.assertEqual(len(data['slot_options']), 6)
        second = data['slot_options'][1]
        self.assertTrue(check_slot_selection({'choice': 2}, data, self.services(), self.now, self.sessions).complete)
        self.assertEqual(data['slot'], second)
        # An exact time off the grid isn't bookable.
        result = check_slot_selection({'date': self.monday.isoformat(), 'time': '09:10'}, data, self.services(), self.now, self.sessions)
        self.assertFalse(result.complete)
        self.assertIn('quarter hour', result.issues[0])
        # Nonsense values are ignored.
        result = check_slot_selection(
            {'date': 'Monday', 'time': '25:00', 'part_of_day': 'night', 'choice': 'two'}, data, self.services(), self.now, self.sessions,
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.issues, [])

    def test_offer_slots_spread(self):
        offered = offer_slots(self.sessions, self.family, self.monday, self.monday + timedelta(days=DEFAULT_SLOT_DAYS - 1), None, self.now)
        self.assertEqual(len(offered), SLOT_OPTIONS_OFFERED)
        by_day = {}
        for slot in offered:
            by_day.setdefault(local(slot).date(), []).append(slot)
        for slots in by_day.values():
            self.assertLessEqual(len(slots), 3)
            self.assertTrue(all(b - a >= timedelta(minutes=90) for a, b in zip(slots, slots[1:])))
        evening = offer_slots(self.sessions, self.family, self.monday, self.monday, 'evening', self.now)
        self.assertEqual(evening, [])  # open until 17:00 only

    def test_parse_clock(self):
        self.assertEqual(_parse_clock('14:30').strftime('%H:%M'), '14:30')
        self.assertEqual(_parse_clock('9:00').strftime('%H:%M'), '09:00')
        self.assertEqual(_parse_clock('14:30:00').strftime('%H:%M'), '14:30')
        for bad in ('2pm', '24:00', '14:60', None, 14):
            with self.subTest(bad=bad):
                self.assertIsNone(_parse_clock(bad))


class BookingPromptTests(unittest.TestCase):
    business = SimpleNamespace(business_name='Snap Studio', description='', location='Singapore')
    service = {'service_id': 1, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30}

    def setUp(self):
        singapore_time(self)

    def test_templates(self):
        tuesday = at(date(2030, 1, 8), '14:00')
        data = {'service': self.service, 'slot': iso(tuesday), 'details': {'name': 'Alice'}}
        self.assertEqual(
            booking_request_message(data, {'name': 'Your name'}),
            'Here is your booking summary:\n- Family Shoot (1 h 30 min)\n- Tue 8 Jan, 2pm – 3:30pm\nPrice: $250.00\n\n'
            'Your details:\n- Your name: Alice\n\nPlease reply CONFIRM to book it, or tell me what you would like to change.',
        )
        self.assertTrue(booking_confirmed_message(self.business, 7, data, {}).startswith(
            'Thank you! Your booking #7 with Snap Studio is confirmed.\n- Family Shoot (1 h 30 min)\n- Tue 8 Jan, 2pm – 3:30pm'
        ))
        options = {'service': self.service, 'slot_options': [iso(tuesday), iso(tuesday + timedelta(hours=2))]}
        self.assertEqual(
            slot_options_message(options, ['That day has already passed.']),
            'That day has already passed.\n\nHere are some available times for Family Shoot ($250.00, 1 h 30 min):\n'
            '1. Tue 8 Jan, 2pm\n2. Tue 8 Jan, 4pm\n\n'
            'Please reply with the number of the time you would like, or tell me another day or time that suits you.',
        )
        self.assertTrue(slot_options_message({'service': self.service}).startswith('Sorry, I could not find a free time for Family Shoot'))

    def test_router_prompt(self):
        prompt = build_router_prompt(self.business, [], 'booking_details', {}, [SimpleNamespace(name='Family Shoot')])
        self.assertIn('Products on sale: none right now.', prompt)
        self.assertIn('Services that can be booked: Family Shoot', prompt)
        self.assertIn('a booking is in progress, at the "Booking details" step.', prompt)
        self.assertIn('"Can I book a family shoot on Saturday?" is ["booking"]', prompt)

    def test_extraction_prompts(self):
        now = at(date(2030, 1, 7), '08:00')
        data = {'service': self.service, 'slot_options': [iso(at(date(2030, 1, 8), '14:00'))]}
        prompt = build_extraction_prompt(self.business, 'slot_selection', data, [], [], now=now)
        self.assertIn('Today is Monday 7 January 2030 (2030-01-07).', prompt)
        self.assertIn('- Mon 7 Jan = 2030-01-07 (today)\n- Tue 8 Jan = 2030-01-08', prompt)
        self.assertIn('- Sun 20 Jan = 2030-01-20', prompt)  # two weeks
        self.assertIn('1. Tue 8 Jan, 2pm', prompt)
        self.assertIn('Never make up a date or time the customer did not ask for.', prompt)
        details = build_extraction_prompt(self.business, 'booking_details', data, [], [{'key': 'name', 'label': 'Name', 'type': 'text'}])
        self.assertIn('"name": "Name" (required; text', details)
        confirm = build_extraction_prompt(self.business, 'booking_confirmation', data, [], [])
        self.assertIn('reply CONFIRM to book it', confirm)

    def test_booking_details_reply(self):
        fields = [{'key': 'name', 'label': 'Name', 'type': 'text'}]
        data = {'service': self.service, 'slot': iso(at(date(2030, 1, 8), '14:00'))}
        prompt = build_reply_prompt(self.business, 'booking_details', data, products=[], fields=fields, missing=['Name'])
        self.assertIn('The booking is confirmed in a later step, not this one.', prompt)
        self.assertIn('so the booking is NOT confirmed yet', prompt)
        self.assertIn('Booking: Family Shoot ($250.00, 1 h 30 min), on Tue 8 Jan, 2pm – 3:30pm.', prompt)
        self.assertIn('## Details to collect\n- "Name"', prompt)
        self.assertIn('Never offer, suggest or promise booking times yourself', prompt)


class BookingStateDataTests(unittest.TestCase):
    service = {'service_id': 1, 'name': 'Family Shoot', 'price': '250.00', 'duration_minutes': 90, 'buffer_minutes': 30}

    def test_valid(self):
        validate_chat_state_data({'service': self.service, 'slot': '2030-01-08T14:00:00+08:00',
                                  'slot_options': ['2030-01-08T14:00:00+08:00'], 'details': {}, 'last_booking_id': 1})

    def test_invalid(self):
        cases = {
            'service missing a key': {'service': {'service_id': 1}},
            'service bad duration': {'service': {**self.service, 'duration_minutes': 0}},
            'slot without timezone': {'slot': '2030-01-08T14:00:00'},
            'slot not a date': {'slot': 'Tuesday 2pm'},
            'options not a list': {'slot_options': '2030-01-08T14:00:00+08:00'},
            'too many options': {'slot_options': ['2030-01-08T14:00:00+08:00'] * 11},
            'bad option': {'slot_options': ['soon']},
            'last_booking_id zero': {'last_booking_id': 0},
        }
        for label, value in cases.items():
            with self.subTest(label), self.assertRaises(ValidationError):
                validate_chat_state_data(value)
