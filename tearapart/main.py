import requests
from dotenv import load_dotenv
import os
from pymongo import MongoClient

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
        print("Data sent to Home Assistant successfully.")
    else:
        print(f"Failed to send data to Home Assistant: {response.status_code}")

def fetch_all_records():
    """Fetch all records from MongoDB collection."""
    return list(collection.find())

def delete_old_records(existing_cars, latest_cars):
    """Delete records from MongoDB that are not found in the latest search."""
    existing_stock_nums = [car['stock_num'] for car in existing_cars]
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"stock_num": car['stock_num']})
            print(f"Deleted record with stock_num: {car['stock_num']}")

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
            print(f"Failed to fetch vehicle details for VIN {vin}.")
            return None
    except Exception as e:
        print(f"Error fetching vehicle details for VIN {vin}: {str(e)}")
        return None

# Tear A Part API endpoint
url = "https://tearapart.com/wp-admin/admin-ajax.php"

# Payload for the POST request
payload = {
    "sif_form_field_store": "SALT LAKE CITY",
    "sif_form_field_make": "MERCEDES-BENZ",
    "makes-sorting-order": "0",
    "models-sorting-order": "0",
    "action": "sif_search_products",
    "sif_verify_request": "c41145a606",
    "sorting[key]": "iyear",
    "sorting[state]": "0",
    "sorting[type]": "int"
}

headers = {
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

response = requests.post(url, headers=headers, data=payload)
cars = response.json()['products']

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
        print(f"Skipping row with invalid data: {car}")

# Fetch all records from MongoDB
existing_cars = fetch_all_records()

# Delete old records not found in the latest search
delete_old_records(existing_cars, cars_of_interest)

# Close MongoDB connection
client.close()
