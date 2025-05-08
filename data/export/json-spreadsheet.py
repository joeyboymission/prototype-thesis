import json
import pandas as pd
from pathlib import Path
import os
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from bson import ObjectId, json_util
import time
import argparse
import sys
import glob

# MongoDB Setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

# Required JSON files
REQUIRED_FILES = ['disp-checkout.json', 'occu-checkout.json', 'odor-checkout.json']

# Custom JSON encoder to handle MongoDB ObjectId conversion to string
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)  # Convert ObjectId to string directly
        return super().default(obj)

def print_status(message, status="INFO"):
    """Print formatted status message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_colors = {
        "INFO": "\033[94m",  # Blue
        "SUCCESS": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "INPUT": "\033[95m"     # Purple
    }
    color = status_colors.get(status, "\033[0m")  # Default to no color
    reset = "\033[0m"
    print(f"{color}[{timestamp}] [{status}] {message}{reset}")

def clear_screen():
    """Clear the console screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print the application header"""
    print("\033[95m" + "="*50)  # Purple color
    print("Smart Cubicle Data Export Tool")
    print("="*50 + "\033[0m")  # Reset color

def print_menu():
    """Print the main menu"""
    print("\n\033[96mSelect Data Source:\033[0m")  # Cyan color
    print("1. Export from MongoDB")
    print("2. Export from Local JSON Files")
    print("3. Exit")
    print("\nEnter your choice (1-3): ", end='')

def get_menu_choice():
    """Get and validate user's menu choice"""
    while True:
        try:
            choice = int(input())
            if 1 <= choice <= 3:
                return choice
            print("\033[93mInvalid choice. Please enter 1, 2, or 3.\033[0m")
        except ValueError:
            print("\033[93mPlease enter a valid number.\033[0m")
        print("Enter your choice (1-3): ", end='')

def check_db_connection():
    """Test MongoDB connection and return status"""
    try:
        print_status("Attempting to connect to MongoDB...")
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        print_status("Successfully connected to MongoDB", "SUCCESS")
        return True, client
    except Exception as e:
        print_status(f"Database Error: {e}", "ERROR")
        return False, None

def get_default_json_dir():
    """Get the default directory containing JSON files"""
    # Get the script's directory
    script_dir = Path(__file__).resolve().parent
    # Go up to 'data' directory
    data_dir = script_dir.parent
    # Default JSON directory is in data/checkout/data-checkout
    default_dir = data_dir / 'checkout' / 'data-checkout'
    return default_dir

def select_directory():
    """Interactive directory selection"""
    default_dir = get_default_json_dir()
    
    while True:
        print_status("Enter the path to the directory containing JSON files:", "INPUT")
        print_status(f"(Press Enter for default: {default_dir})", "INPUT")
        
        dir_path = input().strip()
        
        # Use default path if empty
        if not dir_path:
            dir_path = default_dir
        else:
            dir_path = Path(dir_path)
        
        try:
            # Resolve to absolute path
            dir_path = dir_path.resolve()
            
            if not dir_path.exists():
                print_status(f"Directory not found: {dir_path}", "ERROR")
                continue
            
            # Check for required files
            missing_files = []
            for required_file in REQUIRED_FILES:
                if not (dir_path / required_file).exists():
                    missing_files.append(required_file)
            
            if missing_files:
                print_status("Missing required JSON files:", "ERROR")
                for file in missing_files:
                    print_status(f"  - {file}", "ERROR")
                continue
            
            return dir_path
            
        except Exception as e:
            print_status(f"Error accessing directory: {e}", "ERROR")
            continue

