from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from checkout_app.models import OrderItem, OrderStatus, ScheduleItem
from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider

from .. import past_orders
from ..models import ChatSession
from ..past_orders import Lookup, clean_request, lookup, reply_is_grounded
from ..prompts import (
    build_order_status_prompt,
    format_order_records,
    order_status_fallback_message,
)
from ..tools import Toolbox

SGT = ZoneInfo('Asia/Singapore')
ALICE = '+6591111111'
BOB = '+6592222222'


def make_order(session, *items, status=OrderStatus.PENDING_PAYMENT, created=None):
    """An order placed in `session` (straight to the database). `items`: (name, quantity, unit_price)."""
    return OrderItem.objects.create(
        business=session.business,
        chat_session=session,
        is_sandbox=session.is_sandbox,
        order_status=status,
        created_time=created or timezone.now(),
        order_data={
            'items': [
                {'product_id': n, 'name': name, 'unit_price': price, 'quantity': quantity}
                for n, (name, quantity, price) in enumerate(items, start=1)
            ],
            'details': {'name': 'Alice'},
        },
    )


def make_booking(session, service, start, status=OrderStatus.PENDING_PAYMENT, provider=None):
    """A booking made in `session` (straight to the database)."""
    end = start + timedelta(minutes=service.duration_minutes)
    return ScheduleItem.objects.create(
        business=session.business,
        chat_session=session,
        is_sandbox=session.is_sandbox,
        service=service,
        service_provider=provider,
        start_time=start,
        end_time=end,
        blocked_until=end,
        order_status=status,
        schedule_data={
            'service': {
                'service_id': service.pk, 'name': service.name, 'price': str(service.price),
                'duration_minutes': service.duration_minutes, 'buffer_minutes': 0,
            },
            'details': {'name': 'Alice'},
        },
    )


