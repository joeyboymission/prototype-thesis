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
DATA_DIR = "local-data"
JSON_FILE = os.path.join(DATA_DIR, "occupancy-data.json")
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

def load_visitor_count():
    """Load the last visitor count from database"""
    global visitor_count, current_state, current_start_time, current_visitor_id
    
    # Try MongoDB first if available
    if mongo_collection is not None:
        try:
            # Find the highest visitor_id in MongoDB
            latest = mongo_collection.find_one(
                {"type": "visit"}, 
                sort=[("visitor_id", -1)]
            )
            
            if latest:
                visitor_count = latest.get("visitor_id", 0)
                
                # Check if there's an ongoing visit (no end_time)
                ongoing = mongo_collection.find_one({
                    "type": "visit",
                    "end_time": None
                })
                
                if ongoing:
                    current_state = STATE_OCCUPIED
                    current_visitor_id = ongoing.get("visitor_id")
                    # Convert ISO string to timestamp if needed
                    start_time_str = ongoing.get("start_time")
                    if start_time_str:
                        current_start_time = datetime.datetime.fromisoformat(
                            start_time_str.replace(".000000", "")
                        ).timestamp()
                
                log_message(f"Loaded visitor count from MongoDB: {visitor_count}")
                if current_state == STATE_OCCUPIED:
                    log_message(f"Ongoing visit detected for visitor ID: {current_visitor_id}")
                return True
                
        except Exception as e:
            log_message(f"Error loading from MongoDB: {e}")
    
    # Fallback to local storage
    try:
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
                data = json.load(f)
                
                if isinstance(data, list) and len(data) > 0:
                    # Find highest visitor_id
                    visitor_ids = [entry.get("visitor_id", 0) for entry in data if "visitor_id" in entry]
                    visitor_count = max(visitor_ids) if visitor_ids else 0
                    
                    # Find ongoing visit
                    ongoing = [entry for entry in data if entry.get("end_time") is None]
                    if ongoing and len(ongoing) > 0:
                        current_state = STATE_OCCUPIED
                        current_visitor_id = ongoing[0].get("visitor_id")
                        start_time_str = ongoing[0].get("start_time")
                        if start_time_str:
                            current_start_time = datetime.datetime.fromisoformat(
                                start_time_str.replace(".000000", "")
                            ).timestamp()
                            
                    log_message(f"Loaded visitor count from local storage: {visitor_count}")
                    if current_state == STATE_OCCUPIED:
                        log_message(f"Ongoing visit detected for visitor ID: {current_visitor_id}")
                    return True
                
    except Exception as e:
        log_message(f"Error loading from local file: {e}")
    
    # If no data found, start from zero
    visitor_count = 0
    log_message("No previous data found, starting with visitor count: 0")
    return False

def save_visit_data(entry):
    """Save visit data to both local and MongoDB storage"""
    # Format timestamps in ISO format
    formatted_entry = entry.copy()
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
    
    # Save to local file
    try:
        # Read existing data
        existing_data = []
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
                existing_data = json.load(f)
        
        # Append new entry
        existing_data.append(formatted_entry)
        
        # Write back to file
        with open(JSON_FILE, 'w') as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        
        log_message("Data saved to local storage")
        local_saved = True
    except Exception as e:
        log_message(f"Error saving to local storage: {e}")
        local_saved = False
    
    # Save to MongoDB if available
    mongo_saved = False
    if mongo_collection is not None:
        try:
            mongo_collection.insert_one(formatted_entry)
            log_message("Data saved to MongoDB")
            mongo_saved = True
        except Exception as e:
            log_message(f"Error saving to MongoDB: {e}")
    
    # Return overall success
    return local_saved or mongo_saved

def record_entry():
    """Record a new visitor entry"""
    global visitor_count, current_visitor_id, current_start_time, current_state
    
    visitor_count += 1
    current_visitor_id = visitor_count
    current_time = time.time()
    current_start_time = current_time
    current_state = STATE_OCCUPIED
    
    # Create visit record
    entry = {
        "type": "visit",
        "visitor_id": current_visitor_id,
        "start_time": datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.000000"),
        "end_time": None,
        "duration": None
    }
    
    # Save data
    save_visit_data(entry)
    
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
    entry = {
        "type": "visit",
        "visitor_id": current_visitor_id,
        "start_time": datetime.datetime.fromtimestamp(current_start_time).strftime("%Y-%m-%dT%H:%M:%S.000000"),
        "end_time": datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.000000"),
        "duration": int(duration)
    }
    
    # Save data
    save_visit_data(entry)
    
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
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
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

def signal_handler(sig, frame):
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
    
    # Load previous data
    load_visitor_count()
    
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