def ensure_output_dir(base_dir):
    """Ensure the spreadsheets directory exists"""
    # Get the data directory (parent of export directory)
    data_dir = Path(__file__).resolve().parent.parent
    # Create spreadsheets directory in export
    output_dir = data_dir / 'export' / 'spreadsheets'
    
    if output_dir.exists():
        print_status(f"Found existing spreadsheets directory: {output_dir}")
        existing_files = list(output_dir.glob('*.xlsx'))
        if existing_files:
            print_status("Found existing spreadsheet files:", "WARNING")
            for file in existing_files:
                print_status(f"  - {file.name}", "WARNING")
            print_status("These files will be overwritten with new data", "WARNING")
    else:
        print_status(f"Creating new spreadsheets directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir

def flatten_nested_dict(d, parent_key='', sep='_'):
    """Recursively flatten nested dictionaries"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_nested_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def flatten_json_data(data, collection_type):
    """Flatten nested JSON data into a flat dictionary."""
    flattened = {}
    
    # Handle the main fields
    if '_id' in data:
        if isinstance(data['_id'], dict) and '$oid' in data['_id']:
            flattened['_id'] = data['_id']['$oid']
        else:
            flattened['_id'] = data['_id']
    
    if 'timestamp' in data:
        flattened['timestamp'] = data['timestamp']
    
    if 'reading' in data:
        flattened['reading'] = data['reading']
    
    # Handle start_time and end_time for occupancy data
    if 'start_time' in data:
        flattened['start_time'] = data['start_time']
    if 'end_time' in data:
        flattened['end_time'] = data['end_time']
    
    # Handle different data structures based on collection type
    if collection_type == 'dispenser_resource':
        if 'data' in data:
            # Flatten the nested data structure
            nested_data = flatten_nested_dict(data['data'])
            flattened.update(nested_data)
    
    elif collection_type == 'odor_module':
        # Handle AQI data
        if 'aqi' in data:
            for gas, value in data['aqi'].items():
                flattened[f'{gas}_aqi'] = value
        
        # Handle DHT data
        if 'dht' in data:
            for temp, values in data['dht'].items():
                for key, value in values.items():
                    flattened[f'{temp}_{key}'] = value
    
    elif collection_type == 'occupancy':
        # Handle occupancy data
        if 'data' in data:
            # Flatten the nested data structure
            nested_data = flatten_nested_dict(data['data'])
            flattened.update(nested_data)
    
    return flattened

def load_json_file(file_path):
    """Load and parse JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_status(f"Error loading JSON file {file_path}: {e}", "ERROR")
        return None

def fetch_data_from_db(client, collection_name):
    """Fetch data directly from MongoDB"""
    try:
        db = client["Smart_Cubicle"]
        collection = db[collection_name]
        documents = list(collection.find({}))
        
        # Format timestamps
        for doc in documents:
            # Handle timestamp field
            if 'timestamp' in doc:
                try:
                    if isinstance(doc['timestamp'], str):
                        datetime_obj = datetime.strptime(doc['timestamp'], "%Y-%m-%d %H:%M:%S")
                        doc['timestamp'] = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            
            # Handle start_time and end_time fields for occupancy data
            for time_field in ['start_time', 'end_time']:
                if time_field in doc:
                    try:
                        if isinstance(doc[time_field], str):
                            datetime_obj = datetime.strptime(doc[time_field], "%Y-%m-%d %H:%M:%S")
                            doc[time_field] = datetime_obj.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
        
        return documents
    except Exception as e:
        print_status(f"Error fetching data from database: {e}", "ERROR")
        return None

def fetch_data_from_json(json_dir, collection_name):
    """Fetch data from local JSON files"""
    try:
        # Map collection names to JSON file names
        file_mapping = {
            'dispenser_resource': 'disp-checkout.json',
            'odor_module': 'odor-checkout.json',
            'occupancy': 'occu-checkout.json'
        }
        
        json_file = file_mapping.get(collection_name)
        if not json_file:
            print_status(f"No JSON file mapping found for {collection_name}", "ERROR")
            return None
        
        # Construct path to JSON file
        json_path = json_dir / json_file
        if not json_path.exists():
            print_status(f"JSON file not found: {json_path}", "ERROR")
            return None
        
        print_status(f"Reading {json_file}...")
        return load_json_file(json_path)
    except Exception as e:
        print_status(f"Error loading JSON file: {e}", "ERROR")
        return None

def convert_to_spreadsheet(data, collection_name, output_file):
    """Convert data to spreadsheet format"""
    try:
        print_status(f"Processing {collection_name} data...")
        start_time = time.time()
        
        # Flatten the data
        print_status("Flattening data structure...")
        flattened_data = [flatten_json_data(doc, collection_name) for doc in data]
        
        # Convert to DataFrame
        print_status("Converting to DataFrame...")
        df = pd.DataFrame(flattened_data)
        
        # Save to Excel
        print_status(f"Saving to Excel: {output_file}")
        df.to_excel(output_file, index=False)
        
        end_time = time.time()
        duration = end_time - start_time
        print_status(f"Successfully converted {collection_name} data to {output_file} in {duration:.2f} seconds", "SUCCESS")
        print_status(f"Total rows in spreadsheet: {len(df)}", "SUCCESS")
        
    except Exception as e:
        print_status(f"Error converting {collection_name} data: {e}", "ERROR")

def process_collections(source_type):
    """Process all collections and convert to spreadsheets"""
    print_status("Starting data conversion process...")
    
    # Define collections to process
    collections = {
        'dispenser_resource': 'disp-checkout',
        'odor_module': 'odor-checkout',
        'occupancy': 'occu-checkout'
    }
    
    client = None
    json_dir = None
    
    try:
        if source_type == 'db':
            # Check database connection
            db_status, client = check_db_connection()
            if not db_status:
                print_status("Cannot connect to database. Exiting...", "ERROR")
                return
        else:  # source_type == 'json'
            # Get directory containing JSON files
            json_dir = select_directory()
            if not json_dir:
                return
            print_status(f"Using JSON files from: {json_dir}")
        
        # Create output directory
        output_dir = ensure_output_dir(json_dir if json_dir else Path('data/export'))
        
        # Process each collection
        for collection_name, output_filename in collections.items():
            print_status(f"\nProcessing collection: {collection_name}")
            
            # Get data based on source type
            if source_type == 'db':
                data = fetch_data_from_db(client, collection_name)
            else:  # source_type == 'json'
                data = fetch_data_from_json(json_dir, collection_name)
            
            if data:
                # Update output path to use the same parent directory
                output_file = output_dir / f'{output_filename}.xlsx'
                convert_to_spreadsheet(data, collection_name, output_file)
    
    finally:
        if client:
            client.close()
    
    print_status("\nConversion process completed!", "SUCCESS")

def main():
    while True:
        clear_screen()
        print_header()
        print_menu()
        
        choice = get_menu_choice()
        
        if choice == 1:
            print_status("Selected: Export from MongoDB")
            process_collections('db')
        elif choice == 2:
            print_status("Selected: Export from Local JSON Files")
            process_collections('json')
        else:  # choice == 3
            print_status("Exiting...", "SUCCESS")
            sys.exit(0)
        
        # Wait for user to press Enter before showing menu again
        input("\nPress Enter to continue...")

if __name__ == '__main__':
    main()

