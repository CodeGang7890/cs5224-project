import json

from django.test import SimpleTestCase, TestCase

from configuration_app.models import BusinessConfiguration
from product_app.models import FAQ, Product

from ..prompts import format_catalog
from ..tools import DESCRIPTION_PREVIEW_LENGTH, Toolbox, description_preview, find_product_description

LONG = 'Made fresh every morning with pandan from our own garden. ' * 20 + 'Contains eggs and wheat.'


class ProductDescriptionToolTests(TestCase):
    """get_product_description: one product's full description, for the chatting business only."""

    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        cls.florist = BusinessConfiguration.objects.create(business_name='Florist', location='Singapore')
        cls.kopi = Product.objects.create(business=cls.cafe, name='Kopi C', price='1.80', quantity_available=20, description='Coffee with evaporated milk.')
        cls.kopi_o = Product.objects.create(business=cls.cafe, name='Kopi O', price='1.60', quantity_available=20, description='Black coffee.')
        cls.cake = Product.objects.create(business=cls.cafe, name='Pandan Chiffon Cake (Whole)', price='28.00', quantity_available=4, description=LONG)
        cls.plain = Product.objects.create(business=cls.cafe, name='Plain Toast', price='2.00', quantity_available=5)
        Product.objects.create(business=cls.cafe, name='Seasonal Brunch Plate', price='16.00', is_active=False, description='Secret.')
        Product.objects.create(business=cls.florist, name='Rose Bouquet', price='68.00', quantity_available=5, description='Roses.')
        FAQ.objects.create(business=cls.cafe, question='Are you halal?', answer='No pork or lard is used.')

    def find(self, product):
        return find_product_description(self.cafe, product)

    def test_finds_by_name_in_any_case(self):
        result = self.find('kopi c')
        self.assertEqual(
            result,
            {'id': self.kopi.pk, 'name': 'Kopi C', 'price': '1.80', 'quantity_available': 20, 'description': 'Coffee with evaporated milk.'},
        )
        self.assertEqual(self.find('  KOPI C ')['id'], self.kopi.pk)

    def test_returns_the_whole_long_description(self):
        self.assertEqual(self.find('Pandan Chiffon Cake (Whole)')['description'], LONG)

    def test_finds_by_unique_partial_name_or_id(self):
        self.assertEqual(self.find('chiffon')['id'], self.cake.pk)
        self.assertEqual(self.find('a slice of the pandan chiffon cake (whole) please')['id'], self.cake.pk)
        self.assertEqual(self.find(str(self.kopi_o.pk))['name'], 'Kopi O')
        self.assertEqual(self.find(self.kopi_o.pk)['name'], 'Kopi O')

    def test_ambiguous_name_lists_the_matches(self):
        result = self.find('kopi')
        self.assertEqual(result['error'], 'Several products match "kopi".')
        self.assertEqual(sorted(result['matches']), ['Kopi C', 'Kopi O'])

    def test_no_description(self):
        self.assertEqual(self.find('plain toast')['description'], 'No description has been written for this product.')

    def test_inactive_product_is_not_on_sale(self):
        self.assertEqual(self.find('seasonal brunch plate'), {'error': 'Seasonal Brunch Plate is not on sale at the moment.'})

    def test_unknown_or_other_business_product(self):
        for name in ('Teh Tarik', 'Rose Bouquet'):
            with self.subTest(name):
                result = self.find(name)
                self.assertEqual(result['error'], f'No product called "{name}" is on sale.')
                self.assertEqual(result['products_on_sale'], ['Kopi C', 'Kopi O', 'Pandan Chiffon Cake (Whole)', 'Plain Toast'])

    def test_missing_or_invalid_argument(self):
        for value in (None, '', '   ', True, ['Kopi C'], {'name': 'Kopi C'}):
            with self.subTest(value=value):
                self.assertEqual(self.find(value), {'error': 'Give the name of the product.'})


class ToolboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cafe = BusinessConfiguration.objects.create(business_name='Kopi Café', location='Singapore')
        Product.objects.create(business=cls.cafe, name='Pandan Chiffon Cake (Whole)', price='28.00', quantity_available=4, description=LONG)
        FAQ.objects.create(business=cls.cafe, question='Are you halal?', answer='No pork or lard is used.')

    def setUp(self):
        self.toolbox = Toolbox(self.cafe)

    def test_specs(self):
        specs = {spec['function']['name']: spec['function'] for spec in self.toolbox.specs}
        self.assertEqual(list(specs), ['list_products', 'get_product_description', 'list_faqs'])
        parameters = specs['get_product_description']['parameters']
        self.assertEqual(parameters['required'], ['product'])
        self.assertEqual(parameters['properties']['product']['type'], 'string')
        self.assertEqual(specs['list_faqs']['parameters']['properties'], {})

    def test_get_product_description_with_arguments(self):
        result = json.loads(self.toolbox.run('get_product_description', {'product': 'pandan chiffon cake (whole)'}))
        self.assertEqual(result['description'], LONG)
        self.assertEqual(self.toolbox.calls, [{'name': 'get_product_description', 'arguments': {'product': 'pandan chiffon cake (whole)'}}])

    def test_get_product_description_without_arguments(self):
        for arguments in (None, {}, 'Kopi'):
            with self.subTest(arguments=arguments):
                self.assertEqual(json.loads(self.toolbox.run('get_product_description', arguments)), {'error': 'Give the name of the product.'})

    def test_list_products_shows_only_the_start_of_descriptions(self):
        [product] = json.loads(self.toolbox.run('list_products'))
        self.assertEqual(product['description'], description_preview(LONG))
        self.assertLessEqual(len(product['description']), DESCRIPTION_PREVIEW_LENGTH + 1)
        self.assertTrue(product['description'].endswith('…'))
        self.assertNotIn('Contains eggs', product['description'])

    def test_list_faqs_and_unknown_tool(self):
        self.assertEqual(json.loads(self.toolbox.run('list_faqs')), [{'question': 'Are you halal?', 'answer': 'No pork or lard is used.'}])
        self.assertEqual(json.loads(self.toolbox.run('drop_tables')), {'error': "Unknown tool 'drop_tables'."})


class DescriptionPreviewTests(SimpleTestCase):
    def test_short_text_is_kept(self):
        self.assertEqual(description_preview('Black coffee.'), 'Black coffee.')
        self.assertEqual(description_preview('  Two\n\nlines  '), 'Two lines')

    def test_long_text_is_cut_at_a_word(self):
        preview = description_preview(LONG)
        self.assertTrue(preview.endswith('…'))
        self.assertLessEqual(len(preview), DESCRIPTION_PREVIEW_LENGTH + 1)
        self.assertTrue(LONG.startswith(preview[:-1]))

    def test_catalog_uses_previews(self):
        catalog = format_catalog([
            {'id': 1, 'name': 'Cake', 'description': LONG, 'price': '28.00', 'quantity_available': 4},
            {'id': 2, 'name': 'Tea', 'description': '', 'price': '2.00', 'quantity_available': 0},
        ])
        self.assertEqual(catalog, f'- id 1: Cake, $28.00 (4 available). {description_preview(LONG)}\n- id 2: Tea, $2.00 (sold out)')
