import lgpio
import time
import os
import json
import collections
from datetime import datetime

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

# MongoDB Atlas connection setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
client = None
db = None
collection = None
log_queue = collections.deque(maxlen=20)  # Store maximum 20 log entries

# Local data fallback setup
DATA_DIR = "/home/admin/Documents/local-data"
JSON_FILE = os.path.join(DATA_DIR, "dispenser-data.json")
os.makedirs(DATA_DIR, exist_ok=True)  # Create directory if it doesn't exist

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
    global client, db, collection
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
        
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client['Smart_Cubicle']
        collection = db['dispenser_module']  # Updated collection name
        log_message("Connected to MongoDB successfully.")
        return True
    except Exception as e:
        log_message(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
        client = None
        db = None
        collection = None
        return False

# Initialize MongoDB connection
check_mongo_connection()

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# Define trigger and echo pins for each ultrasonic sensor
triggers = [7, 9, 11, 14]  # GPIO7, GPIO9, GPIO11, GPIO14
echos = [8, 10, 13, 15]    # GPIO8, GPIO10, GPIO13, GPIO15

# Set up GPIO pins
for trigger in triggers:
    lgpio.gpio_claim_output(h, trigger)
for echo in echos:
    lgpio.gpio_claim_input(h, echo)

# Calibration data (only CONT1 for now; others will be added)
CALIBRATION_DATA = {
    "CONT1": {"full": 2.84, "empty": 12.67},
    "CONT2": {"full": 2.37, "empty": 12.21},
    "CONT3": {"full": 2.23, "empty": 12.33},
    "CONT4": {"full": 2.91, "empty": 12.88}
}

# Significant change threshold in mL (to avoid saving unnecessary data)
SIGNIFICANT_CHANGE_THRESHOLD = 10.0

def perform_post_check():
    """Perform Power-On Self Test to verify all components are working"""
    print("\nInitializing Dispenser Module")
    
    test_results = {
        "ultrasonic_sensors": [False] * 4,
        "local_storage": False,
        "mongodb_connection": False
    }
    
    # Test ultrasonic sensors
    for i, (trigger, echo) in enumerate(zip(triggers, echos)):
        try:
            # Perform a test measurement
            _, distance = measure_distance(trigger, echo)
            if distance is not None and 0 < distance < 400:  # Valid distance range: 0-400cm
                test_results["ultrasonic_sensors"][i] = True
                print(f"> Checking SONIC{i+1}: Online")
            else:
                print(f"> Checking SONIC{i+1}: Offline")
        except Exception as e:
            print(f"> Checking SONIC{i+1}: Offline")
            log_message(f"Ultrasonic sensor #{i+1} test failed: {e}")
    
    # Check local storage
    storage_status = "Offline"
    try:
        os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
        existing_data = []
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
                existing_data = json.load(f)
            log_message(f"Local storage accessible with {len(existing_data)} existing records")
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
    if collection is not None:
        try:
            collection.find_one()
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
        any(test_results["ultrasonic_sensors"]) and  # At least one sensor working
        test_results["local_storage"]
        # We don't require MongoDB to be working
    )
    
    if all_okay:
        log_message("POST completed successfully. All essential systems operational.")
    else:
        log_message("POST completed with errors. Some systems may not function properly.")
    
    return all_okay

# Function to save data to local JSON file
def save_to_local_json(reading_doc):
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
        
        # Read existing data
        existing_data = []
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r") as f:
                    existing_data = json.load(f)
                log_message(f"Found existing data file with {len(existing_data)} records")
            except json.JSONDecodeError:
                log_message("Existing file found but couldn't be parsed. Creating new file.")
                existing_data = []
        else:
            log_message(f"Creating new data file: {JSON_FILE}")
        
        # Append new reading
        existing_data.append(reading_doc)
        
        # Write back to file
        temp_file = JSON_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, JSON_FILE)
        log_message(f"Data saved to local storage. Total records: {len(existing_data)}")
        return True
    except IOError as e:
        log_message(f"Error saving to local JSON: {e}")
        return False

