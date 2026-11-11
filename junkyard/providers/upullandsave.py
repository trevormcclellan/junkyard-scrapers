import re

from bs4 import BeautifulSoup

from junkyard.common import checked, InventoryError, optional, request, unique, vehicle, vin_series

PAGE = 'https://upullandsave.com/hebron-ky/rtp-pick-a-part/inventory/'
AJAX = 'https://upullandsave.com/wp-admin/admin-ajax.php'


@checked
def fetch_nonce():
    soup = BeautifulSoup(request('GET', PAGE).text, 'html.parser')
    for script in soup.find_all('script'):
        text = script.get_text()
        if '$rtp.o.ajax' in text:
            match = re.search(r"nonce:\s*['\"]([^'\"]+)['\"]", text)
            if match:
                return match[1]
    raise InventoryError('U Pull & Save inventory nonce is missing')


def ajax(call, **params):
    # The old frontend still used yardsmart_integration; the checker uses inventory.
    return request('POST', AJAX, headers={'referer': PAGE}, data={
        'action': 'inventory', 'api_call': call, '_ajax_nonce': fetch_nonce(), **params}).json()


@checked
def parse_makes(html):
    """Read the server-rendered make options, preserving their submitted values."""
    soup = BeautifulSoup(html, 'html.parser')
    selects = soup.select('select[name="search_form_make"]')
    if len(selects) != 1:
        raise InventoryError('U Pull & Save expected one make dropdown')
    makes, seen = [], set()
    for option in selects[0].find_all('option'):
        name = option.get_text(' ', strip=True)
        value = option.get('value', name)
        if (not value.strip() or option.has_attr('disabled')
                or option.find_parent('optgroup', disabled=True)):
            continue
        if not name:
            raise InventoryError('U Pull & Save make option has no label')
        if value not in seen:
            seen.add(value)
            makes.append({'name': name, 'value': value})
    if not makes:
        raise InventoryError('U Pull & Save make dropdown has no makes')
    return makes


@checked
def get_makes():
    return parse_makes(request('GET', PAGE).text)


@checked
def get_models(make, location):
    return ajax('getModels', **{'params[yard_id]': location, 'params[year]': 'false', 'params[make]': make})


def image_url(url):
    # Retain the upstream image-path workaround used by both original clients.
    return url[::-1].replace('/', '//', 1)[::-1]


@checked
def parse_car(raw, location):
    images = [image_url(item['full']) for item in raw['images']]
    return vehicle(location={'232': 'Hebron', '265': 'Louisville', '595': 'Lexington'}[str(location)],
                   year=raw['year'], make=raw['make'], model=raw['model'], vin=raw['vin'],
                   stock_num=raw['stock_number'], color=raw['color'], row=raw['yard_row'],
                   date=raw['date_set'], notes=raw['notes'], image=images[0] if images else None,
                   image_urls=images)


@checked
def search_inventory(make, model, location):
    nonce = fetch_nonce()
    payload = {
        'draw': 1, 'start': 0, 'length': 100, 'search[value]': '', 'search[regex]': 'false',
        'order[0][column]': 8, 'order[0][dir]': 'desc', 'order[0][name]': '',
        'action': 'inventory', 'api_call': 'getInventoryDatatablesArray',
        'params[yard_id]': location, 'params[year]': 'false', 'params[make]': make or 'false',
        'params[model]': model or 'false', 'params[log]': 'true', '_ajax_nonce': nonce,
    }
    for index, name in enumerate(['false', '', 'year', 'make', 'model', 'stock_number',
                                  'color', 'yard_row', 'date_set', 'vin']):
        for key, value in {'data': name, 'name': '', 'searchable': 'true',
                           'orderable': 'false' if index == 0 else 'true',
                           'search[value]': '', 'search[regex]': 'false'}.items():
            payload[f'columns[{index}][{key}]' if not key.startswith('search[')
                    else f'columns[{index}][search]{key[6:]}'] = value
    results, expected = [], None
    for _ in range(1000):
        data = request('POST', AJAX, headers={'referer': PAGE}, data=payload).json()
        count = int(data['recordsFiltered'] if 'recordsFiltered' in data else data['recordsTotal'])
        if count < 0 or (expected is not None and count != expected):
            raise InventoryError('U Pull & Save result count changed during pagination')
        expected = count
        if not isinstance(data['data'], list):
            raise InventoryError('U Pull & Save data must be a list')
        results.extend(parse_car(raw, location) for raw in data['data'])
        unique(results)
        if len(results) == expected:
            for car in results:
                series = optional(vin_series, car['vin'])
                if series:
                    car['series'] = series
            return results
        if not data['data'] or len(results) > expected:
            raise InventoryError('U Pull & Save returned incomplete inventory')
        payload['start'] = len(results)
    raise InventoryError('U Pull & Save pagination exceeded its safety limit')