class CustomerScopeTests(TestCase):
    """Whose orders a chat sees: the same business and phone number, real or sandbox like the chat."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.alice = ChatSession.objects.create(business=cls.cafe, phone_number=ALICE)
        cls.bob = ChatSession.objects.create(business=cls.cafe, phone_number=BOB)
        cls.alice_at_florist = ChatSession.objects.create(business=cls.florist, phone_number=ALICE)
        cls.alice_sandbox = ChatSession.objects.create(business=cls.cafe, phone_number=ALICE, is_sandbox=True)
        cls.alice_sandbox_2 = ChatSession.objects.create(business=cls.cafe, phone_number=ALICE, is_sandbox=True)
        cls.anonymous_sandbox = ChatSession.objects.create(business=cls.cafe, is_sandbox=True)
        cls.other_anonymous_sandbox = ChatSession.objects.create(business=cls.cafe, is_sandbox=True)

    def ids(self, session):
        return [o['number'] for o in lookup(session, 'order', []).orders]

    def test_only_the_customers_own_orders_with_this_business(self):
        mine = make_order(self.alice, ('Kopi C', 2, '1.80'))
        make_order(self.bob, ('Kopi O', 1, '1.60'))
        make_order(self.alice_at_florist, ('Roses', 1, '68.00'))
        make_order(self.alice_sandbox, ('Kopi C', 1, '1.80'))
        self.assertEqual(self.ids(self.alice), [mine.pk])

    def test_sandbox_chats_with_the_same_number_share_their_orders(self):
        first = make_order(self.alice_sandbox, ('Kopi C', 1, '1.80'), created=timezone.now() - timedelta(days=1))
        second = make_order(self.alice_sandbox_2, ('Kopi O', 1, '1.60'))
        make_order(self.alice, ('Kopi C', 2, '1.80'))  # a real order: not in the sandbox
        self.assertEqual(self.ids(self.alice_sandbox), [second.pk, first.pk])

    def test_sandbox_chats_without_a_number_are_one_test_customer(self):
        # The business testing: an order made in one test chat can be checked from the next.
        first = make_order(self.anonymous_sandbox, ('Kopi C', 1, '1.80'), created=timezone.now() - timedelta(days=1))
        second = make_order(self.other_anonymous_sandbox, ('Kopi O', 1, '1.60'))
        make_order(self.alice_sandbox, ('Kopi C', 3, '1.80'))  # a sandbox chat with a number: another customer
        self.assertEqual(self.ids(self.anonymous_sandbox), [second.pk, first.pk])
        self.assertEqual(self.ids(self.other_anonymous_sandbox), [second.pk, first.pk])
        self.assertNotIn(first.pk, self.ids(self.alice_sandbox))

    def test_someone_elses_number_is_not_found_like_a_number_that_doesnt_exist(self):
        bobs = make_order(self.bob, ('Kopi O', 1, '1.60'))
        found = lookup(self.alice, 'order', [bobs.pk, 99999])
        self.assertEqual((found.orders, found.not_found), ([], [f'order #{bobs.pk}', 'order #99999']))
        self.assertEqual(lookup(self.bob, 'order', [bobs.pk]).orders[0]['number'], bobs.pk)


class LookupTests(TestCase):
    """past_orders.lookup(): the customer's orders and bookings asked about, as records."""

    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Lumen Studio', location='Singapore')
        cls.alice = ChatSession.objects.create(business=cls.studio, phone_number=ALICE)
        cls.bob = ChatSession.objects.create(business=cls.studio, phone_number=BOB)
        cls.portrait = Service.objects.create(business=cls.studio, name='Portrait Session', price='180.00', duration_minutes=60)
        cls.family = Service.objects.create(business=cls.studio, name='Family Shoot', price='250.00', duration_minutes=90)
        cls.mei = ServiceProvider.objects.create(business=cls.studio, name='Mei Lin')
        cls.now = datetime(2026, 10, 10, 9, 0, tzinfo=SGT)

    def test_without_numbers_lists_theirs_newest_first(self):
        placed = datetime(2026, 9, 5, 14, 30, tzinfo=SGT)
        old = make_order(self.alice, ('Prints', 2, '15.00'), ('Album', 1, '80.00'), status=OrderStatus.ORDER_COMPLETED, created=placed)
        new = make_order(self.alice, ('Prints', 1, '15.00'), created=placed + timedelta(days=2))
        past = make_booking(self.alice, self.portrait, datetime(2026, 9, 5, 10, 0, tzinfo=SGT), status=OrderStatus.ORDER_COMPLETED)
        upcoming = make_booking(self.alice, self.family, datetime(2026, 10, 17, 14, 0, tzinfo=SGT), provider=self.mei)
        make_booking(self.bob, self.portrait, datetime(2026, 9, 6, 10, 0, tzinfo=SGT))  # someone else's
        found = lookup(self.alice, 'any', [], now=self.now)
        self.assertEqual([o['number'] for o in found.orders], [new.pk, old.pk])
        self.assertEqual(found.orders[1], {
            'number': old.pk, 'placed': 'Sat 5 Sep 2026, 2:30pm', 'items': '2 × Prints, 1 × Album', 'total': '110.00',
            'status': 'Completed', 'status_meaning': 'the order is completed',
        })
        self.assertEqual([b['number'] for b in found.bookings], [upcoming.pk, past.pk])
        self.assertEqual(found.bookings[0], {
            'number': upcoming.pk, 'service': 'Family Shoot', 'time': 'Sat 17 Oct 2026, 2:00pm to 3:30pm', 'upcoming': True,
            'with': 'Mei Lin', 'total': '250.00', 'status': 'Payment pending',
            'status_meaning': 'the time is held for the customer, but the business has not received the payment yet',
        })
        self.assertEqual((found.bookings[1]['upcoming'], found.bookings[1]['with']), (False, None))
        self.assertEqual(found.not_found, [])
        # Only the kind asked about.
        self.assertEqual(lookup(self.alice, 'order', []).bookings, [])
        self.assertEqual(lookup(self.alice, 'booking', []).orders, [])

    def test_at_most_list_max(self):
        now = timezone.now()
        for n in range(past_orders.LIST_MAX + 1):
            make_order(self.alice, ('Prints', 1, '15.00'), created=now - timedelta(hours=n))
        found = lookup(self.alice, 'order', [])
        self.assertEqual((len(found.orders), found.more_orders), (past_orders.LIST_MAX, True))

    def numbers(self, found):
        return [o['number'] for o in found.orders], [b['number'] for b in found.bookings]

    def test_numbers_of_either_kind(self):
        # Orders and bookings are numbered separately: #N can be an order, a booking, or both.
        order = make_order(self.alice, ('Prints', 1, '15.00'))
        start = datetime(2026, 9, 5, 10, 0, tzinfo=SGT)
        bookings = [make_booking(self.alice, self.portrait, start + timedelta(days=n)) for n in range(2)]
        only_booking = next(b for b in bookings if b.pk != order.pk)
        self.assertEqual(self.numbers(lookup(self.alice, 'booking', [only_booking.pk], now=self.now)), ([], [only_booking.pk]))
        # "Order #N" meaning one of their bookings (customers mix the words up): still found, as a booking.
        self.assertEqual(self.numbers(lookup(self.alice, 'order', [only_booking.pk], now=self.now)), ([], [only_booking.pk]))
        both = [b for b in bookings if b.pk == order.pk]
        if both:  # an order and a booking with the same number: "any" gives both, a kind only that one
            self.assertEqual(self.numbers(lookup(self.alice, 'any', [order.pk], now=self.now)), ([order.pk], [order.pk]))
            self.assertEqual(self.numbers(lookup(self.alice, 'order', [order.pk], now=self.now)), ([order.pk], []))
        self.assertEqual(lookup(self.alice, 'booking', [12345]).not_found, ['booking #12345'])
        self.assertEqual(lookup(self.alice, 'any', [12345]).not_found, ['#12345'])

    def test_each_status(self):
        order = make_order(self.alice, ('Prints', 1, '15.00'))
        for status, label in (
            (OrderStatus.PENDING_PAYMENT, 'Payment pending'),
            (OrderStatus.PAYMENT_RECEIVED, 'Payment received'),
            (OrderStatus.ORDER_COMPLETED, 'Completed'),
        ):
            order.order_status = status
            order.save()
            record = lookup(self.alice, 'order', [order.pk]).orders[0]
            self.assertEqual((record['status'], record['status_meaning']), (label, past_orders.ORDER_STATUS_MEANINGS[status]))


