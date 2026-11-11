import re

from bs4 import BeautifulSoup

from junkyard.common import checked, InventoryError, options, request, unique, vehicle

PAGE = 'https://tearapart.com/used-auto-parts/inventory/'
AJAX = 'https://tearapart.com/wp-admin/admin-ajax.php'


@checked
def fetch_nonce():
    html = request('GET', PAGE).text
    match = re.search(r'sif_ajax_nonce["\s]*:[\s"]*([\w-]+)', html)
    if not match:
        raise InventoryError('Tear-A-Part inventory nonce is missing')
    return match[1]


def ajax(action, **params):
    return request('POST', AJAX, data={
        'action': action, 'sif_verify_request': fetch_nonce(), **params})


@checked
def get_makes_from_tearapart():
    return options(ajax('sif_get_makes').text)


@checked
def get_models_from_tearapart(make):
    return [{'value': '', 'text': 'Any'}] + options(ajax('sif_update_models', make=make, state='0').text)


@checked
def parse_car(raw, make=''):
    image = BeautifulSoup(raw['image_url'] or '', 'html.parser').find('img')
    return vehicle(location=raw['yard_name'], year=raw['iyear'], make=raw.get('make') or make,
                   model=raw['model'] or raw['hol_model'], color=raw['color'], vin=raw['vin'].strip(),
                   stock_num=raw['stocknumber'], reference=raw['reference'], row=raw['vehicle_row'],
                   date=raw['yard_date'], image=image.get('src') if image else None)


@checked
def search_tearapart_inventory(make, model=None, location='SALT LAKE CITY'):
    params = {'sif_form_field_make': make, 'makes-sorting-order': '0', 'models-sorting-order': '0',
              'sorting[key]': 'iyear', 'sorting[state]': '0', 'sorting[type]': 'int'}
    if location:
        params['sif_form_field_store'] = location
    if model:
        params['sif_form_field_model'] = model
    data = ajax('sif_search_products', **params).json()
    if not isinstance(data['products'], list):
        raise InventoryError('Tear-A-Part products must be a list')
    return unique([parse_car(raw, make) for raw in data['products']])
