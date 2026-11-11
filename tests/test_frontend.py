import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from frontend.app import create_app
from frontend.main import routes as main
from frontend.utah import routes as utah
from junkyard.common import InventoryError
from junkyard import worker
from junkyard.providers import lkq


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        block = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network access'))
        block.start()
        self.addCleanup(block.stop)

    def test_health_without_credentials(self):
        self.assertEqual(self.client.get('/healthz').json, {'status': 'ok'})

    def test_worker_and_frontend_share_same_integration(self):
        self.assertIs(main.lkq, worker.lkq)
        with patch.object(lkq, 'search_inventory', return_value=[{'stock_num': '123'}]) as search:
            result = self.client.get('/api/search', query_string={'yard_name': 'lkq', 'query': 'Ford & truck', 'location': 'Cincinnati'})
            worker.searches('lkq')[0][1]()
        self.assertEqual(result.json, {'results': [{'stock_num': '123'}]})
        self.assertEqual(search.call_args_list[0].args, ('Ford & truck', 'Cincinnati'))
        self.assertEqual(search.call_args_list[1].args, ('mercedes', 'Dayton'))

    def test_error_is_502_not_empty_results(self):
        with patch.object(lkq, 'search_inventory', side_effect=InventoryError('changed markup')):
            result = self.client.get('/api/search?yard_name=lkq&query=mercedes&location=Dayton')
        self.assertEqual(result.status_code, 502)
        self.assertIn('error', result.json)
        self.assertNotIn('results', result.json)

    def test_invalid_searches_are_400(self):
        for url in ('/api/search', '/api/search?yard_name=unknown', '/api/search?yard_name=lkq&query=x&location=unknown', '/utah/api/search?yard_name=pullnsave&make=Ford'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_unknown_yard_page_is_404(self):
        self.assertEqual(self.client.get('/junkyard/unknown').status_code, 404)
        self.assertEqual(self.client.get('/utah/junkyard/unknown').status_code, 404)

    def test_all_search_routes_use_shared_provider(self):
        cases = [
            (main.picknpull, 'search_inventory', '/api/search?yard_name=picknpull&make=182&model=22'),
            (main.pullapart, 'search_inventory', '/api/search?yard_name=pullapart&make=37&location=18'),
            (main.upullandsave, 'search_inventory', '/api/search?yard_name=upullandsave&make=Ford&location=232'),
            (utah.tearapart, 'search_tearapart_inventory', '/utah/api/search?yard_name=tearapart&make=Ford'),
            (utah.pullnsave, 'search_pullnsave_inventory', '/utah/api/search?yard_name=pullnsave&make=Ford&location=1'),
            (utah.utpap, 'search_utpap_inventory', '/utah/api/search?yard_name=utpap&make=Ford'),
        ]
        for module, method, url in cases:
            with self.subTest(url=url), patch.object(module, method, return_value=[]) as search:
                self.assertEqual(self.client.get(url).json, {'results': []})
                search.assert_called_once()

    def test_home_and_search_templates_render(self):
        with patch.object(main, 'saved_cars', return_value=[]), patch.object(utah, 'saved_cars', return_value=[]):
            for url in ('/', '/utah/'):
                self.assertEqual(self.client.get(url).status_code, 200)
        for yard in ('lkq', 'jacks'):
            self.assertEqual(self.client.get('/junkyard/' + yard).status_code, 200)
        for yard in ('picknpull', 'pullapart', 'upullandsave'):
            with patch.object(main.PROVIDERS[yard], 'get_makes', return_value=[]):
                self.assertEqual(self.client.get('/junkyard/' + yard).status_code, 200)
        for yard, module, method, data in (
            ('utpap', utah.utpap, 'get_modelmap_from_utpap', {}),
            ('tearapart', utah.tearapart, 'get_makes_from_tearapart', []),
            ('pullnsave', utah.pullnsave, 'get_makes_from_pullnsave', []),
        ):
            with patch.object(module, method, return_value=data):
                self.assertEqual(self.client.get('/utah/junkyard/' + yard).status_code, 200)

    def test_image_route_uses_shared_integration(self):
        images = ['https://example.test/photo.jpg']
        with patch.object(utah.pullnsave, 'images', return_value=images):
            self.assertEqual(self.client.get('/utah/api/images/pullnsave/ABC/1').json, {'count': 1, 'images': images})

    def test_upullandsave_page_preserves_scraped_make_values(self):
        html = (Path(__file__).parent / 'fixtures/upullandsave-makes.html').read_text()
        with patch.object(main.upullandsave, 'request') as http:
            http.return_value.text = html
            result = self.client.get('/junkyard/upullandsave')
        self.assertEqual(result.status_code, 200)
        options = BeautifulSoup(result.data, 'html.parser').select('#make option')
        self.assertEqual([(o['value'], o.get_text()) for o in options], [
            ('', 'Select Make'), ('Ford', 'Ford'), ('Land Rover', 'Land Rover'),
            ('Mercedes-Benz', 'Mercedes-Benz'),
        ])
        http.assert_called_once_with('GET', main.upullandsave.PAGE)
        with patch.object(main.upullandsave, 'get_models', return_value=[]) as models:
            result = self.client.get('/api/models', query_string={
                'yard_name': 'upullandsave', 'make': options[3]['value'], 'location': '232'})
        self.assertEqual(result.status_code, 200)
        models.assert_called_once_with('Mercedes-Benz', '232')
