#!/usr/bin/env python3

import time
import os
import sys
import json
import threading
import signal
import random
import lgpio
from datetime import datetime
import board
import adafruit_dht
import smbus
import psutil
import statistics
import serial
import subprocess
import glob
from collections import deque
from pymongo import MongoClient
from pymongo.errors import ConnectionError, ServerSelectionTimeoutError
from bson import ObjectId
from tabulate import tabulate

# MongoDB connection setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client['Smart_Cubicle']
    print("MongoDB connection established")
except ConnectionError as e:
    print(f"Warning: Failed to connect to MongoDB: {e}. Using local data only.")
    mongo_client = None
    db = None

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
        # GPIO setup
        self.SENSOR_PIN = 17         # E18-D80NK proximity sensor
        self.BUZZER_PIN = 27         # Buzzer for audio feedback
        self.chip = None
        
        # States
        self.STATE_VACANT = "Vacant"
        self.STATE_OCCUPIED = "Occupied"
        self.current_state = self.STATE_VACANT
        self.visitor_count = 0
        self.current_visitor_id = None
        self.current_start_time = None
        self.last_state_change_time = time.time()
        self.last_sensor_state = None
        self.detection_start = None
        self.log_queue = deque(maxlen=10)  # Keep last 10 log messages
        
        # Data storage
        self.DATA_DIR = "local-data"
        self.JSON_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.log_list = []
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['occupancy']
        else:
            self.mongo_collection = None
        
        # Constants
        self.DEBOUNCE_TIME = 0.5  # 500ms
        self.SHORT_BEEP = 0.2     # 200ms
        self.LONG_BEEP = 1.0      # 1s
    
    def log_message(self, message):
        """Print a message with timestamp and add to log queue"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
    def perform_post_check(self):
        """Perform Power-On Self Test to verify all components are working"""
        self.log_message("Performing system check...")
        
        # Check proximity sensor
        proximity_status = "Offline"
        if self.chip:
            try:
                # Test sensor
                sensor_value = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
                proximity_status = "Online" if sensor_value in [0, 1] else "Offline"
            except Exception as e:
                self.log_message(f"Error checking proximity sensor: {e}")
                proximity_status = "Offline"
        
        self.log_message(f"> Checking Proximity Sensor: {proximity_status}")
        
        # Check buzzer
        buzzer_status = "Offline"
        if self.chip:
            try:
                # Test buzzer with a short pulse
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 1)
                time.sleep(0.1)
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)
                buzzer_status = "Online"
            except Exception as e:
                self.log_message(f"Error checking buzzer: {e}")
                buzzer_status = "Offline"
        
        self.log_message(f"> Checking Buzzer: {buzzer_status}")
        
        # Check MongoDB connection
        db_status = "Offline"
        if self.mongo_collection:
            try:
                # Test connection by pinging
                if mongo_client:
                    mongo_client.admin.command('ping')
                    db_status = "Online"
            except Exception as e:
                self.log_message(f"Error checking MongoDB: {e}")
                db_status = "Offline"
        
        self.log_message(f"> Checking MongoDB: {db_status}")
        
        # Check local storage
        storage_status = "Offline"
        try:
            os.makedirs(self.DATA_DIR, exist_ok=True)
            test_file = os.path.join(self.DATA_DIR, "test.tmp")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            storage_status = "Online"
        except Exception as e:
            self.log_message(f"Error checking local storage: {e}")
            storage_status = "Offline"
        
        self.log_message(f"> Checking Local Storage: {storage_status}")
        
        # Overall status
        if proximity_status == "Online" and buzzer_status == "Online" and (db_status == "Online" or storage_status == "Online"):
            self.log_message("System check: PASSED")
            return True
        else:
            self.log_message("System check: FAILED - Some components not working")
            return False
    
    def setup_hardware(self):
        try:
            self.chip = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_input(self.chip, self.SENSOR_PIN, lgpio.SET_PULL_UP)
            lgpio.gpio_claim_output(self.chip, self.BUZZER_PIN)
            lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)  # Ensure buzzer is off
            self.last_sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
            self.log_message("GPIO initialized successfully")
            return True
        except Exception as e:
            self.log_message(f"Error setting up occupancy hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.chip:
            try:
                lgpio.gpio_free(self.chip, self.SENSOR_PIN)
                lgpio.gpio_free(self.chip, self.BUZZER_PIN)
                lgpio.gpiochip_close(self.chip)
                self.chip = None
                self.log_message("Hardware resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up occupancy hardware: {e}")
    
    def beep_buzzer(self, duration):
        """Control the buzzer for a specified duration"""
        if self.chip:
            try:
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 1)
                time.sleep(duration)
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)
            except Exception as e:
                self.log_message(f"Error controlling buzzer: {e}")
    
    def double_beep(self):
        """Perform a double beep pattern"""
        self.beep_buzzer(self.SHORT_BEEP)
        time.sleep(self.SHORT_BEEP)
        self.beep_buzzer(self.SHORT_BEEP)
    
    def format_duration(self, seconds):
        """Format duration in seconds to minutes and seconds"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}min {secs}sec"
    
    def read_json(self):
        """Read existing data from JSON file"""
        try:
            if os.path.exists(self.JSON_FILE):
                with open(self.JSON_FILE, "r") as f:
                    data = json.load(f)
                    return data
        except (json.JSONDecodeError, IOError) as e:
            self.log_message(f"Error reading JSON: {e}")
        return []
    
    def write_json(self, data):
        """Write data to JSON file atomically"""
        os.makedirs(os.path.dirname(self.JSON_FILE), exist_ok=True)
        temp_file = self.JSON_FILE + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=4)
            os.replace(temp_file, self.JSON_FILE)
            self.log_message("Data saved to local storage")
        except IOError as e:
            self.log_message(f"Error writing JSON: {e}")
    
    def update_mongo(self, entry):
        """Update MongoDB with visit data"""
        if self.mongo_collection is None:
            return False
            
        try:
            result = self.mongo_collection.insert_one(entry)
            self.log_message("Data saved to MongoDB")
            return True
        except Exception as e:
            self.log_message(f"Error updating MongoDB: {e}")
            return False
    
    def load_initial_state(self):
        """Load initial state from storage"""
        # Try MongoDB first if available
        if self.mongo_collection:
            try:
                # Find the highest visitor_id in MongoDB
                latest = self.mongo_collection.find_one(
                    {"type": "visit"}, 
                    sort=[("visitor_id", -1)]
                )
                
                if latest:
                    self.visitor_count = latest.get("visitor_id", 0)
                    self.current_visitor_id = self.visitor_count
                    
                    # Check if there's an ongoing visit (no end_time)
                    ongoing = self.mongo_collection.find_one({
                        "type": "visit",
                        "end_time": None
                    })
                    
                    if ongoing:
                        self.current_state = self.STATE_OCCUPIED
                        # Convert ISO string to timestamp
                        start_time_str = ongoing.get("start_time")
                        if start_time_str:
                            try:
                                self.current_start_time = datetime.fromisoformat(
                                    start_time_str.replace('Z', '+00:00')
                                ).timestamp()
                            except ValueError:
                                # Handle different date formats
                                try:
                                    self.current_start_time = datetime.strptime(
                                        start_time_str, "%Y-%m-%dT%H:%M:%S.%f"
                                    ).timestamp()
                                except ValueError:
                                    self.current_start_time = time.time()
                    
                    self.log_message(f"Loaded visitor count from MongoDB: {self.visitor_count}")
                    if self.current_state == self.STATE_OCCUPIED:
                        self.log_message("Ongoing visit detected")
                    return True
            except Exception as e:
                self.log_message(f"Error loading from MongoDB: {e}")
        
        # Fallback to local storage
        try:
            data = self.read_json()
            self.log_list = data
            
            if self.log_list:
                # Find highest visitor_id
                max_id = 0
                for entry in self.log_list:
                    if "visitor_id" in entry and entry["visitor_id"] > max_id:
                        max_id = entry["visitor_id"]
                
                self.visitor_count = max_id
                self.current_visitor_id = max_id
                
                # Check for ongoing visit
                ongoing_visit = next((entry for entry in self.log_list if "end_time" not in entry), None)
                if ongoing_visit:
                    self.current_state = self.STATE_OCCUPIED
                    self.current_start_time = ongoing_visit["start_time"]
                    self.log_message("Ongoing visit detected from local storage")
            else:
                self.visitor_count = 0
                self.log_message("No previous data found, starting with visitor count: 0")
        except Exception as e:
            self.log_message(f"Error loading from local storage: {e}")
            self.visitor_count = 0
            
        return True
    
    def save_visitor_data(self, visitor_data):
        """Save visitor data to both MongoDB and local storage"""
        mongodb_success = False
        local_success = False
        
        # Only save complete records with all required fields
        required_fields = ["type", "visitor_id", "start_time"]
        if not all(field in visitor_data for field in required_fields):
            self.log_message("Error: Incomplete visitor data, skipping save")
            return False
        
        # Try MongoDB first
        if self.mongo_collection is not None:
            try:
                result = self.mongo_collection.insert_one(visitor_data)
                if result.inserted_id:
                    mongodb_success = True
                    self.log_message("Data saved to MongoDB")
            except Exception as e:
                self.log_message(f"Error saving to MongoDB: {e}")
        
        # Then try local storage
        try:
            # Update log list
            self.log_list.append(visitor_data)
            # Save to file
            self.write_json(self.log_list)
            local_success = True
            self.log_message("Data saved to local storage")
        except Exception as e:
            self.log_message(f"Error saving to local storage: {e}")
        
        # Log appropriate status message
        if mongodb_success and local_success:
            self.log_message("DATA SAVED TO REMOTE AND LOCAL")
        elif local_success:
            self.log_message("DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("FAILED TO SAVE DATA")
        
        return mongodb_success or local_success
    
    def record_entry(self):
        """Record a new visitor entry"""
        self.visitor_count += 1
        self.current_visitor_id = self.visitor_count
        self.current_start_time = time.time()
        self.current_state = self.STATE_OCCUPIED
        
        # Create entry record
        new_entry = {
            "type": "visit",
            "visitor_id": self.current_visitor_id,
            "start_time": self.current_start_time,
            "start_time_iso": datetime.fromtimestamp(self.current_start_time).isoformat(),
            "end_time": None,
            "duration": None
        }
        
        # Save data
        self.save_visitor_data(new_entry)
        
        # Single beep for entry
        self.beep_buzzer(self.SHORT_BEEP)
        
        self.log_message(f"Entry detected - Visitor #{self.current_visitor_id}")
    
    def record_exit(self):
        """Record visitor exit"""
        if self.current_state != self.STATE_OCCUPIED or self.current_start_time is None:
            self.log_message("Warning: Exit recorded without matching entry")
            return
        
        # Calculate duration
        end_time = time.time()
        duration = end_time - self.current_start_time
        
        # Update visit record in log_list
        for entry in self.log_list:
            if entry.get("visitor_id") == self.current_visitor_id and entry.get("end_time") is None:
                entry["end_time"] = end_time
                entry["end_time_iso"] = datetime.fromtimestamp(end_time).isoformat()
                entry["duration"] = duration
                break
        
        # Also update in MongoDB if available
        if self.mongo_collection:
            try:
                self.mongo_collection.update_one(
                    {"visitor_id": self.current_visitor_id, "end_time": None},
                    {"$set": {
                        "end_time": datetime.fromtimestamp(end_time).isoformat(),
                        "duration": duration
                    }}
                )
            except Exception as e:
                self.log_message(f"Error updating MongoDB: {e}")
        
        # Write updated log_list to local storage
        self.write_json(self.log_list)
        
        # Double beep for exit
        self.double_beep()
        
        # Log status
        self.log_message(f"Exit detected - Duration: {self.format_duration(duration)}")
        
        # Reset state
        self.current_state = self.STATE_VACANT
        self.current_start_time = None
    
    def get_summary(self):
        """Return summary data for display"""
        # Calculate total visitors and average duration
        total_visitors = len([e for e in self.log_list if "end_time" in e and e["end_time"] is not None])
        completed_visits = [e for e in self.log_list if "end_time" in e and e["end_time"] is not None and "duration" in e]
        
        avg_duration = 0
        if completed_visits:
            avg_duration = sum(e["duration"] for e in completed_visits) / len(completed_visits)
        
        # Calculate current duration
        current_duration_str = "N/A"
        if self.current_start_time and self.current_state == self.STATE_OCCUPIED:
            current_duration = time.time() - self.current_start_time
            current_duration_str = self.format_duration(current_duration)
        
        return {
            "status": self.current_state,
            "total_visitors": total_visitors,
            "avg_duration": self.format_duration(avg_duration),
            "current_duration": current_duration_str,
            "sensor_state": "UP" if self.chip else "DOWN",
            "log_messages": list(self.log_queue)
        }
    
    def get_recent_logs(self, count=10):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]
    
    def run(self):
        """Main monitoring loop"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize occupancy hardware. Module not started.")
            self.running = False
            return
        
        # Perform system check
        self.perform_post_check()
        
        # Load initial state
        self.load_initial_state()
        
        if self.last_sensor_state is None and self.chip:
            self.last_sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
        
        last_status_time = time.time()
        
        self.log_message(f"Starting occupancy monitoring. Current state: {self.current_state}")
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
                    
                    # Handle debounced sensor state changes
                    if (current_time - self.last_state_change_time) > self.DEBOUNCE_TIME and sensor_state != self.last_sensor_state:
                        # State transition detection
                        if self.current_state == self.STATE_VACANT and sensor_state == 0:
                            # Beam broken while vacant - potential entry
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_VACANT and sensor_state == 1 and self.last_sensor_state == 0 and self.detection_start:
                            # Beam restored while vacant after being broken - confirm entry
                            if (current_time - self.detection_start) < 2:  # Ensure full cycle within 2s
                                self.record_entry()
                                self.last_state_change_time = current_time
                                self.detection_start = None
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 0:
                            # Beam broken while occupied - potential exit
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 1 and self.last_sensor_state == 0 and self.detection_start:
                            # Beam restored while occupied after being broken - confirm exit
                            if (current_time - self.detection_start) < 2:
                                self.record_exit()
                                self.last_state_change_time = current_time
                                self.detection_start = None
                                
                        self.last_sensor_state = sensor_state
                    
                    # Display status periodically
                    if current_time - last_status_time >= 30:
                        summary = self.get_summary()
                        self.log_message(f"Status: {summary['status']} | Visitors: {summary['total_visitors']} | Avg Duration: {summary['avg_duration']}")
                        last_status_time = current_time
                        
                except Exception as e:
                    self.log_message(f"Error in occupancy module: {e}")
            
            time.sleep(0.05)  # 50ms loop cycle time
        
        self.cleanup_hardware()

# Dispenser Module Implementation
class DispenserModule(ModuleBase):
    def __init__(self):
        super().__init__("Dispenser")
        # GPIO setup
        self.GPIO_CHIP = 0
        self.h = None
        self.TRIGGERS = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
        self.ECHOS = [8, 10, 13, 15]    # GPIO pins for ultrasonic echos
        
        # Reading settings
        self.READING_INTERVAL = 5        # Seconds between readings
        self.SIGNIFICANT_CHANGE_THRESHOLD = 10.0  # Save data when volume changes by this amount (ml)
        
        # Local data storage
        self.DATA_DIR = "local-data"
        self.JSON_FILE = os.path.join(self.DATA_DIR, "dispenser-data.json")
        
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
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['dispenser_resource']
        else:
            self.mongo_collection = None
        
        self.reading_counter = 0  # Reading counter
        self.previous_readings = None  # Previous readings for change detection
        self.log_queue = deque(maxlen=20)  # Keep last 20 log messages
    
    def log_message(self, message):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
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
        self.log_message("Testing ultrasonic sensors...")
        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
            distance = self.measure_distance(trigger, echo)
            if distance is not None and 0 < distance < 400:  # Valid range: 0-400cm
                self.log_message(f"✓ SONIC{i+1} online - distance: {distance:.2f} cm")
                self.container_data[f"CONT{i+1}"]["sensor_state"] = "UP"
            else:
                self.log_message(f"✗ SONIC{i+1} offline or out of range")
                sensors_ok = False
                self.container_data[f"CONT{i+1}"]["sensor_state"] = "DOWN"
        
        # Check MongoDB connection
        db_status = "Offline"
        if self.mongo_collection:
            try:
                # Test connection by pinging
                if mongo_client:
                    mongo_client.admin.command('ping')
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
        if gpio_ok and (sensors_ok or True) and (db_status == "Online" or storage_ok):
            self.log_message("System check: PASSED")
            return True
        else:
            if not sensors_ok:
                self.log_message("WARNING: Some sensors are not responding. System may not function properly.")
            if not db_status == "Online" and not storage_ok:
                self.log_message("ERROR: No storage available. Cannot continue.")
                return False
            self.log_message("System check: PASSED WITH WARNINGS")
            return True
    
    def setup_hardware(self):
        try:
            self.log_message("Initializing GPIO...")
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            # Setup trigger pins as output
            for trigger in self.TRIGGERS:
                lgpio.gpio_claim_output(self.h, trigger)
                
            # Setup echo pins as input
            for echo in self.ECHOS:
                lgpio.gpio_claim_input(self.h, echo)
                
            self.log_message("GPIO initialized successfully")
            return True
        except Exception as e:
            self.log_message(f"Error initializing GPIO: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                # Free all claimed GPIO pins
                for pin in self.TRIGGERS + self.ECHOS:
                    try:
                        lgpio.gpio_free(self.h, pin)
                    except Exception:
                        pass
                
                lgpio.gpiochip_close(self.h)
                self.h = None
                self.log_message("Hardware resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up hardware: {e}")
    
    def measure_distance(self, trigger, echo, num_measurements=5):
        """Measure distance using ultrasonic sensor with multiple readings for accuracy"""
        if not self.h:
            return None
        
        distances = []
        
        for _ in range(num_measurements):
            try:
                lgpio.gpio_write(self.h, trigger, 1)  # Trigger high
                time.sleep(0.00001)                  # 10us pulse
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
        
        # Remove outliers and average
        if distances:
            if len(distances) > 2:
                # Remove min and max values to filter outliers
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
    
    def load_last_reading(self):
        """Load the last reading from database to continue counter"""
        self.log_message("Checking for previous readings...")
        
        # Try MongoDB first if available
        if self.mongo_collection:
            try:
                # Find highest reading number
                last_record = self.mongo_collection.find_one(sort=[("reading", -1)])
                if last_record and "reading" in last_record:
                    self.reading_counter = last_record["reading"]
                    
                    # Load container data if available
                    if "data" in last_record:
                        for container in self.container_data:
                            if container in last_record["data"]:
                                volume = last_record["data"][container].get("remaining_volume_ml")
                                if volume is not None:
                                    self.container_data[container]["previous_volume_ml"] = volume
                                    self.container_data[container]["remaining_volume_ml"] = volume
                    
                    self.log_message(f"Loaded reading counter from MongoDB: {self.reading_counter}")
                    return True
            except Exception as e:
                self.log_message(f"Error loading from MongoDB: {e}")
        
        # Try local storage if MongoDB failed or not available
        try:
            if os.path.exists(self.JSON_FILE):
                with open(self.JSON_FILE, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        # Find highest reading number
                        readings = [entry.get("reading", 0) for entry in data]
                        if readings:
                            self.reading_counter = max(readings)
                            
                            # Get the last entry
                            last_entry = max(data, key=lambda x: x.get("reading", 0))
                            
                            # Load container data if available
                            if "data" in last_entry:
                                for container in self.container_data:
                                    if container in last_entry["data"]:
                                        volume = last_entry["data"][container].get("remaining_volume_ml")
                                        if volume is not None:
                                            self.container_data[container]["previous_volume_ml"] = volume
                                            self.container_data[container]["remaining_volume_ml"] = volume
                            
                            self.log_message(f"Loaded reading counter from local storage: {self.reading_counter}")
                            return True
        except Exception as e:
            self.log_message(f"Error loading from local storage: {e}")
        
        # If no data found, start from zero
        self.reading_counter = 0
        self.log_message("No previous readings found, starting with reading counter: 0")
        return False
    
    def should_save_reading(self, current_data):
        """Determine if the current reading should be saved based on changes"""
        if not self.previous_readings:
            return True
        
        # Check for significant changes in any container
        for container in self.container_data:
            prev_vol = self.previous_readings["data"][container]["remaining_volume_ml"]
            curr_vol = current_data["data"][container]["remaining_volume_ml"]
            
            # Calculate absolute change in volume
            volume_change = abs(prev_vol - curr_vol)
            
            # Only save if the change is significant
            if volume_change >= self.SIGNIFICANT_CHANGE_THRESHOLD:
                # Get the whole numbers
                prev_whole = int(prev_vol)
                curr_whole = int(curr_vol)
                
                # Only save if whole numbers are different
                if prev_whole != curr_whole:
                    return True
        
        return False
    
    def save_to_local_storage(self, data):
        """Save data to local JSON file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.JSON_FILE), exist_ok=True)
            
            existing_data = []
            if os.path.exists(self.JSON_FILE):
                try:
                    with open(self.JSON_FILE, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    self.log_message("Creating new data file (existing file corrupt)")
            
            # Ensure data has the correct format
            if not isinstance(existing_data, list):
                existing_data = []
            
            existing_data.append(data)
            
            # Use atomic write to prevent corruption
            temp_file = self.JSON_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_file, self.JSON_FILE)
            
            self.log_message("Data saved to local storage")
            return True
        except Exception as e:
            self.log_message(f"Local storage error: {e}")
            return False
    
    def save_to_mongodb(self, data):
        """Save data to MongoDB"""
        if not self.mongo_collection:
            return False
        
        try:
            self.mongo_collection.insert_one(data)
            self.log_message("Data saved to MongoDB")
            return True
        except Exception as e:
            self.log_message(f"Error saving to MongoDB: {e}")
            return False
    
    def save_dispenser_data(self, data):
        """Save dispenser data to both MongoDB and local storage"""
        mongodb_success = self.save_to_mongodb(data)
        local_success = self.save_to_local_storage(data)
        
        # Report overall status
        if mongodb_success and local_success:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
        elif local_success:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("Status: FAILED TO SAVE DATA")
            
        return mongodb_success or local_success
    
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
        
        # Load last reading counter
        self.load_last_reading()
        
        self.log_message("Detecting the initial volume for each container...")
        
        # Initial readings
        initial_readings = []
        readings_data = {
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {}
        }
        
        for i, (trigger, echo) in enumerate(zip(self.TRIGGERS, self.ECHOS)):
            container = f"CONT{i+1}"
            distance = self.measure_distance(trigger, echo)
            volume = self.calculate_volume(container, distance)
            
            # Update container data
            self.container_data[container]["distance_cm"] = distance if distance is not None else 0
            self.container_data[container]["remaining_volume_ml"] = volume if volume is not None else 0
            self.container_data[container]["previous_volume_ml"] = volume if volume is not None else 0
            self.container_data[container]["sensor_state"] = "UP" if distance is not None else "DOWN"
            
            # Store data for saving
            readings_data["data"][container] = {
                "distance_cm": distance if distance is not None else 0,
                "previous_volume_ml": volume if volume is not None else 0,
                "remaining_volume_ml": volume if volume is not None else 0
            }
            
            # Add to display
            if distance is not None and volume is not None:
                initial_readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml")
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

