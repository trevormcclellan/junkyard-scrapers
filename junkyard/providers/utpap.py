import ast
import json
import re

from bs4 import BeautifulSoup

from junkyard.common import checked, InventoryError, request, unique, vehicle


def url(location):
    if location.lower() not in ('orem', 'ogden'):
        raise ValueError('Unsupported UTPAP location')
    return f'https://utpap.com/search-inventory_{location.lower()}.php'


@checked
def get_modelmap_from_utpap():
    html = request('GET', url('Orem')).text
    match = re.search(r'\b(?:var|let|const)\s+modelMap\s*=\s*(\{.*?\})\s*;', html, re.S)
    if not match:
        raise InventoryError('UTPAP model map is missing')
    try:
        data = json.loads(match[1])
    except ValueError:
        # Older responses used Python-compatible single-quoted literals. Never eval upstream code.
        data = ast.literal_eval(match[1])
    if not isinstance(data, dict) or any(not isinstance(v, list) for v in data.values()):
        raise InventoryError('UTPAP model map is invalid')
    return data


@checked
def parse_inventory(html, location):
    table = BeautifulSoup(html, 'html.parser').select_one('table#cars-table')
    if table is None:
        raise InventoryError('UTPAP inventory table is missing')
    results = []
    for row in table.find_all('tr'):
        cols = [col.get_text(strip=True) for col in row.find_all('td')]
        if not cols:
            continue
        results.append(vehicle(location=location, year=cols[0], make=cols[1], model=cols[2],
                               stock_num=cols[3], engine=cols[4], row=cols[5], date=cols[6],
                               image=f'https://utpap.com/{location}-inventory-photos/{cols[3]}.jpeg'))
    return unique(results)


@checked
def search_utpap_inventory(make, model=None, location='Orem'):
    return parse_inventory(request('GET', url(location), params={'make': make, 'model': model or ''}).text,
                           location)