# Function to measure raw data and distance
def measure_raw_data(trigger, echo, num_measurements=5):
    distances = []
    pulse_durations = []
    for _ in range(num_measurements):
        lgpio.gpio_write(h, trigger, 1)  # Trigger high
        time.sleep(0.00001)              # 10us pulse
        lgpio.gpio_write(h, trigger, 0)  # Trigger low
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:
                return None, None
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:
                return None, None
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound in cm/s
        distance = round(distance, 2)
        distances.append(distance)
        pulse_durations.append(pulse_duration)
        time.sleep(0.05)
    
    if distances and pulse_durations:
        avg_distance = sum(distances) / len(distances)
        avg_pulse_duration = sum(pulse_durations) / len(pulse_durations)
        return avg_pulse_duration, avg_distance
    return None, None

# Function to calculate usable volume in mL
def calculate_usable_volume(container, distance):
    if CALIBRATION_DATA[container]["full"] is None or CALIBRATION_DATA[container]["empty"] is None:
        return None  # Cannot calculate without calibration data
    
    full_distance = CALIBRATION_DATA[container]["full"]
    empty_distance = CALIBRATION_DATA[container]["empty"]
    
    if distance <= full_distance:
        return 425.0  # Full usable volume
    elif distance >= empty_distance:
        return 0.0  # Empty usable volume
    else:
        # Linear interpolation for usable volume
        total_distance_range = empty_distance - full_distance
        distance_from_full = distance - full_distance
        volume_fraction = 1 - (distance_from_full / total_distance_range)
        usable_volume = 425.0 * volume_fraction
        return round(usable_volume, 2)

def save_data(reading_doc):
    """Save data in format matching remote database exactly"""
    # Format data
    formatted_data = {
        "reading": reading_doc["reading"],
        "timestamp": reading_doc["timestamp"],
        "data": {
            "CONT1": {
                "distance_cm": round(reading_doc["data"]["CONT1"]["distance_cm"], 4),
                "remaining_volume_ml": round(reading_doc["data"]["CONT1"]["remaining_volume_ml"], 2)
            },
            "CONT2": {
                "distance_cm": round(reading_doc["data"]["CONT2"]["distance_cm"], 4),
                "remaining_volume_ml": round(reading_doc["data"]["CONT2"]["remaining_volume_ml"], 2)
            },
            "CONT3": {
                "distance_cm": round(reading_doc["data"]["CONT3"]["distance_cm"], 4),
                "remaining_volume_ml": round(reading_doc["data"]["CONT3"]["remaining_volume_ml"], 2)
            },
            "CONT4": {
                "distance_cm": round(reading_doc["data"]["CONT4"]["distance_cm"], 4),
                "remaining_volume_ml": round(reading_doc["data"]["CONT4"]["remaining_volume_ml"], 2)
            }
        }
    }
    
    # Always save to local storage first
    save_to_local_json(formatted_data)
    
    # Then try to save to MongoDB if available
    if collection is not None:
        try:
            collection.insert_one(formatted_data)
            log_message("Data also saved to MongoDB")
            return True
        except Exception as e:
            log_message(f"Error saving to MongoDB: {e}. Data saved locally only.")
            collection = None
            return True
    return True

def display_options():
    """Display options menu during monitoring"""
    print("\n" + "=" * 80)
    print("Options:")
    print("1. Refresh Data Log Now")
    print("2. Return to Main Menu")
    print("=" * 80)
    print("\nAuto-refresh in 5 seconds...")

