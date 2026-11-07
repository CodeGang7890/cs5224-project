"""Leaving an order or booking before it's placed (order_flow._leave_branch): cancelling it, and
asking for the other branch (switching over when nothing has been chosen, else holding it back),
with the LLM mocked."""

from unittest.mock import patch

from app.chat_flow.order_flow import advance
from app.chat_flow.prompts import build_reply_prompt, build_router_prompt
from app.chat_flow.settings import ChatSettings
from app.chat_flow.validators import validate_chat_state_data
from app.chat_flow.errors import ValidationError
from app.models import ChatSession, OrderItem, Product

from .chat_helpers import ApiTestCase, DatabaseTestCase, FlowTestMixin

PRODUCTS = [{'id': 1, 'name': 'Wilson Racket', 'description': '', 'price': '329.00', 'quantity_available': 5}]
RACKET = {'product_id': 1, 'name': 'Wilson Racket', 'unit_price': '329.00', 'quantity': 1}


class LeaveBranchTests(DatabaseTestCase):
    """order_flow.advance, called directly: the extraction mocked (nothing found unless set)."""

    def setUp(self):
        super().setUp()
        business = self.make.business('Rally Point Courts')
        self.court = self.make.service(business, 'Badminton Court', [self.make.provider(business, 'Court 1')], price='20.00')
        self.court_data = {
            'service_id': self.court.id, 'name': 'Badminton Court', 'price': '20.00', 'duration_minutes': 60, 'buffer_minutes': 0,
        }
        with self.sessions() as db:
            self.chat_config = ChatSettings.for_business(db, business)
        patcher = patch('app.chat_flow.order_flow.llm.generate_structured', return_value={})
        self.generate = patcher.start()
        self.addCleanup(patcher.stop)

    def advance(self, step, data, services=None, **intents):
        services = [self.court] if services is None else services
        kwargs = {'start_order': False, 'start_booking': False, 'cancel': False, **intents}
        return advance(self.chat_config, step, data, [], PRODUCTS, services=services, **kwargs)

    def extracted_steps(self, turn):
        return [step['step'] for step in turn.steps]

    # --- Switching over: nothing chosen yet ---------------------------------------------------

    def test_booking_instead_of_an_empty_order_switches_over(self):
        turn = self.advance('product_selection', {'last_order_id': 3}, start_booking=True)
        self.assertEqual((turn.step, turn.switched_from, turn.held_back, turn.cancelled), ('service_selection', 'order', None, None))
        self.assertEqual(self.extracted_steps(turn), ['service_selection'])  # the booking's step ran, on this message
        self.assertEqual(turn.data, {'last_order_id': 3})  # the last order placed is kept
        self.assertIn('switched over', turn.stop_reason)

    def test_ordering_instead_of_an_empty_booking_switches_over(self):
        turn = self.advance('service_selection', {}, start_order=True)
        self.assertEqual((turn.step, turn.switched_from), ('product_selection', 'booking'))
        self.assertEqual(self.extracted_steps(turn), ['product_selection'])

    def test_switching_over_offers_no_going_back(self):
        # The new branch is entered with this message: nothing to go back to in it.
        self.advance('product_selection', {}, start_booking=True)
        schema = self.generate.call_args.args[2]
        self.assertNotIn('go_back_to', schema['properties'])

    # --- Not switching: something chosen, or still about this branch --------------------------

    def test_booking_during_an_order_with_items_is_held_back(self):
        data = {'items': [RACKET]}
        turn = self.advance('product_selection', data, start_booking=True)
        self.assertEqual((turn.step, turn.held_back, turn.switched_from), ('product_selection', 'booking', None))
        self.assertEqual(turn.data['items'], [RACKET])  # nothing lost
        self.assertEqual(self.extracted_steps(turn), ['product_selection'])  # the order's step ran as usual
        self.assertIn('has to be finished or cancelled first', turn.stop_reason)

    def test_ordering_during_a_booking_with_a_service_is_held_back(self):
        turn = self.advance('booking_details', {'service': self.court_data, 'slot': '2026-11-09T14:00:00+08:00'}, start_order=True)
        self.assertEqual((turn.step, turn.held_back), ('booking_details', 'order'))
        self.assertEqual(turn.data['service'], self.court_data)

    def test_details_count_as_progress(self):
        turn = self.advance('details_collection', {'details': {'name': 'Alice'}}, start_booking=True)
        self.assertEqual((turn.step, turn.held_back), ('details_collection', 'booking'))

    def test_both_intents_on_an_empty_order_stay_in_the_order(self):
        # "A racket, and can I book a court?": the order goes on (the racket is extracted), the booking waits.
        self.generate.return_value = {'items': [{'product_id': 1, 'quantity': 1}], 'done_choosing': False}
        turn = self.advance('product_selection', {}, start_order=True, start_booking=True)
        self.assertEqual((turn.step, turn.held_back), ('product_selection', 'booking'))
        self.assertEqual(turn.data['items'], [RACKET])

    def test_booking_without_services_is_not_held_back_or_switched(self):
        turn = self.advance('product_selection', {}, services=[], start_booking=True)
        self.assertEqual((turn.step, turn.held_back, turn.switched_from), ('product_selection', None, None))

    def test_the_same_branch_changes_nothing(self):
        turn = self.advance('product_selection', {'items': [RACKET]}, start_order=True)
        self.assertEqual((turn.step, turn.held_back, turn.switched_from, turn.cancelled), ('product_selection', None, None, None))
        self.assertNotIn('switched', turn.stop_reason)

    # --- Cancelling ---------------------------------------------------------------------------

    def test_cancelling_an_order_goes_back_to_the_start(self):
        data = {'items': [RACKET], 'items_confirmed': True, 'details': {'name': 'Alice'}, 'last_booking_id': 4}
        turn = self.advance('confirmation', data, cancel=True)
        self.assertEqual((turn.step, turn.cancelled), ('start', 'order'))
        self.assertEqual(turn.data, {'last_booking_id': 4})
        self.generate.assert_not_called()  # no extraction: nothing to run
        self.assertIn('cancelled the order in progress (at Confirmation)', turn.stop_reason)
        self.assertIsNone(turn.confirmation)

    def test_cancelling_a_booking_goes_back_to_the_start(self):
        turn = self.advance('booking_details', {'service': self.court_data, 'slot': '2026-11-09T14:00:00+08:00'}, cancel=True)
        self.assertEqual((turn.step, turn.cancelled, turn.data), ('start', 'booking', {}))

    def test_cancelling_and_asking_for_the_other_branch_starts_it(self):
        turn = self.advance('product_selection', {'items': [RACKET]}, cancel=True, start_booking=True)
        self.assertEqual((turn.step, turn.cancelled, turn.held_back), ('service_selection', 'order', None))
        self.assertEqual(self.extracted_steps(turn), ['service_selection'])
        self.assertNotIn('items', turn.data)

    def test_cancelling_never_restarts_the_same_branch(self):
        # The extraction reads the whole conversation: restarting could bring the cancelled cart back.
        self.generate.return_value = {'items': [{'product_id': 1, 'quantity': 1}], 'done_choosing': False}
        turn = self.advance('product_selection', {'items': [RACKET]}, cancel=True, start_order=True)
        self.assertEqual((turn.step, turn.data), ('start', {}))
        self.generate.assert_not_called()

    def test_cancel_with_nothing_in_progress_does_nothing(self):
        turn = self.advance('start', {'last_order_id': 3}, cancel=True)
        self.assertEqual((turn.step, turn.cancelled, turn.data), ('start', None, {'last_order_id': 3}))
        self.assertIn('no wish to order or book', turn.stop_reason)

    def test_cancelling_sets_history_start_to_this_message(self):
        turn = advance(
            self.chat_config, 'product_selection', {'items': [RACKET]}, [], PRODUCTS, services=[self.court],
            start_order=False, cancel=True, message_count=7,
        )
        self.assertEqual(turn.data, {'history_start': 6})

    def test_the_steps_read_only_from_history_start(self):
        history = [{'role': 'user', 'content': f'message {n}'} for n in range(5)]  # the chat's 5 latest of 9
        advance(self.chat_config, 'product_selection', {'history_start': 7}, history, PRODUCTS, start_order=True, message_count=9)
        self.assertEqual([m['content'] for m in self.generate.call_args.args[1]], ['message 3', 'message 4'])

    def test_a_switch_keeps_history_start(self):
        turn = self.advance('product_selection', {'history_start': 4}, start_booking=True)
        self.assertEqual(turn.data, {'history_start': 4})

    def test_history_start_is_validated(self):
        validate_chat_state_data({'history_start': 0})
        for bad in (-1, 'x', True, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_chat_state_data({'history_start': bad})

    def test_does_not_change_the_given_data(self):
        data = {'items': [RACKET], 'last_order_id': 3}
        self.advance('product_selection', data, cancel=True)
        self.assertEqual(data, {'items': [RACKET], 'last_order_id': 3})


class LeaveBranchPromptTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.business = self.make.business('Rally Point Courts')

    def reply_prompt(self, step='start', **changes):
        return build_reply_prompt(self.business, step, {}, products=PRODUCTS, fields=[], intents=changes.pop('intents', []), **changes)

    def test_the_router_knows_about_cancelling_and_switching(self):
        prompt = build_router_prompt(self.business, PRODUCTS, 'product_selection', {})
        self.assertIn('- "cancel": an order or booking is in progress and the customer clearly wants to stop all of it', prompt)
        # "Instead" drops the one in progress (cancel); "also" doesn't.
        self.assertIn('during a booking, "nvm I want to buy a racket" is ["order", "cancel"]', prompt)
        self.assertIn('"never mind, I want to book a court instead" is ["booking", "cancel"]', prompt)
        self.assertIn('during an order, "can I also book a court?" is ["booking"]', prompt)
        # Not cancelling everything: part of it, a "no" to a question, or an order placed before.
        self.assertIn('"cancel the roses, I\'ll take tulips" is ["order"]', prompt)
        self.assertIn('(such as "no thanks" or "no, nothing else")', prompt)
        self.assertIn('"cancel my order #12" or "can I cancel my booking from last week?" is ["order_status"]', prompt)
        # Answers to the branch in progress stay in it.
        self.assertIn('While a booking is in progress, its answers (a service, a date or time, their name or details, "yes") are "booking", never "order"', prompt)

    def test_cancelled(self):
        prompt = self.reply_prompt(cancelled='order', intents=['cancel'])
        self.assertIn('## Cancelled\nThe customer just cancelled their order in progress: nothing was placed', prompt)
        self.assertNotIn('## Cancelling', prompt)  # something was cancelled

    def test_switched(self):
        prompt = self.reply_prompt('service_selection', switched_from='order')
        self.assertIn('## Switched\nThe customer asked for a booking instead of the order they had started', prompt)

    def test_held_back(self):
        prompt = self.reply_prompt('product_selection', held_back='booking')
        self.assertIn("## Not started yet\nThe customer also asked for a booking, but only one order or booking", prompt)
        self.assertIn('Do not start, plan or promise the booking, and do not list, suggest or ask about anything for it', prompt)
        self.assertIn('or cancel it and start the booking instead (they can say so in one message, for example "cancel the order and start a booking")', prompt)

    def test_cancel_with_nothing_to_cancel_never_claims_it_cancelled(self):
        prompt = self.reply_prompt(intents=['cancel'])
        self.assertIn('## Cancelling\nThe customer asked to cancel something, but nothing in progress was cancelled.', prompt)
        self.assertIn('never say you cancelled or changed one', prompt)

    def test_nothing_changed_adds_nothing(self):
        prompt = self.reply_prompt('product_selection')
        for heading in ('## Cancelled', '## Switched', '## Not started yet', '## Cancelling'):
            self.assertNotIn(heading, prompt)


class LeaveBranchFlowTests(FlowTestMixin, ApiTestCase):
    """Through the sandbox message API: what's saved, and what the reply is told."""

    def setUp(self):
        super().setUp()
        self.courts = self.make.business('Rally Point Courts', 'Singapore')
        self.user = self.make.user(self.courts, username='courts')
        self.racket = self.make.product(self.courts, 'Wilson Racket', '329.00', total_quantity=5)
        self.court = self.make.service(self.courts, 'Badminton Court', [self.make.provider(self.courts, 'Court 1')], price='20.00')
        self.session = self.make.session(self.courts, is_sandbox=True)
        self.line = {'product_id': self.racket.pk, 'name': 'Wilson Racket', 'unit_price': '329.00', 'quantity': 1}
        self.mock_llm()
        self.login(self.user)

    def at_step(self, step, **data):
        with self.sessions.begin() as db:
            session = db.get(ChatSession, self.session.id)
            session.chat_state_id, session.chat_state_data = step, data
        self.session = self.get(ChatSession, self.session.id)

    def test_booking_instead_of_an_empty_order(self):
        # The bug: "I want to buy racket" started an order; asking for a court instead stayed there.
        self.at_step('product_selection')
        response = self.send('nvm I want to book badminton court instead, is it available?', {'service_id': None}, intents=['booking'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('service_selection', {}))
        self.assertIn('## Switched', self.reply_prompt())
        self.assertIn('Current step: Service selection.', self.reply_prompt())

    def test_cancelling_an_order_saves_the_start(self):
        self.at_step('details_collection', items=[self.line], items_confirmed=True, last_order_id=7)
        response = self.send('Actually, cancel the order', intents=['cancel'])
        # history_start: the cancelling message (the chat's first here).
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('start', {'last_order_id': 7, 'history_start': 0}))
        self.assertEqual(self.calls(structured=True), [])  # no extraction
        self.assertIn('## Cancelled', self.reply_prompt())
        self.assertIn('Current step: Start', self.reply_prompt())
        self.assertIn('cancelled the order in progress', response.json()['debug']['stop_reason'])
        self.assertEqual(self.all(OrderItem), [])

    def test_a_booking_request_during_an_order_with_items_waits(self):
        self.at_step('product_selection', items=[self.line])
        self.send('Can I also book a court?', {'items': [], 'done_choosing': False}, intents=['booking'])
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data['items']), ('product_selection', [self.line]))
        self.assertIn('## Not started yet', self.reply_prompt())

    def test_held_back_at_a_template_step_gets_an_aside(self):
        # At Confirmation the reply is the fixed summary: the aside tells them about the booking.
        self.at_step('confirmation', items=[self.line], items_confirmed=True, details={'name': 'Alice', 'email': 'a@example.com'})
        response = self.send('Can I book a court too?', {'decision': 'none'}, intents=['booking'], reply='Let’s finish your order first.')
        self.assertEqual(self.session.chat_state_id, 'confirmation')
        aside_prompt = self.reply_prompt()
        self.assertIn('## Not started yet', aside_prompt)
        self.assertIn("their order isn't finished", aside_prompt)
        self.assertTrue(response.json()['message'].startswith('Let’s finish your order first.'))  # then the summary

    def test_placing_the_order_while_asking_to_book_invites_the_booking(self):
        self.at_step('confirmation', items=[self.line], items_confirmed=True, details={'name': 'Alice', 'email': 'a@example.com'})
        self.send('Confirm, and can I book a court after?', {'decision': 'confirm'}, intents=['order', 'booking'])
        order, = self.all(OrderItem)
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('start', {'last_order_id': order.pk}))
        self.assertIn('Their order is placed now, so they can start the booking with their next message', self.reply_prompt())

    def test_cancelling_at_confirmation_places_nothing(self):
        self.at_step('confirmation', items=[self.line], items_confirmed=True, details={'name': 'Alice', 'email': 'a@example.com'})
        self.send('cancel', intents=['cancel'])
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data), ('start', {'history_start': 0}))
        self.assertEqual(self.all(OrderItem), [])

    def test_a_cancelled_cart_is_not_read_again_by_the_next_order(self):
        self.send('I want a racket', {'items': [{'product_id': self.racket.pk, 'quantity': 1}], 'done_choosing': False}, intents=['order'])
        self.assertEqual(self.session.chat_state_data['items'], [self.line])
        self.send('never mind, cancel it', intents=['cancel'])
        self.assertEqual(self.session.chat_state_data, {'history_start': 2})  # after the message and its reply
        self.send('ok, I do want to order something after all', {'items': [], 'done_choosing': False}, intents=['order'])
        extraction = self.calls(structured=True)[0]
        self.assertEqual(
            [m['content'] for m in extraction['messages'][1:]],  # after the system prompt
            ['never mind, cancel it', 'OK!', 'ok, I do want to order something after all'],  # not "I want a racket"
        )
        self.assertEqual((self.session.chat_state_id, self.session.chat_state_data.get('history_start')), ('product_selection', 2))

    def test_placing_drops_history_start(self):
        self.at_step('confirmation', items=[self.line], items_confirmed=True, details={'name': 'Alice', 'email': 'a@example.com'}, history_start=0)
        self.send('Confirm', {'decision': 'confirm'}, intents=['order'])
        order, = self.all(OrderItem)
        self.assertEqual(self.session.chat_state_data, {'last_order_id': order.pk})

    def test_held_back_while_the_order_fails_to_place(self):
        # Sold out since it was chosen: back to Product selection, so the booking still has to wait.
        self.at_step('confirmation', items=[self.line], items_confirmed=True, details={'name': 'Alice', 'email': 'a@example.com'})
        with self.sessions.begin() as db:
            db.get(Product, self.racket.pk).total_quantity = 0
        self.send('Confirm, and can I book a court after?', {'decision': 'confirm'}, intents=['order', 'booking'])
        self.assertEqual(self.all(OrderItem), [])
        self.assertEqual(self.session.chat_state_id, 'product_selection')
        self.assertIn("their order isn't finished", self.reply_prompt())

    def test_buying_instead_of_a_booking_with_a_service_chosen(self):
        # The screenshot: at Time slot (the court chosen), "nvm I want to buy racket" is ["order", "cancel"].
        self.at_step('slot_selection', service={
            'service_id': self.court.pk, 'name': 'Badminton Court', 'price': '20.00', 'duration_minutes': 60, 'buffer_minutes': 0,
        }, slot_options=[])
        self.send('nvm I want to buy racket', {'items': [], 'done_choosing': False}, intents=['order', 'cancel'])
        self.assertEqual(self.session.chat_state_id, 'product_selection')
        self.assertNotIn('service', self.session.chat_state_data)
        prompt = self.reply_prompt()
        self.assertIn('## Cancelled\nThe customer just cancelled their booking in progress', prompt)
        self.assertIn('Current step: Product selection.', prompt)

    def test_cancelling_and_booking_reaching_the_times_gets_an_aside(self):
        # The court is chosen on the same message: the reply is the times template, with an aside.
        self.at_step('product_selection', items=[self.line])
        response = self.send(
            'cancel the order and book the badminton court instead', {'service_id': self.court.pk},
            intents=['booking', 'cancel'], reply='Your order is cancelled.',
        )
        self.assertEqual(self.session.chat_state_id, 'slot_selection')
        self.assertEqual(self.session.chat_state_data['service']['service_id'], self.court.pk)
        self.assertNotIn('items', self.session.chat_state_data)
        self.assertIn('## Cancelled', self.reply_prompt())
        self.assertEqual(response.json()['debug']['reply_kind'], 'slot_options')
        self.assertTrue(response.json()['message'].startswith('Your order is cancelled.'))

    def test_cancel_and_order_at_the_start_is_no_contradiction(self):
        # Nothing in progress to cancel; the new order starts. The reply hears only about placed ones.
        self.send('cancel my last order and get me a racket', {'items': [{'product_id': self.racket.pk, 'quantity': 1}], 'done_choosing': False},
                  intents=['order', 'cancel'])
        self.assertEqual(self.session.chat_state_id, 'product_selection')
        prompt = self.reply_prompt()
        self.assertIn('nothing in progress was cancelled. Orders and bookings already placed', prompt)
        self.assertNotIn('no order or booking is in progress', prompt)
