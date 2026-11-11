from urllib.parse import quote

from junkyard.common import checked, optional, request, unique, vehicle, InventoryError

BASE = 'https://www.picknpull.com/api/vehicle'


@checked
def get_makes():
    return request('GET', BASE + '/makes').json()


@checked
def get_models(make):
    return request('GET', BASE + f'/makes/{quote(str(make), safe="")}/models').json()


def details(vin):
    return request('GET', BASE + '/' + quote(vin, safe='')).json()['vehicle']


@checked
def parse_car(car):
    return vehicle(location=car['locationName'], year=car['year'], make=car['make'],
                   model=car['model'], vin=car['vin'], stock_num=car['barCodeNumber'],
                   row=car['row'], date=car['dateAdded'], image=car['imageName'])


@checked
def search_inventory(make, model=None):
    data = request('POST', BASE + '/search', params={
        'makeId': make, 'modelId': model or 0, 'year': '', 'distance': 10,
        'zip': '43207', 'language': 'english'}, data={}).json()
    if not isinstance(data, list) or not data:
        raise InventoryError('Pick-n-Pull response is missing location results')
    results = []
    for location in data:
        if not isinstance(location['vehicles'], list):
            raise InventoryError('Pick-n-Pull vehicles must be a list')
        for raw in location['vehicles']:
            car = parse_car(raw)
            extra = optional(details, car['vin']) or {}
            for key in ('trim', 'engine', 'transmission', 'color'):
                car[key] = extra.get(key, 'Unknown')
            results.append(car)
    return unique(results)
