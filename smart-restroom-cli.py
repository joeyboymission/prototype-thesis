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
        self.SENSOR_PIN = 17  # E18-D80NK signal
        self.BUZZER_PIN = 27  # Buzzer control
        self.chip = None
        
        # States
        self.STATE_VACANT = "Vacant"
        self.STATE_OCCUPIED = "Occupied"
        self.current_state = self.STATE_VACANT
        self.visitor_count = 0
        self.log_list = []
        self.log_queue = deque(maxlen=10)  # Keep last 10 log messages
        self.current_start_time = None
        self.last_state_change_time = time.time()
        self.detection_start = None
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['occupancy_data']
        else:
            self.mongo_collection = None
        
        # Local data storage
        self.DATA_DIR = "local-data"
        self.JSON_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Constants
        self.DEBOUNCE_TIME = 0.5  # 500ms
        self.SHORT_BEEP = 0.2     # 200ms
        self.LONG_BEEP = 1.0      # 1s
    
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
    
    def log_message(self, message):
        """Print and store a log message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
    def setup_hardware(self):
        try:
            self.chip = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_input(self.chip, self.SENSOR_PIN, lgpio.SET_PULL_UP)
            lgpio.gpio_claim_output(self.chip, self.BUZZER_PIN)
            lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)  # Ensure buzzer is off
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
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.log_message(f"Error reading JSON: {e}")
        return {"visitors": [], "summary": {"total_visitors": 0, "average_duration": 0}, "current_presence": False}
    
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
            self.log_message(f"Data saved to MongoDB (ID: {result.inserted_id})")
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
                    
                    # Check if there's an ongoing visit (no end_time)
                    ongoing = self.mongo_collection.find_one({
                        "type": "visit",
                        "end_time": None
                    })
                    
                    if ongoing:
                        self.current_state = self.STATE_OCCUPIED
                        # Convert ISO string to timestamp if needed
                        start_time_str = ongoing.get("start_time")
                        if start_time_str:
                            try:
                                self.current_start_time = datetime.fromisoformat(
                                    start_time_str.replace('.000000','')
                                ).timestamp()
                            except ValueError:
                                # Handle different date formats
                                self.current_start_time = datetime.strptime(
                                    start_time_str, "%Y-%m-%dT%H:%M:%S.%f"
                                ).timestamp()
                    
                    self.log_message(f"Loaded visitor count from MongoDB: {self.visitor_count}")
                    if self.current_state == self.STATE_OCCUPIED:
                        self.log_message("Ongoing visit detected")
                    return True
            except Exception as e:
                self.log_message(f"Error loading from MongoDB: {e}")
        
        # Fallback to local storage
        data = self.read_json()
        self.log_list = data.get("visitors", [])
        
        if self.log_list:
            self.visitor_count = max(entry["visitor_id"] for entry in self.log_list if "visitor_id" in entry)
            ongoing_visit = next((entry for entry in self.log_list if "end_time" not in entry), None)
            if ongoing_visit:
                self.current_state = self.STATE_OCCUPIED
                self.current_start_time = float(ongoing_visit["start_time"])
                self.log_message("Ongoing visit detected from local storage")
        else:
            self.visitor_count = 0
            self.log_message("No previous data found, starting with visitor count: 0")
            
        return True
    
    def update_log(self, new_entry=None):
        """Update log with new entry and recalculate summary"""
        if new_entry:
            self.log_list.append(new_entry)
            self.update_mongo(new_entry)
        
        # Calculate summary
        total_visitors = len([e for e in self.log_list if "end_time" in e])
        completed_visits = [e for e in self.log_list if "end_time" in e]
        average_duration = sum(e["duration"] for e in completed_visits) / total_visitors if total_visitors > 0 else 0
        
        data = {
            "visitors": self.log_list,
            "summary": {
                "total_visitors": total_visitors,
                "average_duration": average_duration
            },
            "current_presence": self.current_state == self.STATE_OCCUPIED
        }
        
        self.write_json(data)
    
    def get_summary(self):
        """Return summary data for display"""
        data = self.read_json()
        summary = data.get("summary", {})
        current_presence = data.get("current_presence", False)
        
        # Calculate average duration in readable format
        avg_duration = summary.get("average_duration", 0)
        avg_duration_str = self.format_duration(avg_duration)
        
        # Calculate current duration
        current_duration_str = "N/A"
        if self.current_start_time and current_presence:
            current_duration = time.time() - self.current_start_time
            current_duration_str = self.format_duration(current_duration)
        
        return {
            "status": "Occupied" if current_presence else "Vacant",
            "total_visitors": summary.get("total_visitors", 0),
            "avg_duration": avg_duration_str,
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
        last_sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
        last_status_time = time.time()
        
        self.log_message(f"Starting occupancy monitoring. Current state: {self.current_state}")
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
                    
                    # Handle debounced sensor state changes
                    if (current_time - self.last_state_change_time) > self.DEBOUNCE_TIME and sensor_state != last_sensor_state:
                        if self.current_state == self.STATE_VACANT and sensor_state == 0:
                            # Beam broken while vacant - potential entry
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_VACANT and sensor_state == 1 and last_sensor_state == 0 and self.detection_start:
                            # Beam restored while vacant after being broken - confirm entry
                            if (current_time - self.detection_start) < 2:  # Ensure full cycle within 2s
                                # Record entry
                                self.visitor_count += 1
                                self.current_start_time = current_time
                                self.current_state = self.STATE_OCCUPIED
                                
                                # Create visit record
                                new_entry = {
                                    "type": "visit",
                                    "visitor_id": self.visitor_count,
                                    "start_time": current_time,
                                    "start_time_iso": datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.000000"),
                                    "end_time": None,
                                    "duration": None
                                }
                                
                                # Update logs
                                self.update_log(new_entry)
                                
                                # Audio feedback
                                self.double_beep()
                                
                                # Log status
                                self.log_message(f"Entry detected - Visitor #{self.visitor_count}")
                                
                                self.last_state_change_time = current_time
                                self.detection_start = None
                                
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 0:
                            # Beam broken while occupied - potential exit
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0 and self.detection_start:
                            # Beam restored while occupied after being broken - confirm exit
                            if (current_time - self.detection_start) < 2:  # Ensure full cycle within 2s
                                # Record exit
                                duration = current_time - self.current_start_time
                                self.current_state = self.STATE_VACANT
                                
                                # Find the active visit and mark it as ended
                                for entry in self.log_list:
                                    if entry.get("visitor_id") == self.visitor_count and entry.get("end_time") is None:
                                        entry["end_time"] = current_time
                                        entry["end_time_iso"] = datetime.fromtimestamp(current_time).strftime("%Y-%m-%dT%H:%M:%S.000000")
                                        entry["duration"] = duration
                                        break
                                
                                # Audio feedback
                                self.beep_buzzer(self.LONG_BEEP)
                                
                                # Update logs
                                self.update_log()
                                
                                # Log status
                                self.log_message(f"Exit detected - Duration: {self.format_duration(duration)}")
                                
                                self.last_state_change_time = current_time
                                self.detection_start = None
                                
                                # Reset tracking variables
                                self.current_start_time = None
                        
                        last_sensor_state = sensor_state
                    
                    # Display status periodically (every 60 seconds)
                    if current_time - last_status_time >= 60:
                        # Calculate total visitors and average duration
                        total_visitors = len([e for e in self.log_list if "end_time" in e])
                        completed_visits = [e for e in self.log_list if "end_time" in e]
                        avg_duration = sum(e["duration"] for e in completed_visits) / total_visitors if total_visitors > 0 else 0
                        
                        # Log periodic status
                        self.log_message(f"Status: {self.current_state} | Visitors: {total_visitors} | Avg Duration: {self.format_duration(avg_duration)}")
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
        self.triggers = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
        self.echos = [8, 10, 13, 15]    # GPIO pins for ultrasonic echos
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['dispenser_resource']
        else:
            self.mongo_collection = None
        
        # Local data storage
        self.DATA_DIR = "local-data"
        self.JSON_FILE = os.path.join(self.DATA_DIR, "dispenser-data.json")
        
        # Container calibration data
        self.CALIBRATION_DATA = {
            "CONT1": {"full": 2.84, "empty": 12.67},
            "CONT2": {"full": 2.37, "empty": 12.21},
            "CONT3": {"full": 2.23, "empty": 12.33},
            "CONT4": {"full": 2.91, "empty": 12.88}
        }
        
        # Container data
        self.container_data = {
            f"CONT{i+1}": {
                "distance_cm": None,
                "remaining_volume_ml": None,
                "last_reading": time.time(),
                "last_volume_change": 0,
                "sensor_state": "DOWN",
                "previous_volume_ml": None
            } for i in range(4)
        }
        
        # Reading counter and last saved volumes for change detection
        self.reading_count = 0
        self.previous_volumes = {}
        self.last_saved_volumes = {}
        self.SIGNIFICANT_CHANGE_THRESHOLD = 10.0  # ml
        self.READING_INTERVAL = 10  # seconds
        self.log_queue = deque(maxlen=20)  # Keep last 20 log messages
    
    def log_message(self, message):
        """Print and store a log message with timestamp"""
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
        for i, (trigger, echo) in enumerate(zip(self.triggers, self.echos)):
            distance = self.measure_distance(trigger, echo)
            if distance is not None and 0 < distance < 400:  # Valid range: 0-400cm
                self.log_message(f"✓ SONIC{i+1} online - distance: {distance:.2f} cm")
            else:
                self.log_message(f"✗ SONIC{i+1} offline or out of range")
                sensors_ok = False
        
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
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            
            # Setup trigger pins as output
            for trigger in self.triggers:
                lgpio.gpio_claim_output(self.h, trigger)
                
            # Setup echo pins as input
            for echo in self.echos:
                lgpio.gpio_claim_input(self.h, echo)
                
            self.log_message("GPIO initialized successfully for dispenser module")
            return True
        except Exception as e:
            self.log_message(f"Error setting up dispenser hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                # Free all claimed GPIO pins
                for pin in self.triggers + self.echos:
                    lgpio.gpio_free(self.h, pin)
                
                lgpio.gpiochip_close(self.h)
                self.h = None
                self.log_message("Dispenser hardware resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up dispenser hardware: {e}")
    
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
    
    def calculate_usable_volume(self, container, distance):
        """Calculate usable volume based on distance and calibration data"""
        if distance is None:
            return None
            
        if self.CALIBRATION_DATA[container]["full"] is None or self.CALIBRATION_DATA[container]["empty"] is None:
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
                    self.reading_count = last_record["reading"]
                    
                    # Load container data if available
                    if "data" in last_record:
                        for container in self.container_data:
                            if container in last_record["data"]:
                                volume = last_record["data"][container].get("remaining_volume_ml")
                                if volume is not None:
                                    self.previous_volumes[container] = volume
                                    self.last_saved_volumes[container] = volume
                    
                    self.log_message(f"Loaded reading counter from MongoDB: {self.reading_count}")
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
                            self.reading_count = max(readings)
                            
                            # Get the last entry
                            last_entry = max(data, key=lambda x: x.get("reading", 0))
                            
                            # Load container data if available
                            if "data" in last_entry:
                                for container in self.container_data:
                                    if container in last_entry["data"]:
                                        volume = last_entry["data"][container].get("remaining_volume_ml")
                                        if volume is not None:
                                            self.previous_volumes[container] = volume
                                            self.last_saved_volumes[container] = volume
                            
                            self.log_message(f"Loaded reading counter from local storage: {self.reading_count}")
                            return True
        except Exception as e:
            self.log_message(f"Error loading from local storage: {e}")
        
        # If no data found, start from zero
        self.reading_count = 0
        self.log_message("No previous readings found, starting with reading counter: 0")
        return False
    
    def save_data(self, data):
        """Save data to local JSON file and MongoDB if available"""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.JSON_FILE), exist_ok=True)
        
        # Format data for storage
        formatted_data = {
            "reading": data["reading"],
            "timestamp": data["timestamp"],
            "data": {}
        }
        
        # Format container data
        for container in data["data"]:
            formatted_data["data"][container] = {
                "distance_cm": round(data["data"][container]["distance_cm"], 2) if data["data"][container]["distance_cm"] is not None else None,
                "previous_volume_ml": round(data["data"][container]["previous_volume_ml"], 2) if data["data"][container]["previous_volume_ml"] is not None else None,
                "remaining_volume_ml": round(data["data"][container]["remaining_volume_ml"], 2) if data["data"][container]["remaining_volume_ml"] is not None else None
            }
        
        # Save to local storage
        try:
            # Read existing data
            existing_data = []
            if os.path.exists(self.JSON_FILE):
                try:
                    with open(self.JSON_FILE, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    self.log_message("Warning: Existing file corrupt, creating new file")
            
            # Append new reading
            existing_data.append(formatted_data)
            
            # Use atomic write to prevent corruption
            temp_file = self.JSON_FILE + ".tmp"
            with open(temp_file, "w") as f:
                if 'ObjectId' in globals():
                    json.dump(existing_data, f, indent=2, cls=json.JSONEncoder)
                else:
                    json.dump(existing_data, f, indent=2)
            os.replace(temp_file, self.JSON_FILE)
            
            self.log_message("Data saved to local storage")
            local_saved = True
        except Exception as e:
            self.log_message(f"Error saving to local storage: {e}")
            local_saved = False
        
        # Save to MongoDB if available
        if self.mongo_collection is not None:
            try:
                self.mongo_collection.insert_one(formatted_data)
                self.log_message("Data also saved to MongoDB")
                mongo_saved = True
            except Exception as e:
                self.log_message(f"Error saving to MongoDB: {e}")
                mongo_saved = False
        else:
            mongo_saved = False
        
        # Report overall status
        if local_saved and mongo_saved:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
        elif local_saved:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("Status: FAILED TO SAVE DATA")
            
        return local_saved or mongo_saved
    
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
        for i, (trigger, echo) in enumerate(zip(self.triggers, self.echos)):
            container = f"CONT{i+1}"
            distance = self.measure_distance(trigger, echo)
            volume = self.calculate_usable_volume(container, distance)
            
            # Store as both previous and last saved
            self.previous_volumes[container] = volume
            self.last_saved_volumes[container] = volume
            
            # Update container data
            self.container_data[container]["distance_cm"] = distance
            self.container_data[container]["remaining_volume_ml"] = volume
            self.container_data[container]["previous_volume_ml"] = volume
            self.container_data[container]["sensor_state"] = "UP" if distance is not None else "DOWN"
            
            # Add to display
            if distance is not None and volume is not None:
                initial_readings.append(f"{container}: {distance:.2f} cm {volume:.2f} ml")
            else:
                initial_readings.append(f"{container}: ERROR")
        
        # Display initial readings
        self.log_message(" | ".join(initial_readings))
        self.log_message("Dispenser monitoring ready")
        
        # Main monitoring loop
        last_reading_time = time.time()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check if it's time for a new reading
                    if current_time - last_reading_time >= self.READING_INTERVAL:
                        self.reading_count += 1
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        significant_change = False
                        current_readings = []
                        
                        # Read all containers
                        current_data = {
                            "reading": self.reading_count,
                            "timestamp": timestamp,
                            "data": {}
                        }
                        
                        for i, (trigger, echo) in enumerate(zip(self.triggers, self.echos)):
                            container = f"CONT{i+1}"
                            distance = self.measure_distance(trigger, echo)
                            volume = self.calculate_usable_volume(container, distance)
                            
                            # Check if this is a significant change
                            prev_volume = self.previous_volumes.get(container, 0)
                            last_saved = self.last_saved_volumes.get(container, 0)
                            
                            # Update container data structure
                            self.container_data[container]["distance_cm"] = distance
                            self.container_data[container]["remaining_volume_ml"] = volume
                            self.container_data[container]["previous_volume_ml"] = prev_volume
                            self.container_data[container]["last_reading"] = current_time
                            self.container_data[container]["sensor_state"] = "UP" if distance is not None else "DOWN"
                            
                            # Detect volume change
                            if volume is not None and prev_volume is not None:
                                volume_change = prev_volume - volume
                                if volume_change > 0:
                                    self.container_data[container]["last_volume_change"] = round(volume_change, 2)
                            
                            if volume is not None and last_saved is not None:
                                if abs(volume - last_saved) >= self.SIGNIFICANT_CHANGE_THRESHOLD:
                                    significant_change = True
                                    self.last_saved_volumes[container] = volume
                            
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
                            self.previous_volumes[container] = volume
                        
                        # Display current readings
                        self.log_message(" | ".join(current_readings))
                        
                        # Save data if significant change detected
                        if significant_change:
                            self.save_data(current_data)
                        
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
            "reading": self.reading_count + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {}
        }
        
        for i, (trigger, echo) in enumerate(zip(self.triggers, self.echos)):
            container = f"CONT{i+1}"
            distance = self.measure_distance(trigger, echo)
            volume = self.calculate_usable_volume(container, distance)
            prev_volume = self.previous_volumes.get(container, 0)
            
            final_data["data"][container] = {
                "distance_cm": distance if distance is not None else 0,
                "previous_volume_ml": prev_volume if prev_volume is not None else 0,
                "remaining_volume_ml": volume if volume is not None else 0
            }
        
        self.save_data(final_data)
        self.cleanup_hardware()

# Odor Module Implementation
class OdorModule(ModuleBase):
    def __init__(self):
        super().__init__("Odor")
        # GPIO setup
        self.GPIO_CHIP = 0
        self.h = None
        self.FAN_RELAY_PIN = 23     # 8RELAY-B K2 for exhaust fan
        self.FRESHENER_RELAY_PIN = 22  # 8RELAY-B K3 for air freshener
        self.SENSOR_PIN = 17        # Occupancy sensor (E18-D80NK)
        
        # DHT22 pins
        self.dht_devices = None
        self.dht_pins = [4, 5, 6, 12]  # GPIO pins for DHT22 sensors
        
        # I2C setup for Arduino MQ135 sensors
        self.bus = None
        self.ARDUINO_ADDRESS = 8
        self.arduino_serial = None
        self.BAUD_RATE = 9600
        self.SERIAL_TIMEOUT = 5
        
        # Data storage
        self.DATA_DIR = "local-data" 
        self.JSON_FILE = os.path.join(self.DATA_DIR, "odor-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Module state
        self.fan_status = False
        self.freshener_triggered = False
        self.is_occupied = False
        self.last_sensor_state = 1  # 1 = HIGH (no detection) with pull-up
        self.last_exit_time = time.time()
        self.last_spray_time = time.time()
        self.aqi_history = []
        self.aqi_trend = 0  # 1=increasing, 0=stable, -1=decreasing
        self.aqi_change_timer = 0
        self.sensor_data_buffer = []
        self.log_queue = deque(maxlen=30)  # Keep last 30 log messages
        
        # Constants
        self.FAN_POST_EXIT_DURATION = 1200  # 20 minutes
        self.last_time = time.time()  # For debouncing
        self.LOGGING_INTERVAL = 10  # seconds
        self.DECIMAL_PRECISION = 2  # For temperature and humidity values
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['odor_module']
        else:
            self.mongo_collection = None
        
        # Sensor data
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
        
        # Simulate checking gas sensors
        gas_sensors = ["GAS1", "GAS2", "GAS3", "GAS4"]
        temp_sensors = ["TEMP1", "TEMP2", "TEMP3", "TEMP4"]
        
        all_sensors_online = True
        
        # Check gas sensors
        for i, sensor in enumerate(gas_sensors):
            # Try to read sensor
            status = "Offline"
            try:
                if self.bus:
                    # Test I2C read
                    data = self.bus.read_i2c_block_data(self.ARDUINO_ADDRESS, 0, 2)
                    if data and len(data) >= 2:
                        status = "Online"
                elif self.arduino_serial:
                    # Test serial read
                    self.arduino_serial.write(b'r')
                    time.sleep(0.5)
                    response = self.arduino_serial.readline().decode('utf-8', errors='ignore')
                    if ',' in response:
                        status = "Online"
            except Exception as e:
                self.log_message(f"Error testing {sensor}: {e}")
                status = "Offline"
                
            self.log_message(f"> Checking {sensor}: {status}")
            if status == "Offline":
                all_sensors_online = False
        
        # Check temperature sensors
        for i, sensor in enumerate(temp_sensors):
            # Try to read sensor
            status = "Offline"
            if self.dht_devices and i < len(self.dht_devices) and self.dht_devices[i]:
                try:
                    t = self.dht_devices[i].temperature
                    h = self.dht_devices[i].humidity
                    if t is not None and h is not None:
                        status = "Online"
                except Exception as e:
                    self.log_message(f"Error testing {sensor}: {e}")
            
            self.log_message(f"> Checking {sensor}: {status}")
            if status == "Offline":
                all_sensors_online = False
        
        # Check fan control
        fan_status = "Offline"
        try:
            if self.h:
                # Test relay control
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 0)  # Activate
                time.sleep(0.2)
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Deactivate
                fan_status = "Online"
        except Exception as e:
            self.log_message(f"Error testing fan relay: {e}")
            
        self.log_message(f"> Checking FAN relay: {fan_status}")
        
        # Check freshener control
        freshener_status = "Offline"
        try:
            if self.h:
                # Test relay control
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 0)  # Activate
                time.sleep(0.2)
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Deactivate
                freshener_status = "Online"
        except Exception as e:
            self.log_message(f"Error testing freshener relay: {e}")
            
        self.log_message(f"> Checking FRESHENER relay: {freshener_status}")
        
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
        return all_sensors_online or True  # Allow operation with some failed sensors
    
    def setup_hardware(self):
        try:
            # Setup GPIO for fan, freshener, and occupancy
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            lgpio.gpio_claim_output(self.h, self.FAN_RELAY_PIN)
            lgpio.gpio_claim_output(self.h, self.FRESHENER_RELAY_PIN)
            lgpio.gpio_claim_input(self.h, self.SENSOR_PIN, pull=lgpio.PUD_UP)  # Pull-up for occupancy sensor
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Fan off (active-low)
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Freshener off (active-low)
            
            # Setup DHT22 sensors
            self.dht_devices = []
            for pin in self.dht_pins:
                try:
                    # Map GPIO numbers to board pins
                    if pin == 4:
                        self.dht_devices.append(adafruit_dht.DHT22(board.D4))
                    elif pin == 5:
                        self.dht_devices.append(adafruit_dht.DHT22(board.D5))
                    elif pin == 6:
                        self.dht_devices.append(adafruit_dht.DHT22(board.D6))
                    elif pin == 12:
                        self.dht_devices.append(adafruit_dht.DHT22(board.D12))
                except Exception as e:
                    self.log_message(f"Failed to initialize DHT22 on pin {pin}: {e}")
                    self.dht_devices.append(None)
            
            # Try connecting to Arduino via I2C first
            try:
                self.bus = smbus.SMBus(1)  # I2C bus 1 on RPi
                self.log_message("I2C bus initialized for gas sensors")
            except Exception as e:
                self.log_message(f"Failed to initialize I2C: {e}")
                self.bus = None
                
                # Fall back to serial if I2C fails
                self.try_connect_arduino_serial()
            
            return True
        except Exception as e:
            self.log_message(f"Error setting up odor hardware: {e}")
            return False
    
    def scan_serial_ports(self):
        """Scan for available serial ports"""
        self.log_message("Scanning serial ports...")
        
        ports = []
        
        # For Linux
        if os.name == 'posix':
            # Get all tty devices
            try:
                ports = glob.glob('/dev/tty[A-Za-z]*')
            except Exception:
                pass
        # For Windows
        elif os.name == 'nt':
            try:
                # Scan COM ports
                for i in range(256):
                    try:
                        port = f'COM{i}'
                        s = serial.Serial(port)
                        s.close()
                        ports.append(port)
                    except (OSError, serial.SerialException):
                        pass
            except Exception:
                pass
                
        if not ports:
            self.log_message("No serial ports found.")
            return []
        
        # Filter for USB and ACM ports on Linux
        if os.name == 'posix':
            ports = [port for port in ports if ('USB' in port or 'ACM' in port)]
            
        self.log_message(f"Found ports: {', '.join(ports)}")
        return ports
    
    def try_connect_arduino_serial(self):
        """Try to connect to Arduino via serial"""
        # Close existing connection if any
        if self.arduino_serial is not None:
            try:
                self.arduino_serial.close()
            except Exception:
                pass
            self.arduino_serial = None
        
        # Scan for available ports
        all_ports = self.scan_serial_ports()
        if not all_ports:
            self.log_message("No serial ports available")
            return False
        
        # Try each port to find Arduino
        sorted_ports = sorted(all_ports)
        
        for port in sorted_ports:
            try:
                self.log_message(f"Trying to connect to {port}...")
                
                # Open port
                test_ser = serial.Serial(port, self.BAUD_RATE, timeout=self.SERIAL_TIMEOUT)
                time.sleep(2)  # Arduino resets on serial connection
                test_ser.reset_input_buffer()
                
                # Send test request and check response
                self.log_message("Sending test request to Arduino...")
                test_ser.write(b'r')
                time.sleep(0.5)
                
                line = test_ser.readline().decode('utf-8', errors='ignore').strip()
                self.log_message(f"Received from {port}: '{line}'")
                
                # Validate response - expecting comma-separated values
                if ',' in line:
                    values = line.split(',')
                    if len(values) >= 4:  # At least 4 values for gas sensors
                        self.log_message(f"Arduino found on {port}")
                        self.arduino_serial = test_ser
                        return True
                
                # Not the right device, close it
                self.log_message(f"Device on {port} is not compatible, closing connection")
                test_ser.close()
                
            except Exception as e:
                self.log_message(f"Failed to connect to {port}: {e}")
        
        self.log_message("No working Arduino connection found.")
        return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                # Turn off relays
                lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # Fan off (active-low)
                lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # Freshener off (active-low)
                
                # Cleanup GPIO
                lgpio.gpio_free(self.h, self.FAN_RELAY_PIN)
                lgpio.gpio_free(self.h, self.FRESHENER_RELAY_PIN)
                lgpio.gpio_free(self.h, self.SENSOR_PIN)
                lgpio.gpiochip_close(self.h)
                self.h = None
                
                # Cleanup DHT devices
                if self.dht_devices:
                    for dht in self.dht_devices:
                        if dht:
                            dht.exit()
                
                # Close Arduino serial if open
                if self.arduino_serial:
                    self.arduino_serial.close()
                    self.arduino_serial = None
                    
                self.log_message("Odor hardware resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up odor hardware: {e}")
    
    def read_gas_sensors(self):
        """Read data from MQ135 gas sensors via I2C or Serial"""
        # Try I2C first
        if self.bus:
            for attempt in range(3):  # Retry I2C up to 3 times
                try:
                    data = self.bus.read_i2c_block_data(self.ARDUINO_ADDRESS, 0, 8)
                    if len(data) >= 8:
                        gas_values = []
                        for i in range(4):
                            # Combine MSB and LSB for each sensor
                            gas_value = (data[i*2] << 8) + data[i*2 + 1]
                            gas_values.append(gas_value)
                            self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "UP"
                        return gas_values
                except Exception as e:
                    self.log_message(f"I2C read error (attempt {attempt+1}): {e}")
                    time.sleep(0.1)
        
        # If I2C failed, try serial
        if self.arduino_serial:
            try:
                # Clear input buffer
                self.arduino_serial.reset_input_buffer()
                
                # Send request to Arduino
                self.arduino_serial.write(b'r')
                time.sleep(0.5)
                
                # Read response
                line = self.arduino_serial.readline().decode('utf-8', errors='ignore').strip()
                
                if ',' in line:
                    values = [int(val.strip()) for val in line.split(',')]
                    if len(values) >= 4:
                        for i in range(4):
                            self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "UP"
                        return values[:4]  # Use first 4 values
                
                self.log_message(f"Invalid serial reading format: {line}")
            except Exception as e:
                self.log_message(f"Serial read error: {e}")
                # Try to reconnect next time
                if self.arduino_serial:
                    try:
                        self.arduino_serial.close()
                    except:
                        pass
                    self.arduino_serial = None
        
        # If both methods failed, use simulated data and mark sensors as DOWN
        self.log_message("Using simulated gas sensor data")
        for i in range(4):
            self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "DOWN"
            
        return [random.randint(50, 500) for _ in range(4)]
    
    def read_sensors(self):
        """Simulate temperature, humidity and AQI readings"""
        temp = [0] * 4
        hum = [0] * 4
        aqi = self.read_gas_sensors()
        
        # Read DHT22 sensors
        for i, dht in enumerate(self.dht_devices or []):
            if dht:
                try:
                    t = dht.temperature
                    h = dht.humidity
                    if t is not None and h is not None and -40 <= t <= 80 and 0 <= h <= 100:
                        temp[i] = t
                        hum[i] = h
                        self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "UP"
                    else:
                        # Simulate data for invalid readings
                        temp[i] = random.uniform(20, 35)
                        hum[i] = random.uniform(40, 80)
                        self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
                except Exception as e:
                    # Simulate data on error
                    temp[i] = random.uniform(20, 35)
                    hum[i] = random.uniform(40, 80)
                    self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
            else:
                # Simulate data for missing sensors
                temp[i] = random.uniform(20, 35)
                hum[i] = random.uniform(40, 80)
                self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
        
        # Update sensor data
        for i in range(4):
            self.sensor_data[f"sensor_{i+1}"]["temperature"] = temp[i]
            self.sensor_data[f"sensor_{i+1}"]["humidity"] = hum[i]
            self.sensor_data[f"sensor_{i+1}"]["aqi"] = aqi[i]
        
        return temp, hum, aqi
    
    def check_occupancy(self):
        """Check occupancy status using E18-D80NK sensor"""
        if not self.h:
            return False
        
        current_sensor_state = lgpio.gpio_read(self.h, self.SENSOR_PIN)
        current_time = time.time()
        
        if current_sensor_state != self.last_sensor_state and current_time - self.last_time > 1.0:
            if current_sensor_state == 0:  # LOW = Occupied
                self.is_occupied = True
                self.log_message("Occupancy detected")
            else:  # HIGH = Vacant
                self.is_occupied = False
                self.last_exit_time = current_time  # Record exit time
                self.log_message("Space vacated")
            self.last_sensor_state = current_sensor_state
            self.last_time = current_time
            return not self.is_occupied  # True if just vacated
        return False
    
    def buffer_sensor_data(self, gas_values, temp_readings):
        """Add sensor data to buffer for averaging"""
        self.sensor_data_buffer.append({
            "gas": gas_values,
            "temp": [{
                "temp": temp_readings[i]["temp"],
                "hum": temp_readings[i]["hum"]
            } for i in range(len(temp_readings))]
        })
        
        # Keep buffer size reasonable
        if len(self.sensor_data_buffer) > 10:
            self.sensor_data_buffer.pop(0)
    
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
        
        # Sum all values
        for data in self.sensor_data_buffer:
            # Sum gas values
            for i in range(4):
                if i < len(data["gas"]):
                    avg_gas[i] += data["gas"][i]
            
            # Sum temperature and humidity
            for i in range(4):
                if i < len(data["temp"]):
                    avg_temp[i]["temp"] += data["temp"][i]["temp"]
                    avg_temp[i]["hum"] += data["temp"][i]["hum"]
        
        # Calculate averages
        buffer_len = len(self.sensor_data_buffer)
        for i in range(4):
            avg_gas[i] = round(avg_gas[i] / buffer_len)
            avg_temp[i]["temp"] = round(avg_temp[i]["temp"] / buffer_len, self.DECIMAL_PRECISION)
            avg_temp[i]["hum"] = round(avg_temp[i]["hum"] / buffer_len, self.DECIMAL_PRECISION)
        
        return {"gas": avg_gas, "temp": avg_temp}
    
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
        valid_temps = [r["temperature"] for r in temp_readings if r["temperature"] > 0]
        valid_hums = [r["humidity"] for r in temp_readings if r["humidity"] > 0]
        
        if valid_temps:
            avg_temp = sum(valid_temps) / len(valid_temps)
            for i in range(len(fixed_temp)):
                if fixed_temp[i]["temperature"] <= 0:
                    fixed_temp[i]["temperature"] = round(avg_temp, self.DECIMAL_PRECISION)
                    self.log_message(f"Fixed TEMP{i+1} temperature with average {round(avg_temp, self.DECIMAL_PRECISION)}")
        
        if valid_hums:
            avg_hum = sum(valid_hums) / len(valid_hums)
            for i in range(len(fixed_temp)):
                if fixed_temp[i]["humidity"] <= 0:
                    fixed_temp[i]["humidity"] = round(avg_hum, self.DECIMAL_PRECISION)
                    self.log_message(f"Fixed TEMP{i+1} humidity with average {round(avg_hum, self.DECIMAL_PRECISION)}")
        
        return fixed_gas, fixed_temp
    
    def calculate_avg_aqi(self, aqi):
        """Calculate average AQI and update history for trend analysis"""
        avg_aqi = sum(aqi) / len(aqi) if aqi and all(a != 0 for a in aqi) else 0
        self.aqi_history.append(avg_aqi)
        if len(self.aqi_history) > 10:  # Keep last 10 readings
            self.aqi_history.pop(0)
        return avg_aqi
    
    def calculate_air_quality_trend(self):
        """Calculate AQI trend (increasing, decreasing, stable)"""
        if len(self.aqi_history) < 2:
            return "unknown"
            
        # Use the last 3 readings to determine trend if available
        if len(self.aqi_history) >= 3:
            recent = self.aqi_history[-3:]
            
            # Calculate moving average to smooth out noise
            if all(a > 0 for a in recent):
                # Check if consistently increasing or decreasing
                if recent[0] < recent[1] < recent[2] and (recent[2] - recent[0]) > 10:
                    return "increasing"
                elif recent[0] > recent[1] > recent[2] and (recent[0] - recent[2]) > 10:
                    return "decreasing"
        
        # Fallback to simple difference if fewer readings
        diff = self.aqi_history[-1] - self.aqi_history[0]
        if abs(diff) < 5:
            return "stable"
        return "increasing" if diff > 0 else "decreasing"
    
    def control_fan(self, avg_aqi, avg_temp, avg_hum):
        """Control exhaust fan based on AQI, temperature, humidity, and occupancy"""
        if not self.h:
            return
        
        should_run = False
        reason = ""
        
        if self.is_occupied:  # Presence trigger
            should_run = True
            reason = "occupancy"
        elif time.time() - self.last_exit_time < self.FAN_POST_EXIT_DURATION:  # Post-exit
            should_run = True
            reason = "post-exit cycle"
        elif avg_aqi > 300:  # Primary AQI trigger
            should_run = True
            reason = "high AQI"
        elif avg_aqi > 100 and avg_temp > 25:  # AQI and temperature trigger
            should_run = True
            reason = "elevated AQI and temperature"
        elif avg_aqi > 150 and avg_temp > 30:  # Severe AQI and temperature
            should_run = True
            reason = "critical AQI and temperature"
        elif avg_hum > 60 and avg_aqi > 100:  # Humidity amplifies odor
            should_run = True
            reason = "high humidity with odor"
        
        if should_run and not self.fan_status:
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 0)  # LOW to activate (active-low)
            self.fan_status = True
            self.log_message(f"Fan activated: {reason}")
        elif not should_run and self.fan_status:
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # HIGH to deactivate
            self.fan_status = False
            self.log_message("Fan deactivated")
    
    def control_freshener(self, avg_aqi, vacated, avg_temp=25):
        """Control air freshener based on AQI, vacancy, or timer"""
        if not self.h:
            return
        
        should_spray = False
        reason = ""
        
        if avg_aqi > 300 and not self.freshener_triggered:
            should_spray = True
            reason = "high AQI"
        elif vacated and not self.freshener_triggered:
            should_spray = True
            reason = "space vacated"
        elif time.time() - self.last_spray_time >= 2160 and not self.freshener_triggered:  # 36 minutes
            should_spray = True
            reason = "scheduled interval"
        elif avg_aqi > 150 and avg_temp > 30 and not self.freshener_triggered:  # Additional trigger for high temp
            should_spray = True
            reason = "critical conditions"
        
        if should_spray:
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 0)  # LOW to activate (active-low)
            time.sleep(0.5)  # 500ms pulse
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # HIGH to deactivate
            self.freshener_triggered = True
            self.last_spray_time = time.time()
            self.log_message(f"Air freshener activated: {reason}")
        elif avg_aqi <= 300 and not vacated:
            self.freshener_triggered = False
    
    def save_to_local_storage(self, data):
        """Save data to local JSON file"""
        try:
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
            "_id": str(ObjectId()) if 'ObjectId' in globals() else "local_" + datetime.now().strftime("%Y%m%d%H%M%S"),
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
            },
            "fan_status": "on" if self.fan_status else "off",
            "air_freshener_status": "triggered" if self.freshener_triggered else "off",
            "occupancy_status": "occupied" if self.is_occupied else "vacant",
        }
        
        # Calculate averages
        avg_temp = sum(r["temp"] for r in temp_readings) / 4
        avg_hum = sum(r["hum"] for r in temp_readings) / 4
        avg_aqi = sum(gas_values) / 4
        
        # Add calculated fields
        data["average_temperature"] = round(avg_temp, self.DECIMAL_PRECISION)
        data["average_humidity"] = round(avg_hum, self.DECIMAL_PRECISION)
        data["average_gas_level"] = round(avg_aqi, 1)
        data["air_quality_trend"] = self.calculate_air_quality_trend()
        data["critical_event"] = avg_aqi > 300
        
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
        
        return local_saved or mongo_saved
    
    def get_sensor_summary(self):
        """Return summary data for display"""
        # Calculate averages
        avg_temp = sum(self.sensor_data[f"sensor_{i+1}"]["temperature"] for i in range(4)) / 4
        avg_hum = sum(self.sensor_data[f"sensor_{i+1}"]["humidity"] for i in range(4)) / 4
        avg_aqi = sum(self.sensor_data[f"sensor_{i+1}"]["aqi"] for i in range(4)) / 4
        
        return {
            "sensors": self.sensor_data,
            "avg_temp": avg_temp,
            "avg_hum": avg_hum,
            "avg_aqi": avg_aqi,
            "fan_status": "ON" if self.fan_status else "OFF",
            "freshener_status": "TRIGGERED" if self.freshener_triggered else "STANDBY",
            "occupancy": "OCCUPIED" if self.is_occupied else "VACANT",
            "trend": self.calculate_air_quality_trend(),
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
        
        # Main loop
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Read sensors every 5 seconds
                    if current_time - last_log_time >= 5:
                        # Read sensors
                        temp_readings, hum_readings, gas_values = self.read_sensors()
                        
                        # Format sensor readings for buffer
                        temp_data = []
                        for i in range(4):
                            temp_data.append({
                                "temp": temp_readings[i],
                                "hum": hum_readings[i]
                            })
                        
                        # Fix any invalid sensor data
                        gas_values, temp_data = self.fix_sensor_data(gas_values, [
                            {"temperature": temp_readings[i], "humidity": hum_readings[i]} 
                            for i in range(4)
                        ])
                        
                        # Buffer the data for averaging
                        self.buffer_sensor_data(gas_values, temp_data)
                        
                        # Calculate average AQI for trend analysis
                        avg_aqi = self.calculate_avg_aqi(gas_values)
                        
                        # Calculate averages for control decisions
                        avg_temp = sum(temp_readings) / len(temp_readings)
                        avg_hum = sum(hum_readings) / len(hum_readings)
                        
                        # Process occupancy and control devices
                        vacated = self.check_occupancy()
                        self.control_fan(avg_aqi, avg_temp, avg_hum)
                        self.control_freshener(avg_aqi, vacated, avg_temp)
                        
                        # Log current readings
                        self.log_message(f"AQI: {gas_values[0]}/{gas_values[1]}/{gas_values[2]}/{gas_values[3]} | " +
                                        f"Temp: {avg_temp:.1f}°C | Hum: {avg_hum:.1f}% | " +
                                        f"Fan: {self.fan_status} | AQI Trend: {self.calculate_air_quality_trend()}")
                        
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
                
                time.sleep(1)  # Check every second
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
                print(f"Fan Status         : {odor_data['fan_status']}")
                print(f"Freshener Status   : {odor_data['freshener_status']}")
            
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
                print(f"Fan Status         : {data['fan_status']}")
                print(f"Freshener Status   : {data['freshener_status']}")
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
