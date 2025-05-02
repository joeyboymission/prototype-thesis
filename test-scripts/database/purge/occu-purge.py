import os
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

def display_menu(db_status):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*50)
    print("Occupancy Module Database Purge Tool")
    print("="*50)
    print(f"Database Status: {'Online' if db_status else 'Offline'}")
    print("-"*50)
    print("1. Purge All Data")
    print("2. Exit Program")
    print("="*50)

def purge_data(client):
    """Purge all data from the occupancy_module collection"""
    try:
        db = client["Smart_Cubicle"]
        collection = db["occupancy_module"]
        
        # Get document count before purge
        doc_count = collection.count_documents({})
        
        # Confirm with user
        print(f"\nFound {doc_count} documents in occupancy_module collection")
        confirm = input("Are you sure you want to purge all data? (yes/no): ")
        
        if confirm.lower() == 'yes':
            # Delete all documents but keep collection and indexes
            result = collection.delete_many({})
            print(f"\nSuccessfully purged {result.deleted_count} documents")
        else:
            print("\nPurge cancelled")
            
    except Exception as e:
        print(f"\nError during purge: {e}")
    
    input("\nPress Enter to continue...")

def main():
    while True:
        db_status, client = check_db_connection()
        display_menu(db_status)
        
        choice = input("\nEnter choice (1-2): ")
        
        if not db_status and choice == '1':
            print("\nError: Database is offline. Cannot purge data.")
            time.sleep(2)
            continue
        
        if choice == "1":
            purge_data(client)
        elif choice == "2":
            print("\nExiting program...")
            if client:
                client.close()
            break
        else:
            print("\nInvalid choice. Please try again.")
            time.sleep(1)

if __name__ == "__main__":
    main()