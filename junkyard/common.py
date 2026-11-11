"""Transport and schema helpers. No database or notification side effects."""
import logging
from functools import wraps

import requests
from bs4 import BeautifulSoup


class InventoryError(RuntimeError):
    """An upstream failure, never an empty inventory result."""


def request(method, url, **kwargs):
    kwargs.setdefault('timeout', (10, 60))
    kwargs.setdefault('headers', {'User-Agent': 'Mozilla/5.0'})
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise InventoryError('Inventory request failed') from exc


def checked(fn):
    """Convert invalid upstream shapes to a distinct, caller-visible failure."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, SyntaxError) as exc:
            raise InventoryError(f'{fn.__module__}.{fn.__name__}: unexpected inventory format') from exc
    return wrapped


def vehicle(**fields):
    fields['year'] = int(fields['year'])
    fields['model'] = fields['model'].strip().upper()
    fields['make'] = (fields.get('make') or '').strip().upper()
    if fields.get('stock_num') in (None, '') or not fields['model']:
        raise InventoryError('Vehicle is missing its stock number or model')
    fields.setdefault('location', '')
    fields.setdefault('image', None)
    fields.setdefault('image_urls', [fields['image']] if fields['image'] else [])
    return fields


def unique(cars):
    seen = set()
    for car in cars:
        key = (car['location'], car['stock_num'])
        if key in seen:
            raise InventoryError('Inventory contains repeated vehicles')
        seen.add(key)
    return cars


def options(html):
    soup = BeautifulSoup(html, 'html.parser')
    nodes = soup.find_all('option')
    if not nodes:
        raise InventoryError('Inventory options are missing')
    return [{'value': n.get('value', ''), 'text': n.get_text(strip=True)} for n in nodes]


def optional(fn, *args):
    """Missing enrichment must not hide an otherwise valid inventory."""
    try:
        return fn(*args)
    except (InventoryError, KeyError, ValueError, TypeError, IndexError):
        logging.getLogger(__name__).warning('Vehicle enrichment unavailable: %s', fn.__name__)
        return None


def vin_series(vin):
    if len(vin or '') != 17:
        return None
    data = request('GET', f'https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}',
                   params={'format': 'json'}).json()
    return data['Results'][0]['Series']
