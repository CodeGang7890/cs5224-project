import re
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from configuration_app.models import BusinessConfiguration

from .models import (
    AVAILABILITY_LENGTH,
    AVAILABILITY_PATTERN,
    SLOT_LETTERS,
    FAQ,
    FAQ_ANSWER_MAX_LENGTH,
    PRODUCT_DESCRIPTION_MAX_LENGTH,
    PRODUCT_INFORMATION_MAX_LENGTH,
    QUANTITY_MAX,
    SLOT_MINUTES,
    SLOTS_PER_DAY,
    Product,
    Service,
    ServiceProvider,
    WeeklyAvailability,
    block_index,
    validate_availability,
)


class ProductModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(
            business_name='Test Café', location='Singapore'
        )

    def make_product(self, **overrides):
        fields = {'business': self.business, 'name': 'Latte', 'price': Decimal('4.50')}
        return Product(**{**fields, **overrides})

    def test_valid_product(self):
        product = self.make_product(total_quantity=10)
        product.full_clean()
        product.save()
        self.assertTrue(product.is_active)
        self.assertEqual((product.quantity_available, product.quantity_on_hold, product.quantity_sold), (10, 0, 0))

    def test_total_quantity_defaults_to_zero(self):
        product = self.make_product()
        product.full_clean()
        self.assertEqual((product.total_quantity, product.quantity_available), (0, 0))

    def test_negative_price_rejected_by_validation(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_product(price=Decimal('-0.01')).full_clean()
        self.assertIn('price', ctx.exception.message_dict)

    def test_negative_price_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(price=Decimal('-1')).save()

    def test_price_limited_to_two_decimal_places(self):
        with self.assertRaises(ValidationError):
            self.make_product(price=Decimal('1.999')).full_clean()

    def test_negative_total_quantity_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_product(total_quantity=-1).full_clean()
        self.assertIn('total_quantity', ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(total_quantity=-1).save()

    def test_total_quantity_limit(self):
        self.make_product(total_quantity=QUANTITY_MAX).full_clean()
        with self.assertRaises(ValidationError):
            self.make_product(total_quantity=QUANTITY_MAX + 1).full_clean()

    def test_description_and_information_length_limits(self):
        self.assertEqual((PRODUCT_DESCRIPTION_MAX_LENGTH, PRODUCT_INFORMATION_MAX_LENGTH), (300, 5000))
        for field, limit in (('description', PRODUCT_DESCRIPTION_MAX_LENGTH), ('information', PRODUCT_INFORMATION_MAX_LENGTH)):
            with self.subTest(field=field):
                self.make_product(**{field: 'x' * limit}).full_clean()
                with self.assertRaises(ValidationError) as ctx:
                    self.make_product(**{field: 'x' * (limit + 1)}).full_clean()
                self.assertIn(field, ctx.exception.message_dict)

    def test_description_and_information_are_optional(self):
        product = self.make_product()
        product.full_clean()
        self.assertEqual((product.description, product.information), ('', ''))

    def test_name_unique_per_business(self):
        self.make_product().save()
        with self.assertRaises(ValidationError):
            self.make_product().full_clean()
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        self.make_product(business=other).full_clean()  # same name, different business: OK

    def test_empty_name_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(name='').save()


class FAQModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(
            business_name='Test Café', location='Singapore'
        )

    def test_long_answer_allowed_up_to_limit(self):
        FAQ(business=self.business, question='Q?', answer='x' * FAQ_ANSWER_MAX_LENGTH).full_clean()

    def test_answer_over_limit_rejected(self):
        faq = FAQ(business=self.business, question='Q?', answer='x' * (FAQ_ANSWER_MAX_LENGTH + 1))
        with self.assertRaises(ValidationError):
            faq.full_clean()

    def test_question_unique_per_business(self):
        FAQ.objects.create(business=self.business, question='Open?', answer='Yes')
        with self.assertRaises(ValidationError):
            FAQ(business=self.business, question='Open?', answer='Still yes').full_clean()

    def test_deleting_business_deletes_products_and_faqs(self):
        Product.objects.create(business=self.business, name='Latte', price=Decimal('4.50'))
        FAQ.objects.create(business=self.business, question='Open?', answer='Yes')
        self.business.delete()
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(FAQ.objects.count(), 0)


class SampleProductAndFAQFixtureTests(TestCase):
    fixtures = ['sample_business_configurations', 'sample_products', 'sample_faqs', 'sample_order_items']

    def test_fixtures_are_valid(self):
        self.assertEqual(Product.objects.count(), 29)  # 20–29: Lumen & Lens's prints and frames
        self.assertEqual(FAQ.objects.count(), 52)  # 35–44: Lumen & Lens, 45–52: Rally Point Courts
        for record in [*Product.objects.all(), *FAQ.objects.all()]:
            with self.subTest(record=str(record)):
                record.full_clean()  # loaddata skips validation

    def test_no_product_is_oversold(self):
        for product in Product.load_stock(Product.objects.all()):
            with self.subTest(product=product.name):
                self.assertGreaterEqual(product.quantity_available, 0)
                product.full_clean()  # includes total_quantity ≥ on hold + sold

    def test_cafe_has_detailed_products_and_faqs(self):
        # Kopi & Co. Café (business 1) is the main test business for the chat assistant.
        cafe_products = Product.objects.filter(business_id=1, is_active=True)
        self.assertEqual(
            sorted(cafe_products.values_list('name', flat=True)),
            ['Iced Teh Tarik', 'Kaya Toast Set', 'Kopi C', 'Pandan Chiffon Cake (Whole)'],
        )
        for product in cafe_products:
            with self.subTest(product=product.name):
                self.assertTrue(product.description)  # a short summary
                self.assertGreater(len(product.information), 500)  # long enough to need get_product_details
        self.assertEqual(FAQ.objects.filter(business_id=1).count(), 12)

    def test_photography_studio_sells_prints_and_frames_for_delivery(self):
        # Lumen & Lens (business 4): sessions are services; prints, frames and albums are products, delivered.
        products = Product.objects.filter(business_id=4)
        self.assertEqual(products.count(), 10)
        for product in products:
            with self.subTest(product=product.name):
                self.assertTrue(product.is_active and product.description)
                self.assertIn('delivered anywhere in Singapore', product.information)
        self.assertTrue(FAQ.objects.filter(business_id=4, question='Do you deliver prints and frames?').exists())
        self.assertEqual(FAQ.objects.filter(business_id=5).count(), 8)

    def test_florist_has_a_realistic_catalogue_and_faqs(self):
        # Bloom & Twine Florist Studio (business 2): fresh, dried / preserved, soap and crochet flowers.
        products = Product.objects.filter(business_id=2)
        self.assertEqual(products.count(), 12)
        self.assertTrue(all(product.is_active for product in products))
        collections = {}
        for product in products:
            with self.subTest(product=product.name):
                sentences = [s for s in product.description.replace('!', '.').split('. ') if s.strip()]
                self.assertLessEqual(len(sentences), 2)  # 1-2 sentences
                self.assertGreater(len(product.information), 1000)  # the long details
                kind = product.information.split('\n', 1)[0]
                self.assertRegex(kind, r'^Type: (fresh|dried|preserved|soap|crochet) flowers')
                collections.setdefault(kind.split()[1], []).append(product.name)
                # Only the product itself (materials, care, allergies…): no prices, variants or logistics.
                self.assertNotRegex(product.information, r'(?i)\$|deliver|bulk|upgrade|add-on|colours:|made to order')
        self.assertEqual({key: len(names) for key, names in collections.items()},
                         {'fresh': 3, 'dried': 2, 'preserved': 1, 'soap': 3, 'crochet': 3})
        self.assertEqual(
            sorted(p.name for p in Product.load_stock(products) if p.quantity_available == 0),
            ['Crochet Forever Rose Bouquet (12 Stems)'],
        )
        bell_jar = Product.objects.get(name='Preserved Rose Bell Jar')
        self.assertEqual((bell_jar.total_quantity, bell_jar.quantity_available), (4, 1))  # the last one
        prices = sorted(products.values_list('price', flat=True))
        self.assertLess(prices[0], Decimal('10'))
        self.assertGreater(prices[-1], Decimal('200'))
        self.assertGreaterEqual(FAQ.objects.filter(business_id=2).count(), 15)


class ProductInformationMigrationTests(TransactionTestCase):
    """0003_product_information: a description longer than the new 300 limit moves to `information`."""

    before = [('product_app', '0002_product_quantity_max'), ('configuration_app', '0001_initial')]
    after = [('product_app', '0003_product_information')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_long_descriptions_move_to_information(self):
        apps = self.migrate(self.before)
        business = apps.get_model('configuration_app', 'BusinessConfiguration').objects.create(
            business_name='Café', location='SG'
        )
        Product = apps.get_model('product_app', 'Product')
        long_text = 'Made fresh every morning.\n\n' + 'Contains eggs and wheat. ' * 40
        long_product = Product.objects.create(business=business, name='Cake', price='28.00', description=long_text)
        short_product = Product.objects.create(business=business, name='Tea', price='2.00', description='Black tea.')

        Product = self.migrate(self.after).get_model('product_app', 'Product')
        long_product = Product.objects.get(pk=long_product.pk)
        self.assertEqual(long_product.information, long_text)
        self.assertLessEqual(len(long_product.description), PRODUCT_DESCRIPTION_MAX_LENGTH)
        self.assertTrue(long_product.description.startswith('Made fresh every morning. Contains eggs'))
        self.assertTrue(long_product.description.endswith('…'))
        short_product = Product.objects.get(pk=short_product.pk)
        self.assertEqual((short_product.description, short_product.information), ('Black tea.', ''))

        # And back: the long description is restored.
        Product = self.migrate(self.before).get_model('product_app', 'Product')
        self.assertEqual(Product.objects.get(pk=long_product.pk).description, long_text)



class ProductTotalQuantityMigrationTests(TransactionTestCase):
    """0004_product_total_quantity: the three stored quantities become one total_quantity."""

    before = [('product_app', '0003_product_information'), ('configuration_app', '0001_initial')]
    after = [('product_app', '0004_product_total_quantity')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_total_is_available_plus_on_hold_plus_sold(self):
        apps = self.migrate(self.before)
        business = apps.get_model('configuration_app', 'BusinessConfiguration').objects.create(
            business_name='Café', location='SG'
        )
        Product = apps.get_model('product_app', 'Product')
        product = Product.objects.create(
            business=business, name='Kopi', price='1.80', quantity_available=5, quantity_on_hold=2, quantity_sold=3
        )

        Product = self.migrate(self.after).get_model('product_app', 'Product')
        self.assertEqual(Product.objects.get(pk=product.pk).total_quantity, 10)

        # And back: everything counts as available.
        Product = self.migrate(self.before).get_model('product_app', 'Product')
        reverted = Product.objects.get(pk=product.pk)
        self.assertEqual((reverted.quantity_available, reverted.quantity_on_hold, reverted.quantity_sold), (10, 0, 0))


class ProductAdminTests(TestCase):
    """Django Admin shows the derived quantities and keeps total_quantity ≥ on hold + sold."""

    fixtures = ['sample_business_configurations', 'sample_products', 'sample_order_items']

    def setUp(self):
        from auth_app.models import BusinessUser

        self.client.force_login(BusinessUser.objects.create_superuser(username='admin', password='pw'))

    def test_changelist_shows_derived_quantities_with_one_orders_query(self):
        from django.test.utils import CaptureQueriesContext
        from django.urls import reverse

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('admin:product_app_product_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quantity available')
        order_queries = [q for q in queries if 'checkout_app_orderitem' in q['sql']]
        self.assertEqual(len(order_queries), 1)  # not one per product

    def test_change_form_rejects_total_below_on_hold_plus_sold(self):
        from django.urls import reverse

        bell_jar = Product.objects.get(name='Preserved Rose Bell Jar')  # 4 in total, 3 in orders
        url = reverse('admin:product_app_product_change', args=[bell_jar.pk])
        form = {
            'business': bell_jar.business_id, 'name': bell_jar.name, 'description': bell_jar.description,
            'information': bell_jar.information, 'price': str(bell_jar.price), 'total_quantity': 2, 'is_active': 'on',
        }
        response = self.client.post(url, form)
        self.assertEqual(response.status_code, 200)  # the form again, with the error
        self.assertContains(response, 'Must be at least 3 (1 on hold and 2 sold in orders)')
        bell_jar.refresh_from_db()
        self.assertEqual(bell_jar.total_quantity, 4)
        response = self.client.post(url, {**form, 'total_quantity': 10})
        self.assertEqual(response.status_code, 302)
        bell_jar.refresh_from_db()
        self.assertEqual(bell_jar.quantity_available, 7)


# --- Service providers, their weeks, and services -----------------------------------------------

def open_hours(*ranges, letter='O', base=None) -> str:
    """A week's letters with `letter` in each `(weekday, 'HH:MM', 'HH:MM')` range (0 = Monday)
    and U elsewhere (or `base`), e.g. open_hours((0, '09:00', '12:00'))."""
    letters = list(base or 'U' * AVAILABILITY_LENGTH)
    for weekday, start, end in ranges:
        first = block_index(weekday, int(start[:2]) * 60 + int(start[3:]))
        last = block_index(weekday, int(end[:2]) * 60 + int(end[3:])) if end != '24:00' else block_index(weekday + 1, 0)
        for index in range(first, last):
            letters[index] = letter
    return ''.join(letters)


MONDAY = date(2030, 1, 7)


class ServiceProviderModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')

    def test_valid_provider(self):
        provider = ServiceProvider(business=self.business, name='Mei', description='Lead photographer')
        provider.full_clean()
        provider.save()
        self.assertTrue(provider.is_active)
        self.assertEqual(str(provider), 'Mei')

    def test_name_required_and_unique_per_business(self):
        ServiceProvider.objects.create(business=self.business, name='Mei')
        with self.assertRaises(ValidationError):
            ServiceProvider(business=self.business, name='Mei').full_clean()
        with self.assertRaises(ValidationError):
            ServiceProvider(business=self.business, name='').full_clean()
        with self.assertRaises(ValidationError):
            ServiceProvider(business=self.business, name='x', description='y' * 301).full_clean()
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        ServiceProvider(business=other, name='Mei').full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ServiceProvider.objects.create(business=self.business, name='Mei')

    def test_deleted_with_business_and_takes_its_weeks(self):
        provider = ServiceProvider.objects.create(business=self.business, name='Mei')
        WeeklyAvailability.objects.create(service_provider=provider, week=MONDAY)
        provider.delete()
        self.assertFalse(WeeklyAvailability.objects.exists())
        ServiceProvider.objects.create(business=self.business, name='Raj')
        self.business.delete()
        self.assertFalse(ServiceProvider.objects.exists())


class WeeklyAvailabilityModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')
        cls.mei = ServiceProvider.objects.create(business=cls.business, name='Mei')

    def test_layout_constants(self):
        self.assertEqual((SLOT_MINUTES, SLOTS_PER_DAY, AVAILABILITY_LENGTH), (15, 96, 672))
        self.assertEqual(SLOT_LETTERS, ('O', 'U', 'H', 'X'))
        self.assertEqual(block_index(0, 0), 0)
        self.assertEqual(block_index(0, 9 * 60), 36)  # Monday 09:00
        self.assertEqual(block_index(1, 0), 96)  # Tuesday 00:00
        self.assertEqual(block_index(6, 23 * 60 + 45), 671)  # Sunday 23:45, the last block
        self.assertEqual(block_index(2, 14 * 60 + 20), 96 * 2 + 57)  # inside the 14:15 block

    def test_defaults_to_unavailable(self):
        week = WeeklyAvailability.objects.create(service_provider=self.mei, week=MONDAY)
        week.full_clean()
        self.assertEqual(week.availability, 'U' * 672)
        self.assertEqual(str(week), 'Mei – week of 07 Jan 2030')
        self.assertEqual(week.business_id, self.business.pk)

    def test_every_letter(self):
        letters = open_hours((0, '09:00', '18:00'))[:-6] + 'OUHHXX'
        week = WeeklyAvailability(service_provider=self.mei, week=MONDAY, availability=letters)
        week.full_clean()
        week.save()
        self.assertEqual((week.block(0, 9 * 60), week.block(0, 8 * 60 + 45)), ('O', 'U'))
        self.assertEqual((week.block(6, 23 * 60), week.block(6, 23 * 60 + 30)), ('H', 'X'))

    def test_invalid_availability(self):
        for label, value in {'too short': 'O' * 671, 'too long': 'O' * 673, 'lowercase': 'o' * 672,
                             'other letter': 'O' * 671 + 'A', 'empty': ''}.items():
            with self.subTest(label), self.assertRaises(ValidationError) as ctx:
                WeeklyAvailability(service_provider=self.mei, week=MONDAY, availability=value).full_clean()
            self.assertIn('availability', ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            validate_availability('O' * 670 + 'ZA')
        self.assertIn("found 'A', 'Z'", ctx.exception.messages[0])

    def test_letters_pattern_works_on_postgresql(self):
        # PostgreSQL rejects regex repeat counts over 255 (`[OUHX]{672}` failed every insert there).
        counts = [int(n) for n in re.findall(r'\{(\d+)\}', AVAILABILITY_PATTERN)]
        self.assertTrue(counts)
        self.assertLessEqual(max(counts), 255)
        for length, valid in ((AVAILABILITY_LENGTH, True), (AVAILABILITY_LENGTH - 1, False), (AVAILABILITY_LENGTH + 1, False)):
            self.assertEqual(bool(re.fullmatch(AVAILABILITY_PATTERN, 'U' * length)), valid)

    def test_invalid_availability_rejected_by_database(self):
        for value in ('O' * 671, 'O' * 671 + 'A'):
            with self.subTest(length=len(value)), self.assertRaises(IntegrityError), transaction.atomic():
                WeeklyAvailability.objects.create(service_provider=self.mei, week=MONDAY, availability=value)

    def test_week_is_a_monday(self):
        with self.assertRaises(ValidationError) as ctx:
            WeeklyAvailability(service_provider=self.mei, week=MONDAY + timedelta(days=2)).full_clean()
        self.assertIn('Must be a Monday', ctx.exception.message_dict['week'][0])

    def test_one_per_provider_and_week(self):
        WeeklyAvailability.objects.create(service_provider=self.mei, week=MONDAY)
        with self.assertRaises(ValidationError):
            WeeklyAvailability(service_provider=self.mei, week=MONDAY).full_clean()
        WeeklyAvailability(service_provider=self.mei, week=MONDAY + timedelta(weeks=1)).full_clean()
        raj = ServiceProvider.objects.create(business=self.business, name='Raj')
        WeeklyAvailability(service_provider=raj, week=MONDAY).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            WeeklyAvailability.objects.create(service_provider=self.mei, week=MONDAY)


class ServiceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.business = BusinessConfiguration.objects.create(business_name='Snap Studio', location='Singapore')

    def make_service(self, **overrides):
        fields = {'business': self.business, 'name': 'Portrait', 'price': Decimal('180.00'), 'duration_minutes': 60}
        return Service(**{**fields, **overrides})

    def test_valid_service(self):
        service = self.make_service(buffer_minutes=15, description='A studio portrait.', information='x' * 5000)
        service.full_clean()
        service.save()
        self.assertTrue(service.is_active)
        self.assertEqual(str(service), 'Portrait')
        self.assertEqual(self.make_service(name='Mini').buffer_minutes, 0)  # no buffer by default

    def test_duration_and_buffer_are_whole_blocks(self):
        for field, value in (
            ('duration_minutes', 0), ('duration_minutes', 10), ('duration_minutes', 50), ('duration_minutes', 1455),
            ('buffer_minutes', 5), ('buffer_minutes', 1455), ('buffer_minutes', -15),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError) as ctx:
                    self.make_service(**{field: value}).full_clean()
                self.assertIn(field, ctx.exception.message_dict)
        for field, value in (('duration_minutes', 15), ('duration_minutes', 1440), ('buffer_minutes', 0), ('buffer_minutes', 45)):
            with self.subTest(field=field, value=value):
                self.make_service(**{field: value}).full_clean()

    def test_constraints_in_the_database(self):
        for overrides in ({'duration_minutes': 0}, {'duration_minutes': 2000}, {'buffer_minutes': 2000}, {'price': Decimal('-1')}, {'name': ''}):
            with self.subTest(**{k: str(v) for k, v in overrides.items()}), self.assertRaises(IntegrityError), transaction.atomic():
                self.make_service(**overrides).save()

    def test_text_limits(self):
        for field, length in (('description', 301), ('information', 5001), ('name', 151)):
            with self.subTest(field), self.assertRaises(ValidationError):
                self.make_service(**{field: 'x' * length}).full_clean()

    def test_name_unique_per_business(self):
        self.make_service().save()
        with self.assertRaises(ValidationError):
            self.make_service().full_clean()
        other = BusinessConfiguration.objects.create(business_name='Other', location='Singapore')
        self.make_service(business=other).full_clean()

    def test_many_to_many_with_service_providers(self):
        # Two photographers: the first can do A, B and C, the second only B and C.
        first = ServiceProvider.objects.create(business=self.business, name='First')
        second = ServiceProvider.objects.create(business=self.business, name='Second')
        a, b, c = (Service.objects.create(business=self.business, name=n, price=100, duration_minutes=60) for n in 'ABC')
        a.service_providers.set([first])
        b.service_providers.set([first, second])
        c.service_providers.set([first, second])
        self.assertEqual(set(first.services.all()), {a, b, c})
        self.assertEqual(set(second.services.all()), {b, c})
        self.assertEqual(list(b.service_providers.order_by('name')), [first, second])
        second.delete()  # deleting a provider only removes the link
        self.assertEqual(list(b.service_providers.all()), [first])
        self.assertTrue(Service.objects.filter(pk=b.pk).exists())

    def test_deleted_with_business(self):
        self.make_service().save()
        self.business.delete()
        self.assertFalse(Service.objects.exists())


class SampleServiceFixtureTests(TestCase):
    """product_app/fixtures/sample_services.json: Lumen & Lens Photography Studio (business 4) and
    Rally Point Courts (business 5)."""

    fixtures = ['sample_business_configurations', 'sample_services']

    def test_fixture_is_valid(self):
        self.assertEqual(ServiceProvider.objects.count(), 6)
        self.assertEqual(Service.objects.count(), 10)
        # 13 weeks per provider, 7 Sep to the week of 30 Nov 2026 (bookings run to the end of November).
        self.assertEqual(WeeklyAvailability.objects.count(), 6 * 13)
        for provider in ServiceProvider.objects.all():
            weeks = list(provider.weekly_availabilities.values_list('week', flat=True))
            self.assertEqual((weeks[0], weeks[-1], len(weeks)), (date(2026, 9, 7), date(2026, 11, 30), 13))
        for item in [*ServiceProvider.objects.all(), *Service.objects.all(), *WeeklyAvailability.objects.all()]:
            with self.subTest(item=str(item)):
                item.full_clean()  # loaddata skips validation
                self.assertIn(item.business_id, (4, 5))
        for service in Service.objects.all():
            with self.subTest(service=service.name):
                self.assertTrue(service.is_active)
                self.assertTrue(service.description and service.information)
                self.assertTrue(service.service_providers.exists())  # bookable

    def test_two_photographers(self):
        mei = ServiceProvider.objects.get(name='Mei Lin')
        arjun = ServiceProvider.objects.get(name='Arjun')
        both = {'Individual Portrait Session', 'Couple Photoshoot', 'Graduation Portraits'}
        self.assertEqual(set(mei.services.values_list('name', flat=True)),
                         both | {'Family Portrait Session', 'Newborn Session', 'Maternity Shoot'})
        self.assertEqual(set(arjun.services.values_list('name', flat=True)), both | {'Corporate Headshots', 'Pet Photoshoot'})
        # A week with no bookings: Mei Tue–Sat 09:00–13:00 and 14:00–18:00 (Saturday until 17:00),
        # Sunday 10:00–16:00, Mondays off.
        week = mei.weekly_availabilities.get(week=date(2026, 11, 2))
        week.availability = week.availability.replace('H', 'O').replace('X', 'O')  # booked blocks were open
        self.assertEqual(week.block(0, 10 * 60), 'U')
        self.assertEqual((week.block(1, 9 * 60), week.block(1, 13 * 60), week.block(1, 14 * 60)), ('O', 'U', 'O'))
        self.assertEqual((week.block(5, 16 * 60 + 45), week.block(5, 17 * 60), week.block(6, 10 * 60)), ('O', 'U', 'O'))
        self.assertEqual(set(week.availability), {'O', 'U'})
        # Arjun: Wed–Sun 10:00–19:00, with lunch.
        week = arjun.weekly_availabilities.get(week=date(2026, 11, 2))
        week.availability = week.availability.replace('H', 'O').replace('X', 'O')
        self.assertEqual((week.block(1, 11 * 60), week.block(2, 10 * 60), week.block(6, 18 * 60 + 45)), ('U', 'O', 'O'))

    def test_court_rental(self):
        # Rally Point Courts: 2 badminton and 2 tennis courts, rented by the hour, 9am to 9pm daily.
        courts = ServiceProvider.objects.filter(business_id=5)
        self.assertEqual(
            sorted(courts.values_list('name', flat=True)),
            ['Badminton Court 1', 'Badminton Court 2', 'Tennis Court 1', 'Tennis Court 2'],
        )
        badminton = Service.objects.get(name='Badminton Court (1 hour)')
        tennis = Service.objects.get(name='Tennis Court (1 hour)')
        for service, kind in ((badminton, 'Badminton'), (tennis, 'Tennis')):
            with self.subTest(service=service.name):
                self.assertEqual((service.duration_minutes, service.buffer_minutes, service.start_interval_minutes), (60, 0, 60))
                self.assertEqual({p.name.split()[0] for p in service.service_providers.all()}, {kind})
                self.assertEqual(service.service_providers.count(), 2)
        open_day = 'U' * 36 + 'O' * 48 + 'U' * 12  # 09:00–21:00
        for week in WeeklyAvailability.objects.filter(service_provider__business_id=5):
            with self.subTest(week=str(week)):
                self.assertEqual(week.availability.replace('H', 'O').replace('X', 'O'), open_day * 7)


class ServiceProvidersMigrationTests(TransactionTestCase):
    """product_app 0006–0007 + checkout_app 0003: each old weekly template becomes a service
    provider with real weeks (current + 3), and bookings are written into them."""

    before = [('product_app', '0005_weeklyavailability_service'), ('checkout_app', '0002_scheduleitem')]
    after = [('product_app', '0007_weekly_availability_per_week'), ('checkout_app', '0003_scheduleitem_service_provider')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_templates_become_providers_with_weeks(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        apps = self.migrate(self.before)
        Business = apps.get_model('configuration_app', 'BusinessConfiguration')
        OldAvailability = apps.get_model('product_app', 'WeeklyAvailability')
        OldService = apps.get_model('product_app', 'Service')
        OldBooking = apps.get_model('checkout_app', 'ScheduleItem')
        studio = Business.objects.create(business_name='Snap', location='SG')
        # Monday 09:00–12:00 open, the rest X (the old "not available") and one H.
        template = open_hours((0, '09:00', '12:00'), base='X' * 672)[:-1] + 'H'
        mei = OldAvailability.objects.create(business=studio, name='Mei', availability=template)
        family = OldService.objects.create(business=studio, name='Family', price=250, duration_minutes=60, buffer_minutes=30)
        family.weekly_availability.set([mei])
        tz = ZoneInfo('Asia/Singapore')
        today = datetime.now(tz).date()
        monday = today - timedelta(days=today.weekday())
        far = monday + timedelta(weeks=6)  # outside the 4 weeks made from the template
        for day, status in ((monday + timedelta(weeks=1), 'pending_payment'), (far, 'payment_received')):
            start = datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=10)
            OldBooking.objects.create(
                business=studio, service=family, weekly_availability=mei, order_status=status,
                start_time=start, end_time=start + timedelta(hours=1), blocked_until=start + timedelta(minutes=90),
                schedule_data={'service': {'service_id': family.pk, 'name': 'Family', 'price': '250.00', 'duration_minutes': 60, 'buffer_minutes': 30}, 'details': {}},
            )

        apps = self.migrate(self.after)
        Provider = apps.get_model('product_app', 'ServiceProvider')
        Week = apps.get_model('product_app', 'WeeklyAvailability')
        Service = apps.get_model('product_app', 'Service')
        Booking = apps.get_model('checkout_app', 'ScheduleItem')
        provider = Provider.objects.get()
        self.assertEqual((provider.name, provider.business_id), ('Mei', studio.pk))
        self.assertEqual(list(Service.objects.get().service_providers.all()), [provider])
        weeks = {w.week: w.availability for w in Week.objects.filter(service_provider=provider)}
        self.assertEqual(sorted(weeks), [monday + timedelta(weeks=n) for n in range(4)] + [far])
        open_monday = open_hours((0, '09:00', '12:00'))  # old X / H became U
        self.assertEqual(weeks[monday], open_monday)
        # The bookings were written in: 10:00–11:30 H (pending) and X (paid), the rest unchanged.
        self.assertEqual(weeks[monday + timedelta(weeks=1)], open_monday[:40] + 'H' * 6 + open_monday[46:])
        self.assertEqual(weeks[far], open_monday[:40] + 'X' * 6 + open_monday[46:])
        self.assertEqual({b.service_provider_id for b in Booking.objects.all()}, {provider.pk})
