#!/usr/bin/env python3
import time
import json
import os
import signal
import sys
import datetime
import lgpio
from collections import deque

# Try to import MongoDB libraries
try:
    from pymongo import MongoClient
    from bson import ObjectId
    
    # MongoDB ObjectId JSON encoder
    class MongoJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ObjectId):
                return str(obj)
            return super().default(obj)
    
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: MongoDB not available. Using local storage only.")
    
    # Fallback encoder
    class MongoJSONEncoder(json.JSONEncoder):
        pass

# Configuration
SENSOR_PIN = 17         # E18-D80NK proximity sensor
BUZZER_PIN = 27         # Buzzer for audio feedback
DATA_DIR = "/home/admin/Documents/local-data"
LOCAL_FILE = os.path.join(DATA_DIR, "occupancy-data.json")
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
DEBOUNCE_TIME = 0.5     # 500ms debounce for sensor
SHORT_BEEP = 0.2        # 200ms
LONG_BEEP = 1.0         # 1s

# States
STATE_VACANT = "Vacant"
STATE_OCCUPIED = "Occupied"

# Global variables
current_state = STATE_VACANT
visitor_count = 0
current_visitor_id = None
current_start_time = None
last_state_change_time = time.time()
last_sensor_state = None
log_queue = deque(maxlen=10)  # Keep last 10 log messages
mongo_collection = None
mongo_client = None
running = True          # Flag for main loop control

# GPIO setup
chip = None

def get_timestamp():
    """Return formatted timestamp string [YYYY-MM-DD HH:MM:SS]"""
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    """Print a message with timestamp and add to log queue"""
    timestamped_msg = f"{get_timestamp()} {message}"
    log_queue.append(timestamped_msg)
    print(timestamped_msg)

def setup_gpio():
    """Initialize GPIO connections"""
    global chip, last_sensor_state
    
    try:
        log_message("Initializing GPIO...")
        chip = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(chip, SENSOR_PIN, lgpio.SET_PULL_UP)
        lgpio.gpio_claim_output(chip, BUZZER_PIN)
        lgpio.gpio_write(chip, BUZZER_PIN, 0)  # Ensure buzzer is off
        last_sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)
        log_message("GPIO initialized successfully")
        return True
    except Exception as e:
        log_message(f"Error initializing GPIO: {e}")
        return False

def connect_to_mongodb():
    """Connect to MongoDB database"""
    global mongo_client, mongo_collection
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB not available, using local storage only")
        return False
    
    try:
        log_message("Connecting to MongoDB...")
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')  # Test connection
        
        db = mongo_client['Smart_Cubicle']
        mongo_collection = db['occupancy']
        log_message("Connected to MongoDB successfully")
        return True
    except Exception as e:
        log_message(f"MongoDB connection error: {e}")
        mongo_collection = None
        mongo_client = None
        return False

def beep_buzzer(duration):
    """Control the buzzer for a specified duration"""
    try:
        if chip is not None:
            lgpio.gpio_write(chip, BUZZER_PIN, 1)
            time.sleep(duration)
            lgpio.gpio_write(chip, BUZZER_PIN, 0)
    except Exception as e:
        log_message(f"Error controlling buzzer: {e}")

def double_beep():
    """Perform a double beep pattern"""
    beep_buzzer(SHORT_BEEP)
    time.sleep(SHORT_BEEP)
    beep_buzzer(SHORT_BEEP)

