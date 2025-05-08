#!/usr/bin/env python3
import time
import json
import os
import signal
import sys
from datetime import datetime
from collections import deque
import threading
from bson import ObjectId
import platform

# Check if we're running on Raspberry Pi for hardware-specific imports
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Try to import hardware-specific libraries
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("Warning: lgpio not available. Hardware features will be simulated.")

# Try to import MongoDB libraries
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

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

# Base module class for common functionality
class ModuleBase:
    def __init__(self, name):
        self.name = name
        self.running = False
        self.paused = False
        self.thread = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
    
    def start(self):
        with self.lock:
            if not self.running:
                self.running = True
                self.paused = False
                self.stop_event.clear()
                self.thread = threading.Thread(target=self.run)
                self.thread.daemon = True
                self.thread.start()
                print(f"{self.name} module started")
        return True
            else:
                print(f"{self.name} module is already running")
        return False

    def stop(self):
        with self.lock:
            if self.running:
                print(f"Stopping {self.name} module...")
                self.running = False
                self.stop_event.set()
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=2)
                print(f"{self.name} module stopped")
                return True
            else:
                print(f"{self.name} module is not running")
                return False
    
    def pause(self):
        with self.lock:
            if self.running:
                self.paused = not self.paused
                status = "paused" if self.paused else "resumed"
                print(f"{self.name} module {status}")
                return True
            else:
                print(f"{self.name} module is not running")
        return False
    
    def status(self):
        status_str = "stopped"
        if self.running:
            status_str = "paused" if self.paused else "running"
        return status_str
    
    def run(self):
        # To be implemented by subclasses
        pass

