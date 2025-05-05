#!/usr/bin/env python3
import os
import subprocess
import time
import json
from datetime import datetime
import glob
import random
import signal
import sys
import statistics
import importlib.util
import threading
from bson import ObjectId
from collections import deque
import platform

# Check if we're running on Raspberry Pi for hardware-specific imports
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Try to import hardware-specific libraries
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("Warning: serial module not available. Arduino communication will be simulated.")

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("Warning: lgpio not available. Hardware features will be simulated.")

# Try to import MongoDB
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

# Try to import DHT sensor library
try:
    import board
    import adafruit_dht
    DHT_AVAILABLE = True
except ImportError:
    DHT_AVAILABLE = False
    print("DHT sensor library not available. Using simulated data.")

# Settings
BAUD_RATE = 9600
SERIAL_TIMEOUT = 5
DATA_DIR = "/home/admin/Documents/local-data"
LOCAL_FILE = os.path.join(DATA_DIR, "odor-data.json")
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
LOGGING_INTERVAL = 120  # Changed from 10 to 120 seconds (2 minutes) to reduce database writes
DECIMAL_PRECISION = 2  # For temperature and humidity values

# GPIO settings for exhaust fan and air freshener
GPIO_CHIP = 0
FAN_RELAY_PIN = 23  # GPIO23, Pin 16, 8RELAY-B K2 for exhaust fan
FRESHENER_RELAY_PIN = 24  # Changed from 22 to 24 to avoid conflict with DHT sensor on GPIO12 (Pin 32)
FAN_POST_EXIT_DURATION = 10  # 10 seconds delay after visitor exits

# DHT22 sensor pins (match dht22-test.py)
DHT_PINS = [4, 5, 6, 12]  # GPIO numbers

# Global variables
arduino_serial = None
mongo_client = None
mongo_db = None
mongo_collection = None
dht_sensors = []
running = True
sensor_data_buffer = []

# GPIO control handle
gpio_handle = None

# Fan and freshener state
fan_status = False
freshener_triggered = False

# Occupancy tracking
is_occupied = False
last_exit_time = time.time()

# Import occu-mod-main.py to access occupancy data
try:
    # Don't try to import from a different directory path
    # This was causing errors with the path: "../occupancy-mod-main/occu-mod-main.py"
    # The main CLI script will handle module coordination instead
    OCCUPANCY_MODULE_AVAILABLE = False
    print("Occupancy module integration skipped - will be handled by main CLI.")
except Exception as e:
    OCCUPANCY_MODULE_AVAILABLE = False
    print(f"Warning: Could not import occupancy module: {e}. Using local occupancy detection.")

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

