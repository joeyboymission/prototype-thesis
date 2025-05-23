#!/usr/bin/env python3
import time
import os
import json
import lgpio
import signal
import sys
from datetime import datetime
from bson import ObjectId

# Try to import MongoDB libraries, but have a fallback if not available
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

# Configuration
GPIO_CHIP = 0
TRIGGERS = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
ECHOS = [8, 10, 13, 15]     # GPIO pins for ultrasonic echos
READING_INTERVAL = 5        # Seconds between readings
SIGNIFICANT_CHANGE_THRESHOLD = 10.0  # Save data when volume changes by this amount (ml)

# MongoDB settings
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

# Local storage settings
DATA_DIR = "/home/admin/Documents/local-data"
LOCAL_FILE = os.path.join(DATA_DIR, "dispenser-data.json")

# Calibration data for each container
CALIBRATION_DATA = {
    "CONT1": {"full": 2.84, "empty": 12.67},
    "CONT2": {"full": 2.37, "empty": 12.21},
    "CONT3": {"full": 2.23, "empty": 12.33},
    "CONT4": {"full": 2.91, "empty": 12.88}
}

# Global variables
h = None                  # GPIO handle
mongo_client = None       # MongoDB client
mongo_db = None           # MongoDB database
mongo_collection = None   # MongoDB collection
running = True            # Flag to control the main loop
reading_counter = 0       # Reading counter
previous_readings = None  # Previous readings

def get_data_template():
    """Initialize data format for a dispenser reading"""
    return {
        "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "reading": reading_counter + 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": {
            "CONT1": {
                "distance_cm": 0.00,
                "previous_volume_ml": 0.00,
                "remaining_volume_ml": 0.00
            },
            "CONT2": {
                "distance_cm": 0.00,
                "previous_volume_ml": 0.00,
                "remaining_volume_ml": 0.00
            },
            "CONT3": {
                "distance_cm": 0.00,
                "previous_volume_ml": 0.00,
                "remaining_volume_ml": 0.00
            },
            "CONT4": {
                "distance_cm": 0.00,
                "previous_volume_ml": 0.00,
                "remaining_volume_ml": 0.00
            }
        }
    }

def log_sensor_readings(data):
    """Log current sensor readings in the required format"""
    readings = []
    for i in range(1, 5):
        container = f"CONT{i}"
        dist = data["data"][container]["distance_cm"]
        vol = data["data"][container]["remaining_volume_ml"]
        readings.append(f"{container}: {dist:.2f} cm {vol:.2f} ml")
    log_message(" | ".join(readings))

def initialize_storage():
    """Initialize storage system and check existing data"""
    global reading_counter
    
    log_message("Checking the connection to Database...")
    
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
                    reading_counter = latest["reading"]
                    log_message(f"Found {len(data)} existing records in local storage")
                    log_message(f"Latest reading number: {reading_counter}")
        except Exception as e:
            log_message(f"Error reading local data file: {e}")
    else:
        log_message("Local data file does not exist, will create when first data is saved")
    
    return True

def connect_to_mongodb():
    """Connect to MongoDB and restore latest state"""
    global mongo_client, mongo_db, mongo_collection, reading_counter
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
    
    try:
        log_message("Checking the connection to Database...")
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.admin.command('ping')
        
        mongo_db = mongo_client["Smart_Cubicle"]
        mongo_collection = mongo_db["dispenser_resource"]  # Using the correct collection name
        
        # Check if collection exists and has data
        if mongo_collection.count_documents({}) > 0:
            log_message("Found existing data in remote database")
            latest_doc = mongo_collection.find_one(sort=[("timestamp", -1)])
            if latest_doc:
                reading_counter = latest_doc.get("reading", 0)
                log_message(f"Latest remote reading number: {reading_counter}")
        
        log_message("Database Connected Successfully!")
        return True
    except Exception as e:
        log_message(f"MongoDB connection error: {e}")
        mongo_client = None
        mongo_db = None
        mongo_collection = None
        return False

def save_to_mongodb(data):
    """Save data to MongoDB"""
    if not MONGODB_AVAILABLE or mongo_collection is None:
        return False
    
    try:
        mongo_collection.insert_one(data)
        return True
    except Exception as e:
        log_message(f"Error saving to MongoDB: {e}")
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
            json.dump(existing_data, f, indent=2)
        os.replace(temp_file, LOCAL_FILE)
        
        return True
    except Exception as e:
        log_message(f"Local storage error: {e}")
        return False

def save_dispenser_data(dispenser_data):
    """Save dispenser data to both MongoDB and local storage"""
    mongodb_success = save_to_mongodb(dispenser_data)
    local_success = save_to_local_storage(dispenser_data)
    
    return mongodb_success or local_success

def should_save_reading(current_reading):
    """Determine if the current reading should be saved based on changes"""
    if not previous_readings:
        return True
    
    # Minimum volume change threshold (in ml) to consider significant
    MIN_VOLUME_CHANGE = 10.0  # Only save if volume changes by at least 10ml
    
    for container in ["CONT1", "CONT2", "CONT3", "CONT4"]:
        prev_vol = previous_readings["data"][container]["remaining_volume_ml"]
        curr_vol = current_reading["data"][container]["remaining_volume_ml"]
        
        # Calculate absolute change in volume
        volume_change = abs(prev_vol - curr_vol)
        
        # Only save if the change is significant (more than MIN_VOLUME_CHANGE)
        if volume_change >= MIN_VOLUME_CHANGE:
            # Get the whole numbers
            prev_whole = int(prev_vol)
            curr_whole = int(curr_vol)
            
            # Only save if whole numbers are different
            if prev_whole != curr_whole:
                return True
    
    return False

