#!/usr/bin/env python3
import time
import os
import json
import lgpio
import signal
import sys
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

# Configuration
GPIO_CHIP = 0
TRIGGERS = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
ECHOS = [8, 10, 13, 15]     # GPIO pins for ultrasonic echos
READING_INTERVAL = 5        # Seconds between readings
SIGNIFICANT_CHANGE_THRESHOLD = 10.0  # Save data when volume changes by this amount (ml)

# MongoDB settings
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

# Local storage settings
DATA_DIR = "local-data"
JSON_FILE = os.path.join(DATA_DIR, "dispenser-data.json")

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
mongo_collection = None   # MongoDB collection
reading_counter = 0       # Reading counter
previous_volumes = {}     # Previous volume readings
last_saved_volumes = {}   # Last saved volume readings
running = True            # Flag to control the main loop

def get_timestamp():
    """Return formatted timestamp string [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    """Print a message with timestamp"""
    print(f"{get_timestamp()} {message}")

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

def connect_to_mongodb():
    """Connect to MongoDB database"""
    global mongo_client, mongo_collection
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
        
    try:
        log_message("Connecting to MongoDB...")
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')  # Test connection
        
        db = mongo_client['Smart_Cubicle']
        mongo_collection = db['dispenser_resource']
        
        log_message("Connected to MongoDB successfully!")
        return True
    except Exception as e:
        log_message(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
        mongo_client = None
        mongo_collection = None
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

def load_last_reading():
    """Load the last reading from database to continue counter"""
    global reading_counter
    
    log_message("Checking for previous readings...")
    
    # Try MongoDB first if available
    if mongo_collection is not None:
        try:
            # Find highest reading number
            last_record = mongo_collection.find_one(sort=[("reading", -1)])
            if last_record and "reading" in last_record:
                reading_counter = last_record["reading"]
                log_message(f"Loaded reading counter from MongoDB: {reading_counter}")
                return True
        except Exception as e:
            log_message(f"Error loading from MongoDB: {e}")
    
    # Try local storage if MongoDB failed or not available
    try:
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    # Find highest reading number
                    readings = [entry.get("reading", 0) for entry in data]
                    if readings:
                        reading_counter = max(readings)
                        log_message(f"Loaded reading counter from local storage: {reading_counter}")
                        return True
    except Exception as e:
        log_message(f"Error loading from local storage: {e}")
    
    # If no data found, start from zero
    reading_counter = 0
    log_message("No previous readings found, starting with reading counter: 0")
    return False

def save_data(data):
    """Save data to local JSON file and MongoDB if available"""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
    
    # Format data for storage
    formatted_data = {
        "reading": data["reading"],
        "timestamp": data["timestamp"],
        "data": {
            "CONT1": {
                "distance_cm": round(data["data"]["CONT1"]["distance_cm"], 2),
                "previous_volume_ml": round(data["data"]["CONT1"]["previous_volume_ml"], 2),
                "remaining_volume_ml": round(data["data"]["CONT1"]["remaining_volume_ml"], 2)
            },
            "CONT2": {
                "distance_cm": round(data["data"]["CONT2"]["distance_cm"], 2),
                "previous_volume_ml": round(data["data"]["CONT2"]["previous_volume_ml"], 2),
                "remaining_volume_ml": round(data["data"]["CONT2"]["remaining_volume_ml"], 2)
            },
            "CONT3": {
                "distance_cm": round(data["data"]["CONT3"]["distance_cm"], 2),
                "previous_volume_ml": round(data["data"]["CONT3"]["previous_volume_ml"], 2),
                "remaining_volume_ml": round(data["data"]["CONT3"]["remaining_volume_ml"], 2)
            },
            "CONT4": {
                "distance_cm": round(data["data"]["CONT4"]["distance_cm"], 2),
                "previous_volume_ml": round(data["data"]["CONT4"]["previous_volume_ml"], 2),
                "remaining_volume_ml": round(data["data"]["CONT4"]["remaining_volume_ml"], 2)
            }
        }
    }
    
    # Save to local storage
    try:
        # Read existing data
        existing_data = []
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                log_message("Warning: Existing file corrupt, creating new file")
        
        # Append new reading
        existing_data.append(formatted_data)
        
        # Use atomic write to prevent corruption
        temp_file = JSON_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, JSON_FILE)
        
        log_message("Data saved to local storage")
        local_saved = True
    except Exception as e:
        log_message(f"Error saving to local storage: {e}")
        local_saved = False
    
    # Save to MongoDB if available
    if mongo_collection is not None:
        try:
            mongo_collection.insert_one(formatted_data)
            log_message("Data also saved to MongoDB")
            mongo_saved = True
        except Exception as e:
            log_message(f"Error saving to MongoDB: {e}")
            mongo_saved = False
    else:
        mongo_saved = False
    
    # Report overall status
    if local_saved and mongo_saved:
        log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
    elif local_saved:
        log_message("Status: DATA SAVED TO LOCAL ONLY")
    else:
        log_message("Status: FAILED TO SAVE DATA")
        
    return local_saved or mongo_saved

def signal_handler(sig, frame):
    """Handle Ctrl+C to exit cleanly"""
    global running
    print("\nStopping...")
    running = False

def perform_system_check():
    """Test all system components"""
    log_message("Performing system check...")
    
    # Check GPIO
    gpio_ok = setup_gpio()
    if gpio_ok:
        log_message("✓ GPIO initialized")
    else:
        log_message("✗ GPIO initialization failed")
        return False
    
    # Check sensors
    sensors_ok = True
    log_message("Testing ultrasonic sensors...")
    for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
        distance = measure_distance(trigger, echo)
        if distance is not None and 0 < distance < 400:  # Valid range: 0-400cm
            log_message(f"✓ SONIC{i+1} online - distance: {distance:.2f} cm")
        else:
            log_message(f"✗ SONIC{i+1} offline or out of range")
            sensors_ok = False
    
    # Check MongoDB
    mongodb_ok = connect_to_mongodb()
    
    # Check local storage
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "test.tmp"), "w") as f:
            f.write("test")
        os.remove(os.path.join(DATA_DIR, "test.tmp"))
        log_message("✓ Local storage accessible")
        storage_ok = True
    except Exception as e:
        log_message(f"✗ Local storage error: {e}")
        storage_ok = False
    
    # Overall result
    if gpio_ok and sensors_ok and (mongodb_ok or storage_ok):
        log_message("System check: PASSED")
        return True
    else:
        if not sensors_ok:
            log_message("WARNING: Some sensors are not responding. System may not function properly.")
        if not mongodb_ok and not storage_ok:
            log_message("ERROR: No storage available. Cannot continue.")
            return False
        log_message("System check: PASSED WITH WARNINGS")
        return True

def start_monitoring():
    """Main function to monitor dispenser containers"""
    global reading_counter, previous_volumes, last_saved_volumes, running
    
    # Setup signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Perform system check
    if not perform_system_check():
        log_message("Critical error: System check failed")
        return
    
    # Load last reading counter
    load_last_reading()
    
    log_message("Detecting the initial volume for each container...")
    
    # Initial readings
    initial_readings = []
    for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
        container = f"CONT{i+1}"
        distance = measure_distance(trigger, echo)
        volume = calculate_volume(container, distance)
        
        # Store as both previous and last saved
        previous_volumes[container] = volume
        last_saved_volumes[container] = volume
        
        # Add to display
        if distance is not None and volume is not None:
            initial_readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml")
        else:
            initial_readings.append(f"{container}: ERROR")
    
    # Display initial readings
    log_message(" | ".join(initial_readings))
    log_message("The sensors are ready!")
    
    # Main monitoring loop
    log_message("Starting continuous monitoring. Press Ctrl+C to stop.")
    last_reading_time = time.time()
    
    try:
        while running:
            current_time = time.time()
            
            # Check if it's time for a new reading
            if current_time - last_reading_time >= READING_INTERVAL:
                reading_counter += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                significant_change = False
                current_readings = []
                
                # Read all containers
                current_data = {
                    "reading": reading_counter,
                    "timestamp": timestamp,
                    "data": {}
                }
                
                for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
                    container = f"CONT{i+1}"
                    distance = measure_distance(trigger, echo)
                    volume = calculate_volume(container, distance)
                    
                    # Check if this is a significant change
                    prev_volume = previous_volumes.get(container, 0)
                    last_saved = last_saved_volumes.get(container, 0)
                    
                    if volume is not None and last_saved is not None:
                        if abs(volume - last_saved) >= SIGNIFICANT_CHANGE_THRESHOLD:
                            significant_change = True
                            last_saved_volumes[container] = volume
                    
                    # Format for display
                    if distance is not None and volume is not None:
                        current_readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml")
                    else:
                        current_readings.append(f"{container}: ERROR")
                    
                    # Store data
                    current_data["data"][container] = {
                        "distance_cm": distance if distance is not None else 0,
                        "previous_volume_ml": prev_volume if prev_volume is not None else 0,
                        "remaining_volume_ml": volume if volume is not None else 0
                    }
                    
                    # Update previous volume
                    previous_volumes[container] = volume
                
                # Display current readings
                log_message(" | ".join(current_readings))
                
                # Save data if significant change detected
                if significant_change:
                    save_data(current_data)
                
                last_reading_time = current_time
                
            # Small delay to prevent CPU overuse
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        log_message("Monitoring interrupted by user")
    finally:
        # Save final reading regardless of changes
        log_message("Saving final reading before exit...")
        
        # Create final reading data
        final_data = {
            "reading": reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {}
        }
        
        for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
            container = f"CONT{i+1}"
            distance = measure_distance(trigger, echo)
            volume = calculate_volume(container, distance)
            prev_volume = previous_volumes.get(container, 0)
            
            final_data["data"][container] = {
                "distance_cm": distance if distance is not None else 0,
                "previous_volume_ml": prev_volume if prev_volume is not None else 0,
                "remaining_volume_ml": volume if volume is not None else 0
            }
        
        save_data(final_data)

def main():
    """Main program entry point"""
    try:
        # Print welcome message
        print("\n" + "="*80)
        print("╔═══════════════════════════════════════════════════╗")
        print("║              SMART RESTROOM SYSTEM                ║")
        print("║                DISPENSER MODULE                   ║")
        print("╚═══════════════════════════════════════════════════╝")
        print("="*80)
        
        log_message("Dispenser Module Starting")
        
        # Create data directory
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Start monitoring
        start_monitoring()
        
    except Exception as e:
        log_message(f"Unhandled error: {e}")
    finally:
        # Clean up
        if h is not None:
            for pin in TRIGGERS + ECHOS:
                lgpio.gpio_free(h, pin)
            lgpio.gpiochip_close(h)
        
        if mongo_client is not None:
            mongo_client.close()
            
        log_message("Dispenser Module Stopped")

if __name__ == "__main__":
    main()
