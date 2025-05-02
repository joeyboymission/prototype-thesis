import os
import json
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

def ensure_checkout_dir():
    """Ensure the checkout directory exists"""
    checkout_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(checkout_dir):
        os.makedirs(checkout_dir)
    return checkout_dir

def export_data(client):
    """Export data from occupancy_module collection to JSON"""
    try:
        db = client["Smart_Cubicle"]
        collection = db["occupancy_module"]
        
        # Get all documents
        documents = list(collection.find({}, {'_id': False}))
        
        # Format timestamps for better readability
        for doc in documents:
            if 'start_time' in doc:
                doc['start_time'] = doc['start_time']
            if 'end_time' in doc:
                doc['end_time'] = doc['end_time']
        
        # Ensure checkout directory exists
        checkout_dir = ensure_checkout_dir()
        output_file = os.path.join(checkout_dir, 'occu-checkout.json')
        
        # Write to JSON file
        with open(output_file, 'w') as f:
            json.dump(documents, f, indent=2)
            
        print(f"\nSuccessfully exported {len(documents)} documents to {output_file}")
        
    except Exception as e:
        print(f"\nError during export: {e}")

def main():
    print("\n" + "="*50)
    print("Occupancy Module Data Checkout Tool")
    print("="*50)
    
    # Check database connection
    db_status, client = check_db_connection()
    if not db_status:
        print("Error: Cannot connect to database. Exiting...")
        return
    
    print("Database connected successfully!")
    print("Starting data export...")
    
    # Export data
    export_data(client)
    
    # Close connection
    client.close()
    print("\nCheckout complete!")

if __name__ == "__main__":
    main()