def log_message(message):
    """Log a message with timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def setup_gpio():
    """Initialize GPIO for ultrasonic sensors"""
    global h
    
    try:
        log_message("Initializing GPIO...")
        h = lgpio.gpiochip_open(GPIO_CHIP)
        
        # Setup trigger pins as output
        for trigger in TRIGGERS:
            lgpio.gpio_claim_output(h, trigger)
            
        # Setup echo pins as input
        for echo in ECHOS:
            lgpio.gpio_claim_input(h, echo)
            
        log_message("GPIO initialized successfully")
        return True
    except Exception as e:
        log_message(f"Error initializing GPIO: {e}")
        return False

def measure_distance(trigger, echo, num_measurements=5):
    """Measure distance using ultrasonic sensor with multiple readings for accuracy"""
    distances = []
    
    for _ in range(num_measurements):
        lgpio.gpio_write(h, trigger, 1)  # Trigger high
        time.sleep(0.00001)              # 10us pulse
        lgpio.gpio_write(h, trigger, 0)  # Trigger low
        
        # Wait for echo to go high
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:  # Timeout after 0.5s
                return None
        
        # Wait for echo to go low
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:  # Timeout after 0.5s
                return None
        
        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound: 343 m/s -> 17150 cm/s
        distances.append(round(distance, 2))
        
        time.sleep(0.05)  # Short delay between measurements
    
    # Remove outliers and average
    if distances:
        if len(distances) > 2:
            # Remove min and max values
            distances.remove(min(distances))
            distances.remove(max(distances))
        
        # Average the remaining values
        return sum(distances) / len(distances)
    
    return None

def calculate_volume(container, distance):
    """Calculate remaining volume based on distance measurement"""
    if distance is None:
        return None
        
    full_distance = CALIBRATION_DATA[container]["full"]
    empty_distance = CALIBRATION_DATA[container]["empty"]
    
    if distance <= full_distance:
        return 425.0  # Full container (ml)
    elif distance >= empty_distance:
        return 0.0    # Empty container (ml)
    else:
        # Linear interpolation between full and empty
        total_distance_range = empty_distance - full_distance
        distance_from_full = distance - full_distance
        volume_fraction = 1 - (distance_from_full / total_distance_range)
        volume = 425.0 * volume_fraction
        return round(volume, 2)

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    log_message("Shutting down...")
    
    # Save final reading regardless of changes
    if previous_readings:
        save_dispenser_data(previous_readings)
    
    running = False

def main():
    global running, reading_counter, previous_readings
    
    try:
        # Setup signal handler for Ctrl+C
        signal.signal(signal.SIGINT, signal_handler)
        
        log_message("=== Dispenser Module Starting ===")
        
        # Connect to MongoDB first
        mongodb_connected = connect_to_mongodb()
        if not mongodb_connected:
            log_message("No MongoDB connection. Using local storage only.")
        
        # Initialize storage system
        if not initialize_storage():
            log_message("Failed to initialize storage system")
            return
        
        # Initialize GPIO
        if not setup_gpio():
            log_message("Failed to initialize GPIO")
            return
        
        log_message("Detecting the initial volume for each container...")
        
        # Create initial data template
        data = get_data_template()
        
        # Read all containers
        for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
            container = f"CONT{i+1}"
            distance = measure_distance(trigger, echo)
            volume = calculate_volume(container, distance)
            
            # Store data with 2 decimal precision
            data["data"][container]["distance_cm"] = round(distance if distance is not None else 0.00, 2)
            data["data"][container]["remaining_volume_ml"] = round(volume if volume is not None else 0.00, 2)
            if previous_readings and previous_readings["data"][container]["remaining_volume_ml"] is not None:
                data["data"][container]["previous_volume_ml"] = round(previous_readings["data"][container]["remaining_volume_ml"], 2)
            else:
                data["data"][container]["previous_volume_ml"] = data["data"][container]["remaining_volume_ml"]
        
        # Log initial readings
        log_sensor_readings(data)
        log_message("The sensors are ready!")
        
        while running:
            # Create data template
            data = get_data_template()
            
            # Read all containers
            for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
                container = f"CONT{i+1}"
                distance = measure_distance(trigger, echo)
                volume = calculate_volume(container, distance)
                
                # Store data with 2 decimal precision
                data["data"][container]["distance_cm"] = round(distance if distance is not None else 0.00, 2)
                data["data"][container]["remaining_volume_ml"] = round(volume if volume is not None else 0.00, 2)
                if previous_readings and previous_readings["data"][container]["remaining_volume_ml"] is not None:
                    data["data"][container]["previous_volume_ml"] = round(previous_readings["data"][container]["remaining_volume_ml"], 2)
                else:
                    data["data"][container]["previous_volume_ml"] = data["data"][container]["remaining_volume_ml"]
            
            # Always log the readings to show current state
            log_sensor_readings(data)
            
            # Only save if there's a significant whole number change
            if should_save_reading(data):
                save_dispenser_data(data)
                log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
            
            # Update previous readings
            previous_readings = data
            
            # Wait for the next reading interval
            time.sleep(READING_INTERVAL)
            
    except Exception as e:
        log_message(f"Error in main loop: {e}")
    finally:
        # Cleanup
        if h is not None:
            for pin in TRIGGERS + ECHOS:
                try:
                    lgpio.gpio_free(h, pin)
                except:
                    pass
            try:
                lgpio.gpiochip_close(h)
            except:
                pass
        
        if mongo_client:
            try:
                mongo_client.close()
            except:
                pass
        
        log_message("Dispenser Module Stopped")

if __name__ == "__main__":
    main()
