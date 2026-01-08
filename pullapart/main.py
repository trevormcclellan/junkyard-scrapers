import requests
from dotenv import load_dotenv
import os
from pymongo import MongoClient
from datetime import datetime
from traceback import format_exc
from urllib.parse import urlparse
import sys
import json

# Load environment variables
load_dotenv()

LOGGING_PREFIX = "(Pull-a-Part)"

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

def fetch_vehicle_details(vehicle):
    """Fetch extended vehicle details."""
    try:
        locID = vehicle["locID"]
        ticketID = vehicle["ticketID"]
        lineID = vehicle["lineID"]
        url = f"https://inventoryservice.pullapart.com/VehicleExtendedInfo/{locID}/{ticketID}/{lineID}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to fetch vehicle details for vehicle {vehicle}.")
            update_health_status("unhealthy")
            return None
    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error fetching vehicle details for vehicle {vehicle}: {str(e)}")
        update_health_status("unhealthy")
        return None
    
def fetch_vehicle_image(vehicle):
    """Fetch vehicle image """
    try:
        locID = vehicle["locID"]
        ticketID = vehicle["ticketID"]
        lineID = vehicle["lineID"]
        url = f"https://imageservice.pullapart.com/img/retrieveimage/?locID={locID}&ticketID={ticketID}&lineID={lineID}&programID=35&imageIndex=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data["webPath"]
        else:
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Failed to fetch vehicle image for vehicle {vehicle}.")
            update_health_status("unhealthy")
            return None
    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error fetching vehicle image for vehicle {vehicle}: {str(e)}")
        update_health_status("unhealthy")
        return None

def update_health_status(status):
    directory = "/tmp/pullapart"
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

try:
    # Pull-a-Part API endpoint
    url = "https://inventoryservice.pullapart.com/Vehicle/Search"

    # Payload for the POST request
    payload = json.dumps({
        "Locations": [
            18,
            8,
            35
        ],
        "MakeID": 37,
        "Models": [],
        "Years": []
    })

    headers = {
        'content-type': 'application/json'
    }

    cars = []

    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Check for HTTP errors

        try:
            data = response.json()  # Attempt to parse JSON response
            for location in data:
                if 'exact' in location:
                    cars.extend(location['exact'])
                    print(f"{str(datetime.now())} - Succesfully fetched {len(location['exact'])} cars from Pull-a-Part.")
                else:
                    print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error: 'exact' key not found in the response: {location}")
                    update_health_status("unhealthy")
                    sys.exit(1)
        except Exception as e:
            print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error parsing JSON response: {e} - {response.text}")
            update_health_status("unhealthy")
            sys.exit(1)

    except Exception as e:
        print(f"{str(datetime.now())} - {LOGGING_PREFIX} Error: Request failed - {e}")
        update_health_status("unhealthy")
        sys.exit(1)

    # List to store cars of interest
    cars_of_interest = []

    # Iterate through each car in the response
    for car in cars:
        try:
            location = car['locName']
            location_id = car['locID']
            year = int(car['modelYear'])
            model = (car['modelName']).upper()
            vin = car['vin']
            stock_num = car['vinID']
            row = car['row']
            date = car['dateYardOn']
            interest_level = 0  # Default interest level

            # Apply filter criteria
            if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
                interest_level = 1
                
            car_data = {
                "location": location,
                "location_id": location_id,
                "year": year,
                "model": model,
                "vin": vin,
                "stock_num": stock_num,
                "row": row,
                "date": date,
                "interest_level": interest_level
            }

            # Check if the car is already in the database
            existing_car = collection.find_one({"stock_num": stock_num})
            if existing_car is None:
                # Fetch vehicle image
                image_url = fetch_vehicle_image(car)
                car_data["image"] = image_url

                details = fetch_vehicle_details(car)
                if details:
                    car_data["trim"] = details["trim"] if details["trim"] else None
                    car_data["engine"] = str(details["engineSize"]) + "L " + details["engineBlock"] + str(details["engineCylinders"]) if details["engineBlock"] else None
                    car_data["transmission"] = str(details["transSpeeds"]) + " speed " + details["transType"] if details["transType"] else None
                    car_data["color"] = details["color"] if details["color"] else None
                    car_data["style"] = details["style"] if details["style"] else None
                
                # Send the notification
                send_to_home_assistant(car_data)
                # Add the car to the database
                collection.insert_one(car_data)

            # Check if image has been added for an existing car if not already present
            elif existing_car.get("image") is None or not is_url(existing_car["image"]):
                # Fetch vehicle image if not already present
                image_url = fetch_vehicle_image(car)
                if image_url and image_url != existing_car.get("image"):
                    print(f"{str(datetime.now())} - {LOGGING_PREFIX} Updating image for existing car: {stock_num}")
                    existing_car["image"] = image_url
                    collection.update_one({"stock_num": stock_num}, {"$set": {"image": image_url}})
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
    print(f"{str(datetime.now())} - {LOGGING_PREFIX} An error occurred in pullapart: {format_exc()}")
    update_health_status("unhealthy")

# Close MongoDB connection
client.close()
