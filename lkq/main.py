import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
from traceback import print_exc
import os

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
    response = requests.post(home_assistant_webhook_url, json=data)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to send data to Home Assistant: {response.status_code}")
        update_health_status("unhealthy")

def fetch_all_records(yard):
    """Fetch all records from MongoDB collection."""
    return list(collection.find({"location": yard}))

def delete_old_records(existing_cars, latest_cars):
    """Delete records from MongoDB that are not found in the latest search."""
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"stock_num": car['stock_num']})
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Deleted record: {car}")

def update_health_status(status):
    directory = "/tmp/LKQ"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

def fetch_page(page, location):
    yard = location.lower()
    yard_id = yard_ids.get(yard)
    yard = yard.lower()
    yard_id = yard_ids.get(yard)
    url = f"https://www.lkqpickyourpart.com/DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx?page=1&filter=mercedes&store={yard_id}"
    payload = {}
    headers = {
        'referer': f'https://www.lkqpickyourpart.com/inventory/{yard}-{yard_id}/?search=mercedes'
    }

    response = requests.get(url, headers=headers, data=payload)
    response.raise_for_status()  # Raise an error for bad responses
    return response.text

def search_yard(yard):
    try:
        cars_of_interest = []
        page_num = 1

        while True:
            page = fetch_page(page_num, yard)
            page_num += 1
            soup = BeautifulSoup(page, 'html.parser')
            rows = soup.find_all('div', {'class': 'pypvi_resultRow'})


            health = "healthy"

            # Check if the rows were found
            if rows:
                print(f"{str(datetime.now())} - Successully fetched {len(rows)} cars from LKQ.")
                for row in rows:
                    car_data = {
                        "location": yard,
                        "interest_level": 0,
                    }
                    # Extract the year and model from the row
                    ymm_tag = row.find('a', {'class': 'pypvi_ymm'})
                    if ymm_tag:
                        # Get all the text, join with spaces to remove HTML artifacts like <wbr>
                        ymm_text = ' '.join(ymm_tag.stripped_strings)  # E.g. '2014 MERCEDES-BENZ GL450'
                        parts = ymm_text.split(maxsplit=2)

                        if len(parts) == 3:
                            year, make, model = parts
                            car_data['year'] = int(year)
                            car_data['make'] = make.upper()
                            car_data['model'] = model.upper()
                        else:
                            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Skipping row with unexpected YMM format: {ymm_text}")
                            update_health_status("unhealthy")
                            continue
                    else:
                        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Skipping row without YMM tag: {row}")
                        update_health_status("unhealthy")
                        continue
                    # Get all the details in the row with the class 'pypvi_detailItem'
                    details = row.find_all('div', {'class': 'pypvi_detailItem'})
                    for detail in details:
                        try:
                            for b_tag in detail.find_all('b'):
                                key = b_tag.get_text(strip=True).rstrip(':')
                                
                                # Value is usually a direct sibling
                                value = ''
                                next_node = b_tag.next_sibling

                                # If value is plain text (string or NavigableString)
                                while next_node and (next_node.name is None or next_node.name == 'br'):
                                    if isinstance(next_node, str):
                                        value += next_node.strip()
                                    next_node = next_node.next_sibling

                                # Special case: "Available" uses a <time> tag
                                if key == "Available":
                                    time_tag = b_tag.find_next('time')
                                    if time_tag and time_tag.has_attr('datetime'):
                                        value = time_tag['datetime']
                                    elif time_tag:
                                        value = time_tag.get_text(strip=True)

                                # Store in dictionary
                                if key == "Color":
                                    car_data['color'] = value
                                elif key == "VIN":
                                    car_data['vin'] = value
                                elif key == "Stock #":
                                    car_data['stock_num'] = value
                                elif key == "Available":
                                    car_data['date'] = value
                                elif key == "Section":
                                    car_data['section'] = value
                                elif key == "Row":
                                    car_data['row'] = value
                                elif key == "Space":
                                    car_data['space'] = value

                        except ValueError:
                            # Handle the case where conversion to int fails (e.g., year is not a number)
                            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Skipping row with invalid data: {detail.get_text(strip=True)}")
                            update_health_status("unhealthy")

                    # Extract the main image URL from the row
                    main_image = row.find('a', {'class': 'pypvi_image'})
                    if main_image and 'href' in main_image.attrs:
                        car_data['image'] = main_image['href']
                    else:
                        print(f"{str(datetime.now())} - {LOGGING_PREFIX} No main image found for row: {row}")
                        update_health_status("unhealthy")

                    # Extract all image URLs from the row
                    image_urls = []
                    images_div = row.find('div', {'class': 'pypvi_images'})
                    if images_div:
                        image_urls = [a['href'] for a in images_div.find_all('a', href=True)]
                        if image_urls:
                            car_data['image_urls'] = image_urls
                    else:
                        print(f"{str(datetime.now())} - {LOGGING_PREFIX} No images found for row: {row}")
                        update_health_status("unhealthy")


                    year = car_data['year']
                    model = car_data['model']
                    if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model.startswith('E')):
                        car_data['interest_level'] = 1  # Set interest level for cars of interest

                    cars_of_interest.append(car_data)
                    # Check if the car is already in the database
                    existing_car = collection.find_one({"stock_num": car_data['stock_num']})
                    if existing_car is None:
                        # Send the notification
                        send_to_home_assistant(car_data)
                        # Add the car to the database
                        collection.insert_one(car_data)

                end = soup.find('div', {'class': 'pypvi_end'})
                if end:
                    break
                    
            else:
                print(f"{str(datetime.now())} - {LOGGING_PREFIX} pypvi_resultRow div not found: {page}")
                update_health_status("unhealthy")
                return

        # Fetch all records from MongoDB
        existing_cars = fetch_all_records(yard)

        # Delete old records not found in the latest search
        delete_old_records(existing_cars, cars_of_interest)

        # If everything is successful, set the status to healthy
        update_health_status(health)
    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} An error occurred in LKQ: {print_exc(e)}")
        update_health_status("unhealthy")

search_yard("Dayton")
search_yard("Cincinnati")