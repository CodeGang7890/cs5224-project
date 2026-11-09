import copy
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from chat_app.models import ChatSession
from configuration_app.models import BusinessConfiguration
from product_app.models import Service, ServiceProvider, WeeklyAvailability

from ..models import PAYMENT_REFERENCE_PATTERN, OrderItem, OrderStatus, ScheduleItem, new_payment_reference
from ..validators import validate_order_data, validate_schedule_data

VALID_ORDER_DATA = {
    'items': [
        {'product_id': 1, 'name': 'Kopi C', 'unit_price': '1.80', 'quantity': 2},
        {'product_id': 2, 'name': 'Kaya Toast Set', 'unit_price': '5.50', 'quantity': 1},
    ],
    'details': {'name': 'Alice', 'email': 'alice@example.com', 'postal_code': 238801},
}

VALID_SCHEDULE_DATA = {
    'service': {'service_id': 1, 'name': 'Family', 'price': '250.00', 'duration_minutes': 60, 'buffer_minutes': 30},
    'details': {'name': 'Alice', 'email': 'alice@example.com'},
}


class ValidateOrderDataTests(SimpleTestCase):
    def assertInvalid(self, value, message_part):
        with self.assertRaises(ValidationError) as ctx:
            validate_order_data(value)
        self.assertTrue(
            any(message_part in message for message in ctx.exception.messages),
            f'{message_part!r} not in {ctx.exception.messages}',
        )

    def test_valid(self):
        validate_order_data(VALID_ORDER_DATA)
        validate_order_data({**VALID_ORDER_DATA, 'details': {}})  # a flow without details collection
        item = VALID_ORDER_DATA['items'][0]
        for price in ('0', '0.00', '5', '5.5', '99999999.99'):
            with self.subTest(price=price):
                validate_order_data({'items': [{**item, 'unit_price': price}], 'details': {}})

    def test_invalid(self):
        item = VALID_ORDER_DATA['items'][0]
        cases = {
            'not an object': ([], 'must be an object'),
            'missing items': ({'details': {}}, 'Missing field(s) items'),
            'missing details': ({'items': [item]}, 'Missing field(s) details'),
            'unknown field': ({**VALID_ORDER_DATA, 'total': '3.60'}, 'Unknown field(s) total'),
            'items not a list': ({'items': {}, 'details': {}}, 'items must be a list'),
            'no items': ({'items': [], 'details': {}}, 'items must have at least one item'),
            'item missing field': ({'items': [{'product_id': 1}], 'details': {}}, 'must be an object with exactly'),
            'item extra field': ({'items': [{**item, 'note': 'x'}], 'details': {}}, 'must be an object with exactly'),
            'product_id not int': ({'items': [{**item, 'product_id': '1'}], 'details': {}}, 'product_id must be an integer'),
            'duplicate product': ({'items': [item, {**item, 'quantity': 1}], 'details': {}}, 'listed more than once'),
            'blank name': ({'items': [{**item, 'name': ''}], 'details': {}}, 'name must be a non-blank string'),
            'numeric price': ({'items': [{**item, 'unit_price': 1.8}], 'details': {}}, 'unit_price must be a decimal string'),
            'negative price': ({'items': [{**item, 'unit_price': '-1.00'}], 'details': {}}, 'unit_price must be'),
            'three decimals': ({'items': [{**item, 'unit_price': '1.805'}], 'details': {}}, 'unit_price must be'),
            'price too big': ({'items': [{**item, 'unit_price': '100000000.00'}], 'details': {}}, 'unit_price must be'),
            'price not a number': ({'items': [{**item, 'unit_price': 'abc'}], 'details': {}}, 'unit_price must be'),
            'infinite price': ({'items': [{**item, 'unit_price': 'Infinity'}], 'details': {}}, 'unit_price must be'),
            'zero quantity': ({'items': [{**item, 'quantity': 0}], 'details': {}}, 'quantity must be an integer from 1'),
            'bool quantity': ({'items': [{**item, 'quantity': True}], 'details': {}}, 'quantity must be an integer from 1'),
            'huge quantity': ({'items': [{**item, 'quantity': 1_000_001}], 'details': {}}, 'quantity must be an integer from 1'),
            'details not object': ({'items': [item], 'details': 'Alice'}, 'details must be an object'),
            'bad detail key': ({'items': [item], 'details': {'Postal Code': 1}}, "details: invalid key 'Postal Code'"),
            'blank detail': ({'items': [item], 'details': {'name': ' '}}, 'details: name must be a non-blank string or a number'),
            'bool detail': ({'items': [item], 'details': {'agreed': False}}, 'details: agreed must be'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label):
                self.assertInvalid(value, message_part)

    def test_every_error_is_listed(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_order_data({'items': [{'product_id': 'x', 'name': '', 'unit_price': 1, 'quantity': 0}], 'details': []})
        self.assertEqual(len(ctx.exception.messages), 5, ctx.exception.messages)


class OrderItemModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')

    def test_defaults_and_total(self):
        order = OrderItem(business=self.business, order_data=VALID_ORDER_DATA)
        order.full_clean()
        order.save()
        self.assertEqual(order.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.order_status, 'pending_payment')
        self.assertFalse(order.is_sandbox)
        self.assertIsNone(order.chat_session)
        self.assertEqual(order.total, Decimal('9.10'))  # 2 × 1.80 + 5.50
        self.assertRegex(order.payment_reference, PAYMENT_REFERENCE_PATTERN)

    def test_payment_reference_is_random_128_bits(self):
        references = {new_payment_reference() for _ in range(1000)}
        self.assertEqual(len(references), 1000)
        for reference in list(references)[:10]:
            self.assertRegex(reference, PAYMENT_REFERENCE_PATTERN)  # 32 hex characters = 128 bits
        first, second = (OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA) for _ in range(2))
        self.assertNotEqual(first.payment_reference, second.payment_reference)

    def test_invalid_payment_reference_rejected_by_the_database(self):
        for reference in ('', 'ABCDEF' + '0' * 26, '0' * 31, 'g' * 32):
            with self.subTest(reference=reference), self.assertRaises(IntegrityError), transaction.atomic():
                OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA, payment_reference=reference)

    def test_statuses(self):
        self.assertEqual(OrderStatus.values, ['pending_payment', 'payment_received', 'order_completed', 'payment_failed'])
        for status in OrderStatus.values:
            OrderItem(business=self.business, order_data=VALID_ORDER_DATA, order_status=status).full_clean()

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            OrderItem(business=self.business, order_data=VALID_ORDER_DATA, order_status='shipped').full_clean()
        self.assertIn('order_status', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA, order_status='shipped')

    def test_invalid_order_data_rejected_by_full_clean(self):
        with self.assertRaises(ValidationError) as ctx:
            OrderItem(business=self.business, order_data={'items': []}).full_clean()
        self.assertIn('order_data', ctx.exception.message_dict)

    def test_a_business_with_orders_cant_be_deleted(self):
        OrderItem.objects.create(business=self.business, order_data=VALID_ORDER_DATA)
        with self.assertRaises(ProtectedError):
            self.business.delete()
        self.assertTrue(OrderItem.objects.exists())


class SampleOrderItemFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_chat_sessions', 'sample_order_items']

    def test_fixture_is_valid(self):
        orders = OrderItem.objects.all()
        self.assertEqual(orders.count(), 64)  # 31–49: Lumen & Lens print orders; 50–61: Rally Point Courts; 62–64: Business Test (kept from production)
        self.assertEqual(set(orders.values_list('order_status', flat=True)), set(OrderStatus.values))
        for order in orders:
            with self.subTest(order=order.pk):
                order.full_clean()  # loaddata skips validation
                self.assertRegex(order.payment_reference, PAYMENT_REFERENCE_PATTERN)
        self.assertEqual(len(set(orders.values_list('payment_reference', flat=True))), 64)

    def test_florist_has_many_realistic_orders(self):
        orders = OrderItem.objects.filter(business_id=2)
        self.assertGreaterEqual(orders.count(), 20)
        self.assertEqual(set(orders.values_list('order_status', flat=True)), set(OrderStatus.values))
        self.assertFalse(orders.filter(is_sandbox=True).exists())
        for order in orders:
            with self.subTest(order=order.pk):
                self.assertEqual(set(order.order_data['details']), {'name', 'card_message', 'collection_date'})
                self.assertGreaterEqual(order.updated_time, order.created_time)


class SampleLumenOrderFixtureTests(TestCase):
    """Lumen & Lens's print and frame orders: delivered, with the photos to print."""

    fixtures = ['sample_business_configurations', 'sample_chat_sessions', 'sample_order_items']

    def test_orders_are_delivered(self):
        orders = OrderItem.objects.filter(business_id=4)
        self.assertEqual(orders.count(), 19)
        self.assertEqual(set(orders.values_list('order_status', flat=True)), set(OrderStatus.values))
        for order in orders:
            with self.subTest(order=order.pk):
                self.assertEqual(set(order.order_data['details']), {'name', 'email', 'photos', 'delivery_address'})
                self.assertRegex(order.order_data['details']['delivery_address'], r'Singapore \d{6}$')
                self.assertTrue(all(20 <= line['product_id'] <= 29 for line in order.order_data['items']))
                self.assertLess(order.created_time, datetime(2026, 10, 11, 12, tzinfo=dt_timezone(timedelta(hours=8))))


