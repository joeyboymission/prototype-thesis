import os
import json
import random
import time  # Added missing time import
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

# MongoDB Setup - Same as odor-mod-main.py
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

def check_db_connection():
    """Test MongoDB connection and return status"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        return True, client
    except Exception as e:
        print(f"Database Error: {e}")
        return False, None

def generate_random_data():
    """Generate random sensor data matching remote format exactly"""
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return {
        "timestamp": timestamp,
        "aqi": {
            "GAS1": random.randint(0, 500),
            "GAS2": random.randint(0, 500),
            "GAS3": random.randint(0, 500),
            "GAS4": random.randint(0, 500)
        },
        "dht": {
            "TEMP1": {
                "temp": round(random.uniform(20, 40), 1),
                "hum": round(random.uniform(40, 90), 1)
            },
            "TEMP2": {
                "temp": round(random.uniform(20, 40), 1),
                "hum": round(random.uniform(40, 90), 1)
            },
            "TEMP3": {
                "temp": round(random.uniform(20, 40), 1),
                "hum": round(random.uniform(40, 90), 1)
            },
            "TEMP4": {
                "temp": round(random.uniform(20, 40), 1),
                "hum": round(random.uniform(40, 90), 1)
            }
        }
    }

def display_menu(db_status):
    """Display the main menu with database status"""
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*50)
    print("Odor Module Database Test Tool")
    print("="*50)
    print(f"Database Status: {'Online' if db_status else 'Offline'}")
    print("-"*50)
    print("1. Send Single Random Data")
    print("2. Start Continuous Data (5s)")
    print("3. Exit Program")
    print("="*50)

def continuous_send(client, collection):
    """Continuously send random data every 5 seconds"""
    try:
        print("\nStarting continuous data send (Press CTRL+C to stop)")
        while True:
            data = generate_random_data()
            result = collection.insert_one(data)
            
            # Clear screen before printing new data
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("\nData sent successfully!")
            print(f"Timestamp: {data['timestamp']}")
            
            # Fixed string formatting for AQI values
            aqi_values = [f"GAS{i+1}: {data['aqi'][f'GAS{i+1}']}" 
                         for i in range(4)]
            print("AQI Values:", ", ".join(aqi_values))
            
            # Fixed string formatting for temperature values
            temp_values = [f"TEMP{i+1}: {data['dht'][f'TEMP{i+1}']['temp']}°C" 
                          for i in range(4)]
            print("Temperature Values:", ", ".join(temp_values))
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nContinuous send stopped")
        input("Press Enter to return to menu...")

def main():
    while True:
        db_status, client = check_db_connection()
        display_menu(db_status)
        
        choice = input("\nEnter choice (1-3): ")
        
        if not db_status and choice in ['1', '2']:
            print("\nError: Database is offline. Cannot send data.")
            time.sleep(2)
            continue
        
        if choice == "1":
            try:
                data = generate_random_data()
                db = client["Smart_Cubicle"]
                collection = db["odor_module"]  # Updated collection name
                result = collection.insert_one(data)
                
                print("\nData sent successfully!")
                print(f"Timestamp: {data['timestamp']}")
                
                # Fixed string formatting for single send
                aqi_values = [f"GAS{i+1}: {data['aqi'][f'GAS{i+1}']}" 
                            for i in range(4)]
                print("AQI Values:", ", ".join(aqi_values))
                
                temp_values = [f"TEMP{i+1}: {data['dht'][f'TEMP{i+1}']['temp']}°C" 
                             for i in range(4)]
                print("Temperature Values:", ", ".join(temp_values))
                
                input("\nPress Enter to continue...")
                
            except Exception as e:
                print(f"\nError: {e}")
                input("Press Enter to continue...")
                
        elif choice == "2":
            try:
                db = client["Smart_Cubicle"]
                collection = db["odor_module"]  # Updated collection name
                continuous_send(client, collection)
            except Exception as e:
                print(f"\nError: {e}")
                input("Press Enter to continue...")
        elif choice == "3":
            print("\nExiting program...")
            if client:
                client.close()
            break
            
        else:
            print("\nInvalid choice. Please try again.")
            time.sleep(1)

if __name__ == "__main__":
    main()