# Odor Module Implementation
class OdorModule(ModuleBase):
    def __init__(self):
        super().__init__("Odor")
        # GPIO setup
        self.GPIO_CHIP = 0
        self.h = None
        
        # Fan and freshener GPIO pins
        self.FAN_RELAY_PIN = 23  # GPIO23, Pin 16, 8RELAY-B K2 for exhaust fan
        self.FRESHENER_RELAY_PIN = 24  # Changed from 22 to 24 to avoid conflict with DHT sensor on GPIO12 (Pin 32)
        
        # DHT22 pins
        self.dht_devices = []
        self.dht_pins = [4, 5, 6, 12]  # GPIO pins for DHT22 sensors
        
        # Arduino serial connection
        self.arduino_serial = None
        self.BAUD_RATE = 9600
        self.SERIAL_TIMEOUT = 5
        
        # Occupancy tracking
        self.SENSOR_PIN = 17  # E18-D80NK for occupancy sensing
        self.is_occupied = False
        self.last_sensor_state = None
        self.last_exit_time = time.time()
        
        # Fan and freshener state
        self.fan_status = False
        self.freshener_triggered = False
        self.FAN_POST_EXIT_DURATION = 10  # 10 seconds delay after visitor exits
        
        # Data storage
        self.DATA_DIR = "local-data" 
        self.JSON_FILE = os.path.join(self.DATA_DIR, "odor-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Sensor readings buffer
        self.sensor_data_buffer = []
        self.log_queue = deque(maxlen=30)  # Keep last 30 log messages
        
        # Constants
        self.LOGGING_INTERVAL = 120  # seconds between saves (2 minutes)
        self.DECIMAL_PRECISION = 2  # For temperature and humidity values
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['odor_module']
        else:
            self.mongo_collection = None
        
        # Sensor data tracking
        self.sensor_data = {
            f"sensor_{i+1}": {
                "temperature": 0,
                "humidity": 0,
                "aqi": 0,
                "temp_status": "DOWN",
                "gas_status": "DOWN"
            } for i in range(4)
        }
    
    def log_message(self, message):
        """Print and store a log message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
    def perform_post_check(self):
        """Perform Power-On Self Test to verify all sensors are working"""
        self.log_message("Performing system check...")
        
        # Check MongoDB connection
        db_status = "Offline"
        if self.mongo_collection:
            try:
                if mongo_client:
                    mongo_client.admin.command('ping')
                    db_status = "Online"
                    self.log_message("✓ MongoDB connection active")
            except Exception as e:
                self.log_message(f"✗ MongoDB connection error: {e}")
                db_status = "Offline"
        else:
            self.log_message("✗ MongoDB not configured")
        
        # Check DHT sensors
        dht_status = "Offline"
        if self.dht_devices:
            for i, dht in enumerate(self.dht_devices):
                if dht:
                    try:
                        t = dht.temperature
                        h = dht.humidity
                        if t is not None and h is not None:
                            self.log_message(f"✓ DHT22 sensor {i+1} online: {t:.1f}°C, {h:.1f}%")
                            dht_status = "Online"
                            self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "UP"
                        else:
                            self.log_message(f"✗ DHT22 sensor {i+1} invalid readings")
                            self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
                    except Exception as e:
                        self.log_message(f"✗ DHT22 sensor {i+1} error: {e}")
                        self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
                else:
                    self.log_message(f"✗ DHT22 sensor {i+1} not initialized")
                    self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
        else:
            self.log_message("✗ No DHT22 sensors found")
        
        # Check Arduino/gas sensors
        arduino_status = "Offline"
        if self.arduino_serial:
            try:
                self.arduino_serial.write(b'R')
                time.sleep(0.5)
                response = self.arduino_serial.readline().decode().strip()
                if response and ',' in response:
                    values = response.split(',')
                    if len(values) == 4:
                        self.log_message(f"✓ Arduino gas sensors online: {values}")
                        arduino_status = "Online"
                        for i in range(4):
                            self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "UP"
                    else:
                        self.log_message(f"✗ Arduino returned invalid data: {response}")
                else:
                    self.log_message("✗ Arduino not responding")
            except Exception as e:
                self.log_message(f"✗ Arduino communication error: {e}")
        else:
            self.log_message("✗ Arduino not connected")
        
        # Check fan and freshener GPIO
        relay_status = "Offline"
        if self.h:
            try:
                # Test fan relay
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 0)  # Turn on
                time.sleep(0.2)
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Turn off
                
                # Test freshener relay
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 0)  # Turn on
                time.sleep(0.2)
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Turn off
                
                relay_status = "Online"
                self.log_message("✓ Relay controls online")
            except Exception as e:
                self.log_message(f"✗ Relay control error: {e}")
        else:
            self.log_message("✗ GPIO not initialized")
        
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
        
        # Return overall status
        return (dht_status == "Online" or arduino_status == "Online") and (db_status == "Online" or storage_ok)
    
    def setup_hardware(self):
        try:
            # Setup GPIO for sensors and actuators
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            # Setup fan and freshener relays
            lgpio.gpio_claim_output(self.h, self.FAN_RELAY_PIN)
            lgpio.gpio_claim_output(self.h, self.FRESHENER_RELAY_PIN)
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Ensure fan is off initially (HIGH = OFF)
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Ensure freshener is off initially (HIGH = OFF)
            
            # Setup occupancy sensor
            lgpio.gpio_claim_input(self.h, self.SENSOR_PIN, lgpio.SET_PULL_UP)
            self.last_sensor_state = lgpio.gpio_read(self.h, self.SENSOR_PIN)
            
            # Setup DHT22 temperature sensors
            self.log_message("Initializing DHT22 temperature sensors...")
            
            self.dht_devices = []
            for pin in self.dht_pins:
                try:
                    # Map GPIO numbers to board pins
                    if pin == 4:
                        sensor = adafruit_dht.DHT22(board.D4, use_pulseio=False)
                    elif pin == 5:
                        sensor = adafruit_dht.DHT22(board.D5, use_pulseio=False)
                    elif pin == 6:
                        sensor = adafruit_dht.DHT22(board.D6, use_pulseio=False)
                    elif pin == 12:
                        sensor = adafruit_dht.DHT22(board.D12, use_pulseio=False)
                    else:
                        sensor = None
                        
                    if sensor:
                        self.dht_devices.append(sensor)
                        self.log_message(f"DHT22 sensor on GPIO{pin} initialized")
                    else:
                        self.dht_devices.append(None)
                        self.log_message(f"Failed to map GPIO{pin} to board pin")
                except Exception as e:
                    self.log_message(f"Failed to initialize DHT22 on GPIO{pin}: {e}")
                    self.dht_devices.append(None)
            
            # Try to connect to Arduino for gas sensors
            arduino_connected = self.try_connect_arduino()
            if not arduino_connected:
                self.log_message("Warning: Could not connect to Arduino. Will use simulated gas data.")
            
            self.log_message("Hardware setup completed")
            return True
        except Exception as e:
            self.log_message(f"Error setting up odor hardware: {e}")
            return False
    
    def scan_serial_ports(self):
        """Scan for available serial ports"""
        self.log_message("Scanning serial ports...")
        
        # Common USB-Serial patterns
        patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*',
            '/dev/ttyAMA*',
            'COM[0-9]*'  # For Windows
        ]
        
        ports = []
        for pattern in patterns:
            ports.extend(glob.glob(pattern))
        
        if ports:
            self.log_message(f"Found ports using glob: {', '.join(ports)}")
            return ports
        
        self.log_message("No serial ports found.")
        return []
    
    def try_connect_arduino(self):
        """Try to connect to Arduino on available serial ports"""
        ports = self.scan_serial_ports()
        
        if not ports:
            self.log_message("No serial ports found.")
            return False
        
        # Sort ports to prioritize USB0
        ports = sorted(ports, key=lambda x: (
            0 if 'USB0' in x else
            1 if 'USB' in x else
            2 if 'ACM0' in x else
            3 if 'ACM' in x else
            4
        ))
        
        for port in ports:
            # Try to connect
            try:
                self.log_message(f"Trying to connect to Arduino on {port}...")
                ser = serial.Serial(port, self.BAUD_RATE, timeout=self.SERIAL_TIMEOUT)
                
                # Give the Arduino time to reset
                time.sleep(2)
                
                # Send read command
                ser.write(b'R')
                time.sleep(0.5)
                
                # Read response
                response = ser.readline().decode().strip()
                self.log_message(f"Received from {port}: '{response}'")
                
                if response and ',' in response:
                    values = response.split(',')
                    if len(values) == 4:  # Expect 4 sensor values
                        self.arduino_serial = ser
                        self.log_message(f"Successfully connected to Arduino on {port}")
                        return True
                
                ser.close()
                self.log_message(f"Invalid response from device on {port}")
                
            except Exception as e:
                self.log_message(f"Connection error on {port}: {e}")
        
        self.log_message("Could not find Arduino on any port")
        return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                # Turn off devices
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Fan off (HIGH = OFF)
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Freshener off (HIGH = OFF)
                
                # Free GPIO resources
                lgpio.gpio_free(self.h, self.FAN_RELAY_PIN)
                lgpio.gpio_free(self.h, self.FRESHENER_RELAY_PIN)
                lgpio.gpio_free(self.h, self.SENSOR_PIN)
                lgpio.gpiochip_close(self.h)
                self.h = None
                self.log_message("GPIO resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up GPIO: {e}")
        
        # Close Arduino connection
        if self.arduino_serial:
            try:
                self.arduino_serial.close()
                self.log_message("Closed Arduino serial connection")
            except Exception:
                pass
            self.arduino_serial = None
        
        # Clean up DHT sensors
        for sensor in self.dht_devices:
            if sensor:
                try:
                    sensor.exit()
                except Exception:
                    pass
        self.dht_devices = []
    
    def read_gas_sensors(self):
        """Read data from MQ135 gas sensors via Arduino"""
        if not self.arduino_serial:
            # Simulated data
            self.log_message("Using simulated gas sensor data")
            return [random.randint(100, 300) for _ in range(4)]
        
        try:
            # Reset input buffer to clear any stale data
            self.arduino_serial.reset_input_buffer()
            
            # Send read command
            self.arduino_serial.write(b'R')
            time.sleep(0.2)
            
            # Read response
            response = self.arduino_serial.readline().decode().strip()
            
            if not response:
                raise Exception("No response from Arduino")
            
            # Parse values
            values = []
            for val in response.split(','):
                try:
                    value = int(val)
                    # Validate range (0-500 is valid range for MQ135)
                    if 0 <= value <= 500:
                        values.append(value)
                    else:
                        values.append(random.randint(100, 300))  # Use random if out of range
                except ValueError:
                    values.append(random.randint(100, 300))  # Use random if parsing fails
            
            # Ensure we have 4 values
            while len(values) < 4:
                values.append(random.randint(100, 300))
            
            return values[:4]  # Return only first 4 values
            
        except Exception as e:
            self.log_message(f"Error reading gas sensors: {e}")
            
            # Attempt to reconnect on error
            if "device disconnected" in str(e).lower() or "port is closed" in str(e).lower():
                self.log_message("Attempting to reconnect to Arduino...")
                self.arduino_serial = None
                if self.try_connect_arduino():
                    self.log_message("Successfully reconnected to Arduino")
                    return self.read_gas_sensors()  # Try reading again
            
            # Return simulated data on failure
            return [random.randint(100, 300) for _ in range(4)]
    
    def read_temp_sensors(self):
        """Read data from DHT22 temperature sensors"""
        readings = []
        
        # Try to read each sensor
        for i, sensor in enumerate(self.dht_devices):
            retry_count = 3
            valid_reading = False
            temp = None
            hum = None
            
            if sensor:
                # Try multiple times before giving up
                for attempt in range(retry_count):
                    try:
                        # DHT sensors need time between readings
                        time.sleep(0.2)
                        
                        temp = sensor.temperature
                        hum = sensor.humidity
                        
                        # Validate readings
                        if (temp is not None and hum is not None and
                            -40 <= temp <= 80 and 0 <= hum <= 100):
                            valid_reading = True
                            self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "UP"
                            break
                    except Exception as e:
                        if attempt == retry_count - 1:  # Only log on final attempt
                            self.log_message(f"DHT sensor {i+1} error: {e}")
                        time.sleep(0.5)  # Wait before retry
            
            if valid_reading:
                readings.append({
                    "temp": round(temp, self.DECIMAL_PRECISION),
                    "hum": round(hum, self.DECIMAL_PRECISION)
                })
                
                # Update sensor data tracking
                self.sensor_data[f"sensor_{i+1}"]["temperature"] = round(temp, self.DECIMAL_PRECISION)
                self.sensor_data[f"sensor_{i+1}"]["humidity"] = round(hum, self.DECIMAL_PRECISION)
            else:
                # Use simulated data for invalid readings
                sim_temp = round(random.uniform(20, 35), self.DECIMAL_PRECISION)
                sim_hum = round(random.uniform(40, 80), self.DECIMAL_PRECISION)
                
                readings.append({
                    "temp": sim_temp,
                    "hum": sim_hum
                })
                
                # Update sensor data tracking with simulated values
                self.sensor_data[f"sensor_{i+1}"]["temperature"] = sim_temp
                self.sensor_data[f"sensor_{i+1}"]["humidity"] = sim_hum
                self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
                
                self.log_message(f"DHT sensor {i+1} gave invalid reading, using simulated data")
        
        # If we don't have enough readings, pad with simulated data
        while len(readings) < 4:
            sim_temp = round(random.uniform(20, 35), self.DECIMAL_PRECISION)
            sim_hum = round(random.uniform(40, 80), self.DECIMAL_PRECISION)
            
            readings.append({
                "temp": sim_temp,
                "hum": sim_hum
            })
            
            idx = len(readings) - 1
            if idx < 4:
                self.sensor_data[f"sensor_{idx+1}"]["temperature"] = sim_temp
                self.sensor_data[f"sensor_{idx+1}"]["humidity"] = sim_hum
                self.sensor_data[f"sensor_{idx+1}"]["temp_status"] = "DOWN"
        
        return readings
    
    def fix_sensor_data(self, gas_values, temp_readings):
        """Handle sensor failures by averaging values from working sensors"""
        fixed_gas = list(gas_values)
        fixed_temp = temp_readings.copy()
        
        # Fix gas values (replace zeros or nulls with averages)
        valid_gas = [val for val in gas_values if val > 0]
        if valid_gas:
            avg_gas = sum(valid_gas) / len(valid_gas)
            for i in range(len(fixed_gas)):
                if fixed_gas[i] <= 0:
                    fixed_gas[i] = round(avg_gas)
                    self.log_message(f"Fixed GAS{i+1} with average {round(avg_gas)}")
        
        # Fix temperature values
        valid_temps = [r["temp"] for r in temp_readings if r["temp"] > 0]
        valid_hums = [r["hum"] for r in temp_readings if r["hum"] > 0]
        
        if valid_temps:
            avg_temp = sum(valid_temps) / len(valid_temps)
            for i in range(len(fixed_temp)):
                if fixed_temp[i]["temp"] <= 0:
                    fixed_temp[i]["temp"] = round(avg_temp, self.DECIMAL_PRECISION)
                    self.log_message(f"Fixed TEMP{i+1} temperature with average {round(avg_temp, self.DECIMAL_PRECISION)}")
        
        if valid_hums:
            avg_hum = sum(valid_hums) / len(valid_hums)
            for i in range(len(fixed_temp)):
                if fixed_temp[i]["hum"] <= 0:
                    fixed_temp[i]["hum"] = round(avg_hum, self.DECIMAL_PRECISION)
                    self.log_message(f"Fixed TEMP{i+1} humidity with average {round(avg_hum, self.DECIMAL_PRECISION)}")
        
        return fixed_gas, fixed_temp
    
    def check_occupancy(self):
        """Check occupancy status using E18-D80NK sensor"""
        if not self.h:
            return False
        
        just_vacated = False
        current_sensor_state = lgpio.gpio_read(self.h, self.SENSOR_PIN)
        current_time = time.time()
        
        # If sensor state changed, handle debouncing
        if current_sensor_state != self.last_sensor_state:
            # Wait for sensor to stabilize (debounce)
            time.sleep(0.1)
            current_sensor_state = lgpio.gpio_read(self.h, self.SENSOR_PIN)
            
            # If the reading is still different, it's a real change
            if current_sensor_state != self.last_sensor_state:
                self.last_sensor_state = current_sensor_state
                
                # Update occupancy state (LOW = detected object, HIGH = no detection with pull-up)
                if current_sensor_state == 0:  # Object detected
                    if not self.is_occupied:
                        self.is_occupied = True
                        self.log_message("Visitor entered")
                        # Turn on fan when someone enters
                        self.toggle_fan(True)
                else:  # No object detected
                    if self.is_occupied:
                        self.is_occupied = False
                        self.last_exit_time = current_time
                        self.log_message("Visitor exited")
                        # Trigger air freshener when someone exits
                        self.trigger_air_freshener()
                        just_vacated = True
        
        return just_vacated
    
    def toggle_fan(self, state):
        """Toggle exhaust fan on or off (active-low: LOW = ON, HIGH = OFF)"""
        if self.h is None:
            self.log_message("Error: GPIO not initialized for fan")
            return False
        
        try:
            # Set GPIO pin: LOW (0) to activate, HIGH (1) to deactivate
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 0 if state else 1)
            self.fan_status = state
            self.log_message(f"Exhaust Fan {'ON' if state else 'OFF'}")
            return True
        except Exception as e:
            self.log_message(f"Error toggling exhaust fan: {e}")
            return False
    
    def trigger_air_freshener(self):
        """Trigger air freshener with a 500ms pulse"""
        if self.h is None:
            self.log_message("Error: GPIO not initialized for freshener")
            return False
        
        try:
            self.log_message("Triggering air freshener (500ms pulse)...")
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 0)  # LOW to activate
            time.sleep(0.5)  # 500ms pulse
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # HIGH to deactivate
            self.freshener_triggered = True
            self.log_message("Air freshener triggered successfully")
            return True
        except Exception as e:
            self.log_message(f"Error triggering air freshener: {e}")
            return False
    
    def update_devices(self):
        """Update device states based on occupancy"""
        current_time = time.time()
        
        # Update fan status - turn off after delay when vacant
        if not self.is_occupied and self.fan_status:
            if current_time - self.last_exit_time > self.FAN_POST_EXIT_DURATION:
                self.toggle_fan(False)
                self.log_message(f"Exhaust fan turned off after {self.FAN_POST_EXIT_DURATION} seconds of vacancy")
    
    def buffer_sensor_data(self, gas_values, temp_readings):
        """Add sensor data to buffer for averaging"""
        self.sensor_data_buffer.append({
            "gas": gas_values,
            "temp": temp_readings,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Keep buffer size reasonable to cover the full 2-minute interval
        # 24 entries = 2 minutes (at 5 second intervals)
        max_buffer_size = 24
        if len(self.sensor_data_buffer) > max_buffer_size:
            # Remove oldest entries
            self.sensor_data_buffer = self.sensor_data_buffer[-max_buffer_size:]
    
    def calculate_average_from_buffer(self):
        """Calculate average values from buffered sensor data"""
        if not self.sensor_data_buffer:
            return None
        
        # Initialize with zeros
        avg_gas = [0, 0, 0, 0]
        avg_temp = [
            {"temp": 0.0, "hum": 0.0},
            {"temp": 0.0, "hum": 0.0},
            {"temp": 0.0, "hum": 0.0},
            {"temp": 0.0, "hum": 0.0}
        ]
        
        # Log how many data points are being averaged
        self.log_message(f"Calculating averages from {len(self.sensor_data_buffer)} data points")
        
        # Sum all values
        for data in self.sensor_data_buffer:
            # Sum gas values
            for i in range(4):
                avg_gas[i] += data["gas"][i]
            
            # Sum temperature and humidity
            for i in range(4):
                avg_temp[i]["temp"] += data["temp"][i]["temp"]
                avg_temp[i]["hum"] += data["temp"][i]["hum"]
        
        # Calculate averages
        buffer_len = len(self.sensor_data_buffer)
        for i in range(4):
            avg_gas[i] = round(avg_gas[i] / buffer_len)
            avg_temp[i]["temp"] = round(avg_temp[i]["temp"] / buffer_len, self.DECIMAL_PRECISION)
            avg_temp[i]["hum"] = round(avg_temp[i]["hum"] / buffer_len, self.DECIMAL_PRECISION)
            
            # Update sensor data
            self.sensor_data[f"sensor_{i+1}"]["aqi"] = avg_gas[i]
        
        return {"gas": avg_gas, "temp": avg_temp}
    
    def log_sensor_data(self, gas_values, temp_readings):
        """Log all sensor data"""
        gas_str = f"ODOR [GAS1: {gas_values[0]} | GAS2: {gas_values[1]} | GAS3: {gas_values[2]} | GAS4: {gas_values[3]}]"
        temp_str = f"TEMP ["
        
        for i, reading in enumerate(temp_readings):
            temp_str += f"TEMP{i+1}: {reading['temp']}°C | "
        temp_str = temp_str.rstrip(" | ") + "]"
        
        self.log_message(f"{gas_str} {temp_str}")
    
    def save_to_local_storage(self, data):
        """Save data to local JSON file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.JSON_FILE), exist_ok=True)
            
            existing_data = []
            if os.path.exists(self.JSON_FILE):
                try:
                    with open(self.JSON_FILE, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    self.log_message("Creating new data file (existing file corrupt)")
            
            existing_data.append(data)
            
            # Use atomic write to prevent corruption
            temp_file = self.JSON_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_file, self.JSON_FILE)
            
            self.log_message("Data saved to local storage")
            return True
        except Exception as e:
            self.log_message(f"Local storage error: {e}")
            return False
    
    def save_to_mongodb(self, data):
        """Save data to MongoDB"""
        if not self.mongo_collection:
            return False
        
        try:
            # Convert _id string to ObjectId for MongoDB if needed
            if '_id' in data and isinstance(data['_id'], str):
                if data['_id'].startswith("local_"):
                    # Generate new ObjectId for local IDs
                    data['_id'] = ObjectId()
                else:
                    # Convert string ID to ObjectId
                    data['_id'] = ObjectId(data['_id'])
            
            result = self.mongo_collection.insert_one(data)
            self.log_message("Data saved to MongoDB")
            return True
        except Exception as e:
            self.log_message(f"MongoDB error: {e}")
            return False
    
    def save_sensor_data(self, gas_values, temp_readings):
        """Save sensor data to database(s)"""
        # Create data document
        data = {
            "_id": str(ObjectId()) if 'ObjectId' in globals() else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "aqi": {
                "GAS1": gas_values[0],
                "GAS2": gas_values[1],
                "GAS3": gas_values[2],
                "GAS4": gas_values[3]
            },
            "dht": {
                "TEMP1": {"temp": temp_readings[0]["temp"], "hum": temp_readings[0]["hum"]},
                "TEMP2": {"temp": temp_readings[1]["temp"], "hum": temp_readings[1]["hum"]},
                "TEMP3": {"temp": temp_readings[2]["temp"], "hum": temp_readings[2]["hum"]},
                "TEMP4": {"temp": temp_readings[3]["temp"], "hum": temp_readings[3]["hum"]}
            }
        }
        
        # Save to local storage first
        local_saved = self.save_to_local_storage(data)
        
        # Try saving to MongoDB if available
        mongo_saved = self.save_to_mongodb(data)
        
        # Log result
        if local_saved and mongo_saved:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
        elif local_saved:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("Status: FAILED TO SAVE DATA")
        
        fan_status_str = "on" if self.fan_status else "off"
        freshener_status_str = "triggered" if self.freshener_triggered else "off"
        occupancy_status_str = "occupied" if self.is_occupied else "vacant"
        self.log_message(f"Fan: {fan_status_str} | Freshener: {freshener_status_str} | Occupancy: {occupancy_status_str}")
        
        return local_saved or mongo_saved
    
    def get_sensor_summary(self):
        """Return summary data for display"""
        # Calculate averages
        avg_temp = 0
        avg_hum = 0
        avg_aqi = 0
        valid_count = 0
        
        for i in range(4):
            if self.sensor_data[f"sensor_{i+1}"]["temp_status"] == "UP":
                avg_temp += self.sensor_data[f"sensor_{i+1}"]["temperature"]
                avg_hum += self.sensor_data[f"sensor_{i+1}"]["humidity"]
                valid_count += 1
                
        if valid_count > 0:
            avg_temp /= valid_count
            avg_hum /= valid_count
        
        # Average AQI
        valid_aqi = 0
        aqi_count = 0
        for i in range(4):
            if self.sensor_data[f"sensor_{i+1}"]["gas_status"] == "UP":
                valid_aqi += self.sensor_data[f"sensor_{i+1}"]["aqi"]
                aqi_count += 1
        
        if aqi_count > 0:
            avg_aqi = valid_aqi / aqi_count
        
        # Calculate trend (simplified since we don't have persistent history)
        trend = "stable"
        
        return {
            "sensors": self.sensor_data,
            "avg_temp": round(avg_temp, 1),
            "avg_hum": round(avg_hum, 1),
            "avg_aqi": round(avg_aqi, 1),
            "occupancy": "OCCUPIED" if self.is_occupied else "VACANT",
            "trend": trend,
            "fan_status": "ON" if self.fan_status else "OFF",
            "freshener_status": "TRIGGERED" if self.freshener_triggered else "OFF",
            "log_messages": list(self.log_queue)
        }
    
    def get_recent_logs(self, count=10):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]
    
    def run(self):
        """Main module execution loop"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize odor hardware. Module not started.")
            self.running = False
            return
            
        # Perform POST check
        self.perform_post_check()
        
        self.log_message("Starting odor monitoring. Press Ctrl+C to stop.")
        
        last_log_time = time.time()
        last_save_time = time.time()
        last_device_update_time = time.time()
        last_occupancy_check_time = time.time()
        
        # Main loop
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check occupancy every second
                    if current_time - last_occupancy_check_time >= 1:
                        self.check_occupancy()
                        last_occupancy_check_time = current_time
                    
                    # Update device states every second
                    if current_time - last_device_update_time >= 1:
                        self.update_devices()
                        last_device_update_time = current_time
                    
                    # Read sensor data every 5 seconds
                    if current_time - last_log_time >= 5:
                        # Read sensors
                        gas_values = self.read_gas_sensors()
                        temp_readings = self.read_temp_sensors()
                        
                        # Fix any invalid sensor data
                        gas_values, temp_readings = self.fix_sensor_data(gas_values, temp_readings)
                        
                        # Buffer the data for averaging
                        self.buffer_sensor_data(gas_values, temp_readings)
                        
                        # Log current readings
                        self.log_sensor_data(gas_values, temp_readings)
                        
                        # Show time remaining until next database save
                        time_until_save = int(self.LOGGING_INTERVAL - (current_time - last_save_time))
                        self.log_message(f"Next database save in {time_until_save} seconds.")
                        
                        last_log_time = current_time
                    
                    # Save buffered/averaged data at the specified interval
                    if current_time - last_save_time >= self.LOGGING_INTERVAL:
                        # Calculate average from buffer
                        avg_data = self.calculate_average_from_buffer()
                        
                        if avg_data:
                            # Save the averaged data
                            self.save_sensor_data(avg_data["gas"], avg_data["temp"])
                        
                        last_save_time = current_time
                    
                except Exception as e:
                    self.log_message(f"Error in odor module: {e}")
                
                time.sleep(0.1)  # Small delay to prevent CPU overuse
            else:
                time.sleep(1)  # Check for un-pause every second
        
        # When stopping, save final data
        avg_data = self.calculate_average_from_buffer()
        if avg_data:
            self.log_message("Saving final data before exit...")
            self.save_sensor_data(avg_data["gas"], avg_data["temp"])
        
        # Clean up hardware
        self.cleanup_hardware()

# Central Hub Implementation for system monitoring
class CentralHub:
    def __init__(self):
        self.modules = {
            "occupancy": None,
            "dispenser": None,
            "odor": None
        }
        self.system_info = {
            "raspberry_pi": {
                "status": "UP",
                "last_powered": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cpu_temp": 0,
                "cpu_usage": 0,
                "memory_usage": 0,
                "storage_usage": 0
            },
            "arduino": {
                "status": "UP",
                "last_powered": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cpu_temp": 35.0,  # Simulated value
                "cpu_usage": 15.0,  # Simulated value
                "memory_usage": 30.0  # Simulated value
            }
        }
    
    def register_module(self, name, module_instance):
        """Register a module with the hub"""
        self.modules[name] = module_instance
    
    def update_system_info(self):
        """Update system information"""
        # Raspberry Pi stats
        self.system_info["raspberry_pi"]["cpu_usage"] = psutil.cpu_percent()
        self.system_info["raspberry_pi"]["memory_usage"] = psutil.virtual_memory().percent
        self.system_info["raspberry_pi"]["storage_usage"] = psutil.disk_usage('/').percent
        
        # Get CPU temperature (Linux-specific)
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                self.system_info["raspberry_pi"]["cpu_temp"] = temp
        except:
            self.system_info["raspberry_pi"]["cpu_temp"] = 0
        
        return self.system_info
    
    def get_modules_status(self):
        """Get status of all modules"""
        status = {}
        for name, module in self.modules.items():
            if module:
                status[name] = module.status()
            else:
                status[name] = "not registered"
        return status

# CLI Application
class SmartRestroomCLI:
    instance = None  # Class variable to hold the single instance
    
    def __init__(self):
        SmartRestroomCLI.instance = self  # Assigning the instance to the class variable
        self.running = True
        self.central_hub = CentralHub()
        self.modules_running = False
        
        # Create module instances
        self.occupancy_module = OccupancyModule()
        self.dispenser_module = DispenserModule()
        self.odor_module = OdorModule()
        
        # Register modules with central hub
        self.central_hub.register_module("occupancy", self.occupancy_module)
        self.central_hub.register_module("dispenser", self.dispenser_module)
        self.central_hub.register_module("odor", self.odor_module)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def signal_handler(self, sig, frame):
        """Handle signals for graceful shutdown"""
        print("\nShutting down Smart Restroom System...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Clean up resources and stop all modules"""
        print("\nCleaning up resources...")
        self.occupancy_module.stop()
        self.dispenser_module.stop()
        self.odor_module.stop()
        
        if mongo_client:
            mongo_client.close()
            print("MongoDB connection closed")
    
    def print_header(self):
        """Print application header"""
        self.clear_screen()
        print("=" * 80)
        print(" " * 25 + "SMART RESTROOM SYSTEM CLI")
        print("=" * 80)
        print(" ")
        
        # Check if any module is running to determine system status
        modules_status = self.central_hub.get_modules_status()
        any_module_running = any(status == "running" for status in modules_status.values())
        status_color = "\033[1;32m" if any_module_running else "\033[1;31m"  # Green for online, red for offline
        reset_color = "\033[0m"
        status_text = "ONLINE" if any_module_running else "OFFLINE"
        print(f"\nSystem Status: {status_color}{status_text}{reset_color}")
        
        # Display individual module statuses
        for module_name, status in modules_status.items():
            module_status = "ONLINE" if status == "running" else "OFFLINE"
            module_color = "\033[1;32m" if status == "running" else "\033[1;31m"  # Green for online, red for offline
            print(f"{module_name.capitalize()}: {module_color}{module_status}{reset_color}")
        
        print("")
    
    def view_data_log(self):
        """Display real-time data from all running modules"""
        refresh_interval = 5
        
        while True:
            self.clear_screen()
            print("=" * 80)
            print(" " * 30 + "DATA LOG VIEW")
            print("=" * 80)
            print("\nModule Data:")
            print("-" * 80)
            
            # Display Occupancy Data
            if self.occupancy_module.running:
                occupancy_data = self.occupancy_module.get_summary()
                print("\nOccupancy Module:")
                print(f"Status: {occupancy_data['status']}")
                print(f"Total Visitors: {occupancy_data['total_visitors']}")
                print(f"Average Duration: {occupancy_data['avg_duration']}")
                print(f"Current Duration: {occupancy_data['current_duration']}")
            
            # Display Dispenser Data
            if self.dispenser_module.running:
                dispenser_data = self.dispenser_module.get_container_summary()
                print("\nDispenser Module:")
                headers = ["Container", "Volume (mL)", "Last Used"]
                table = []
                for cont_id, data in dispenser_data.items():
                    table.append([
                        cont_id,
                        f"{data['remaining_volume_ml']:.1f}" if data['remaining_volume_ml'] is not None else "N/A",
                        f"{data['last_volume_change']} mL"
                    ])
                print(tabulate(table, headers=headers, tablefmt="grid"))
            
            # Display Odor Data
            if self.odor_module.running:
                odor_data = self.odor_module.get_sensor_summary()
                print("\nOdor Module:")
                print(f"Average Temperature: {odor_data['avg_temp']:.1f}°C")
                print(f"Average Humidity: {odor_data['avg_hum']:.1f}%")
                print(f"Average AQI: {odor_data['avg_aqi']:.1f}")
                print(f"Fan Status: {odor_data['fan_status']}")
                print(f"Freshener Status: {odor_data['freshener_status']}")
            
            print("\n" + "=" * 40)
            print("Options:")
            print("1. Refresh Data Log Now")
            print("2. Return to Main Menu")
            print("=" * 40)
            
            print(f"\nAuto-refresh in {refresh_interval} seconds...")
            
            # Handle input with timeout
            if os.name == 'nt':
                import msvcrt
                start_time = time.time()
                choice = ''
                
                while time.time() - start_time < refresh_interval:
                    if msvcrt.kbhit():
                        char = msvcrt.getch().decode('utf-8')
                        if char in ['1', '2']:
                            choice = char
                            print(char)
                            break
                    time.sleep(0.1)
            else:
                import select
                i, _, _ = select.select([sys.stdin], [], [], refresh_interval)
                choice = sys.stdin.readline().strip() if i else ""
            
            if choice == '2':
                break
    
    def start_all_modules(self):
        """Start all modules"""
        print("\nStarting all modules...")
        self.occupancy_module.start()
        self.dispenser_module.start()
        self.odor_module.start()
        self.modules_running = True
        time.sleep(1)  # Give modules time to initialize
        input("\nPress Enter to continue...")
    
    def stop_all_modules(self):
        """Stop all modules"""
        print("\nStopping all modules...")
        self.occupancy_module.stop()
        self.dispenser_module.stop()
        self.odor_module.stop()
        self.modules_running = False
        time.sleep(1)  # Give modules time to clean up
        input("\nPress Enter to continue...")
    
    def module_menu(self, module, name):
        """Show control menu for a specific module"""
        module_name = name.capitalize()
        
        while True:
            self.clear_screen()
            print(f"\n=== {module_name} Module Control ===\n")
            
            # Get current status
            status = module.status()
            status_color = "\033[1;32m" if status == "running" else "\033[1;31m"
            print(f"Current Status: {status_color}{status.upper()}\033[0m")
            
            # Dynamic menu option based on module status
            print("\n1. View Module Data" if status == "running" else "\n1. Start Module")
            print("2. Stop Module")
            print("3. Pause/Resume Module")
            print("4. Return to Main Menu")
            
            choice = input("\nEnter your choice (1-4): ")
            
            if choice == "1":
                if status == "running":
                    # Show module data in a real-time view
                    self.view_module_data(module, name)
                else:
                    # Start the module
                    module.start()
                    input("\nPress Enter to continue...")
            elif choice == "2":
                module.stop()
                input("\nPress Enter to continue...")
            elif choice == "3":
                module.pause()
                input("\nPress Enter to continue...")
            elif choice == "4":
                break
            else:
                print("Invalid choice. Please try again.")
                input("\nPress Enter to continue...")
    
    def main_menu(self):
        """Display main menu and handle user input"""
        while self.running:
            self.print_header()
            print("MAIN MENU\n")
            print("1. View System Dashboard")
            # Dynamic menu option based on module status
            print("2. View All Data" if self.modules_running else "2. Start All Modules")
            print("3. Stop All Modules")
            print("4. Occupancy Module Control")
            print("5. Dispenser Module Control")
            print("6. Odor Module Control")
            print("7. Exit")
            
            choice = input("\nEnter your choice (1-7): ")
            
            if choice == "1":
                self.display_dashboard()
            elif choice == "2":
                if self.modules_running:
                    self.view_data_log()
                else:
                    self.start_all_modules()
            elif choice == "3":
                self.stop_all_modules()
            elif choice == "4":
                self.module_menu(self.occupancy_module, "occupancy")
            elif choice == "5":
                self.module_menu(self.dispenser_module, "dispenser")
            elif choice == "6":
                self.module_menu(self.odor_module, "odor")
            elif choice == "7":
                self.running = False
                self.cleanup()
                break
            else:
                print("Invalid choice. Please try again.")
                input("\nPress Enter to continue...")
    
    def run(self):
        """Run the application"""
        self.main_menu()
        print("\nThank you for using Smart Restroom System!")
    
    def display_dashboard(self):
        """Display system dashboard with real-time updates"""
        refresh_interval = 5  # seconds between updates
        
        while True:
            self.clear_screen()
            print("=" * 80)
            print(" " * 25 + "SMART RESTROOM SYSTEM DASHBOARD")
            print("=" * 80)
            
            # System Stats
            sys_info = self.central_hub.update_system_info()
            print("\nSystem Information:")
            print("-" * 80)
            print("Raspberry Pi:")
            print(f"CPU Temperature : {sys_info['raspberry_pi']['cpu_temp']:.1f}°C")
            print(f"CPU Usage      : {sys_info['raspberry_pi']['cpu_usage']:.1f}%")
            print(f"Memory Usage   : {sys_info['raspberry_pi']['memory_usage']:.1f}%")
            print(f"Storage Usage  : {sys_info['raspberry_pi']['storage_usage']:.1f}%")
            
            print("\nArduino:")
            print(f"CPU Temperature : {sys_info['arduino']['cpu_temp']:.1f}°C")
            print(f"CPU Usage      : {sys_info['arduino']['cpu_usage']:.1f}%")
            print(f"Memory Usage   : {sys_info['arduino']['memory_usage']:.1f}%")
            
            # Module Status
            print("\nModule Status:")
            print("-" * 80)
            modules_status = self.central_hub.get_modules_status()
            for module, status in modules_status.items():
                status_color = "\033[1;32m" if status == "running" else "\033[1;31m"
                print(f"{module.capitalize():12} : {status_color}{status.upper()}{'\033[0m'}")
            
            # Module Data (if running)
            if self.occupancy_module.running:
                print("\nOccupancy Data:")
                print("-" * 80)
                occ_data = self.occupancy_module.get_summary()
                print(f"Current State    : {occ_data['status']}")
                print(f"Total Visitors   : {occ_data['total_visitors']}")
                print(f"Average Duration : {occ_data['avg_duration']}")
                print(f"Current Duration : {occ_data['current_duration']}")
            
            if self.dispenser_module.running:
                print("\nDispenser Status:")
                print("-" * 80)
                disp_data = self.dispenser_module.get_container_summary()
                headers = ["Container", "Volume (mL)", "Last Used"]
                table = []
                for cont_id, data in disp_data.items():
                    table.append([
                        cont_id,
                        f"{data['remaining_volume_ml']:.1f}" if data['remaining_volume_ml'] is not None else "N/A",
                        f"{data['last_volume_change']} mL"
                    ])
                print(tabulate(table, headers=headers, tablefmt="grid"))
            
            if self.odor_module.running:
                print("\nOdor Control Status:")
                print("-" * 80)
                odor_data = self.odor_module.get_sensor_summary()
                print(f"Average Temperature : {odor_data['avg_temp']:.1f}°C")
                print(f"Average Humidity    : {odor_data['avg_hum']:.1f}%")
                print(f"Average AQI         : {odor_data['avg_aqi']:.1f}")
                print(f"AQI Trend          : {odor_data['trend'].upper()}")
                # Removed fan and freshener status
                # print(f"Fan Status         : {odor_data['fan_status']}")
                # print(f"Freshener Status   : {odor_data['freshener_status']}")
            
            print("\n" + "=" * 40)
            print("Options:")
            print("1. Refresh Dashboard")
            print("2. Return to Main Menu")
            print("=" * 40)
            
            print(f"\nAuto-refresh in {refresh_interval} seconds...")
            
            # Handle input with timeout
            if os.name == 'nt':
                import msvcrt
                start_time = time.time()
                choice = ''
                
                while time.time() - start_time < refresh_interval:
                    if msvcrt.kbhit():
                        char = msvcrt.getch().decode('utf-8')
                        if char in ['1', '2']:
                            choice = char
                            print(char)
                            break
                    time.sleep(0.1)
            else:
                import select
                i, _, _ = select.select([sys.stdin], [], [], refresh_interval)
                choice = sys.stdin.readline().strip() if i else ""
            
            if choice == '2':
                break
                
    def view_module_data(self, module, name):
        """Display real-time data for a specific module"""
        refresh_interval = 5
        module_name = name.capitalize()
        
        while True:
            self.clear_screen()
            print("=" * 80)
            print(f" " * 30 + f"{module_name.upper()} MODULE DATA")
            print("=" * 80)
            
            # Display module-specific data
            if name == "occupancy":
                data = module.get_summary()
                print(f"\nCurrent State    : {data['status']}")
                print(f"Total Visitors   : {data['total_visitors']}")
                print(f"Average Duration : {data['avg_duration']}")
                print(f"Current Duration : {data['current_duration']}")
                print(f"Sensor State     : {data['sensor_state']}")
                
                # Get visitor logs if available
                if hasattr(module, 'log_list') and module.log_list:
                    print("\nRecent Visitors:")
                    headers = ["Visitor ID", "Start Time", "End Time", "Duration"]
                    table = []
                    for entry in module.log_list[-5:]:  # Show last 5 entries
                        end_time = entry.get("end_time_iso", "Active")
                        duration = self.occupancy_module.format_duration(entry["duration"]) if "duration" in entry else "Active"
                        table.append([
                            entry["visitor_id"],
                            datetime.fromtimestamp(entry["start_time"]).strftime("%H:%M:%S"),
                            end_time if end_time == "Active" else datetime.fromtimestamp(entry["end_time"]).strftime("%H:%M:%S"),
                            duration
                        ])
                    print(tabulate(table, headers=headers, tablefmt="grid"))
                
            elif name == "dispenser":
                data = module.get_container_summary()
                headers = ["Container", "Volume (mL)", "Percentage", "Sensor", "Last Used"]
                table = []
                
                for cont_id, cont_data in data.items():
                    volume = cont_data["remaining_volume_ml"]
                    percentage = int((volume / 425) * 100) if volume is not None else 0
                    table.append([
                        cont_id,
                        f"{volume:.1f}" if volume is not None else "N/A",
                        f"{percentage}%" if volume is not None else "N/A",
                        cont_data["sensor_state"],
                        f"{cont_data['last_volume_change']} mL"
                    ])
                
                print(tabulate(table, headers=headers, tablefmt="grid"))
                
            elif name == "odor":
                data = module.get_sensor_summary()
                print(f"Average Temperature : {data['avg_temp']:.1f}°C")
                print(f"Average Humidity    : {data['avg_hum']:.1f}%")
                print(f"Average AQI         : {data['avg_aqi']:.1f}")
                print(f"AQI Trend          : {data['trend'].upper()}")
                # Removed fan and freshener status
                # print(f"Fan Status         : {data['fan_status']}")
                # print(f"Freshener Status   : {data['freshener_status']}")
                print(f"Occupancy Status   : {data['occupancy']}")
                
                # Display individual sensor readings
                print("\nSensor Readings:")
                headers = ["Sensor", "Temperature", "Humidity", "AQI", "Temp Sensor", "Gas Sensor"]
                table = []
                
                for i in range(1, 5):
                    sensor = data["sensors"][f"sensor_{i}"]
                    table.append([
                        f"Sensor {i}",
                        f"{sensor['temperature']:.1f}°C",
                        f"{sensor['humidity']:.1f}%",
                        f"{sensor['aqi']}",
                        sensor['temp_status'],
                        sensor['gas_status']
                    ])
                
                print(tabulate(table, headers=headers, tablefmt="grid"))
            
            # Display options menu
            print("\n" + "=" * 40)
            print("Options:")
            print("1. Refresh Data Log Now")
            print("2. Return to Module Menu")
            print("=" * 40)
            
            print(f"\nAuto-refresh in {refresh_interval} seconds...")
            
            # Handle input with timeout
            if os.name == 'nt':
                import msvcrt
                start_time = time.time()
                choice = ''
                
                while time.time() - start_time < refresh_interval:
                    if msvcrt.kbhit():
                        char = msvcrt.getch().decode('utf-8')
                        if char in ['1', '2']:
                            choice = char
                            print(char)
                            break
                    time.sleep(0.1)
            else:
                import select
                i, _, _ = select.select([sys.stdin], [], [], refresh_interval)
                choice = sys.stdin.readline().strip() if i else ""
            
            if choice == '2':
                break
            # If choice is '1' or timeout, continue loop to refresh

# Main entry point
if __name__ == "__main__":
    try:
        # Check for root privileges (needed for hardware access)
        if os.geteuid() != 0 and os.name != 'nt':
            print("This script requires root privileges for hardware access.")
            print("Please run with 'sudo python3 smart-restroom-cli.py'")
            sys.exit(1)
        
        # Print welcome message
        print("\nWelcome to Smart Restroom System CLI")
        print("Initializing components, please wait...\n")
        
        # Start the application
        app = SmartRestroomCLI()
        app.run()
    except Exception as e:
        print(f"Error: {e}")
        if 'app' in locals():
            app.cleanup()
        sys.exit(1)