class SampleStockFixtureTests(TestCase):
    """The sample products' quantities, derived from the sample orders."""

    fixtures = ['sample_business_configurations', 'sample_products', 'sample_chat_sessions', 'sample_order_items']

    def test_quantities(self):
        from product_app.models import Product

        products = {p.name: p for p in Product.load_stock(Product.objects.all())}
        for product in products.values():
            with self.subTest(product=product.name):
                self.assertGreaterEqual(product.quantity_available, 0)
        rose = products['Classic Red Rose Bouquet (12 Stems)']
        self.assertEqual((rose.total_quantity, rose.quantity_available, rose.quantity_on_hold, rose.quantity_sold), (19, 15, 2, 2))
        bell_jar = products['Preserved Rose Bell Jar']
        self.assertEqual((bell_jar.total_quantity, bell_jar.quantity_available, bell_jar.quantity_on_hold, bell_jar.quantity_sold), (4, 1, 1, 2))



@override_settings(SCHEDULE_TIME_ZONE='Asia/Singapore')
class ScheduleItemModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.studio = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        cls.mei = ServiceProvider.objects.create(business=cls.studio, name='Mei')
        cls.family = Service.objects.create(business=cls.studio, name='Family', price='250.00', duration_minutes=60, buffer_minutes=30)
        cls.start = datetime(2030, 1, 7, 1, 0, tzinfo=dt_timezone.utc)

    def make(self, **overrides):
        fields = {
            'business': self.studio,
            'service': self.family,
            'service_provider': self.mei,
            'start_time': self.start,
            'end_time': self.start + timedelta(hours=1),
            'blocked_until': self.start + timedelta(minutes=90),
            'schedule_data': copy.deepcopy(VALID_SCHEDULE_DATA),
        }
        return ScheduleItem(**{**fields, **overrides})

    def test_valid(self):
        booking = self.make()
        booking.full_clean()
        booking.save()
        self.assertEqual(booking.order_status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(booking.total, Decimal('250.00'))
        self.assertEqual(str(booking), f'Booking #{booking.pk} (Snap Studio)')
        self.make(service=None, service_provider=None).full_clean()  # e.g. both deleted since

    def test_times_must_match_the_snapshot(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make(end_time=self.start + timedelta(minutes=45)).full_clean()
        self.assertIn('end_time', ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            self.make(blocked_until=self.start + timedelta(hours=1)).full_clean()
        self.assertIn('blocked_until', ctx.exception.message_dict)

    def test_times_constrained_in_the_database(self):
        for overrides in ({'end_time': self.start}, {'blocked_until': self.start + timedelta(minutes=30)}, {'order_status': 'lost'}):
            with self.subTest(list(overrides)), self.assertRaises(IntegrityError), transaction.atomic():
                self.make(**overrides).save()

    def test_related_records_must_be_the_same_business(self):
        theirs = Service.objects.create(business=self.other, name='Theirs', price=1, duration_minutes=60)
        their_provider = ServiceProvider.objects.create(business=self.other, name='Them')
        their_chat = ChatSession.objects.create(business=self.other, is_sandbox=True)
        for field, value in (('service', theirs), ('service_provider', their_provider), ('chat_session', their_chat)):
            with self.subTest(field), self.assertRaises(ValidationError) as ctx:
                self.make(**{field: value}).full_clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_invalid_schedule_data(self):
        service = VALID_SCHEDULE_DATA['service']
        cases = {
            'not an object': ([], 'must be an object'),
            'missing details': ({'service': service}, 'Missing field(s) details'),
            'unknown field': ({**VALID_SCHEDULE_DATA, 'items': []}, 'Unknown field(s) items'),
            'service missing a field': ({'service': {'name': 'x'}, 'details': {}}, 'service must be an object with exactly'),
            'service_id not int': ({'service': {**service, 'service_id': '1'}, 'details': {}}, 'service_id must be an integer'),
            'blank name': ({'service': {**service, 'name': ' '}, 'details': {}}, 'name must be a non-blank string'),
            'numeric price': ({'service': {**service, 'price': 250}, 'details': {}}, 'price must be a decimal string'),
            'negative price': ({'service': {**service, 'price': '-1.00'}, 'details': {}}, 'price must be a decimal string'),
            'zero duration': ({'service': {**service, 'duration_minutes': 0}, 'details': {}}, 'duration_minutes must be a positive'),
            'bool buffer': ({'service': {**service, 'buffer_minutes': True}, 'details': {}}, 'buffer_minutes must be an integer'),
            'bad detail': ({'service': service, 'details': {'Name': 'x'}}, "details: invalid key 'Name'"),
            'blank detail': ({'service': service, 'details': {'name': ''}}, 'details: name must be a non-blank'),
        }
        for label, (value, message_part) in cases.items():
            with self.subTest(label), self.assertRaises(ValidationError) as ctx:
                validate_schedule_data(value)
            self.assertTrue(any(message_part in m for m in ctx.exception.messages), ctx.exception.messages)

    def test_kept_when_the_chat_is_deleted(self):
        chat = ChatSession.objects.create(business=self.studio, is_sandbox=True)
        booking = self.make(chat_session=chat)
        booking.save()
        chat.delete()
        booking.refresh_from_db()
        self.assertIsNone(booking.chat_session)
        self.assertEqual(booking.schedule_data['service']['name'], 'Family')

    def test_its_service_and_provider_cant_be_deleted(self):
        self.make().save()
        for record in (self.family, self.mei):
            with self.subTest(record=record), self.assertRaises(ProtectedError):
                record.delete()

    def test_a_business_with_bookings_cant_be_deleted(self):
        self.make().save()
        with self.assertRaises(ProtectedError):
            self.studio.delete()
        self.assertTrue(ScheduleItem.objects.exists())


class SampleScheduleItemFixtureTests(TestCase):
    """checkout_app/fixtures/sample_schedule_items.json: 110 Lumen & Lens and Rally Point Courts
    bookings: none in September, some in October, most upcoming in November and December 2026."""

    fixtures = [
        'sample_business_configurations', 'sample_services', 'sample_chat_configurations', 'sample_chat_sessions',
        'sample_schedule_items',
    ]

    def test_fixture_is_valid(self):
        bookings = list(ScheduleItem.objects.select_related('service', 'service_provider'))
        self.assertEqual(len(bookings), 113)  # 111–113: Business Test, kept from production
        providers_of = {s.pk: set(s.service_providers.values_list('pk', flat=True)) for s in Service.objects.all()}
        for booking in bookings:
            with self.subTest(booking=booking.pk):
                booking.full_clean()  # loaddata skips validation; this also checks the times match the snapshot
                self.assertIn(booking.business_id, (4, 5, 7))
                self.assertIn(booking.service_provider_id, providers_of[booking.service_id])
                self.assertLessEqual(booking.created_time, booking.start_time)
                self.assertGreaterEqual(booking.updated_time, booking.created_time)
        # No two bookings of one provider overlap (with their buffers).
        by_provider = {}
        for booking in sorted(bookings, key=lambda b: b.start_time):
            by_provider.setdefault(booking.service_provider_id, []).append(booking)
        for provider_bookings in by_provider.values():
            for a, b in zip(provider_bookings, provider_bookings[1:]):
                self.assertLessEqual(a.blocked_until, b.start_time, (a.pk, b.pk))
        self.assertEqual({b.order_status for b in bookings}, set(OrderStatus.values))
        references = [b.payment_reference for b in bookings]
        self.assertEqual(len(set(references)), 113)
        for reference in references:
            self.assertRegex(reference, PAYMENT_REFERENCE_PATTERN)
        self.assertEqual(sorted(b.pk for b in bookings if b.is_sandbox), [5, 111, 112, 113])  # 111–113: Business Test's Chat Sandbox

    def test_the_letters_match_the_bookings(self):
        """Each booking's blocks are H while pending, X once paid, and its buffer too where it was
        open (a buffer over closed time stays U, like checkout_app.schedule paints it); no other
        block is H or X."""
        expected, buffers = {}, set()
        # A booking whose payment failed takes up no time: its blocks are back to O.
        for booking in ScheduleItem.objects.exclude(order_status=OrderStatus.PAYMENT_FAILED):
            letter = 'H' if booking.order_status == OrderStatus.PENDING_PAYMENT else 'X'
            moment = booking.start_time
            while moment < booking.blocked_until:
                local = moment.astimezone(dt_timezone(timedelta(hours=8)))
                monday = local.date() - timedelta(days=local.weekday())
                key = (booking.service_provider_id, monday, local.weekday() * 96 + (local.hour * 60 + local.minute) // 15)
                expected[key] = letter
                if moment >= booking.end_time:
                    buffers.add(key)
                moment += timedelta(minutes=15)
        mismatches = []
        for week in WeeklyAvailability.objects.all():
            for index, letter in enumerate(week.availability):
                key = (week.service_provider_id, week.week, index)
                if (letter in 'HX' or key in expected) and letter != expected.get(key):
                    if not (letter == 'U' and key in buffers):
                        mismatches.append((str(week), index, letter, expected.get(key)))
        self.assertEqual(mismatches, [])

    def test_a_few_payments_failed_and_their_time_is_free(self):
        failed = ScheduleItem.objects.filter(order_status=OrderStatus.PAYMENT_FAILED)
        self.assertEqual(sorted(failed.values_list('business_id', flat=True)), [4, 5, 5, 5, 5, 5, 5, 7, 7])
        for booking in failed:
            local = booking.start_time.astimezone(dt_timezone(timedelta(hours=8)))
            week = WeeklyAvailability.objects.get(
                service_provider_id=booking.service_provider_id, week=local.date() - timedelta(days=local.weekday())
            )
            index = local.weekday() * 96 + (local.hour * 60 + local.minute) // 15
            with self.subTest(booking=booking.pk):
                self.assertEqual(week.availability[index], 'O')

    def test_bookings_from_october_to_december(self):
        sgt = dt_timezone(timedelta(hours=8))
        months = sorted({b.start_time.astimezone(sgt).month for b in ScheduleItem.objects.all()})
        self.assertEqual(months, [10, 11, 12])  # September is empty
        self.assertEqual(ScheduleItem.objects.filter(business_id=4).count(), 12)

    def test_court_bookings_on_the_hour(self):
        courts = ScheduleItem.objects.filter(business_id=5)
        self.assertEqual(courts.count(), 98)
        self.assertEqual(set(courts.values_list('order_status', flat=True)), set(OrderStatus.values))
        sgt = dt_timezone(timedelta(hours=8))
        days = set()
        for booking in courts:
            start = booking.start_time.astimezone(sgt)
            with self.subTest(booking=booking.pk):
                self.assertEqual((start.minute, booking.end_time - booking.start_time), (0, timedelta(hours=1)))
                self.assertTrue(9 <= start.hour <= 20)  # the last one ends at 9pm
                self.assertEqual(set(booking.schedule_data['details']) - {'players'}, {'name', 'email'})
            days.add(start.date())
        self.assertEqual((min(days).month, max(days).month), (10, 12))
        # Booked in advance, never after "now" (11 Oct 2026); only past ones are completed.
        now = datetime(2026, 10, 11, 12, tzinfo=sgt)
        self.assertFalse(courts.filter(created_time__gt=now).exists())
        self.assertFalse(courts.filter(order_status=OrderStatus.ORDER_COMPLETED, start_time__gt=now).exists())


    def test_the_booking_made_in_a_chat(self):
        booking = ScheduleItem.objects.get(pk=1)
        session = booking.chat_session
        self.assertEqual(session.pk, 20)
        self.assertEqual(session.chat_state_data, {'last_booking_id': 1})
        self.assertEqual(booking.schedule_data['details'], {
            'name': 'Priya Raman', 'people': 4, 'notes': 'Bringing our dog Mochi',
        })
        confirm, reply = session.chat_message_json[-2:]
        self.assertEqual(confirm['message'], 'CONFIRM')
        self.assertTrue(reply['message'].startswith('Thank you! Your booking #1 with Lumen & Lens Photography Studio is confirmed.'))
        # Saved after the customer confirmed, and before they were told.
        self.assertLessEqual(datetime.fromisoformat(confirm['message_time']), booking.created_time)
        self.assertLessEqual(booking.created_time, datetime.fromisoformat(reply['message_time']))


class PaymentReferenceMigrationTests(TransactionTestCase):
    """checkout_app 0005–0006: every existing order and booking gets its own payment reference."""

    # Replay checkout migrations while keeping the unrelated business schema current.
    before = [('checkout_app', '0004_payment_failed_status'), ('configuration_app', '0012_business_payment_expiry')]
    after = [('checkout_app', '0006_payment_reference_required'), ('configuration_app', '0012_business_payment_expiry')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_existing_rows_get_distinct_references(self):
        apps = self.migrate(self.before)
        # Through the current model: configuration_app isn't rolled back, and its newer columns are required.
        business = apps.get_model('configuration_app', 'BusinessConfiguration').objects.get(
            pk=BusinessConfiguration.objects.create(business_name='Kopi', location='SG').pk
        )
        OldOrder = apps.get_model('checkout_app', 'OrderItem')
        for _ in range(3):
            OldOrder.objects.create(business=business, order_data=VALID_ORDER_DATA)
        apps = self.migrate(self.after)
        references = list(apps.get_model('checkout_app', 'OrderItem').objects.values_list('payment_reference', flat=True))
        self.assertEqual(len(set(references)), 3)
        for reference in references:
            self.assertRegex(reference, PAYMENT_REFERENCE_PATTERN)
