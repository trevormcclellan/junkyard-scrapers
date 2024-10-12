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
home_assistant_webhook_url = f"https://ha.tsmcclel.cfd/api/webhook/{os.getenv('HOME_ASSISTANT_WEBHOOK_ID')}"

def send_to_home_assistant(data):
    response = requests.post(home_assistant_webhook_url, json=data)
    if response.status_code == 200:
        print(f"{str(datetime.now())} - Data sent to Home Assistant successfully.")
    else:
        print(f"{str(datetime.now())} - Failed to send data to Home Assistant: {response.status_code}")
        update_health_status("unhealthy")

def fetch_all_records(yard):
    """Fetch all records from MongoDB collection."""
    return list(collection.find({"yard": yard}))

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
    directory = "/tmp/pullnsave"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(f"{directory}/health_status.txt", "w") as file:
        file.write(status)

def search_yard(yard):
    try:
        url = "https://pullnsave.com/wp-admin/admin-ajax.php"

        payload = f"makes=Mercedes-Benz&models=0&years=1976&endYears=2002&store={yard}&beginDate=&endDate=&action=getVehicles"
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }

        response = requests.post(url, headers=headers, data=payload)
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'table', 'id': 'vehicletable1'})

        cars_of_interest = []

        health = "healthy"

        # Check if the table was found
        if table:
            # Find all rows in the table body
            rows = table.find('tbody').find_all('tr')
            print(f"{str(datetime.now())} - Successully fetched {len(rows)} cars from Pull-n-Save.")
            
            for row in rows:
                # Get all the columns in the row
                cols = row.find_all('td')

                # Extract the image URL
                img_tag = cols[0].find('img')
            
                # Extract the image URL from the 'src' attribute
                if img_tag and 'src' in img_tag.attrs:
                    image = img_tag['src']
                else:
                    image = None  # Handle case where no image is found

                # Extract text from each column and strip any extra whitespace
                col_data = [col.text.strip() for col in cols]
                if col_data:
                    try:
                        year = int(col_data[1])
                        model = col_data[2].upper()
                        date = col_data[3]
                        row = col_data[4]
                        yard_name = col_data[5]
                        color = col_data[6]
                        stock_num = col_data[7]
                        vin = col_data[8]

                        car_data = {
                            "yard": yard,
                            "location": yard_name,
                            "year": year,
                            "model": model,
                            "color": color,
                            "vin": vin,
                            "stock_num": stock_num,
                            "row": row,
                            "date": date,
                            "image": image
                        }

                        if (year >= 1976 and year <= 1985) or (year >= 1996 and year <= 2002 and "E-CLASS" in model):
                            cars_of_interest.append(car_data)
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
                    except ValueError:
                        # Handle the case where conversion to int fails (e.g., year is not a number)
                        print(f"{str(datetime.now())} - Skipping row with invalid data: {col_data}")
                        update_health_status("unhealthy")
        else:
            print(f"{str(datetime.now())} - Table not found.")
            health = "unhealthy"

        # Fetch all records from MongoDB
        existing_cars = fetch_all_records(yard)

        # Delete old records not found in the latest search
        delete_old_records(existing_cars, cars_of_interest)

        # If everything is successful, set the status to healthy
        update_health_status(health)
    except Exception as e:
        print(f"{str(datetime.now())} - An error occurred in pullnsave: {print_exc(e)}")
        update_health_status("unhealthy")

search_yard(1)
search_yard(6)