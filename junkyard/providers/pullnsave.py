from urllib.parse import quote

from bs4 import BeautifulSoup

from junkyard.common import checked, InventoryError, options, request, unique, vehicle

AJAX = 'https://pullnsave.com/wp-admin/admin-ajax.php'


@checked
def get_makes_from_pullnsave():
    return options(request('POST', AJAX, data={'action': 'getMakes'}).text)


@checked
def get_models_from_pullnsave(make):
    return options(request('POST', AJAX, data={
        'Form': 'searchVehicleForm', 'Year': 0, 'endYear': 0, 'Make': make, 'action': 'getModels'}).text)


@checked
def parse_inventory(html, make, location):
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one('table#vehicletable1')
    if table is None:
        h2 = soup.find('h2')
        if h2 and "I'm sorry but there are no matching vehicles at" in h2.get_text():
            return []
        raise InventoryError('Pull-n-Save inventory table is missing')
    body = table.find('tbody')
    if body is None:
        raise InventoryError('Pull-n-Save inventory table body is missing')
    results = []
    for row in body.find_all('tr'):
        cols = row.find_all('td')
        if not cols:
            continue
        text = [col.get_text(strip=True) for col in cols]
        image = cols[0].find('img')
        results.append(vehicle(yard=int(location), location=text[5], year=text[1], make=make,
                               model=text[2], date=text[3], row=text[4], color=text[6],
                               stock_num=text[7], vin=text[8], image=image.get('src') if image else None))
    return unique(results)


@checked
def search_pullnsave_inventory(make, model, location, year=0, end_year=0):
    response = request('POST', AJAX, data={
        'makes': make, 'models': model or 0, 'years': year, 'endYears': end_year,
        'store': location, 'beginDate': '', 'endDate': '', 'action': 'getVehicles'})
    return parse_inventory(response.text, make, location)


@checked
def images(stock_num, yard):
    key = quote(f'{stock_num}-{yard}', safe='')
    data = request('GET', f'https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/{key}/').json()
    if not isinstance(data, list):
        raise InventoryError('Pull-n-Save image list is invalid')
    return [f'https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/{key}/OrderId/{index}'
            for index in range(1, len(data) + 1)]