class CleanRequestTests(SimpleTestCase):
    """What the extraction LLM returns, made safe before anything is looked up."""

    def test_kind_and_numbers(self):
        self.assertEqual(clean_request({'kind': 'booking', 'numbers': [3]}), ('booking', [3]))
        self.assertEqual(clean_request({'kind': 'order', 'numbers': ['#12', '7', 12, 7]}), ('order', [12, 7]))

    def test_anything_else_is_dropped(self):
        self.assertEqual(clean_request({}), ('any', []))
        self.assertEqual(clean_request({'kind': 'everything', 'numbers': 'all'}), ('any', []))
        self.assertEqual(clean_request({'kind': 'order', 'numbers': [True, -1, 0, 1.5, None, 'the last one', [4]]}), ('order', []))
        self.assertEqual(clean_request({'kind': 'order', 'numbers': list(range(1, 20))})[1], [1, 2, 3, 4, 5])


class GroundingTests(SimpleTestCase):
    """reply_is_grounded(): a reply may only name the order / booking numbers in the records."""

    found = Lookup(kind='any', numbers=[1], orders=[{'number': 12}], bookings=[{'number': 7}], not_found=['#1'])

    def test_numbers_found_or_asked_about(self):
        for reply in (
            'Order #12 is paid, and booking #7 is coming up.',
            "I couldn't find #1 among your orders.",
            'Your order 12 is paid.',
            'Nothing to report.',
            'It costs $3.60 and starts at 2:30pm on 5 Sep 2026.',  # prices, times and dates aren't numbers of orders
        ):
            with self.subTest(reply=reply):
                self.assertTrue(reply_is_grounded(reply, self.found))

    def test_a_number_not_found_may_only_be_said_not_found(self):
        for reply, grounded in (
            ("Booking #7 is coming up. I couldn't find #1 among your bookings.", True),
            ('#1 does not match any of your orders. Could you check the number?', True),
            ('Sorry, I cannot find booking #1.', True),
            ('Your booking #1 for a Newborn Session on Monday, 2nd October 2026 is in the "Payment pending" status.', False),
            ('Booking #1 is paid!', False),
        ):
            with self.subTest(reply=reply):
                self.assertEqual(reply_is_grounded(reply, self.found), grounded)

    def test_any_other_number_was_made_up(self):
        for reply in (
            'Your booking #2 for a Newborn Session is paid.',
            'Order #12 is paid, and order #13 is pending.',
            'booking number 99 is done',
            'Order no. 4 is ready.',
            'Your orders 12 and # 5 are paid.',
        ):
            with self.subTest(reply=reply):
                self.assertFalse(reply_is_grounded(reply, self.found))


