import os
import json
import random
import time
from datetime import datetime
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
    """Generate random dispenser data"""
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    def get_status(level):
        if level == 0: return "EMPTY"
        if level < 20: return "LOW"
        return "OK"
    
    # Generate random levels
    level1 = random.randint(0, 100)
    level2 = random.randint(0, 100)
    
    return {
        "timestamp": timestamp,
        "dispenser": {
            "DISP1": {
                "level": level1,
                "status": get_status(level1)
            },
            "DISP2": {
                "level": level2,
                "status": get_status(level2)
            }
        },
        "dispense_count": {
            "DISP1": random.randint(0, 50),
            "DISP2": random.randint(0, 50)
        }
    }

def display_menu(db_status):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*50)
    print("Dispensing Module Database Test Tool")
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
            
            print("\nData sent successfully!")
            print(f"Timestamp: {data['timestamp']}")
            print("Dispenser Levels:")
            for disp, info in data['dispenser'].items():
                print(f"{disp}: Level={info['level']}%, Status={info['status']}")
            print("Dispense Counts:", 
                  ", ".join(f"{k}: {v}" for k, v in data['dispense_count'].items()))
            
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
            try:
                data = generate_random_data()
                db = client["Smart_Cubicle"]
                collection = db["dispenser_module"]
                result = collection.insert_one(data)
                
                print("\nData sent successfully!")
                print(f"Timestamp: {data['timestamp']}")
                print("Dispenser Levels:")
                for disp, info in data['dispenser'].items():
                    print(f"{disp}: Level={info['level']}%, Status={info['status']}")
                print("Dispense Counts:", 
                      ", ".join(f"{k}: {v}" for k, v in data['dispense_count'].items()))
                
            except Exception as e:
                print(f"\nError: {e}")
                input("Press Enter to continue...")
        elif choice == "2":
            try:
                db = client["Smart_Cubicle"]
                collection = db["dispenser_module"]
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

# Run the main function only if this module is executed as the main program
if __name__ == "__main__":
    main()
