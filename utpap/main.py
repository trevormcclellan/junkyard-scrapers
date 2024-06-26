import requests
from bs4 import BeautifulSoup
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
    latest_stock_nums = [car['stock_num'] for car in latest_cars]

    for car in existing_cars:
        if car['stock_num'] not in latest_stock_nums:
            collection.delete_one({"stock_num": car['stock_num']})
            print(f"Deleted record with stock_num: {car['stock_num']}")

url = "https://utpap.com/wp-content/themes/enterprise/inventory_search_files/search-inventory_orem.php?make=MERCEDES-BENZ&model="

payload = {}
headers = {
    'Referer': 'https://utpap.com/wp-content/themes/enterprise/inventory_search_files/search-inventory_orem.php',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

response = requests.get(url, headers=headers, data=payload)
soup = BeautifulSoup(response.text, 'html.parser')
table = soup.find('table', {'class': 'resultsTable', 'id': 'cars-table'})

cars_of_interest = []

# Check if the table was found
if table:
    # Find all rows in the table
    rows = table.find_all('tr')
    
    for row in rows:
        # Get all the columns in the row
        cols = row.find_all('td')
        # Extract text from each column and strip any extra whitespace
        col_data = [col.text.strip() for col in cols]
        if col_data:
            try:
                year = int(col_data[0])
                model = col_data[2].upper()
                stock_num = col_data[3]
                row = col_data[4]
                date = col_data[6]
                image = f"https://utpap.com/wp-content/themes/enterprise/inventory-photos-orem/{stock_num}.jpeg"

                car_data = {
                    "year": year,
                    "model": model,
                    "stock_num": stock_num,
                    "row": row,
                    "date": date,
                    "image": image
                }

                if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and model == "E-CLASS"):
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
                print(f"Skipping row with invalid data: {col_data}")
else:
    print("Table not found.")

# Fetch all records from MongoDB
existing_cars = fetch_all_records()

# Delete old records not found in the latest search
delete_old_records(existing_cars, cars_of_interest)
