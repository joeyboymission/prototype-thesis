#!/usr/bin/env python3
import time
import os
import json
import signal
import sys
from datetime import datetime
from bson import ObjectId
import threading
from collections import deque
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

# Try to import MongoDB libraries, but have a fallback if not available
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

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

# Dispenser Module Implementation
class DispenserModule(ModuleBase):
    def __init__(self):
        super().__init__("Dispenser")
        # Configuration
        self.GPIO_CHIP = 0
        
        # GPIO pins from pin-config.md
        self.TRIGGERS = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
        self.ECHOS = [8, 10, 13, 15]     # GPIO pins for ultrasonic echos
        
        self.READING_INTERVAL = 5        # Seconds between readings
        self.SIGNIFICANT_CHANGE_THRESHOLD = 10.0  # Save data when volume changes by this amount (ml)

        # MongoDB settings
        self.MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

        # Local storage settings
        self.DATA_DIR = "/home/admin/Documents/local-data"
        self.LOCAL_FILE = os.path.join(self.DATA_DIR, "dispenser-data.json")

        # Calibration data for each container
        self.CALIBRATION_DATA = {
            "CONT1": {"full": 2.84, "empty": 12.67},
            "CONT2": {"full": 2.37, "empty": 12.21},
            "CONT3": {"full": 2.23, "empty": 12.33},
            "CONT4": {"full": 2.91, "empty": 12.88}
        }
        
        # Container data
        self.container_data = {
            f"CONT{i+1}": {
                "distance_cm": 0.00,
                "previous_volume_ml": 0.00,
                "remaining_volume_ml": 0.00,
                "sensor_state": "DOWN",
                "last_reading": time.time(),
                "last_volume_change": 0
            } for i in range(4)
        }

        # Global variables
        self.h = None                  # GPIO handle
        self.mongo_client = None       # MongoDB client
        self.mongo_db = None           # MongoDB database
        self.mongo_collection = None   # MongoDB collection
        self.reading_counter = 0       # Reading counter
        self.previous_readings = None  # Previous readings
        self.log_queue = deque(maxlen=20)  # Keep last 20 log messages
        self.claimed_pins = []         # List of successfully claimed GPIO pins
        self.active_sensors = []       # List of sensor pairs (trigger, echo) that were successfully claimed
        
        # If we're on Windows, adjust the paths
        if os.name == 'nt':
            self.DATA_DIR = "local-data"
            self.LOCAL_FILE = os.path.join(self.DATA_DIR, "dispenser-data.json")

    def get_data_template(self):
        """Initialize data format for a dispenser reading"""
        return {
            "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "reading": self.reading_counter + 1,
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

    def log_sensor_readings(self, data):
    """Log current sensor readings in the required format"""
    readings = []
    for i in range(1, 5):
        container = f"CONT{i}"
        dist = data["data"][container]["distance_cm"]
        vol = data["data"][container]["remaining_volume_ml"]
        readings.append(f"{container}: {dist:.2f} cm {vol:.2f} ml")
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
            self.mongo_collection = self.mongo_db["dispenser_resource"]  # Using the correct collection name
        
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

    def save_dispenser_data(self, dispenser_data):
    """Save dispenser data to both MongoDB and local storage"""
        mongodb_success = self.save_to_mongodb(dispenser_data)
        local_success = self.save_to_local_storage(dispenser_data)
        
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
        if not self.previous_readings:
        return True
    
    # Minimum volume change threshold (in ml) to consider significant
    MIN_VOLUME_CHANGE = 10.0  # Only save if volume changes by at least 10ml
    
    for container in ["CONT1", "CONT2", "CONT3", "CONT4"]:
            prev_vol = self.previous_readings["data"][container]["remaining_volume_ml"]
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

    def setup_hardware(self):
        """Initialize GPIO for ultrasonic sensors"""
        
        global LGPIO_AVAILABLE
        
        if not LGPIO_AVAILABLE:
            self.log_message("Running in simulation mode (lgpio not available)")
            return True
        
        try:
            self.log_message("Initializing GPIO...")
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            self.claimed_pins = []
            self.active_sensors = []
            
            # Try to claim each trigger and echo pin pair
            for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
                trigger_claimed = False
                echo_claimed = False
                
                try:
                    # Try to claim trigger pin
                    lgpio.gpio_claim_output(self.h, trigger)
                    self.claimed_pins.append(trigger)
                    trigger_claimed = True
                    self.log_message(f"Successfully claimed trigger pin GPIO{trigger}")
                except Exception as e:
                    self.log_message(f"Could not claim trigger pin GPIO{trigger}: {e}")
                
                try:
                    # Try to claim echo pin
                    lgpio.gpio_claim_input(self.h, echo)
                    self.claimed_pins.append(echo)
                    echo_claimed = True
                    self.log_message(f"Successfully claimed echo pin GPIO{echo}")
                except Exception as e:
                    self.log_message(f"Could not claim echo pin GPIO{echo}: {e}")
                
                # Only add to active sensors if both pins were claimed
                if trigger_claimed and echo_claimed:
                    self.active_sensors.append((trigger, echo))
                    self.log_message(f"Ultrasonic sensor {i+1} (CONT{i+1}) is active")
                else:
                    # If one pin was claimed but the other wasn't, release the claimed one
                    if trigger_claimed and not echo_claimed:
                        try:
                            lgpio.gpio_free(self.h, trigger)
                            self.claimed_pins.remove(trigger)
                            self.log_message(f"Released GPIO{trigger} because echo pin could not be claimed")
                        except:
                            pass
                    elif echo_claimed and not trigger_claimed:
                        try:
                            lgpio.gpio_free(self.h, echo)
                            self.claimed_pins.remove(echo)
                            self.log_message(f"Released GPIO{echo} because trigger pin could not be claimed")
                        except:
                            pass
            
            # Check if we were able to claim at least some sensor pairs
            if self.active_sensors:
                self.log_message(f"GPIO initialized with {len(self.active_sensors)} active ultrasonic sensors")
                return True
            else:
                self.log_message("Failed to claim any ultrasonic sensor pairs")
                # We'll still return True so the module runs in simulation mode for all sensors
        return True
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
            self.active_sensors = []
            self.log_message("GPIO resources cleaned up")

    def measure_distance(self, trigger, echo, num_measurements=5):
    """Measure distance using ultrasonic sensor with multiple readings for accuracy"""
        if not LGPIO_AVAILABLE:
            # Return simulated distance between 5-15cm
            import random
            return random.uniform(5.0, 15.0)
        
        # Check if this sensor pair is in the list of active sensors
        if not (trigger, echo) in self.active_sensors:
            # Use simulation for sensors that weren't successfully claimed
            import random
            return random.uniform(5.0, 15.0)
        
    distances = []
    
    for _ in range(num_measurements):
            try:
                lgpio.gpio_write(self.h, trigger, 1)  # Trigger high
        time.sleep(0.00001)              # 10us pulse
                lgpio.gpio_write(self.h, trigger, 0)  # Trigger low
        
        # Wait for echo to go high
        start_time = time.time()
                while lgpio.gpio_read(self.h, echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:  # Timeout after 0.5s
                return None
        
        # Wait for echo to go low
        start_time = time.time()
                while lgpio.gpio_read(self.h, echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:  # Timeout after 0.5s
                return None
        
        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound: 343 m/s -> 17150 cm/s
        distances.append(round(distance, 2))
        
        time.sleep(0.05)  # Short delay between measurements
            except Exception as e:
                self.log_message(f"Error measuring distance: {e}")
                return None
    
    # Remove outliers and average
    if distances:
        if len(distances) > 2:
            # Remove min and max values
            distances.remove(min(distances))
            distances.remove(max(distances))
        
        # Average the remaining values
        return sum(distances) / len(distances)
    
    return None

    def calculate_volume(self, container, distance):
    """Calculate remaining volume based on distance measurement"""
    if distance is None:
        return None
        
        full_distance = self.CALIBRATION_DATA[container]["full"]
        empty_distance = self.CALIBRATION_DATA[container]["empty"]
    
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

    def perform_post_check(self):
        """Perform Power-On Self Test to verify all components are working"""
        self.log_message("Performing system check...")
        
        # Check GPIO
        gpio_ok = self.setup_hardware()
        if gpio_ok:
            if len(self.active_sensors) > 0:
                self.log_message(f"✓ GPIO initialized with {len(self.active_sensors)} active sensor pairs")
            else:
                self.log_message("✓ GPIO initialized but no sensor pairs could be claimed")
        else:
            self.log_message("✗ GPIO initialization failed")
            return False
        
        # Check sensors
        sensors_ok = True
        self.log_message("Testing ultrasonic sensors...")
        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
            if (trigger, echo) in self.active_sensors:
                # This is a real sensor we can use
                distance = self.measure_distance(trigger, echo)
                if distance is not None and 0 < distance < 400:  # Valid range: 0-400cm
                    self.log_message(f"✓ SONIC{i+1} online - distance: {distance:.2f} cm")
                    self.container_data[f"CONT{i+1}"]["sensor_state"] = "UP"
                else:
                    self.log_message(f"✗ SONIC{i+1} not responding or out of range")
                    sensors_ok = False
                    self.container_data[f"CONT{i+1}"]["sensor_state"] = "DOWN"
            else:
                # This is a simulated sensor
                distance = self.measure_distance(trigger, echo)  # This will return simulated data
                self.log_message(f"✓ SONIC{i+1} simulated - distance: {distance:.2f} cm")
                self.container_data[f"CONT{i+1}"]["sensor_state"] = "SIMULATED"
        
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
        if (len(self.active_sensors) > 0 or self.active_sensors == []) and (db_status == "Online" or storage_ok):
            self.log_message("System check: PASSED")
            return True
        else:
            if sensors_ok == False and len(self.active_sensors) > 0:
                self.log_message("WARNING: Some sensors are not responding. System may not function properly.")
            if not db_status == "Online" and not storage_ok:
                self.log_message("ERROR: No storage available. Cannot continue.")
                return False
            self.log_message("System check: PASSED WITH WARNINGS")
            return True

    def get_container_summary(self):
        """Get summary data for all containers"""
        return self.container_data

    def get_recent_logs(self, count=10):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]

    def run(self):
        """Main function to monitor dispenser containers"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize dispenser hardware. Module not started.")
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
        
        self.log_message("Detecting the initial volume for each container...")
        
        # Initial readings
        initial_readings = []
        readings_data = {
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {}
        }
        
        # Check if we have active sensors or need to use simulation mode for all
        using_simulation = len(self.active_sensors) == 0
        if using_simulation:
            self.log_message("No active ultrasonic sensors. Using simulation mode for all containers.")
        
        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
            container = f"CONT{i+1}"
            
            # Get the distance measurement (real or simulated)
            distance = self.measure_distance(trigger, echo)
            volume = self.calculate_volume(container, distance)
            
            # Update container data
            self.container_data[container]["distance_cm"] = distance if distance is not None else 0
            self.container_data[container]["remaining_volume_ml"] = volume if volume is not None else 0
            self.container_data[container]["previous_volume_ml"] = volume if volume is not None else 0
            
            # Set sensor state based on whether we're using the actual sensor or simulation
            if (trigger, echo) in self.active_sensors:
                self.container_data[container]["sensor_state"] = "UP"
            else:
                # If we don't have this active sensor, mark it as simulated
                self.container_data[container]["sensor_state"] = "SIMULATED"
            
            # Store data for saving
            readings_data["data"][container] = {
                "distance_cm": distance if distance is not None else 0,
                "previous_volume_ml": volume if volume is not None else 0,
                "remaining_volume_ml": volume if volume is not None else 0
            }
            
            # Add to display
            if distance is not None and volume is not None:
                sensor_state = "(SIMULATED)" if (trigger, echo) not in self.active_sensors else ""
                initial_readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml {sensor_state}")
            else:
                initial_readings.append(f"{container}: ERROR")
        
        # Display initial readings
        self.log_message(" | ".join(initial_readings))
        
        # Save initial readings
        self.save_dispenser_data(readings_data)
        self.previous_readings = readings_data
        self.reading_counter += 1
        
        self.log_message("Dispenser monitoring ready")
        
        # Main monitoring loop
        last_reading_time = time.time()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check if it's time for a new reading
                    if current_time - last_reading_time >= self.READING_INTERVAL:
                        readings = []
                        current_data = {
                            "reading": self.reading_counter + 1,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "data": {}
                        }
                        
                        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
                container = f"CONT{i+1}"
                            distance = self.measure_distance(trigger, echo)
                            volume = self.calculate_volume(container, distance)
                            
                            prev_volume = self.container_data[container]["remaining_volume_ml"]
                            
                            # Update container data
                            self.container_data[container]["distance_cm"] = distance if distance is not None else 0
                            self.container_data[container]["previous_volume_ml"] = prev_volume
                            self.container_data[container]["remaining_volume_ml"] = volume if volume is not None else 0
                            self.container_data[container]["sensor_state"] = "UP" if distance is not None else "DOWN"
                            self.container_data[container]["last_reading"] = current_time
                            
                            # Calculate volume change if sensor is working
                            if volume is not None and prev_volume is not None and prev_volume > volume:
                                volume_change = prev_volume - volume
                                self.container_data[container]["last_volume_change"] = round(volume_change, 2)
                            
                            # Store data for saving
                            current_data["data"][container] = {
                                "distance_cm": distance if distance is not None else 0,
                                "previous_volume_ml": prev_volume,
                                "remaining_volume_ml": volume if volume is not None else 0
                            }
                            
                            # Format for display
                            if distance is not None and volume is not None:
                                readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml")
                            else:
                                readings.append(f"{container}: ERROR")
                        
                        # Display current readings
                        self.log_message(" | ".join(readings))
                        
                        # Only save if there's a significant change
                        if self.should_save_reading(current_data):
                            self.save_dispenser_data(current_data)
                            self.reading_counter += 1
                        
                        # Update previous readings
                        self.previous_readings = current_data
                        
                        last_reading_time = current_time
                    
                except Exception as e:
                    self.log_message(f"Error in dispenser module: {e}")
                
                time.sleep(1)  # Check every second
                else:
                time.sleep(1)  # Check for un-pause every second
        
        # Save final reading regardless of changes
        self.log_message("Saving final reading before exit...")
        
        # Create final reading data
        final_data = {
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {}
        }
        
        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
            container = f"CONT{i+1}"
            distance = self.measure_distance(trigger, echo)
            volume = self.calculate_volume(container, distance)
            prev_volume = self.container_data[container]["remaining_volume_ml"]
            
            final_data["data"][container] = {
                "distance_cm": distance if distance is not None else 0,
                "previous_volume_ml": prev_volume,
                "remaining_volume_ml": volume if volume is not None else 0
            }
        
        self.save_dispenser_data(final_data)
        self.cleanup_hardware()


# If run directly (for testing)
if __name__ == "__main__":
    print("Dispenser Module - Starting in standalone mode...")
    try:
        # Check for root privileges (needed for hardware access)
        if os.geteuid() != 0 and os.name != 'nt':
            print("This script requires root privileges for hardware access.")
            print("Please run with 'sudo python3 disp_mod_main.py'")
            sys.exit(1)
            
        # Handle Ctrl+C gracefully
        def signal_handler(signum, frame):
            if dispenser_module.running:
                dispenser_module.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create and start module
        dispenser_module = DispenserModule()
        dispenser_module.start()
        
        # Keep the script running
        while dispenser_module.running:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
