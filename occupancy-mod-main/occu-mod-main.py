import lgpio
import time
import json
import os
import collections
from datetime import datetime

# Define global variables at the module level
mongo_collection = None
client = None
log_queue = collections.deque(maxlen=20)  # Store maximum 20 log entries

# Try to import MongoDB libraries, but have a fallback if not available
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    from bson import ObjectId
    MONGODB_AVAILABLE = True
    
    # Create a custom JSON encoder to handle MongoDB ObjectId
    class MongoJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ObjectId):
                return str(obj)  # Convert ObjectId to string
            return super().default(obj)
            
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")
    
    # Fallback encoder if MongoDB is not available
    class MongoJSONEncoder(json.JSONEncoder):
        pass

# GPIO setup
SENSOR_PIN = 17  # E18-D80NK signal
BUZZER_PIN = 27  # Buzzer control
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(chip, SENSOR_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_output(chip, BUZZER_PIN)
lgpio.gpio_write(chip, BUZZER_PIN, 0)

# MongoDB setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

def get_timestamp():
    """Return formatted timestamp string [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    """Print a message with timestamp and add to log queue"""
    timestamped_msg = f"{get_timestamp()} {message}"
    log_queue.append(timestamped_msg)
    print(timestamped_msg)

def display_log_window(clear=True):
    """Display the log window with recent entries only"""
    if clear:
        os.system('cls' if os.name == 'nt' else 'clear')
    
    print("\n" + "=" * 80)
    print("Recent Log Messages:")
    print("-" * 80)
    
    # Display all logs in the queue (max 20)
    for msg in log_queue:
        print(msg)
    
    # Fill remaining lines to keep consistent window size
    remaining_lines = 20 - len(log_queue)
    for _ in range(remaining_lines):
        print("")

def check_mongo_connection():
    global mongo_collection, client
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
        
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client['Smart_Cubicle']
        mongo_collection = db['occupancy'] 
        log_message("Connected to MongoDB successfully.")
        return True
    except Exception as e:
        log_message(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
        mongo_collection = None
        client = None
        return False

# Initialize MongoDB connection
check_mongo_connection()

# Constants
DEBOUNCE_TIME = 0.5  # 500ms
SHORT_BEEP = 0.2     # 200ms
LONG_BEEP = 1.0      # 1s
DATA_DIR = "/home/admin/Documents/local-data"
JSON_FILE = os.path.join(DATA_DIR, "occupancy-data.json")

# States
STATE_VACANT = "Vacant"
STATE_OCCUPIED = "Occupied"

# Variables
current_state = STATE_VACANT
visitor_count = -1
log_list = []
current_start_time = None
last_state_change_time = time.time()

def perform_post_check():
    """Perform Power-On Self Test to verify database connectivity"""
    print("\nInitializing Occupancy Module")
    
    test_results = {
        "local_storage": False,
        "mongodb_connection": False
    }
    
    # Check local storage
    storage_status = "Offline"
    try:
        os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
        existing_data = {}
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
                existing_data = json.load(f)
            log_message(f"Local storage accessible with existing data")
            storage_status = "Online"
        else:
            log_message("Local storage accessible (no existing data file)")
            storage_status = "Online"
        test_results["local_storage"] = True
        print(f"> Checking Local Storage: {storage_status}")
    except Exception as e:
        print(f"> Checking Local Storage: {storage_status}")
        log_message(f"Local storage test failed: {e}")
    
    # Check MongoDB connectivity
    mongodb_status = "Offline"
    if mongo_collection is not None:
        try:
            mongo_collection.find_one()
            test_results["mongodb_connection"] = True
            mongodb_status = "Online"
            print(f"> Checking MongoDB: {mongodb_status}")
        except Exception as e:
            print(f"> Checking MongoDB: {mongodb_status}")
            log_message(f"MongoDB connection test failed: {e}")
    else:
        print(f"> Checking MongoDB: {mongodb_status}")
        log_message("MongoDB not connected, using local storage only")
    
    # Return overall result
    all_okay = (
        test_results["local_storage"] and
        test_results["mongodb_connection"]
    )
    
    if all_okay:
        log_message("POST completed successfully. All essential systems operational.")
    else:
        log_message("POST completed with errors. Some systems may not function properly.")
    
    return all_okay

# Buzzer control
def beep_buzzer(duration):
    """Control the buzzer for a specified duration"""
    try:
        lgpio.gpio_write(chip, BUZZER_PIN, 1)
        time.sleep(duration)
        lgpio.gpio_write(chip, BUZZER_PIN, 0)
        log_message(f"Buzzer activated for {duration} seconds")
    except Exception as e:
        log_message(f"Error controlling buzzer: {e}")

def double_beep():
    """Perform a double beep pattern"""
    try:
        beep_buzzer(SHORT_BEEP)
        time.sleep(SHORT_BEEP)
        beep_buzzer(SHORT_BEEP)
        log_message("Double beep performed")
    except Exception as e:
        log_message(f"Error performing double beep: {e}")

# Format duration
def format_duration(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}sec"

# JSON handling
def read_json(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log_message(f"Error reading JSON: {e}")
    return {"visitors": [], "summary": {"total_visitors": 0, "average_duration": 0}, "current_presence": False}

def write_json(file_path, data):
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    temp_file = file_path + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4, cls=MongoJSONEncoder)
        os.replace(temp_file, file_path)
    except IOError as e:
        log_message(f"Error writing JSON: {e}")

# MongoDB handling
def update_mongo(entry):
    """Update MongoDB with properly formatted data"""
    global mongo_collection
    
    # Format data to match remote database exactly
    formatted_data = {
        "type": "visit",
        "visitor_id": entry["visitor_id"],
        "start_time": datetime.fromtimestamp(entry["start_time"]).strftime("%Y-%m-%dT%H:%M:%S.000000"),
        "end_time": datetime.fromtimestamp(entry["end_time"]).strftime("%Y-%m-%dT%H:%M:%S.000000") if "end_time" in entry else None,
        "duration": int(entry["duration"]) if "duration" in entry else None
    }
    
    # Always save to local storage first
    save_to_local_json(formatted_data)
    
    # Then try to save to MongoDB if available
    if mongo_collection is not None:
        try:
            mongo_collection.insert_one(formatted_data)
            log_message("Data also saved to MongoDB.")
        except Exception as e:
            log_message(f"Error updating MongoDB: {e}. Data saved locally only.")
            mongo_collection = None

def save_to_local_json(entry):
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
        
        # Read existing data
        existing_data = []
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r") as f:
                    data = json.load(f)
                    # Ensure data is a list
                    if isinstance(data, list):
                        existing_data = data
                    else:
                        log_message("Existing data is not in list format. Creating new list.")
                        existing_data = []
                log_message(f"Found existing data file with {len(existing_data)} records")
            except json.JSONDecodeError:
                log_message("Existing file found but couldn't be parsed. Creating new file.")
                existing_data = []
        else:
            log_message(f"Creating new data file: {JSON_FILE}")
        
        # Append new entry (already formatted correctly)
        existing_data.append(entry)
        
        # Write back to file
        temp_file = JSON_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, JSON_FILE)
        log_message(f"Data saved to local storage. Total records: {len(existing_data)}")
    except Exception as e:
        log_message(f"Error saving to local JSON: {e}")

# Load initial state
def load_initial_state(file_path):
    global current_state, visitor_count, log_list, current_start_time
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    data = read_json(file_path)
    
    # Handle the case where data is a list (direct entries) instead of a dictionary with "visitors" key
    if isinstance(data, list):
        log_list = data
        log_message("Loaded data in list format directly")
    else:
        log_list = data.get("visitors", [])
        log_message("Loaded data in dictionary format with 'visitors' key")
    
    if log_list:
        try:
            visitor_count = max(entry["visitor_id"] for entry in log_list)
            ongoing_visit = next((entry for entry in log_list if "end_time" not in entry), None)
            if ongoing_visit:
                current_state = STATE_OCCUPIED
                current_start_time = float(ongoing_visit["start_time"])
        except (KeyError, ValueError) as e:
            log_message(f"Error processing visitor data: {e}. Resetting visitor count.")
            visitor_count = -1
    else:
        visitor_count = -1

# Update JSON and MongoDB logs
def update_log(file_path, new_entry=None):
    if new_entry:
        log_list.append(new_entry)
        update_mongo(new_entry)
    
    total_visitors = len([e for e in log_list if "end_time" in e])
    completed_visits = [e for e in log_list if "end_time" in e]
    average_duration = sum(e["duration"] for e in completed_visits) / total_visitors if total_visitors > 0 else 0
    data = {
        "visitors": log_list,
        "summary": {
            "total_visitors": total_visitors,
            "average_duration": average_duration
        },
        "current_presence": current_state == STATE_OCCUPIED
    }
    write_json(file_path, data)

def save_current_state():
    """Save the current occupancy state to both local and remote databases"""
    global current_state, visitor_count, current_start_time
    
    current_time = time.time()
    timestamp = datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.000000")
    
    # Create a visit entry with the exact format
    visit_entry = {
        "type": "visit",
        "visitor_id": max(visitor_count, 0),
        "start_time": timestamp,
        "end_time": None,
        "duration": None
    }
    
    # Save to local JSON
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
        
        # Read existing data
        existing_data = []
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r") as f:
                    data = json.load(f)
                    # Ensure data is a list
                    if isinstance(data, list):
                        existing_data = data
                    else:
                        log_message("Existing data is not in list format. Creating new list.")
                        existing_data = []
            except json.JSONDecodeError:
                log_message("Existing file found but couldn't be parsed. Creating new file.")
                existing_data = []
        
        # Append new entry
        existing_data.append(visit_entry)
        
        # Write back to file
        temp_file = JSON_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, JSON_FILE)
        
        # Try to save to MongoDB if available
        if mongo_collection is not None:
            try:
                mongo_collection.insert_one(visit_entry)
                log_message(f"Visit data saved to both local and remote databases at {timestamp}")
                return True
            except Exception as e:
                log_message(f"Error updating MongoDB: {e}. Data saved locally only.")
                log_message(f"Visit data saved to local database at {timestamp}")
                return True
        else:
            log_message(f"Visit data saved to local database at {timestamp}")
            return True
    except Exception as e:
        log_message(f"Error saving data: {e}")
        return False

def display_options():
    """Display options menu during monitoring"""
    print("\n" + "=" * 80)
    print("Options:")
    print("1. Refresh Data Log Now")
    print("2. Return to Main Menu")
    print("=" * 80)
    print("\nAuto-refresh in 5 seconds...")

# Monitor occupancy
def monitor_occupancy(file_path):
    global current_state, visitor_count, log_list, current_start_time, last_state_change_time
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Run POST check
    perform_post_check()
    
    # Load initial state
    load_initial_state(file_path)
    log_message("Now monitoring occupancy!")
    log_message(f"Visitor Count: {max(visitor_count, 0)}")
    log_message(f"Presence: {current_state}")
    log_message("Duration: null" if current_start_time is None else f"Duration: {format_duration(time.time() - current_start_time)}")
    log_message("Press CTRL+C to return to menu")

    last_sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)
    detection_start = None
    last_display_time = time.time()
    last_log_time = time.time()
    last_save_time = time.time()
    last_state = current_state
    last_visitor_count = visitor_count
    display_width = 80

    import select
    import sys

    while True:
        current_time = time.time()
        sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)

        if (current_time - last_state_change_time) > DEBOUNCE_TIME and sensor_state != last_sensor_state:
            if current_state == STATE_VACANT and sensor_state == 0:
                detection_start = current_time
            elif current_state == STATE_VACANT and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                if (current_time - detection_start) < 2:  # Ensure full cycle within 2s
                    current_state = STATE_OCCUPIED
                    visitor_count += 1
                    current_start_time = current_time
                    new_entry = {
                        "visitor_id": visitor_count,
                        "start_time": current_time,
                        "start_time_iso": datetime.fromtimestamp(current_time).isoformat()
                    }
                    
                    # Create a formatted status line
                    status_line = f"Visitor Count: {max(visitor_count, 0)} | Status: Occupied"
                    log_message(status_line)
                    double_beep()
                    update_log(file_path, new_entry)
                    last_state_change_time = current_time
                    detection_start = None

            elif current_state == STATE_OCCUPIED and sensor_state == 0:
                detection_start = current_time
            elif current_state == STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                if (current_time - detection_start) < 2:
                    current_state = STATE_VACANT
                    end_time = current_time
                    duration = end_time - current_start_time
                    formatted_duration = format_duration(duration)
                    
                    for entry in log_list:
                        if entry["visitor_id"] == visitor_count and "end_time" not in entry:
                            entry["end_time"] = end_time
                            entry["duration"] = duration
                            entry["end_time_iso"] = datetime.fromtimestamp(end_time).isoformat()
                            update_mongo({
                                "visitor_id": entry["visitor_id"],
                                "start_time": entry["start_time"],
                                "start_time_iso": entry["start_time_iso"],
                                "end_time": end_time,
                                "end_time_iso": entry["end_time_iso"],
                                "duration": duration
                            })
                            break
                    
                    # Create a formatted status line
                    status_line = f"Visitor Count: {max(visitor_count, 0)} | Status: Vacant | Duration: {formatted_duration}"
                    log_message(status_line)
                    beep_buzzer(LONG_BEEP)
                    update_log(file_path)
                    last_state_change_time = current_time
                    detection_start = None

            last_sensor_state = sensor_state
        
        # Save current state every 5 seconds
        if current_time - last_save_time >= 5:
            save_current_state()
            last_save_time = current_time
        
        # Refresh log display periodically
        if current_time - last_display_time >= 1:
            display_log_window()
            last_display_time = current_time

        # Only log status changes or every 30 seconds
        if (current_state != last_state or visitor_count != last_visitor_count or 
            current_time - last_log_time >= 30):
            # Create a status summary
            status_line = f"Visitor Count: {max(visitor_count, 0)} | Status: {current_state}"
            if current_state == STATE_OCCUPIED and current_start_time is not None:
                status_line += f" | Duration so far: {format_duration(time.time() - current_start_time)}"
            log_message(status_line)
            last_log_time = current_time
            last_state = current_state
            last_visitor_count = visitor_count

        # Display options menu periodically
        if current_time - last_display_time >= 5:
            display_options()
            last_display_time = current_time
        
        # Check for keyboard input (non-blocking)
        if select.select([sys.stdin], [], [], 0)[0]:
            choice = sys.stdin.readline().strip()
            if choice == "1":
                log_message("Manual refresh triggered")
                status_line = f"Visitor Count: {max(visitor_count, 0)} | Status: {current_state}"
                if current_state == STATE_OCCUPIED and current_start_time is not None:
                    status_line += f" | Duration so far: {format_duration(time.time() - current_start_time)}"
                log_message(status_line)
                last_display_time = current_time
                display_log_window()
            elif choice == "2":
                log_message("Returning to main menu...")
                break

        time.sleep(0.05)

# CLI Menu
def main():
    while True:
        print("\n" + "="*80)
        print("╔═══════════════════════════════════════════════════╗")
        print("║              SMART RESTROOM SYSTEM                ║")
        print("║                OCCUPANCY MODULE                   ║")
        print("╚═══════════════════════════════════════════════════╝")
        print("="*80)
        print("1. Start the Module")
        print("2. Exit the Program")
        
        choice = input("\nEnter your choice (1-2): ")
        
        if choice == "1":
            try:
                monitor_occupancy(JSON_FILE)
            except KeyboardInterrupt:
                log_message("Monitoring stopped. Returning to menu...")
            except PermissionError as e:
                log_message(f"Permission error accessing {DATA_DIR}: {e}. Try running with sudo.")
        elif choice == "2":
            log_message("Exiting program...")
            break
        else:
            print("Invalid choice. Please select 1 or 2.")

if __name__ == "__main__":
    try:
        log_message("Initializing Occupancy Module...")
        main()
    finally:
        lgpio.gpiochip_close(chip)
        if client is not None:
            client.close()