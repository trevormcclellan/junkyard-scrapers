from junkyard.common import checked, optional, request, unique, vehicle, InventoryError

BASE = 'https://inventoryservice.pullapart.com'


@checked
def get_makes():
    return request('GET', BASE + '/Make/').json()


@checked
def get_models(make, location):
    return request('GET', BASE + '/Model/OnYard', params={'locations': location, 'makeID': make}).json()


def image(raw):
    return request('GET', 'https://imageservice.pullapart.com/img/retrieveimage/', params={
        'locID': raw['locID'], 'ticketID': raw['ticketID'], 'lineID': raw['lineID'],
        'programID': 35, 'imageIndex': 1}).json()['webPath']


def details(raw):
    return request('GET', BASE + f"/VehicleExtendedInfo/{raw['locID']}/{raw['ticketID']}/{raw['lineID']}").json()


@checked
def parse_car(raw):
    return vehicle(location=raw['locName'], location_id=raw['locID'], year=raw['modelYear'],
                   make=raw.get('makeName', ''), model=raw['modelName'], vin=raw['vin'],
                   stock_num=raw['vinID'], row=raw['row'], date=raw['dateYardOn'])


@checked
def search_inventory(make, model, location):
    locations = location if isinstance(location, (list, tuple)) else [location]
    data = request('POST', BASE + '/Vehicle/Search', json={
        'Locations': [int(loc) for loc in locations], 'MakeID': int(make),
        'Models': [model] if model else [], 'Years': []}).json()
    if not isinstance(data, list) or not data:
        raise InventoryError('Pull-a-Part response is missing location results')
    results = []
    for group in data:
        if not isinstance(group['exact'], list):
            raise InventoryError('Pull-a-Part exact results must be a list')
        for raw in group['exact']:
            car = parse_car(raw)
            car['image'] = optional(image, raw)
            car['image_urls'] = [car['image']] if car['image'] else []
            extra = optional(details, raw) or {}
            car.update({key: extra.get(key) for key in ('trim', 'color', 'style')})
            car['engine'] = (f"{extra.get('engineSize', '')}L {extra['engineBlock']}{extra.get('engineCylinders', '')}"
                             if extra.get('engineBlock') else None)
            car['transmission'] = (f"{extra.get('transSpeeds', '')} speed {extra['transType']}"
                                   if extra.get('transType') else None)
            results.append(car)
    return unique(results)
