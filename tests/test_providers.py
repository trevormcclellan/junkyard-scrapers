import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup

from junkyard.common import InventoryError, request
from junkyard.providers import jacks, lkq, picknpull, pullapart, pullnsave, tearapart, upullandsave, utpap

FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(name):
    text = (FIXTURES / name).read_text()
    return json.loads(text) if name.endswith('.json') else text


def response(data):
    result = Mock()
    result.text = data if isinstance(data, str) else ''
    result.json.return_value = data
    return result


class ProviderTests(unittest.TestCase):
    def setUp(self):
        block = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network access'))
        block.start()
        self.addCleanup(block.stop)

    def test_transport_timeout_and_http_errors(self):
        with patch('junkyard.common.requests.request', return_value=response('ok')) as http:
            request('GET', 'https://example.test/')
            self.assertEqual(http.call_args.kwargs['timeout'], (10, 60))
        with patch('junkyard.common.requests.request', side_effect=requests.Timeout):
            with self.assertRaises(InventoryError):
                request('GET', 'https://example.test/')
        with patch('junkyard.common.requests.request') as http:
            http.return_value.raise_for_status.side_effect = requests.HTTPError
            with self.assertRaises(InventoryError):
                request('GET', 'https://example.test/')

    def test_lkq_current_markup_and_all_images(self):
        row = BeautifulSoup(fixture('lkq.html'), 'html.parser').select_one('.pypvi_resultRow')
        car = lkq.parse_car(row, 'Cincinnati')
        self.assertEqual((car['stock_num'], car['color'], car['row'], car['space']), ('1253-39358', 'Silver', '12', '3'))
        self.assertEqual(car['year'], 2001)
        self.assertEqual(len(car['image_urls']), 2)
        self.assertNotIn('interest_level', car)

    def test_lkq_uses_user_query_and_paginates(self):
        first = fixture('lkq.html').replace('<div class="pypvi_end"></div>', '')
        with patch.object(lkq, 'request', side_effect=[response(first), response('<div class="pypvi_end"></div>')]) as http:
            cars = lkq.search_inventory('ford & truck', 'Cincinnati')
        self.assertEqual(len(cars), 1)
        self.assertEqual(http.call_args_list[0].kwargs['params']['filter'], 'ford & truck')
        self.assertEqual(http.call_args.kwargs['params']['page'], 2)

    def test_lkq_does_not_return_partial_results(self):
        first = fixture('lkq.html').replace('<div class="pypvi_end"></div>', '')
        for last in ('<h1>Challenge</h1>', first):
            with self.subTest(last=last[:20]), patch.object(lkq, 'request', side_effect=[response(first), response(last)]):
                with self.assertRaises(InventoryError):
                    lkq.search_inventory('mercedes', 'Cincinnati')

    def test_lkq_missing_fields_fail(self):
        row = BeautifulSoup(fixture('lkq.html'), 'html.parser').select_one('.pypvi_resultRow')
        row.select_one('.pypvi_stock').decompose()
        row.attrs.pop('id')
        with self.assertRaises(InventoryError):
            lkq.parse_car(row, 'Cincinnati')

    def test_picknpull_multiple_locations_and_model_id(self):
        data = fixture('picknpull.json')
        other = copy.deepcopy(data[0])
        other['vehicles'][0]['locationName'] = 'Other'
        with patch.object(picknpull, 'request', return_value=response(data + [other])) as http, patch.object(picknpull, 'details', return_value={'trim':'Sport'}):
            cars = picknpull.search_inventory('182', '456')
        self.assertEqual(len(cars), 2)
        self.assertEqual(http.call_args.kwargs['params']['modelId'], '456')
        self.assertEqual(cars[0]['trim'], 'Sport')
        self.assertEqual(cars[0]['image'], 'https://example.test/car.jpg')

    def test_picknpull_missing_vehicle_list_fails(self):
        with patch.object(picknpull, 'request', return_value=response([{}])):
            with self.assertRaises(InventoryError):
                picknpull.search_inventory(182)

    def test_pullapart_schema_and_enrichment(self):
        with patch.object(pullapart, 'request', return_value=response(fixture('pullapart.json'))) as http, patch.object(pullapart, 'image', return_value='https://example.test/car.jpg'), patch.object(pullapart, 'details', return_value={'engineSize':3.2,'engineBlock':'V','engineCylinders':6,'transSpeeds':5,'transType':'Auto'}):
            car = pullapart.search_inventory('37', None, '18')[0]
        self.assertEqual(car['stock_num'], 123)  # Preserve existing Mongo identity type.
        self.assertEqual(car['engine'], '3.2L V6')
        self.assertEqual(http.call_args.kwargs['json']['Locations'], [18])

    def test_upullandsave_filtered_count_and_updated_action(self):
        with patch.object(upullandsave, 'fetch_nonce', return_value='nonce'), patch.object(upullandsave, 'request', return_value=response(fixture('upullandsave.json'))) as http:
            car = upullandsave.search_inventory('Mercedes-Benz', '', '232')[0]
        self.assertEqual(http.call_count, 1)  # recordsTotal includes cars outside the filter.
        payload = http.call_args.kwargs['data']
        self.assertEqual(payload['action'], 'inventory')
        self.assertEqual(payload['columns[0][search][value]'], '')
        self.assertEqual(car['image'], 'https://example.test/path//car.jpg')
        self.assertEqual(car['location'], 'Hebron')

    def test_upullandsave_makes_use_page_not_ajax(self):
        with patch.object(upullandsave, 'request', return_value=response(fixture('upullandsave-makes.html'))) as http:
            makes = upullandsave.get_makes()
        http.assert_called_once_with('GET', upullandsave.PAGE)
        self.assertEqual(makes, [
            {'name': 'Ford', 'value': 'Ford'},
            {'name': 'Land Rover', 'value': 'Land Rover'},
            {'name': 'Mercedes-Benz', 'value': 'Mercedes-Benz'},
        ])

    def test_upullandsave_makes_missing_empty_or_ambiguous_fail(self):
        for html in (
            '<h1>Checking your browser</h1>',
            '<select name="year"><option>2001</option></select>',
            '<select name="search_form_make"><option value="">Please Select A Make</option></select>',
            '<select name="search_form_make"><option>Ford</option></select>' * 2,
            '<select name="search_form_make"><option value="Ford"></option></select>',
        ):
            with self.subTest(html=html), self.assertRaises(InventoryError):
                upullandsave.parse_makes(html)

    def test_upullandsave_makes_preserve_values_and_ignore_other_controls(self):
        html = '''<select name="make"><option>Wrong dropdown</option></select>
            <select name="search_form_year"><option>2001</option></select>
            <select name="search_form_make">
                <option value="">Please Select A Make</option>
                <option value="FORD"> Ford </option><option value="FORD">Ford</option>
                <option value="A&amp;B"> A &amp; B </option>
                <option value="disabled" disabled>Unavailable</option>
                <optgroup disabled><option value="unavailable">Unavailable group</option></optgroup>
            </select>'''
        self.assertEqual(upullandsave.parse_makes(html), [
            {'name': 'Ford', 'value': 'FORD'}, {'name': 'A & B', 'value': 'A&B'},
        ])

    def test_upullandsave_models_keep_ajax_contract(self):
        models = [{'name': 'E-CLASS'}]
        with patch.object(upullandsave, 'fetch_nonce', return_value='test-nonce'), patch.object(upullandsave, 'request', return_value=response(models)) as http:
            self.assertEqual(upullandsave.get_models('Mercedes-Benz', '232'), models)
        http.assert_called_once_with('POST', upullandsave.AJAX, headers={'referer': upullandsave.PAGE}, data={
            'action': 'inventory', 'api_call': 'getModels', '_ajax_nonce': 'test-nonce',
            'params[yard_id]': '232', 'params[year]': 'false', 'params[make]': 'Mercedes-Benz',
        })

    def test_upullandsave_nonce_works_with_both_quote_styles(self):
        for quote in ('"', "'"):
            with patch.object(upullandsave, 'request', return_value=response(f'<script>$rtp.o.ajax = {{nonce: {quote}abc-123{quote}}};</script>')):
                self.assertEqual(upullandsave.fetch_nonce(), 'abc-123')

    def test_upullandsave_incomplete_page_fails(self):
        first = fixture('upullandsave.json')
        first['recordsFiltered'] = 2
        last = {'recordsFiltered':2, 'data':[]}
        with patch.object(upullandsave, 'fetch_nonce', return_value='nonce'), patch.object(upullandsave, 'request', side_effect=[response(first), response(last)]):
            with self.assertRaises(InventoryError):
                upullandsave.search_inventory('Mercedes-Benz', None, 232)

    def test_tearapart_parsing_and_worker_search_all_locations(self):
        with patch.object(tearapart, 'ajax', return_value=response(fixture('tearapart.json'))) as http:
            car = tearapart.search_tearapart_inventory('MERCEDES-BENZ', location=None)[0]
        self.assertEqual(car['model'], 'E-CLASS')
        self.assertEqual(car['image'], 'https://example.test/car.jpg')
        self.assertNotIn('sif_form_field_store', http.call_args.kwargs)

    def test_html_providers(self):
        cars = jacks.parse_inventory(fixture('jacks.html'))
        self.assertEqual(len(cars), 2)
        self.assertEqual(cars[0]['stock_num'], '1982Mercedes-Benz300DBlue3.0 diesel102026-10-20')
        car = utpap.parse_inventory(fixture('utpap.html'), 'Ogden')[0]
        self.assertEqual(car['location'], 'Ogden')
        self.assertIn('/Ogden-inventory-photos/', car['image'])
        car = pullnsave.parse_inventory(fixture('pullnsave.html'), 'Mercedes-Benz', '1')[0]
        self.assertEqual(car['yard'], 1)
        self.assertEqual(car['location'], 'Salt Lake City')

    def test_missing_tables_are_errors_not_empty_results(self):
        for fn, args in ((jacks.parse_inventory, ()), (utpap.parse_inventory, ('Orem',)), (pullnsave.parse_inventory, ('Mercedes-Benz', 1))):
            with self.subTest(provider=fn.__module__), self.assertRaises(InventoryError):
                fn('<h1>Service unavailable</h1>', *args)

    def test_valid_empty_responses(self):
        self.assertEqual(jacks.parse_inventory('<table id="vehicles"><tbody></tbody></table>'), [])
        self.assertEqual(utpap.parse_inventory('<table id="cars-table"></table>', 'Orem'), [])
        self.assertEqual(pullnsave.parse_inventory("<h2>I'm sorry but there are no matching vehicles at this yard</h2>", 'Mercedes-Benz', 1), [])
        with patch.object(lkq, 'request', return_value=response('<div class="pypvi_end"></div>')):
            self.assertEqual(lkq.search_inventory('ford', 'Dayton'), [])
        with patch.object(tearapart, 'ajax', return_value=response({'products':[]})):
            self.assertEqual(tearapart.search_tearapart_inventory('Ford'), [])

    def test_utpap_model_map_is_data_not_code(self):
        with patch.object(utpap, 'request', return_value=response(fixture('utpap.html'))):
            self.assertEqual(utpap.get_modelmap_from_utpap()['FORD'], ['FOCUS'])
        with patch.object(utpap, 'request', return_value=response("<script>var modelMap = {'FORD': __import__('os').getcwd()};</script>")):
            with self.assertRaises(InventoryError):
                utpap.get_modelmap_from_utpap()