def format_duration(seconds):
    """Format duration in seconds to minutes and seconds"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}sec"

def initialize_storage():
    """Initialize storage system and check existing data"""
    global current_visitor_id, visitor_count
    
    log_message("Checking storage system...")
    
    # Create local data directory if it doesn't exist
    if not os.path.exists(DATA_DIR):
        log_message(f"Creating local data directory: {DATA_DIR}")
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception as e:
            log_message(f"Error creating data directory: {e}")
            return False
    
    # Check local file
    if os.path.exists(LOCAL_FILE):
        try:
            with open(LOCAL_FILE, "r") as f:
                data = json.load(f)
                if data:
                    latest = data[-1]
                    current_visitor_id = latest["visitor_id"]
                    visitor_count = len(data)
                    log_message(f"Found {len(data)} existing records in local storage")
                    log_message(f"Latest local visitor ID: {current_visitor_id}")
        except Exception as e:
            log_message(f"Error reading local data file: {e}")
    else:
        log_message("Local data file does not exist, will create when first data is saved")
    
    return True

def connect_to_mongodb():
    """Connect to MongoDB and restore latest state"""
    global mongo_client, mongo_collection, current_visitor_id, visitor_count
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
    
    try:
        log_message("Connecting to MongoDB...")
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.admin.command('ping')
        
        db = mongo_client["Smart_Cubicle"]
        mongo_collection = db["occupancy"]
        
        # Check if collection exists and has data
        if mongo_collection.count_documents({}) > 0:
            log_message("Found existing data in remote database")
            latest_doc = mongo_collection.find_one(sort=[("visitor_id", -1)])
            if latest_doc:
                current_visitor_id = latest_doc["visitor_id"]
                visitor_count = mongo_collection.count_documents({})
                log_message(f"Latest remote visitor ID: {current_visitor_id}")
                log_message(f"Total visitors in remote DB: {visitor_count}")
        
        log_message("Connected to MongoDB successfully!")
        return True
    except Exception as e:
        log_message(f"MongoDB connection error: {e}")
        mongo_client = None
        mongo_collection = None
        return False

def save_to_local_storage(data):
    """Save data to local JSON file"""
    try:
        # Ensure the directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        existing_data = []
        if os.path.exists(LOCAL_FILE):
            try:
                with open(LOCAL_FILE, "r") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                log_message("Creating new data file (existing file corrupt)")
        
        # Ensure data has the correct format
        if not isinstance(existing_data, list):
            existing_data = []
        
        existing_data.append(data)
        
        # Use atomic write to prevent corruption
        temp_file = LOCAL_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, LOCAL_FILE)
        
        return True
    except Exception as e:
        log_message(f"Local storage error: {e}")
        return False

def save_visitor_data(visitor_data):
    """Save visitor data to both MongoDB and local storage"""
    success = True
    
    if MONGODB_AVAILABLE and mongo_collection:
        try:
            mongo_collection.insert_one(visitor_data)
        except Exception as e:
            log_message(f"Error saving to MongoDB: {e}")
            success = False
    
    local_success = save_to_local_storage(visitor_data)
    if not local_success:
        success = False
    
    if success:
        log_message("DATA SAVED TO REMOTE AND LOCAL")
    else:
        log_message("ERROR SAVING DATA")
    
    return success

def get_data_template():
    """Initialize data format for a visitor record"""
    return {
        "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "type": "visit",
        "visitor_id": current_visitor_id + 1,
        "start_time": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
        "end_time": None,
        "duration": None
    }

def record_entry():
    """Record a new visitor entry"""
    global visitor_count, current_visitor_id, current_start_time, current_state
    
    visitor_count += 1
    current_visitor_id = visitor_count
    current_time = time.time()
    current_start_time = current_time
    current_state = STATE_OCCUPIED
    
    # Create visit record
    entry = get_data_template()
    
    # Save data
    save_visitor_data(entry)
    
    # Audio feedback
    double_beep()
    
    # Log status
    log_message(f"Visitor Count: {visitor_count} | Status: {current_state} | Visitor ID: {current_visitor_id}")

def record_exit():
    """Record visitor exit"""
    global current_state, current_start_time, current_visitor_id
    
    if current_state != STATE_OCCUPIED or current_start_time is None:
        log_message("Warning: Attempting to record exit but no active visitor")
        return
    
    current_time = time.time()
    duration = current_time - current_start_time
    current_state = STATE_VACANT
    
    # Create visit record with exit info
    entry = get_data_template()
    entry["visitor_id"] = current_visitor_id
    entry["start_time"] = datetime.datetime.fromtimestamp(current_start_time).strftime("%Y-%m-%dT%H:%M:%S.%f")
    entry["end_time"] = datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.%f")
    entry["duration"] = int(duration)
    
    # Save data
    save_visitor_data(entry)
    
    # Audio feedback
    beep_buzzer(LONG_BEEP)
    
    # Log status
    log_message(f"Visitor Count: {visitor_count} | Status: {current_state} | Duration: {format_duration(duration)}")
    
    # Reset current tracking variables
    current_start_time = None
    current_visitor_id = None

def display_status():
    """Display current status summary"""
    status = []
    status.append(f"Number of Visitor: {visitor_count}")
    status.append(f"Presence: {current_state}")
    status.append(f"Visitor ID: {current_visitor_id if current_state == STATE_OCCUPIED else 'None'}")
    
    # Calculate total visitors from JSON
    total = 0
    try:
        if os.path.exists(LOCAL_FILE):
            with open(LOCAL_FILE, 'r') as f:
                data = json.load(f)
                total = len(data)
    except:
        pass
    
    status.append(f"Total Number of Visitor: {total}")
    
    if current_state == STATE_OCCUPIED and current_start_time is not None:
        elapsed = time.time() - current_start_time
        status.append(f"Current Duration: {format_duration(elapsed)}")
    
    print("\n" + "-" * 40)
    for line in status:
        print(line)
    print("-" * 40)

def signal_handler(signum, frame):
    """Handle Ctrl+C to exit cleanly"""
    global running
    print("\nStopping...")
    running = False

def perform_system_check():
    """Perform system check on startup"""
    log_message("Performing system check...")
    
    # Check GPIO
    gpio_ok = setup_gpio()
    if gpio_ok:
        log_message("✓ GPIO initialized")
    else:
        log_message("✗ GPIO initialization failed")
    
    # Check MongoDB
    mongodb_ok = connect_to_mongodb()
    if mongodb_ok:
        log_message("✓ MongoDB connected")
    else:
        log_message("✗ MongoDB not available, using local storage")
    
    # Check local storage
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        log_message("✓ Local storage ready")
        storage_ok = True
    except Exception as e:
        log_message(f"✗ Local storage error: {e}")
        storage_ok = False
    
    # Overall check result
    if gpio_ok and (mongodb_ok or storage_ok):
        log_message("System check: PASSED")
        return True
    else:
        log_message("System check: FAILED - Some components not working")
        return False

def monitor_occupancy():
    """Main function to monitor occupancy state"""
    global current_state, last_sensor_state, last_state_change_time, running
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # System check
    if not perform_system_check():
        log_message("Critical error: System check failed")
        return
    
    # Initialize storage system
    if not initialize_storage():
        log_message("Failed to initialize storage system")
        return
    
    # Connect to MongoDB first
    mongodb_connected = connect_to_mongodb()
    if mongodb_connected:
        log_message("MongoDB connected. Data will be saved to remote and local storage.")
    else:
        log_message("No MongoDB connection. Data will be saved to local storage only.")
    
    # Display initial status
    display_status()
    
    log_message("Starting occupancy monitoring... (Press Ctrl+C to exit)")
    
    detection_start = None
    last_status_time = time.time()
    
    # Main monitoring loop
    while running:
        current_time = time.time()
        sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)
        
        # Handle debounced sensor state changes
        if (current_time - last_state_change_time) > DEBOUNCE_TIME and sensor_state != last_sensor_state:
            # State transition detection
            if current_state == STATE_VACANT and sensor_state == 0:
                # Beam broken while vacant - potential entry
                detection_start = current_time
            elif current_state == STATE_VACANT and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                # Beam restored while vacant after being broken - confirm entry
                if (current_time - detection_start) < 2:  # Ensure full cycle within 2s
                    record_entry()
                    last_state_change_time = current_time
                    detection_start = None
            elif current_state == STATE_OCCUPIED and sensor_state == 0:
                # Beam broken while occupied - potential exit
                detection_start = current_time
            elif current_state == STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                # Beam restored while occupied after being broken - confirm exit
                if (current_time - detection_start) < 2:
                    record_exit()
                    last_state_change_time = current_time
                    detection_start = None
                    
            last_sensor_state = sensor_state
        
        # Display status periodically
        if current_time - last_status_time >= 30:
            display_status()
            last_status_time = current_time
            
        # Small delay to prevent CPU overuse
        time.sleep(0.05)

def main():
    """Main program entry point"""
    try:
        log_message("=== Occupancy Module Starting ===")
        monitor_occupancy()
    except KeyboardInterrupt:
        log_message("Program interrupted by user")
    except Exception as e:
        log_message(f"Error: {e}")
    finally:
        # Clean up
        if chip is not None:
            lgpio.gpiochip_close(chip)
        if mongo_client is not None:
            mongo_client.close()
        log_message("=== Occupancy Module Stopped ===")

if __name__ == "__main__":
    main()
