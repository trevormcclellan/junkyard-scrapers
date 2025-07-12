import requests
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from datetime import datetime
from traceback import print_exc
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
home_assistant_webhook_url = f"https://ha.tsmcclel.top/api/webhook/{os.getenv('HOME_ASSISTANT_WEBHOOK_ID')}"

def send_to_home_assistant(data):
    response = requests.post(home_assistant_webhook_url, json=data)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - Failed to send data to Home Assistant: {response.status_code}")
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
            print(f"{str(datetime.now())} - Deleted record with stock_num: {car['stock_num']}")

def fetch_vehicle_details(vin):
    """Fetch vehicle details from picknpull using VIN."""
    try:
        url = f"https://www.picknpull.com/api/vehicle/{vin}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data["vehicle"]
        else:
            print(f"{str(datetime.now())} - Failed to fetch vehicle details for VIN {vin}.")
            update_health_status("unhealthy")
            return None
    except Exception as e:
        print(f"{str(datetime.now())} - Error fetching vehicle details for VIN {vin}: {str(e)}")
        update_health_status("unhealthy")
        return None

def update_health_status(status):
    directory = "/tmp/picknpull"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

try:
    # Pick-n-Pull API endpoint
    url = "https://www.picknpull.com/api/vehicle/search?&makeId=182&modelId=0&year=&distance=10&zip=43207&language=english"

    # Payload for the POST request
    payload = {}

    headers = {
        'accept': 'application/json, text/plain, */*',
    }

    cars = []

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Check for HTTP errors

        try:
            data = response.json()  # Attempt to parse JSON response
            data = data[0]
            if 'vehicles' in data:
                cars = data['vehicles']
                print(f"{str(datetime.now())} - Succesfully fetched {len(cars)} cars from Pick-n-Pull.")
            else:
                print("Error: 'vehicles' key not found in the response")
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
            location = car['locationName']
            year = int(car['year'])
            model = (car['model']).upper()
            vin = car['vin']
            stock_num = car['barCodeNumber']
            row = car['row']
            date = car['dateAdded']
            image_url = car['imageName']
            interest_level = 0  # Default interest level

            # Apply filter criteria
            if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
                interest_level = 1
                
            car_data = {
                "location": location,
                "year": year,
                "model": model,
                "vin": vin,
                "stock_num": stock_num,
                "row": row,
                "date": date,
                "image": image_url,
                "interest_level": interest_level
            }

            # Check if the car is already in the database
            existing_car = collection.find_one({"stock_num": stock_num})
            if existing_car is None:
                details = fetch_vehicle_details(vin)
                car_data["trim"] = details.get("trim", "Unknown") if details else "Unknown"
                car_data["engine"] = details.get("engine", "Unknown") if details else "Unknown"
                car_data["transmission"] = details.get("transmission", "Unknown") if details else "Unknown"
                car_data["color"] = details.get("color", "Unknown") if details else "Unknown"
                
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
    print(f"{str(datetime.now())} - An error occurred in picknpull: {print_exc(e)}")
    update_health_status("unhealthy")

# Close MongoDB connection
client.close()
