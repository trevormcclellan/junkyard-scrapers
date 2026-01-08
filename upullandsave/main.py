import requests
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from datetime import datetime
from traceback import format_exc
from urllib.parse import urlparse
import sys

# Load environment variables
load_dotenv()

LOGGING_PREFIX = "(U Pull & Save)"

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

def send_to_home_assistant(data):
    response = requests.post(home_assistant_webhook_url, json=data)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to send data to Home Assistant: {response.status_code}")
        update_health_status("unhealthy")

def fetch_all_records():
    """Fetch all records from MongoDB collection."""
    return list(collection.find())

def delete_old_records(existing_cars, latest_cars):
    """Delete records from MongoDB that are not found in the latest search."""
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"stock_num": car['stock_num']})
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Deleted record: {car}")

def fetch_vehicle_details(vin):
    """Fetch vehicle details from NHTSA API using VIN."""
    try:
        nhtsa_api_url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
        response = requests.get(nhtsa_api_url)
        if response.status_code == 200:
            data = response.json()
            series = data['Results'][0]['Series']
            return series
        else:
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to fetch vehicle details for VIN {vin}.")
            update_health_status("unhealthy")
            return None
    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error fetching vehicle details for VIN {vin}: {str(e)}")
        update_health_status("unhealthy")
        return None

def update_health_status(status):
    directory = "/tmp/upullandsave"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

def is_url(string):
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def fetch_page(req_start, req_length):
    url = "https://upullandsave.com/wp-admin/admin-ajax.php"

    # Payload for the POST request
    payload = f"draw=1&columns%5B0%5D%5Bdata%5D=false&columns%5B0%5D%5Bname%5D=&columns%5B0%5D%5Bsearchable%5D=true&columns%5B0%5D%5Borderable%5D=false&columns%5B0%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B0%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B1%5D%5Bdata%5D=&columns%5B1%5D%5Bname%5D=&columns%5B1%5D%5Bsearchable%5D=true&columns%5B1%5D%5Borderable%5D=true&columns%5B1%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B1%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B2%5D%5Bdata%5D=year&columns%5B2%5D%5Bname%5D=&columns%5B2%5D%5Bsearchable%5D=true&columns%5B2%5D%5Borderable%5D=true&columns%5B2%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B2%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B3%5D%5Bdata%5D=make&columns%5B3%5D%5Bname%5D=&columns%5B3%5D%5Bsearchable%5D=true&columns%5B3%5D%5Borderable%5D=true&columns%5B3%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B3%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B4%5D%5Bdata%5D=model&columns%5B4%5D%5Bname%5D=&columns%5B4%5D%5Bsearchable%5D=true&columns%5B4%5D%5Borderable%5D=true&columns%5B4%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B4%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B5%5D%5Bdata%5D=stock_number&columns%5B5%5D%5Bname%5D=&columns%5B5%5D%5Bsearchable%5D=true&columns%5B5%5D%5Borderable%5D=true&columns%5B5%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B5%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B6%5D%5Bdata%5D=color&columns%5B6%5D%5Bname%5D=&columns%5B6%5D%5Bsearchable%5D=true&columns%5B6%5D%5Borderable%5D=true&columns%5B6%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B6%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B7%5D%5Bdata%5D=yard_row&columns%5B7%5D%5Bname%5D=&columns%5B7%5D%5Bsearchable%5D=true&columns%5B7%5D%5Borderable%5D=true&columns%5B7%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B7%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B8%5D%5Bdata%5D=date_set&columns%5B8%5D%5Bname%5D=&columns%5B8%5D%5Bsearchable%5D=true&columns%5B8%5D%5Borderable%5D=true&columns%5B8%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B8%5D%5Bsearch%5D%5Bregex%5D=false&columns%5B9%5D%5Bdata%5D=vin&columns%5B9%5D%5Bname%5D=&columns%5B9%5D%5Bsearchable%5D=true&columns%5B9%5D%5Borderable%5D=true&columns%5B9%5D%5Bsearch%5D%5Bvalue%5D=&columns%5B9%5D%5Bsearch%5D%5Bregex%5D=false&order%5B0%5D%5Bcolumn%5D=8&order%5B0%5D%5Bdir%5D=desc&order%5B0%5D%5Bname%5D=&start={req_start}&length={req_length}&search%5Bvalue%5D=&search%5Bregex%5D=false&action=yardsmart_integration&api_call=getInventoryDatatablesArray&params%5Byard_id%5D=232&params%5Byear%5D=false&params%5Bmake%5D=MERCEDES-BENZ&params%5Bmodel%5D=false&params%5Blog%5D=true"
    headers = {
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
    }

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Check for HTTP errors
        return response.json()  # Return JSON response directly

    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error: Request failed - {e}")
        update_health_status("unhealthy")
        sys.exit(1)
    