# Occupancy Module Implementation
class OccupancyModule(ModuleBase):
    def __init__(self):
        super().__init__("Occupancy")
        # Configuration
        self.GPIO_CHIP = 0
        
        # Use exact GPIO pins from pin-config.md
        self.PIR_PINS = [17]  # E18-D80NK Proximity Sensor: GPIO17 (Pin 11)
        self.BUZZER_PIN = 27  # Buzzer: GPIO27 (Pin 13)
        
        self.READING_INTERVAL = 1     # Seconds between readings
        
        # MongoDB settings
        self.MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
        
        # Local storage settings
        self.DATA_DIR = "/home/admin/Documents/local-data"
        self.LOCAL_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")
        
        # Cubicle state data
        self.cubicle_data = {
            f"CUB{i+1}": {
                "status": "VACANT",
                "occupied_time": None,
                "previous_status": None,
                "sensor_state": "DOWN",
                "last_change": None,
                "last_reading": time.time()
            } for i in range(3)
        }
        
        # Global variables
        self.h = None                  # GPIO handle
        self.mongo_client = None       # MongoDB client
        self.mongo_db = None           # MongoDB database
        self.mongo_collection = None   # MongoDB collection
        self.reading_counter = 0       # Reading counter
        self.log_queue = deque(maxlen=20)  # Keep last 20 log messages
        self.claimed_pins = []         # List of successfully claimed GPIO pins
        
        # If we're on Windows, adjust the paths
        if os.name == 'nt':
            self.DATA_DIR = "local-data"
            self.LOCAL_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")

    def get_data_template(self):
        """Initialize data format for an occupancy reading"""
    return {
            "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "CUB1": {
                    "status": "VACANT",
                    "occupied_time": None,
                    "previous_status": None
                },
                "CUB2": {
                    "status": "VACANT",
                    "occupied_time": None,
                    "previous_status": None
                },
                "CUB3": {
                    "status": "VACANT",
                    "occupied_time": None,
                    "previous_status": None
                }
            }
        }

    def log_sensor_readings(self, data):
        """Log current sensor readings in the required format"""
        readings = []
        for i in range(1, 4):
            cubicle = f"CUB{i}"
            status = data["data"][cubicle]["status"]
            occupied_time = data["data"][cubicle]["occupied_time"] or "N/A"
            readings.append(f"{cubicle}: {status} {occupied_time}")
        self.log_message(" | ".join(readings))

    def log_message(self, message):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)

    def initialize_storage(self):
        """Initialize storage system and check existing data"""
        self.log_message("Checking the connection to Database...")
        
        # Create local data directory if it doesn't exist
        if not os.path.exists(self.DATA_DIR):
            self.log_message(f"Creating local data directory: {self.DATA_DIR}")
            try:
                os.makedirs(self.DATA_DIR, exist_ok=True)
            except Exception as e:
                self.log_message(f"Error creating data directory: {e}")
                return False
        
        # Check local file
        if os.path.exists(self.LOCAL_FILE):
            try:
                with open(self.LOCAL_FILE, "r") as f:
                    data = json.load(f)
                    if data:
                        latest = data[-1]
                        self.reading_counter = latest["reading"]
                        self.log_message(f"Found {len(data)} existing records in local storage")
                        self.log_message(f"Latest reading number: {self.reading_counter}")
            except Exception as e:
                self.log_message(f"Error reading local data file: {e}")
        else:
            self.log_message("Local data file does not exist, will create when first data is saved")
        
        return True

    def connect_to_mongodb(self):
        """Connect to MongoDB and restore latest state"""
        global MONGODB_AVAILABLE
        
        if not MONGODB_AVAILABLE:
            self.log_message("MongoDB support not available, using local storage only.")
            return False
        
        try:
            self.log_message("Checking the connection to Database...")
            self.mongo_client = MongoClient(self.MONGO_URI, serverSelectionTimeoutMS=5000)
            # Test connection
            self.mongo_client.admin.command('ping')
            
            self.mongo_db = self.mongo_client["Smart_Cubicle"]
            self.mongo_collection = self.mongo_db["occupancy_resource"]  # Using the correct collection name
            
            # Check if collection exists and has data
            if self.mongo_collection.count_documents({}) > 0:
                self.log_message("Found existing data in remote database")
                latest_doc = self.mongo_collection.find_one(sort=[("timestamp", -1)])
                if latest_doc:
                    self.reading_counter = latest_doc.get("reading", 0)
                    self.log_message(f"Latest remote reading number: {self.reading_counter}")
            
            self.log_message("Database Connected Successfully!")
        return True
    except Exception as e:
            self.log_message(f"MongoDB connection error: {e}")
            self.mongo_client = None
            self.mongo_db = None
            self.mongo_collection = None
        return False

    def save_to_mongodb(self, data):
        """Save data to MongoDB"""
        if not MONGODB_AVAILABLE or self.mongo_collection is None:
        return False
    
        try:
            self.mongo_collection.insert_one(data)
            return True
        except Exception as e:
            self.log_message(f"Error saving to MongoDB: {e}")
            return False
    
    def save_to_local_storage(self, data):
        """Save data to local JSON file"""
    try:
            # Ensure the directory exists
            os.makedirs(self.DATA_DIR, exist_ok=True)
        
        existing_data = []
            if os.path.exists(self.LOCAL_FILE):
            try:
                    with open(self.LOCAL_FILE, "r") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                    self.log_message("Creating new data file (existing file corrupt)")
        
            # Ensure data has the correct format
        if not isinstance(existing_data, list):
            existing_data = []
        
            existing_data.append(data)
            
            # Use atomic write to prevent corruption
            temp_file = self.LOCAL_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_file, self.LOCAL_FILE)
            
            return True
        except Exception as e:
            self.log_message(f"Local storage error: {e}")
            return False

    def save_occupancy_data(self, occupancy_data):
        """Save occupancy data to both MongoDB and local storage"""
        mongodb_success = self.save_to_mongodb(occupancy_data)
        local_success = self.save_to_local_storage(occupancy_data)
        
        # Report overall status
    if mongodb_success and local_success:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
    elif local_success:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
    else:
            self.log_message("Status: FAILED TO SAVE DATA")
    
    return mongodb_success or local_success

    def should_save_reading(self, current_reading):
        """Determine if the current reading should be saved based on changes"""
        # Always save when occupancy changes
        for i in range(1, 4):
            cubicle = f"CUB{i}"
            if current_reading["data"][cubicle]["status"] != self.cubicle_data[cubicle]["previous_status"]:
                return True
        return False

    def setup_hardware(self):
        """Initialize GPIO for PIR sensors"""
        global LGPIO_AVAILABLE
        
        if not LGPIO_AVAILABLE:
            self.log_message("Running in simulation mode (lgpio not available)")
            return True
        
        try:
            self.log_message("Initializing GPIO...")
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            # Store pins that were successfully claimed
            self.claimed_pins = []
            
            # Try to claim each PIR pin, skipping any that are already in use
            for pir in self.PIR_PINS:
                try:
                    lgpio.gpio_claim_input(self.h, pir)
                    self.claimed_pins.append(pir)
                    self.log_message(f"Successfully claimed PIR sensor on GPIO{pir}")
    except Exception as e:
                    self.log_message(f"Could not claim PIR sensor on GPIO{pir}: {e}")
            
            # Check if we were able to claim at least some pins
            if self.claimed_pins:
                self.log_message(f"GPIO initialized with {len(self.claimed_pins)} pins")
                return True
            else:
                self.log_message("Failed to claim any GPIO pins")
                return False
        except Exception as e:
            self.log_message(f"Error initializing GPIO: {e}")
            return False
    
    def cleanup_hardware(self):
        """Clean up GPIO resources"""
        if not LGPIO_AVAILABLE:
        return
    
        if self.h is not None:
            # Only clean up pins that were successfully claimed
            for pin in self.claimed_pins:
                try:
                    lgpio.gpio_free(self.h, pin)
                    self.log_message(f"Released GPIO{pin}")
                except:
                    pass
                
            try:
                lgpio.gpiochip_close(self.h)
            except:
                pass
            
            self.h = None
            self.claimed_pins = []
            self.log_message("GPIO resources cleaned up")

    def read_pir_sensor(self, pir_index):
        """Read PIR sensor state (0=No motion, 1=Motion detected)"""
        if not LGPIO_AVAILABLE:
            # Simulate random occupancy states (20% chance of occupancy)
            import random
            return 1 if random.random() < 0.2 else 0
        
        # Check if we have a valid GPIO handle
        if self.h is None:
            return 0
        
        # Check if the pin is within range and was successfully claimed
        if 0 <= pir_index < len(self.PIR_PINS):
            pir_pin = self.PIR_PINS[pir_index]
            if pir_pin in self.claimed_pins:
                try:
                    return lgpio.gpio_read(self.h, pir_pin)
                except Exception as e:
                    self.log_message(f"Error reading PIR {pir_index} state: {e}")
            else:
                # Use simulation for pins we couldn't claim
                import random
                return 1 if random.random() < 0.2 else 0
        
        return 0

    def perform_post_check(self):
        """Perform Power-On Self Test to verify all components are working"""
        self.log_message("Performing system check...")
    
    # Check GPIO
        gpio_ok = self.setup_hardware()
    if gpio_ok:
            self.log_message("✓ GPIO initialized")
    else:
            self.log_message("✗ GPIO initialization failed")
            return False
        
        # Check sensors
        sensors_ok = True
        self.log_message("Testing PIR sensors...")
        for i in range(len(self.PIR_PINS)):
            sensor_value = self.read_pir_sensor(i)
            self.log_message(f"✓ PIR{i+1} reading: {sensor_value}")
            
            # Update sensor state
            self.cubicle_data[f"CUB{i+1}"]["sensor_state"] = "UP"
        
        # Check MongoDB connection
        db_status = "Offline"
        if self.mongo_collection:
            try:
                # Test connection by pinging
                if self.mongo_client:
                    self.mongo_client.admin.command('ping')
                    db_status = "Online"
                    self.log_message("✓ MongoDB connection active")
            except Exception as e:
                self.log_message(f"✗ MongoDB connection error: {e}")
                db_status = "Offline"
    else:
            self.log_message("✗ MongoDB not configured")
    
    # Check local storage
    try:
            os.makedirs(self.DATA_DIR, exist_ok=True)
            test_file = os.path.join(self.DATA_DIR, "test.tmp")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            self.log_message("✓ Local storage accessible")
        storage_ok = True
    except Exception as e:
            self.log_message(f"✗ Local storage error: {e}")
        storage_ok = False
    
        # Overall result
        if gpio_ok and storage_ok:
            self.log_message("System check: PASSED")
        return True
    else:
            if not db_status == "Online" and not storage_ok:
                self.log_message("ERROR: No storage available. Cannot continue.")
        return False
            self.log_message("System check: PASSED WITH WARNINGS")
            return True

    def get_cubicle_summary(self):
        """Get summary data for all cubicles"""
        return self.cubicle_data

    def get_recent_logs(self, count=10):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]

    def run(self):
        """Main function to monitor cubicle occupancy"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize occupancy hardware. Module not started.")
            self.running = False
        return
    
        # Perform system check
        self.perform_post_check()
        
        # Connect to MongoDB first
        mongodb_connected = self.connect_to_mongodb()
        if not mongodb_connected:
            self.log_message("No MongoDB connection. Using local storage only.")
        
    # Initialize storage system
        if not self.initialize_storage():
            self.log_message("Failed to initialize storage system")
        return
    
        self.log_message("Detecting the initial state for each cubicle...")
        
        # Initial readings
        readings_data = self.get_data_template()
        
        for i in range(len(self.PIR_PINS)):
            cubicle = f"CUB{i+1}"
            pir_state = self.read_pir_sensor(i)
            
            # Set status based on PIR reading
            new_status = "OCCUPIED" if pir_state else "VACANT"
            
            # Update cubicle data
            self.cubicle_data[cubicle]["status"] = new_status
            self.cubicle_data[cubicle]["previous_status"] = new_status
            self.cubicle_data[cubicle]["occupied_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == "OCCUPIED" else None
            self.cubicle_data[cubicle]["sensor_state"] = "UP"
            self.cubicle_data[cubicle]["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Store data for saving
            readings_data["data"][cubicle]["status"] = new_status
            readings_data["data"][cubicle]["occupied_time"] = self.cubicle_data[cubicle]["occupied_time"]
            readings_data["data"][cubicle]["previous_status"] = new_status
        
        # Log and save initial readings
        self.log_sensor_readings(readings_data)
        self.save_occupancy_data(readings_data)
        self.reading_counter += 1
        
        self.log_message("Occupancy monitoring ready")
    
    # Main monitoring loop
        last_reading_time = time.time()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check if it's time for a new reading
                    if current_time - last_reading_time >= self.READING_INTERVAL:
                        current_data = self.get_data_template()
                        data_changed = False
                        
                        for i in range(len(self.PIR_PINS)):
                            cubicle = f"CUB{i+1}"
                            pir_state = self.read_pir_sensor(i)
                            
                            # Get previous status
                            prev_status = self.cubicle_data[cubicle]["status"]
                            
                            # Determine new status
                            new_status = "OCCUPIED" if pir_state else "VACANT"
                            
                            # Check if status changed
                            status_changed = new_status != prev_status
                            
                            # If newly occupied, update occupied time
                            occupied_time = None
                            if new_status == "OCCUPIED":
                                if status_changed:
                                    occupied_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                else:
                                    occupied_time = self.cubicle_data[cubicle]["occupied_time"]
                            
                            # Update cubicle data
                            self.cubicle_data[cubicle]["previous_status"] = prev_status
                            self.cubicle_data[cubicle]["status"] = new_status
                            self.cubicle_data[cubicle]["occupied_time"] = occupied_time
                            self.cubicle_data[cubicle]["last_reading"] = current_time
                            
                            if status_changed:
                                self.cubicle_data[cubicle]["last_change"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                data_changed = True
                            
                            # Store data for saving
                            current_data["data"][cubicle]["status"] = new_status
                            current_data["data"][cubicle]["occupied_time"] = occupied_time
                            current_data["data"][cubicle]["previous_status"] = prev_status
                        
                        # Always log the readings to show current state
                        self.log_sensor_readings(current_data)
                        
                        # Only save if there's a change in status
                        if data_changed:
                            self.save_occupancy_data(current_data)
                            self.reading_counter += 1
                        
                        last_reading_time = current_time
                    
                except Exception as e:
                    self.log_message(f"Error in occupancy module: {e}")
                
                time.sleep(0.1)  # Short sleep to avoid CPU overhead
            else:
                time.sleep(0.5)  # Check for un-pause every half second
        
        # Save final reading before exit
        self.log_message("Saving final reading before exit...")
        
        # Create final reading data
        final_data = self.get_data_template()
        
        for i in range(len(self.PIR_PINS)):
            cubicle = f"CUB{i+1}"
            
            # Store final state
            final_data["data"][cubicle]["status"] = self.cubicle_data[cubicle]["status"]
            final_data["data"][cubicle]["occupied_time"] = self.cubicle_data[cubicle]["occupied_time"]
            final_data["data"][cubicle]["previous_status"] = self.cubicle_data[cubicle]["previous_status"]
        
        self.save_occupancy_data(final_data)
        self.cleanup_hardware()

# If run directly (for testing)
if __name__ == "__main__":
    print("Occupancy Module - Starting in standalone mode...")
    try:
        # Check for root privileges (needed for hardware access)
        if os.geteuid() != 0 and os.name != 'nt':
            print("This script requires root privileges for hardware access.")
            print("Please run with 'sudo python3 occu_mod_main.py'")
            sys.exit(1)
            
        # Handle Ctrl+C gracefully
        def signal_handler(signum, frame):
            if occupancy_module.running:
                occupancy_module.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create and start module
        occupancy_module = OccupancyModule()
        occupancy_module.start()
        
        # Keep the script running
        while occupancy_module.running:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
