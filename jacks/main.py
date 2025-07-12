import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
from traceback import print_exc
import os

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

def update_health_status(status):
    directory = "/tmp/jacks"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)


try:
    url = "https://jacksusedautoparts.com/vehicleInventory.php"
    payload = {}
    headers = {}

    response = requests.get(url, headers=headers, data=payload)
    response.raise_for_status()  # Raise an error for bad responses
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'id': 'vehicles'})

    cars_of_interest = []

    health = "healthy"

    # Check if the table was found
    if table:
        # Find all rows in the table
        rows = table.find('tbody').find_all('tr')
        print(f"{str(datetime.now())} - Successully fetched {len(rows)} cars from Jack's.")
        
        for row in rows:
            # Get all the columns in the row
            cols = row.find_all('td')
            # Extract text from each column and strip any extra whitespace
            col_data = [col.text.strip() for col in cols]
            if col_data:
                try:
                    year = int(col_data[0])
                    make = col_data[1].upper()
                    if not "MERCEDES" in make:
                        continue
                    model = col_data[2].upper()
                    color = col_data[3]
                    engine = col_data[4]
                    row = col_data[5]
                    date = col_data[6]

                    stock_num = col_data[0] + col_data[1] + col_data[2] + col_data[3] + col_data[4] + col_data[5] + col_data[6]

                    car_data = {
                        "year": year,
                        "model": model,
                        "color": color,
                        "engine": engine,
                        "stock_num": stock_num,
                        "row": row,
                        "date": date,
                        "interest_level": 0,
                    }

                    if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
                        car_data["interest_level"] = 1
                    
                    cars_of_interest.append(car_data)
                    # Check if the car is already in the database
                    existing_car = collection.find_one({"stock_num": stock_num})
                    if existing_car is None:
                        # Send the notification
                        send_to_home_assistant(car_data)
                        # Add the car to the database
                        collection.insert_one(car_data)
                except ValueError:
                    # Handle the case where conversion to int fails (e.g., year is not a number)
                    print(f"{str(datetime.now())} - Skipping row with invalid data: {col_data}")
                    update_health_status("unhealthy")
    else:
        print(f"{str(datetime.now())} - Table not found.")
        health = "unhealthy"

    # Fetch all records from MongoDB
    existing_cars = fetch_all_records()

    # Delete old records not found in the latest search
    delete_old_records(existing_cars, cars_of_interest)

    # If everything is successful, set the status to healthy
    update_health_status(health)
except Exception as e:
    print(f"{str(datetime.now())} - An error occurred in Jack's: {print_exc(e)}")
    update_health_status("unhealthy")
