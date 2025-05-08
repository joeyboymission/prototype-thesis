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
    """Ensure the checkout-data directory exists within the checkout directory"""
    # Get the current script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create the checkout-data directory within the checkout directory
    checkout_dir = os.path.join(script_dir, "checkout-data")
    if not os.path.exists(checkout_dir):
        print(f"Creating checkout-data directory: {checkout_dir}")
        os.makedirs(checkout_dir)
    
    return checkout_dir

def format_timestamp(doc, field_name):
    """Format timestamp field in document"""
    if field_name in doc:
        try:
            if isinstance(doc[field_name], str):
                datetime_obj = datetime.strptime(doc[field_name], "%Y-%m-%d %H:%M:%S")
                doc[field_name] = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass  # Keep original if formatting fails

def export_collection_data(client, collection_name, output_filename):
    """Export data from specified collection to JSON"""
    try:
        db = client["Smart_Cubicle"]
        collection = db[collection_name]
        
        # Get all documents including _id field
        documents = list(collection.find({}))
        
        # Format timestamps based on collection type
        for doc in documents:
            if collection_name == "occupancy":
                format_timestamp(doc, "start_time")
                format_timestamp(doc, "end_time")
            else:  # dispenser_resource and odor_module
                format_timestamp(doc, "timestamp")
        
        # Ensure checkout directory exists
        checkout_dir = ensure_checkout_dir()
        output_file = os.path.join(checkout_dir, output_filename)
        
        # Write to JSON file using custom JSON encoder
        with open(output_file, 'w') as f:
            json.dump(documents, f, indent=2, cls=MongoJSONEncoder)
            
        print(f"\nSuccessfully exported {len(documents)} documents to {output_file}")
        print(f"File path: {output_file}")
        
        return True
    except Exception as e:
        print(f"\nError exporting {collection_name}: {e}")
        return False

def main():
    print("\n" + "="*50)
    print("Smart Cubicle Data Checkout Tool")
    print("="*50)
    
    # Check database connection
    db_status, client = check_db_connection()
    if not db_status:
        print("Error: Cannot connect to database. Exiting...")
        return
    
    print("Database connected successfully!")
    print("Starting data export...")
    
    # Define collections to export
    collections = {
        "dispenser_resource": "disp-checkout.json",
        "occupancy": "occu-checkout.json",
        "odor_module": "odor-checkout.json"
    }
    
    # Export data from each collection
    success_count = 0
    for collection_name, output_file in collections.items():
        print(f"\nExporting {collection_name}...")
        if export_collection_data(client, collection_name, output_file):
            success_count += 1
    
    # Close connection
    client.close()
    
    # Print summary
    print("\n" + "="*50)
    print(f"Checkout Summary: {success_count}/{len(collections)} collections exported successfully")
    print("="*50)

if __name__ == "__main__":
    main()