# Odor Module Implementation
class OdorModule(ModuleBase):
    def __init__(self):
        super().__init__("Odor")
        # Configuration
        self.GPIO_CHIP = 0
        self.MQ2_PIN = 26          # Analog input pin for MQ2 gas sensor
        self.FAN_PIN = 13          # GPIO pin for fan control
        self.READING_INTERVAL = 5  # Seconds between readings
        self.FAN_THRESHOLD = 200   # Threshold for fan activation
        
        # MongoDB settings
        self.MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
        
        # Local storage settings
        self.DATA_DIR = "/home/admin/Documents/local-data"
        self.LOCAL_FILE = os.path.join(self.DATA_DIR, "odor-data.json")
        
        # Global variables
        self.h = None                  # GPIO handle
        self.mongo_client = None       # MongoDB client
        self.mongo_db = None           # MongoDB database
        self.mongo_collection = None   # MongoDB collection
        self.reading_counter = 0       # Reading counter
        self.previous_reading = None   # Previous reading value
        self.log_queue = deque(maxlen=20)  # Keep last 20 log messages
        
        # Sensor data
        self.sensor_data = {
            "value": 0,
            "previous_value": 0,
            "sensor_state": "DOWN",
            "fan_state": "OFF",
            "last_reading": time.time(),
            "status": "GOOD"  # AIR QUALITY STATUS ("GOOD", "POOR", "BAD")
        }
        
        # If we're on Windows, adjust the paths
        if os.name == 'nt':
            self.DATA_DIR = "local-data"
            self.LOCAL_FILE = os.path.join(self.DATA_DIR, "odor-data.json")

    def get_data_template(self):
        """Initialize data format for an odor reading"""
        return {
            "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "sensor_value": 0,
                "previous_value": 0,
                "air_quality": "GOOD",
                "fan_state": "OFF"
            }
        }

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
            self.mongo_collection = self.mongo_db["odor_resource"]  # Using the correct collection name
            
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

    def save_odor_data(self, odor_data):
        """Save odor data to both MongoDB and local storage"""
        mongodb_success = self.save_to_mongodb(odor_data)
        local_success = self.save_to_local_storage(odor_data)
        
        # Report overall status
        if mongodb_success and local_success:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
        elif local_success:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("Status: FAILED TO SAVE DATA")
            
        return mongodb_success or local_success

    def should_save_reading(self, current_reading, previous_reading):
        """Determine if the current reading should be saved based on changes"""
        if previous_reading is None:
            return True
        
        # Get the current and previous sensor values
        current_value = current_reading["data"]["sensor_value"]
        prev_value = previous_reading["data"]["sensor_value"]
        
        # Calculate the absolute change
        value_change = abs(current_value - prev_value)
        
        # Save if there's a significant change (more than 10% or 20 units, whichever is greater)
        significant_change = max(prev_value * 0.1, 20)
        if value_change >= significant_change:
            return True
            
        # Also save if air quality status changed
        if current_reading["data"]["air_quality"] != previous_reading["data"]["air_quality"]:
            return True
            
        # Or if fan state changed
        if current_reading["data"]["fan_state"] != previous_reading["data"]["fan_state"]:
            return True
            
        return False

    def setup_hardware(self):
        """Initialize GPIO for MQ2 sensor and fan control"""
        global LGPIO_AVAILABLE
        
        if not LGPIO_AVAILABLE:
            self.log_message("Running in simulation mode (lgpio not available)")
            return True
        
        try:
            self.log_message("Initializing GPIO...")
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            # For MQ2, we would normally set up ADC here, but we're simulating readings
            
            # Setup fan pin as output
            lgpio.gpio_claim_output(self.h, self.FAN_PIN)
            lgpio.gpio_write(self.h, self.FAN_PIN, 0)  # Initialize fan to OFF
                
            self.log_message("GPIO initialized successfully")
            return True
        except Exception as e:
            self.log_message(f"Error initializing GPIO: {e}")
            return False

    def cleanup_hardware(self):
        """Clean up GPIO resources"""
        if not LGPIO_AVAILABLE:
            return
        
        if self.h is not None:
            try:
                # Turn off fan
                lgpio.gpio_write(self.h, self.FAN_PIN, 0)
                lgpio.gpio_free(self.h, self.FAN_PIN)
            except:
                pass
            try:
                lgpio.gpiochip_close(self.h)
            except:
                pass
            self.h = None
            self.log_message("GPIO resources cleaned up")

    def set_fan_state(self, state):
        """Set fan state (0=OFF, 1=ON)"""
        if not LGPIO_AVAILABLE:
            # Just update the state in memory
            self.sensor_data["fan_state"] = "ON" if state else "OFF"
            return True
        
        if self.h is not None:
            try:
                lgpio.gpio_write(self.h, self.FAN_PIN, state)
                self.sensor_data["fan_state"] = "ON" if state else "OFF"
                return True
            except Exception as e:
                self.log_message(f"Error setting fan state: {e}")
        return False

    def read_mq2_sensor(self):
        """Read MQ2 sensor value (simulated for now)"""
        try:
            # In a real implementation, we would read from an ADC
            # For now, we'll simulate values between 100-400
            # In a real implementation, we would use something like:
            # adc_value = read_adc_value(MQ2_PIN)
            
            # Simulate some realistic sensor behavior
            base_value = 150  # Base line value when air is clean
            
            # Add some random fluctuation (-10 to +10)
            import random
            fluctuation = random.randint(-10, 10)
            
            # Every so often (10% chance), simulate a "bad air" event
            if random.random() < 0.1:
                # Simulate poor air quality (200-400 range)
                base_value = random.randint(200, 400)
            
            # Return the simulated sensor reading
            return base_value + fluctuation
            
        except Exception as e:
            self.log_message(f"Error reading MQ2 sensor: {e}")
            return 0

    def get_air_quality_status(self, sensor_value):
        """Determine air quality based on sensor value"""
        if sensor_value < 180:
            return "GOOD"
        elif sensor_value < 300:
            return "POOR"
        else:
            return "BAD"

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
        
        # Check the MQ2 sensor
        sensor_value = self.read_mq2_sensor()
        self.log_message(f"MQ2 sensor reading: {sensor_value}")
        if sensor_value > 0:
            self.log_message("✓ MQ2 sensor responding")
            self.sensor_data["sensor_state"] = "UP"
        else:
            self.log_message("✗ MQ2 sensor not responding")
            self.sensor_data["sensor_state"] = "DOWN"
        
        # Test the fan
        self.log_message("Testing fan...")
        self.set_fan_state(1)  # Turn ON
        time.sleep(1)
        self.set_fan_state(0)  # Turn OFF
        self.log_message("✓ Fan tested")
        
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

    def get_sensor_summary(self):
        """Get summary data for the sensor"""
        return self.sensor_data

    def get_recent_logs(self, count=10):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]

    def run(self):
        """Main function to monitor odor levels"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize odor sensor hardware. Module not started.")
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
        
        self.log_message("Detecting the initial air quality...")
        
        # Initial reading
        sensor_value = self.read_mq2_sensor()
        air_quality = self.get_air_quality_status(sensor_value)
        fan_state = "ON" if sensor_value >= self.FAN_THRESHOLD else "OFF"
        
        # Set fan based on reading
        self.set_fan_state(1 if fan_state == "ON" else 0)
        
        # Update sensor data
        self.sensor_data["value"] = sensor_value
        self.sensor_data["previous_value"] = sensor_value
        self.sensor_data["status"] = air_quality
        
        # Create and save initial reading
        initial_data = self.get_data_template()
        initial_data["data"]["sensor_value"] = sensor_value
        initial_data["data"]["previous_value"] = sensor_value
        initial_data["data"]["air_quality"] = air_quality
        initial_data["data"]["fan_state"] = fan_state
        
        self.log_message(f"Initial reading: {sensor_value} - Air quality: {air_quality} - Fan: {fan_state}")
        self.save_odor_data(initial_data)
        self.previous_reading = initial_data
        self.reading_counter += 1
        
        self.log_message("Air quality monitoring ready")
        
        # Main monitoring loop
        last_reading_time = time.time()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check if it's time for a new reading
                    if current_time - last_reading_time >= self.READING_INTERVAL:
                        # Read sensor
                        sensor_value = self.read_mq2_sensor()
                        
                        # Get previous value
                        prev_value = self.sensor_data["value"]
                        
                        # Determine air quality
                        air_quality = self.get_air_quality_status(sensor_value)
                        
                        # Determine if fan should be on
                        should_fan_be_on = sensor_value >= self.FAN_THRESHOLD
                        
                        # Update fan state if needed
                        if (should_fan_be_on and self.sensor_data["fan_state"] == "OFF") or \
                           (not should_fan_be_on and self.sensor_data["fan_state"] == "ON"):
                            self.set_fan_state(1 if should_fan_be_on else 0)
                        
                        # Get current fan state after potential update
                        current_fan_state = self.sensor_data["fan_state"]
                        
                        # Update sensor data
                        self.sensor_data["previous_value"] = prev_value
                        self.sensor_data["value"] = sensor_value
                        self.sensor_data["status"] = air_quality
                        self.sensor_data["last_reading"] = current_time
                        
                        # Create current reading data
                        current_data = self.get_data_template()
                        current_data["data"]["sensor_value"] = sensor_value
                        current_data["data"]["previous_value"] = prev_value
                        current_data["data"]["air_quality"] = air_quality
                        current_data["data"]["fan_state"] = current_fan_state
                        
                        # Log current reading
                        self.log_message(f"Reading: {sensor_value} - Air quality: {air_quality} - Fan: {current_fan_state}")
                        
                        # Save if significant change or first reading
                        if self.should_save_reading(current_data, self.previous_reading):
                            self.save_odor_data(current_data)
                            self.reading_counter += 1
                            self.previous_reading = current_data
                        
                        last_reading_time = current_time
                    
                except Exception as e:
                    self.log_message(f"Error in odor module: {e}")
                
                time.sleep(0.5)  # Short sleep to avoid CPU overhead
            else:
                time.sleep(0.5)  # Check for un-pause every half second
        
        # Save final reading before exit
        self.log_message("Saving final reading before exit...")
        
        # Create final reading data
        final_data = self.get_data_template()
        sensor_value = self.read_mq2_sensor()
        air_quality = self.get_air_quality_status(sensor_value)
        
        # Turn off fan
        self.set_fan_state(0)
        
        # Store final state
        final_data["data"]["sensor_value"] = sensor_value
        final_data["data"]["previous_value"] = self.sensor_data["value"]
        final_data["data"]["air_quality"] = air_quality
        final_data["data"]["fan_state"] = "OFF"
        
        self.save_odor_data(final_data)
        self.cleanup_hardware()

# If run directly (for testing)
if __name__ == "__main__":
    print("Odor Module - Starting in standalone mode...")
    try:
        # Check for root privileges (needed for hardware access)
        if os.geteuid() != 0 and os.name != 'nt':
            print("This script requires root privileges for hardware access.")
            print("Please run with 'sudo python3 odor_mod_main.py'")
            sys.exit(1)
            
        # Handle Ctrl+C gracefully
        def signal_handler(signum, frame):
            if odor_module.running:
                odor_module.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create and start module
        odor_module = OdorModule()
        odor_module.start()
        
        # Keep the script running
        while odor_module.running:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)