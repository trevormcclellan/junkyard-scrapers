import os
import re

from bs4 import BeautifulSoup

from junkyard.common import InventoryError, checked, request, unique, vehicle

YARD_IDS = {'dayton': '1257', 'cincinnati': '1253'}


@checked
def parse_car(row, location):
    parts = row.select_one('.pypvi_ymm').get_text(' ', strip=True).split(maxsplit=2)
    stock = row.select_one('.pypvi_stock')
    stock_text = stock.get_text(' ', strip=True) if stock else ''
    color, separator, stock_num = stock_text.rpartition('·')
    stock_num = stock_num.strip() if separator else row.get('id', '').strip()
    if not re.fullmatch(r'\d+-\d+', stock_num):
        raise InventoryError('LKQ stock number is missing or invalid')
    fields = dict(location=location, year=parts[0], make=parts[1], model=parts[2],
                  stock_num=stock_num, color=color.strip() if separator else '')
    for cell in row.select('table.locate td'):
        label, value = cell.find('span'), cell.find('b')
        if label is not None and value is not None:
            key = label.get_text(strip=True).rstrip(':').lower()
            if key in ('section', 'row', 'space'):
                fields[key] = value.get_text(' ', strip=True)
    for detail in row.select('.pypvi_detailItem'):
        match = re.match(r'^VIN\s*:?\s+([A-Z0-9]+)\b', detail.get_text(' ', strip=True), re.I)
        if match:
            fields['vin'] = match[1].upper()
            break
    time = row.select_one('.pypvi_available time')
    if time is not None:
        fields['date'] = time.get('datetime') or time.get_text(strip=True)
    for key in ('vin', 'date', 'section', 'row', 'space'):
        if not fields.get(key):
            raise InventoryError(f'LKQ vehicle is missing {key}')
    image = row.select_one('a.pypvi_image[href]')
    fields['image'] = image['href'] if image else None
    fields['image_urls'] = list(dict.fromkeys(
        ([fields['image']] if image else []) + [a['href'] for a in row.select('.pypvi_images a[href]')]))
    return vehicle(**fields)


@checked
def search_inventory(query, location):
    yard = location.lower()
    if yard not in YARD_IDS:
        raise ValueError('Unsupported LKQ location')
    base = os.getenv('LKQ_PROXY_URL', 'http://cloudflare-bypass:8000').rstrip('/')
    results = []
    for page in range(1, 1001):
        response = request('GET', base + '/DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx',
                           params={'page': page, 'filter': query or '', 'store': YARD_IDS[yard]},
                           headers={'x-hostname': 'https://www.pyp.com',
                                    'referer': f'https://www.pyp.com/inventory/{yard}-{YARD_IDS[yard]}/'})
        soup = BeautifulSoup(response.text, 'html.parser')
        rows, end = soup.select('.pypvi_resultRow'), soup.select_one('.pypvi_end')
        if not rows and end is None:
            raise InventoryError('LKQ returned neither inventory nor an end marker')
        results.extend(parse_car(row, location) for row in rows)
        unique(results)
        if end is not None:
            return results
    raise InventoryError('LKQ pagination exceeded its safety limit')