try:
    cars = []
    first_page_length = 10  # Number of records to fetch per page
    data = fetch_page(0, first_page_length)

    if 'data' in data:
        cars = data['data']
    else:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error: 'data' key not found in the response: {data}")
        update_health_status("unhealthy")
        sys.exit(1)

    records_total = data.get('recordsTotal', 0)
    if records_total > first_page_length:
        data = fetch_page(first_page_length, records_total - first_page_length)
        if 'data' in data:
            cars.extend(data['data'])
        else:
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error: 'data' key not found in the response: {data}")
            update_health_status("unhealthy")
            sys.exit(1)
        
    print(f"{str(datetime.now())} - Succesfully fetched {len(cars)} cars from U Pull & Save.")

    # List to store cars of interest
    cars_of_interest = []

    # Iterate through each car in the response
    for car in cars:
        try:
            year = int(car['year'])
            model = (car['model']).upper()
            vin = car['vin']
            stock_num = car['stock_number']
            color = car['color']
            row = car['yard_row']
            date = car['date_set']
            image_url = car['images'][0]['url'] if car['images'] else None
            image_urls = [image['url'] for image in car['images']] if car['images'] else []
            interest_level = 0  # Default interest level

            # Apply filter criteria
            if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
                interest_level = 1
                
            car_data = {
                "location": "Hebron",
                "year": year,
                "model": model,
                "vin": vin,
                "stock_num": stock_num,
                "color": color,
                "row": row,
                "date": date,
                "image": image_url,
                "image_urls": image_urls,
                "interest_level": interest_level
            }

            # Check if the car is already in the database
            existing_car = collection.find_one({"stock_num": stock_num})
            if existing_car is None:
                # Fetch additional details from NHTSA API
                if len(vin) == 17:  # Check if VIN is 17 characters
                    series = fetch_vehicle_details(vin)
                    if series:
                        car_data['series'] = series
                
                # Send the notification
                send_to_home_assistant(car_data)
                # Add the car to the database
                collection.insert_one(car_data)

            # Check if image has been added for an existing car if not already present
            elif existing_car.get("image") is None or not is_url(existing_car["image"]):
                # Fetch vehicle image if not already present
                if image_url and image_url != existing_car.get("image"):
                    print(f"{str(datetime.now())} - {LOGGING_PREFIX} Updating image for existing car: {stock_num}")
                    existing_car["image"] = image_url
                    existing_car["image_urls"] = image_urls
                    collection.update_one({"stock_num": stock_num}, {"$set": {"image": image_url, "image_urls": image_urls}})
                    # Send to Home Assistant minus the Object ID
                    existing_car.pop("_id", None)
                    send_to_home_assistant(existing_car)

            cars_of_interest.append(car_data)

        except ValueError:
            # Handle cases where conversion to int fails
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Skipping row with invalid data: {car}")
            update_health_status("unhealthy")

    # Fetch all records from MongoDB
    existing_cars = fetch_all_records()

    # Delete old records not found in the latest search
    delete_old_records(existing_cars, cars_of_interest)

    # If everything is successful, set the status to healthy
    update_health_status("healthy")

except Exception as e:
    print(f"{str(datetime.now())} - {LOGGING_PREFIX} An error occurred in U Pull & Save: {format_exc()}")
    update_health_status("unhealthy")

# Close MongoDB connection
client.close()