class RecordsTextTests(SimpleTestCase):
    """The records as the reply prompt gets them, and the fallback reply written by code."""

    order = {
        'number': 12, 'placed': 'Sat 5 Sep 2026, 2:30pm', 'items': '2 × Kopi C', 'total': '3.60',
        'status': 'Payment received', 'status_meaning': 'the business has received the payment; the order is not completed yet',
    }
    booking = {
        'number': 7, 'service': 'Couple Photoshoot', 'time': 'Sat 10 Oct 2026, 10:30am to 12:00pm', 'upcoming': True,
        'with': 'Mei Lin', 'total': '280.00', 'status': 'Payment pending', 'status_meaning': 'not paid yet',
    }

    def test_records(self):
        found = Lookup(kind='any', numbers=[12, 7, 1], orders=[self.order], bookings=[self.booking], not_found=['#1'])
        self.assertEqual(format_order_records(found), (
            '- Order #12, placed Sat 5 Sep 2026, 2:30pm: 2 × Kopi C. Total $3.60. Status: Payment received '
            '(the business has received the payment; the order is not completed yet).\n'
            '- Booking #7: Couple Photoshoot, Sat 10 Oct 2026, 10:30am to 12:00pm, with Mei Lin (upcoming). '
            'Total $280.00. Status: Payment pending (not paid yet).\n'
            "- Not found among this customer's orders and bookings: #1."
        ))
        self.assertEqual(
            format_order_records(Lookup(kind='booking', numbers=[])), '- This customer has no bookings in the records.'
        )

    def test_prompt_rules(self):
        prompt = build_order_status_prompt(SimpleNamespaceBusiness(), '- Order #12 …')
        self.assertIn('## What the records say\n- Order #12 …', prompt)
        for rule in (
            'Never add, guess or change anything',
            'Copy numbers, dates, times, prices and statuses exactly as written.',
            "tell them you couldn't find it among their orders or bookings",
            'Never say or suggest that it belongs to someone else.',
            "say honestly that you don't know, and that the team can help",
            "You can't take payments, or change, cancel or refund anything in this chat: never offer to.",
        ):
            self.assertIn(rule, prompt)

    def test_fallback_message(self):
        found = Lookup(kind='any', numbers=[1], orders=[self.order], bookings=[self.booking], not_found=['#1'])
        self.assertEqual(order_status_fallback_message(found), (
            "Here's what I found:\n"
            '- Order #12 (Sat 5 Sep 2026, 2:30pm): 2 × Kopi C, $3.60. Status: Payment received.\n'
            '- Booking #7: Couple Photoshoot, Sat 10 Oct 2026, 10:30am to 12:00pm, $280.00. Status: Payment pending.\n\n'
            "I couldn't find #1 among your orders or bookings. Could you check the number?\n\n"
            'Is there anything else I can help you with?'
        ))
        self.assertEqual(
            order_status_fallback_message(Lookup(kind='order', numbers=[])),
            "Sorry, I couldn't find any orders for you. Is there anything else I can help you with?",
        )


class SimpleNamespaceBusiness:
    business_name = 'Kopi Café'


class NoOrderToolsTests(TestCase):
    def test_the_toolbox_has_no_order_lookups(self):
        business = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        names = [spec['function']['name'] for spec in Toolbox(business).specs]
        self.assertEqual(names, ['list_products', 'get_product_details', 'list_services', 'get_service_details', 'list_faqs'])
