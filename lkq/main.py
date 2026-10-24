import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
from traceback import format_exc
import os
import re

# Load environment variables
load_dotenv()

LOGGING_PREFIX = "(LKQ)"

# MongoDB connection details
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME')
MONGO_COLLECTION_NAME = os.getenv('MONGO_COLLECTION_NAME')

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

# Home Assistant webhook URL
home_assistant_webhook_url = f"https://ha.tsmcclel.top/api/webhook/{os.getenv('HOME_ASSISTANT_WEBHOOK_ID')}"

yard_ids = {
    "dayton": "1257",
    "cincinnati": "1253",
}

def send_to_home_assistant(data):
    response = requests.post(home_assistant_webhook_url, json=data, timeout=30)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to send data to Home Assistant: {response.status_code}")
        raise RuntimeError(f"Home Assistant returned HTTP {response.status_code}")

def fetch_all_records(yard):
    """Fetch all records from MongoDB collection."""
    return list(collection.find({"location": yard}))

def delete_old_records(existing_cars, latest_cars):
    """Delete records from MongoDB that are not found in the latest search."""
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"location": car["location"], "stock_num": car["stock_num"]})
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Deleted record: {car}")

def update_health_status(status):
    directory = "/tmp/LKQ"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

def fetch_page(page, location):
    yard = location.lower()
    yard_id = yard_ids[yard]
    url = (
        "http://cloudflare-bypass:8000/DesktopModules/pyp_vehicleInventory/"
        f"getVehicleInventory.aspx?page={page}&filter=mercedes&store={yard_id}"
    )
    headers = {
        'x-hostname': 'https://www.pyp.com',
        'referer': f'https://www.pyp.com/inventory/{yard}-{yard_id}/?search=mercedes'
    }
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


def parse_car(row, yard):
    """Parse the October 2026 inventory markup into the existing webhook schema."""
    car = {"location": yard, "interest_level": 0}
    ymm = row.select_one('.pypvi_ymm')
    if ymm is None:
        raise ValueError("Vehicle is missing its year/make/model")
    parts = ymm.get_text(' ', strip=True).split(maxsplit=2)
    if len(parts) != 3:
        raise ValueError(f"Unexpected year/make/model: {parts}")
    car.update(year=int(parts[0]), make=parts[1].upper(), model=parts[2].upper())

    # Example: <div class="pypvi_stock">Silver · 1253-39358</div>
    stock = row.select_one('.pypvi_stock')
    stock_text = stock.get_text(' ', strip=True) if stock else ''
    color, separator, stock_num = stock_text.rpartition('·')
    car['stock_num'] = stock_num.strip() if separator else row.get('id', '').strip()
    car['color'] = color.strip() if separator else ''
    if not re.fullmatch(r'\d+-\d+', car['stock_num']):
        raise ValueError(f"Missing or invalid stock number: {stock_text!r}")

    # Labels are now spans, and their values are bold within table cells.
    for cell in row.select('table.locate td'):
        label, value = cell.find('span'), cell.find('b')
        if label is not None and value is not None:
            key = label.get_text(strip=True).rstrip(':').lower()
            if key in ('section', 'row', 'space'):
                car[key] = value.get_text(' ', strip=True)

    for detail in row.select('.pypvi_detailItem'):
        match = re.match(r'^VIN\s*:?\s+([A-Z0-9]+)\b',
                         detail.get_text(' ', strip=True), re.IGNORECASE)
        if match:
            car['vin'] = match.group(1).upper()
            break
    time_tag = row.select_one('.pypvi_available time')
    if time_tag is not None:
        car['date'] = time_tag.get('datetime') or time_tag.get_text(strip=True)

    main_image = row.select_one('a.pypvi_image[href]')
    if main_image is not None:
        car['image'] = main_image['href']
    # Keep the same image_urls behavior as the original checker (extra photos).
    car['image_urls'] = [a['href'] for a in row.select('.pypvi_images a[href]')]
    for field in ('vin', 'date', 'section', 'row', 'space'):
        if not car.get(field):
            raise ValueError(f"Vehicle {car['stock_num']} is missing {field}")

    year, model = car['year'], car['model']
    if 1976 <= year <= 1985 or (1996 <= year <= 2002 and model.startswith('E')):
        car['interest_level'] = 1
    return car


def search_yard(yard):
    try:
        latest_cars = []
        seen = set()
        page_num = 1
        while True:
            soup = BeautifulSoup(fetch_page(page_num, yard), 'html.parser')
            rows = soup.select('.pypvi_resultRow')
            end = soup.select_one('.pypvi_end')
            if not rows and end is None:
                raise ValueError(f"No inventory rows or end marker on page {page_num}")
            for row in rows:
                car = parse_car(row, yard)
                if car['stock_num'] in seen:
                    raise ValueError(f"Repeated stock number on page {page_num}: {car['stock_num']}")
                seen.add(car['stock_num'])
                latest_cars.append(car)
            print(f"{datetime.now()} - {LOGGING_PREFIX} Fetched {len(rows)} cars from {yard}, page {page_num}.")
            if end is not None:
                break
            page_num += 1
            if page_num > 1000:
                raise ValueError("Inventory exceeded pagination safety limit")

        # Only change the database after every page has been parsed successfully.
        for car in latest_cars:
            key = {"location": yard, "stock_num": car['stock_num']}
            if collection.find_one(key) is None:
                send_to_home_assistant(car)
                collection.insert_one(car)
        delete_old_records(fetch_all_records(yard), latest_cars)
        return True
    except Exception:
        print(f"{datetime.now()} - {LOGGING_PREFIX} An error occurred in {yard}: {format_exc()}")
        update_health_status("unhealthy")
        return False


if __name__ == '__main__':
    # Run both yards even if one fails; don't let the second hide the first failure.
    results = [search_yard("Dayton"), search_yard("Cincinnati")]
    update_health_status("healthy" if all(results) else "unhealthy")
