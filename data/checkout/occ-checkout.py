import os
import json
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId, json_util

# MongoDB Setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

# Custom JSON encoder to handle MongoDB ObjectId conversion to string
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)  # Convert ObjectId to string directly
        return super().default(obj)

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
    """Ensure the data-checkout directory exists"""
    # Get the parent directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    # Create the data-checkout directory if it doesn't exist
    checkout_dir = os.path.join(parent_dir, "data-checkout")
    if not os.path.exists(checkout_dir):
        print(f"Creating data-checkout directory: {checkout_dir}")
        os.makedirs(checkout_dir)
    
    return checkout_dir

def export_data(client):
    """Export data from occupancy_module collection to JSON"""
    try:
        db = client["Smart_Cubicle"]
        collection = db["occupancy"]  # Keep the correct collection name
        
        # Get all documents including _id field
        documents = list(collection.find({}))
        
        # Format timestamps for better readability
        for doc in documents:
            if 'start_time' in doc:
                # Ensure start_time is properly formatted
                try:
                    if isinstance(doc['start_time'], str):
                        # If already a string, ensure it's properly formatted
                        datetime_obj = datetime.strptime(doc['start_time'], "%Y-%m-%d %H:%M:%S")
                        doc['start_time'] = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    # Keep original if formatting fails
                    pass
            
            if 'end_time' in doc:
                # Ensure end_time is properly formatted
                try:
                    if isinstance(doc['end_time'], str):
                        # If already a string, ensure it's properly formatted
                        datetime_obj = datetime.strptime(doc['end_time'], "%Y-%m-%d %H:%M:%S")
                        doc['end_time'] = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    # Keep original if formatting fails
                    pass
        
        # Ensure checkout directory exists
        checkout_dir = ensure_checkout_dir()
        output_file = os.path.join(checkout_dir, 'occu-checkout.json')
        
        # Write to JSON file using custom JSON encoder instead of json_util.dumps
        with open(output_file, 'w') as f:
            json.dump(documents, f, indent=2, cls=MongoJSONEncoder)
            
        print(f"\nSuccessfully exported {len(documents)} documents to {output_file}")
        print(f"File path: {output_file}")
        
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