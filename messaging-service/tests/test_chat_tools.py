"""Ported from configuration-service's chat_app/tests/test_tools.py."""

import json
import unittest

from app.chat_flow.prompts import format_catalog
from app.chat_flow.tools import Toolbox, find_product_details

from .chat_helpers import DatabaseTestCase

SHORT = 'A light, springy pandan chiffon cake, baked fresh every morning.'
LONG = 'Made fresh every morning with pandan from our own garden. ' * 20 + 'Contains eggs and wheat.'


class ProductDetailsToolTests(DatabaseTestCase):
    """get_product_details: one product's description and information, for the chatting business only."""

    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.florist = self.make.business('Florist')
        self.kopi = self.make.product(
            self.cafe, 'Kopi C', '1.80', total_quantity=20,
            description='Coffee with evaporated milk.', information='Roasted with butter, so not dairy-free.',
        )
        self.kopi_o = self.make.product(self.cafe, 'Kopi O', '1.60', total_quantity=20, description='Black coffee.')
        self.cake = self.make.product(self.cafe, 'Pandan Chiffon Cake (Whole)', '28.00', total_quantity=4, description=SHORT, information=LONG)
        self.plain = self.make.product(self.cafe, 'Plain Toast', '2.00', total_quantity=5)
        # Django's total_quantity default is 0.
        self.make.product(self.cafe, 'Seasonal Brunch Plate', '16.00', total_quantity=0, is_active=False, description='Secret.')
        self.make.product(self.florist, 'Rose Bouquet', '68.00', total_quantity=5, description='Roses.')
        self.make.faq(self.cafe, 'Are you halal?', 'No pork or lard is used.')

    def find(self, product):
        with self.sessions() as db:
            return find_product_details(db, self.cafe, product)

    def test_finds_by_name_in_any_case(self):
        result = self.find('kopi c')
        self.assertEqual(
            result,
            {
                'id': self.kopi.pk,
                'name': 'Kopi C',
                'price': '1.80',
                'quantity_available': 20,
                'description': 'Coffee with evaporated milk.',
                'information': 'Roasted with butter, so not dairy-free.',
            },
        )
        self.assertEqual(self.find('  KOPI C ')['id'], self.kopi.pk)

    def test_returns_the_description_and_the_whole_long_information(self):
        result = self.find('Pandan Chiffon Cake (Whole)')
        self.assertEqual((result['description'], result['information']), (SHORT, LONG))

    def test_finds_by_unique_partial_name_or_id(self):
        self.assertEqual(self.find('chiffon')['id'], self.cake.pk)
        self.assertEqual(self.find('a slice of the pandan chiffon cake (whole) please')['id'], self.cake.pk)
        self.assertEqual(self.find(str(self.kopi_o.pk))['name'], 'Kopi O')
        self.assertEqual(self.find(self.kopi_o.pk)['name'], 'Kopi O')

    def test_ambiguous_name_lists_the_matches(self):
        result = self.find('kopi')
        self.assertEqual(result['error'], 'Several products match "kopi".')
        self.assertEqual(sorted(result['matches']), ['Kopi C', 'Kopi O'])

    def test_no_description_or_information(self):
        result = self.find('plain toast')
        self.assertEqual(result['description'], 'No description has been written for this product.')
        self.assertEqual(result['information'], 'No further information has been written for this product.')

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


class ToolboxTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.cafe = self.make.business('Kopi Café')
        self.make.product(
            self.cafe, 'Pandan Chiffon Cake (Whole)', '28.00', total_quantity=4,
            description=SHORT, information=LONG,
        )
        self.make.faq(self.cafe, 'Are you halal?', 'No pork or lard is used.')
        self.toolbox = Toolbox(self.cafe, self.sessions)

    def test_specs(self):
        specs = {spec['function']['name']: spec['function'] for spec in self.toolbox.specs}
        self.assertEqual(list(specs), ['list_products', 'get_product_details', 'list_services', 'get_service_details', 'list_faqs'])
        self.assertIn('information', specs['get_product_details']['description'])
        parameters = specs['get_product_details']['parameters']
        self.assertEqual(parameters['required'], ['product'])
        self.assertEqual(parameters['properties']['product']['type'], 'string')
        self.assertEqual(specs['list_faqs']['parameters']['properties'], {})

    def test_get_product_details_with_arguments(self):
        result = json.loads(self.toolbox.run('get_product_details', {'product': 'pandan chiffon cake (whole)'}))
        self.assertEqual((result['description'], result['information']), (SHORT, LONG))
        self.assertEqual(self.toolbox.calls, [{'name': 'get_product_details', 'arguments': {'product': 'pandan chiffon cake (whole)'}}])

    def test_get_product_details_without_arguments(self):
        for arguments in (None, {}, 'Kopi'):
            with self.subTest(arguments=arguments):
                self.assertEqual(json.loads(self.toolbox.run('get_product_details', arguments)), {'error': 'Give the name of the product.'})

    def test_list_products_shows_descriptions_but_not_information(self):
        [product] = json.loads(self.toolbox.run('list_products'))
        self.assertEqual(product['description'], SHORT)
        self.assertNotIn('information', product)

    def test_list_faqs_and_unknown_tool(self):
        self.assertEqual(json.loads(self.toolbox.run('list_faqs')), [{'question': 'Are you halal?', 'answer': 'No pork or lard is used.'}])
        self.assertEqual(json.loads(self.toolbox.run('drop_tables')), {'error': "Unknown tool 'drop_tables'."})


class CatalogTests(unittest.TestCase):
    def test_catalog_shows_whole_descriptions_on_one_line(self):
        catalog = format_catalog([
            {'id': 1, 'name': 'Cake', 'description': 'Light and springy.\n\nBaked daily.', 'price': '28.00', 'quantity_available': 4},
            {'id': 2, 'name': 'Tea', 'description': '', 'price': '2.00', 'quantity_available': 0},
        ])
        self.assertEqual(catalog, '- id 1: Cake, $28.00 (4 available). Light and springy. Baked daily.\n- id 2: Tea, $2.00 (sold out)')
