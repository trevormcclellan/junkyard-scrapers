from bs4 import BeautifulSoup

from junkyard.common import checked, InventoryError, request, unique, vehicle


@checked
def parse_inventory(html):
    table = BeautifulSoup(html, 'html.parser').select_one('table#vehicles')
    if table is None or table.find('tbody') is None:
        raise InventoryError("Jack's inventory table is missing")
    results = []
    for row in table.find('tbody').find_all('tr'):
        cols = [col.get_text(strip=True) for col in row.find_all('td')]
        if not cols:
            continue
        results.append(vehicle(location="Jack's", year=cols[0], make=cols[1], model=cols[2],
                               color=cols[3], engine=cols[4], row=cols[5], date=cols[6],
                               stock_num=''.join(cols[:7])))
    return unique(results)


@checked
def search_inventory(make=None):
    cars = parse_inventory(request('GET', 'https://jacksusedautoparts.com/vehicleInventory.php').text)
    return [car for car in cars if not make or make.upper() in car['make']]