# Main monitoring function
def start_monitoring():
    reading_count = 0
    previous_volumes = {}
    delay_between_readings = 5  # seconds between readings
    last_saved_volumes = {}  # To track when significant changes occur
    last_display_time = time.time()
    
    # Run POST check
    perform_post_check()
    
    log_message("Dispenser Module - Liquid Level Monitoring")
    log_message("Press CTRL+C to return to menu\n")
    
    # Set up non-blocking input
    import select
    import sys
    
    try:
        while True:
            current_time = time.time()
            reading_count += 1
            current_reading = {}
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            significant_change_detected = False
            
            # Clear and update the display
            display_log_window()
            
            # Format for display line
            log_message(f"Reading {reading_count}")
            
            for i in range(4):
                container = f"CONT{i+1}"
                trigger = triggers[i]
                echo = echos[i]
                
                pulse_duration, distance = measure_raw_data(trigger, echo)
                if pulse_duration is None or distance is None:
                    log_message(f"{container}: Measurement failed (timeout or error)")
                    current_reading[container] = {
                        "distance_cm": None,
                        "remaining_volume_ml": None
                    }
                else:
                    volume = calculate_usable_volume(container, distance)
                    amount_used = None
                    if reading_count > 1 and container in previous_volumes and previous_volumes[container] is not None and volume is not None:
                        amount_used = round(previous_volumes[container] - volume, 2)
                        if amount_used < 0:
                            amount_used = 0
                    
                    # Check if this is a significant change from last saved value
                    if (container not in last_saved_volumes or 
                        last_saved_volumes[container] is None or 
                        volume is None or
                        abs(volume - last_saved_volumes.get(container, 0)) >= SIGNIFICANT_CHANGE_THRESHOLD):
                        significant_change_detected = True
                        last_saved_volumes[container] = volume
                    
                    # Add to status items with 2 decimal places
                    status_line = f"{container}: {volume:.2f} mL"
                    if amount_used is not None and amount_used > 0:
                        status_line += f", Used: {amount_used:.2f} mL"
                    
                    log_message(status_line)
                    
                    current_reading[container] = {
                        "distance_cm": round(distance, 2),  # Round to 2 decimal places
                        "remaining_volume_ml": round(volume, 2) if volume is not None else None
                    }
                
                previous_volumes[container] = volume
            
            # Only save data if a significant change is detected
            if significant_change_detected:
                reading_doc = {
                    "reading": reading_count,
                    "timestamp": timestamp,
                    "data": current_reading
                }
                save_data(reading_doc)
                log_message("Significant change detected - Data saved")
            
            # Display options menu periodically
            if current_time - last_display_time >= 5:
                display_options()
                last_display_time = current_time
            
            # Check for keyboard input (non-blocking)
            if select.select([sys.stdin], [], [], 0)[0]:
                choice = sys.stdin.readline().strip()
                if choice == "1":
                    log_message("Manual refresh triggered")
                    last_display_time = current_time
                    # Force save on manual refresh
                    reading_doc = {
                        "reading": reading_count,
                        "timestamp": timestamp,
                        "data": current_reading,
                        "manual_refresh": True
                    }
                    save_data(reading_doc)
                elif choice == "2":
                    log_message("Returning to main menu...")
                    break
            
            # Wait for specified time before next reading
            time.sleep(delay_between_readings)
            
    except KeyboardInterrupt:
        log_message("\nMonitoring stopped. Returning to menu...")

def main():
    """Main CLI menu function."""
    try:
        while True:
            print("\n" + "="*80)
            print("╔═══════════════════════════════════════════════════╗")
            print("║              SMART RESTROOM SYSTEM                ║")
            print("║                DISPENSER MODULE                   ║")
            print("╚═══════════════════════════════════════════════════╝")
            print("="*80)
            print("1. Start the Module")
            print("2. Exit the Program")
            
            choice = input("\nEnter your choice (1-2): ")
            
            if choice == "1":
                start_monitoring()
            elif choice == "2":
                log_message("Exiting program...")
                break
            else:
                print("Invalid choice. Please select 1 or 2.")
    except Exception as e:
        log_message(f"\nAn error occurred: {e}")
    finally:
        # Cleanup GPIO pins and close chip
        for pin in triggers + echos:
            lgpio.gpio_free(h, pin)
        lgpio.gpiochip_close(h)
        if client:
            client.close()

if __name__ == "__main__":
    log_message("Initializing Dispenser Module...")
    main()