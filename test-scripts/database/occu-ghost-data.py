import os
import json
import random
import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

# MongoDB Setup
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
    """Generate random occupancy data"""
    current_time = datetime.now()
    # Generate random duration between 1-10 minutes
    duration = random.uniform(60, 600)  # seconds
    start_time = current_time - timedelta(seconds=duration)
    
    return {
        "visitor_id": random.randint(1, 100),
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": round(duration, 1)
    }

def display_menu(db_status):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*50)
    print("Occupancy Module Database Test Tool")
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
        visitor_id = 1
        while True:
            data = generate_random_data()
            data['visitor_id'] = visitor_id
            result = collection.insert_one(data)
            
            print("\nData sent successfully!")
            print(f"Visitor ID: {data['visitor_id']}")
            print(f"Start Time: {data['start_time']}")
            print(f"End Time: {data['end_time']}")
            print(f"Duration: {data['duration']:.1f} seconds")
            
            visitor_id += 1
            time.sleep(5)
            os.system('cls' if os.name == 'nt' else 'clear')
            
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
            data = generate_random_data()
            try:
                db = client["Smart_Cubicle"]
                collection = db["occupancy_module"]
                result = collection.insert_one(data)
                print("\nData sent successfully!")
                print(f"Visitor ID: {data['visitor_id']}")
                print(f"Start Time: {data['start_time']}")
                print(f"End Time: {data['end_time']}")
                print(f"Duration: {data['duration']:.1f} seconds")
            except Exception as e:
                print(f"\nError: {e}")
                input("Press Enter to continue...")
        elif choice == "2":
            try:
                db = client["Smart_Cubicle"]
                collection = db["occupancy_module"]
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
