import requests
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
from datetime import datetime
from traceback import print_exc
import re
import sys

# Load environment variables
load_dotenv()

# MongoDB connection details
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB_NAME = os.getenv('MONGO_DB_NAME')
MONGO_COLLECTION_NAME = os.getenv('MONGO_COLLECTION_NAME')

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
collection = db[MONGO_COLLECTION_NAME]

# Home Assistant webhook URL
home_assistant_webhook_url = f"https://ha.tsmcclel.cfd/api/webhook/{os.getenv('HOME_ASSISTANT_WEBHOOK_ID')}"

def send_to_home_assistant(data):
    response = requests.post(home_assistant_webhook_url, json=data)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - Failed to send data to Home Assistant: {response.status_code}")
        update_health_status("unhealthy")

def fetch_nonce():
    url = "https://tearapart.com/used-auto-parts/inventory/"
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    }

    response = requests.get(url, headers=headers)
    html_content = response.text

    soup = BeautifulSoup(html_content, 'html.parser')
    script_tag = soup.find('script', {'id': 'sif_plugin js frontend main-js-extra'})
    script_content = script_tag.string

    nonce_match = re.search(r'sif_ajax_nonce":"(\w+)"', script_content)
    return nonce_match.group(1) if nonce_match else None

def fetch_all_records():
    """Fetch all records from MongoDB collection."""
    return list(collection.find())

def delete_old_records(existing_cars, latest_cars):
    """Delete records from MongoDB that are not found in the latest search."""
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"stock_num": car['stock_num']})
            print(f"{str(datetime.now())} - Deleted record with stock_num: {car['stock_num']}")

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
            print(f"{str(datetime.now())} - Failed to fetch vehicle details for VIN {vin}.")
            update_health_status("unhealthy")
            return None
    except Exception as e:
        print(f"{str(datetime.now())} - Error fetching vehicle details for VIN {vin}: {str(e)}")
        update_health_status("unhealthy")
        return None

def update_health_status(status):
    directory = "/tmp/tearapart"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

try:
    # Tear A Part API endpoint
    url = "https://tearapart.com/wp-admin/admin-ajax.php"

    # Payload for the POST request
    payload = {
        "sif_form_field_store": "SALT LAKE CITY",
        "sif_form_field_make": "MERCEDES-BENZ",
        "makes-sorting-order": "0",
        "models-sorting-order": "0",
        "action": "sif_search_products",
        "sif_verify_request": fetch_nonce(),
        "sorting[key]": "iyear",
        "sorting[state]": "0",
        "sorting[type]": "int"
    }

    headers = {
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    }

    cars = []

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Check for HTTP errors

        try:
            data = response.json()  # Attempt to parse JSON response
            if 'products' in data:
                cars = data['products']
                print(f"{str(datetime.now())} - Succesfully fetched {len(cars)} cars from Tear-A-Part.")
            else:
                print("Error: 'products' key not found in the response")
                update_health_status("unhealthy")
                sys.exit(1)
        except Exception as e:
            print("Error: Failed to parse JSON response")
            update_health_status("unhealthy")
            sys.exit(1)

    except Exception as e:
        print(f"{str(datetime.now())} - Error: Request failed - {e}")
        update_health_status("unhealthy")
        sys.exit(1)

    # List to store cars of interest
    cars_of_interest = []

    # Iterate through each car in the response
    for car in cars:
        try:
            year = int(car['iyear'])
            model = (car['model'] or car['hol_model']).upper()
            color = car['color']
            vin = car['vin'].strip()
            stock_num = car['stocknumber']
            reference = car['reference']
            row = car['vehicle_row']
            date = car['yard_date']
            image_url = car['image_url'].strip().split('"')[1]  # Extract image URL from HTML string

            # Apply filter criteria
            if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
                car_data = {
                    "year": year,
                    "model": model,
                    "color": color,
                    "vin": vin,
                    "stock_num": stock_num,
                    "reference": reference,
                    "row": row,
                    "date": date,
                    "image": image_url
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

                cars_of_interest.append(car_data)

        except ValueError:
            # Handle cases where conversion to int fails
            print(f"{str(datetime.now())} - Skipping row with invalid data: {car}")
            update_health_status("unhealthy")

    # Fetch all records from MongoDB
    existing_cars = fetch_all_records()

    # Delete old records not found in the latest search
    delete_old_records(existing_cars, cars_of_interest)

    # If everything is successful, set the status to healthy
    update_health_status("healthy")

except Exception as e:
    print(f"{str(datetime.now())} - An error occurred in tearapart: {print_exc(e)}")
    update_health_status("unhealthy")

# Close MongoDB connection
client.close()
