#!/usr/bin/env python3

import time
import os
import sys
import json
import threading
import signal
import random
from datetime import datetime
import psutil
from tabulate import tabulate

# Constants for simulation
SIMULATION_INTERVAL = 5  # seconds between simulated data updates
DATA_DIR = "./data/debug"

# Custom debug handler to capture debug messages
class DebugHandler:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugHandler, cls).__new__(cls)
            cls._instance.messages = []
            cls._instance.enabled = True
        return cls._instance
    
    def log(self, message):
        """Add a message to the debug log"""
        if self.enabled:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.messages.append(f"[{timestamp}] {message}")
            if len(self.messages) > 100:  # Keep last 100 messages
                self.messages.pop(0)
    
    def disable(self):
        """Disable debug logging"""
        self.enabled = False
    
    def enable(self):
        """Enable debug logging"""
        self.enabled = True
    
    def get_messages(self):
        """Get all debug messages"""
        return self.messages
    
    def clear(self):
        """Clear all debug messages"""
        self.messages.clear()

# Create a global instance
debug_handler = DebugHandler()

# Override the built-in print function for debug messages
original_print = print
def debug_print(*args, **kwargs):
    message = " ".join(map(str, args))
    if message.startswith("[DEBUG]"):
        debug_handler.log(message[8:].strip())  # Remove "[DEBUG]" prefix and strip whitespace
    else:
        original_print(*args, **kwargs)

# Replace the built-in print with our custom function
print = debug_print


# Mock classes to replace hardware-dependent libraries
class MockLGPIO:
    def gpiochip_open(self, chip):
        debug_handler.log(f"GPIO chip {chip} opened")
        return chip
    
    def gpiochip_close(self, handle):
        debug_handler.log(f"GPIO chip {handle} closed")
    
    def gpio_claim_output(self, handle, pin):
        debug_handler.log(f"GPIO pin {pin} claimed as output")
    
    def gpio_claim_input(self, handle, pin, pull=None):
        debug_handler.log(f"GPIO pin {pin} claimed as input with pull={pull}")
    
    def gpio_write(self, handle, pin, value):
        debug_handler.log(f"GPIO pin {pin} set to {value}")
    
    def gpio_read(self, handle, pin):
        # Simulate random sensor readings
        return random.choice([0, 1])
    
    def gpio_free(self, handle, pin):
        debug_handler.log(f"GPIO pin {pin} freed")
    
    # Constants to simulate pull-up resistors
    SET_PULL_UP = 1
    PUD_UP = 2


class MockDHT:
    def __init__(self, pin):
        self.pin = pin
        self.temperature = random.uniform(20, 35)  # °C
        self.humidity = random.uniform(30, 80)     # %
    
    def exit(self):
        print(f"[DEBUG] DHT sensor on pin {self.pin} exited")


class MockBoard:
    D4 = 4
    D5 = 5
    D6 = 6
    D12 = 12


class MockSMBus:
    def __init__(self, bus):
        self.bus = bus
    
    def read_i2c_block_data(self, address, register, length):
        # Generate random sensor values (2 bytes per sensor)
        data = []
        for _ in range(length // 2):
            val = random.randint(50, 800)  # Random AQI value
            data.extend([(val >> 8) & 0xFF, val & 0xFF])  # MSB, LSB
        return data


class MockMongoClient:
    def __init__(self, uri=None):
        self.uri = uri
        print(f"[DEBUG] MongoDB client created with URI: {uri}")
    
    def __getitem__(self, db_name):
        print(f"[DEBUG] Accessing database: {db_name}")
        return MockDB(db_name)
    
    def close(self):
        print("[DEBUG] MongoDB connection closed")


class MockDB:
    def __init__(self, name):
        self.name = name
    
    def __getitem__(self, collection_name):
        debug_handler.log(f"Accessing collection: {collection_name}")
        return MockCollection(collection_name)


class MockCollection:
    def __init__(self, name):
        self.name = name
    
    def insert_one(self, document):
        print(f"[DEBUG] Inserted document into {self.name}: {document}")
        return {"inserted_id": "mock_id_" + str(random.randint(1000, 9999))}


# Mock imports
lgpio = MockLGPIO()
adafruit_dht = MockDHT
board = MockBoard()
smbus = MockSMBus


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
        # GPIO setup - simulated
        self.SENSOR_PIN = 17  # E18-D80NK signal
        self.BUZZER_PIN = 27  # Buzzer control
        self.chip = None
        
        # States
        self.STATE_VACANT = "Vacant"
        self.STATE_OCCUPIED = "Occupied"
        self.current_state = self.STATE_VACANT
        self.visitor_count = 0
        self.log_list = []
        self.current_start_time = None
        self.last_state_change_time = time.time()
        self.detection_start = None
        
        # MongoDB collection
        self.mongo_collection = None
        
        # Local data storage
        self.DATA_DIR = DATA_DIR
        self.JSON_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Constants
        self.DEBOUNCE_TIME = 0.5  # 500ms
        self.SHORT_BEEP = 0.2     # 200ms
        self.LONG_BEEP = 1.0      # 1s
        
        # Simulation variables
        self.simulation_timer = 0
        self.simulation_state_duration = random.randint(30, 120)  # Random duration for state
    
    def perform_post_check(self):
        """Perform Power-On Self Test to verify all components are working"""
        print("\nConnected to the MongoDB successfully")
        print("Initializing Occupancy Module")
        
        # Check proximity sensor
        proximity_status = "Online"
        if self.chip:
            try:
                # Simulate reading from sensor
                sensor_value = random.choice([0, 1])  # Random value for simulation
                proximity_status = "Online" if sensor_value in [0, 1] else "Offline"
            except:
                proximity_status = "Offline"
        else:
            proximity_status = "Offline"
        print(f"> Checking Proximity Sensor: {proximity_status}")
        
        # Check buzzer
        buzzer_status = "Online"
        if self.chip:
            try:
                # Simulate buzzer check
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 1)
                time.sleep(0.1)
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)
                buzzer_status = "Online"
            except:
                buzzer_status = "Offline"
        else:
            buzzer_status = "Offline"
        print(f"> Checking Buzzer: {buzzer_status}")
        
        return proximity_status == "Online" and buzzer_status == "Online"
    
    def setup_hardware(self):
        try:
            self.chip = lgpio.gpiochip_open(0)  # Simulated
            return True
        except Exception as e:
            print(f"Error setting up occupancy hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.chip:
            try:
                lgpio.gpiochip_close(self.chip)
                self.chip = None
            except Exception as e:
                print(f"Error cleaning up occupancy hardware: {e}")
    
    def beep_buzzer(self, duration):
        print(f"[DEBUG] Beep buzzer for {duration}s")
    
    def double_beep(self):
        print("[DEBUG] Double beep")
    
    def format_duration(self, seconds):
        """Format seconds into a readable duration string"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}min {secs}sec"
    
    def read_json(self):
        try:
            if os.path.exists(self.JSON_FILE):
                with open(self.JSON_FILE, "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading JSON: {e}")
        return {"visitors": [], "summary": {"total_visitors": 0, "average_duration": 0}, "current_presence": False}
    
    def write_json(self, data):
        os.makedirs(os.path.dirname(self.JSON_FILE), exist_ok=True)
        try:
            with open(self.JSON_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"Error writing JSON: {e}")
    
    def update_mongo(self, entry):
        print(f"[DEBUG] MongoDB update: {entry}")
    
    def load_initial_state(self):
        data = self.read_json()
        self.log_list = data.get("visitors", [])
        if self.log_list:
            self.visitor_count = max(entry["visitor_id"] for entry in self.log_list)
            ongoing_visit = next((entry for entry in self.log_list if "end_time" not in entry), None)
            if ongoing_visit:
                self.current_state = self.STATE_OCCUPIED
                self.current_start_time = float(ongoing_visit["start_time"])
        else:
            self.visitor_count = 0
    
    def update_log(self, new_entry=None):
        if new_entry:
            self.log_list.append(new_entry)
            self.update_mongo(new_entry)
        
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
            "sensor_state": "UP" if self.chip else "DOWN"
        }
    
    def run(self):
        if not self.setup_hardware():
            print("Failed to initialize occupancy hardware. Module not started.")
            self.running = False
            return
        
        # Perform POST check
        self.perform_post_check()
        
        # Load initial state
        self.load_initial_state()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Simulate occupancy state changes every random interval
                    self.simulation_timer += SIMULATION_INTERVAL
                    if self.simulation_timer >= self.simulation_state_duration:
                        self.simulation_timer = 0
                        self.simulation_state_duration = random.randint(30, 120)
                        
                        if self.current_state == self.STATE_VACANT:
                            # Simulate person entering
                            self.current_state = self.STATE_OCCUPIED
                            self.visitor_count += 1
                            self.current_start_time = current_time
                            new_entry = {
                                "visitor_id": self.visitor_count,
                                "start_time": current_time,
                                "start_time_iso": datetime.fromtimestamp(current_time).isoformat()
                            }
                            self.double_beep()
                            self.update_log(new_entry)
                            print(f"[DEBUG] Person entered. Visitor #{self.visitor_count}")
                            
                        else:
                            # Simulate person leaving
                            self.current_state = self.STATE_VACANT
                            end_time = current_time
                            duration = end_time - self.current_start_time
                            
                            # Find the active visit and mark it as ended
                            for entry in self.log_list:
                                if "end_time" not in entry:
                                    entry["end_time"] = end_time
                                    entry["duration"] = duration
                                    entry["end_time_iso"] = datetime.fromtimestamp(end_time).isoformat()
                                    break
                                    
                            self.beep_buzzer(self.LONG_BEEP)
                            self.update_log()
                            print(f"[DEBUG] Person left. Duration: {self.format_duration(duration)}")
                    
                except Exception as e:
                    print(f"Error in occupancy module: {e}")
            
            time.sleep(SIMULATION_INTERVAL)
        
        self.cleanup_hardware()


# Dispenser Module Implementation
class DispenserModule(ModuleBase):
    def __init__(self):
        super().__init__("Dispenser")
        # GPIO setup - simulated
        self.GPIO_CHIP = 0
        self.h = None
        self.triggers = [7, 9, 11, 14]  # GPIO pins for ultrasonic triggers
        self.echos = [8, 10, 13, 15]    # GPIO pins for ultrasonic echos
        
        # MongoDB collection - simulated
        self.mongo_collection = None
        
        # Container calibration data
        self.CALIBRATION_DATA = {
            "CONT1": {"full": 2.84, "empty": 12.67},
            "CONT2": {"full": 2.37, "empty": 12.21},
            "CONT3": {"full": 2.23, "empty": 12.33},
            "CONT4": {"full": 2.91, "empty": 12.88}
        }
        
        # Container data - initial values
        self.container_data = {
            f"CONT{i+1}": {
                "distance_cm": random.uniform(2.0, 12.0),
                "remaining_volume_ml": random.uniform(50, 425),
                "last_reading": time.time(),
                "last_volume_change": 0,
                "sensor_state": "UP"
            } for i in range(4)
        }
        
        self.reading_count = 0
        self.usage_simulation = [10, 20, 5, 15]  # ml used per interval per container
    
    def perform_post_check(self):
        """Perform Power-On Self Test to verify all components are working"""
        print("\nConnected to the MongoDB successfully")
        print("Initializing Dispenser Module")
        
        # Check ultrasonic sensors
        for i in range(4):
            sonic_status = "Offline"
            if self.h:
                try:
                    # Simulate ultrasonic sensor check
                    # In real implementation, we'd send a trigger pulse and check for echo
                    trigger_pin = self.triggers[i]
                    echo_pin = self.echos[i]
                    
                    # Simulate successful reading
                    pulse_duration = random.uniform(0.001, 0.02)  # Simulate echo time
                    distance = pulse_duration * 17150  # Convert to distance
                    
                    if 2 <= distance <= 400:  # Valid range for HC-SR04
                        sonic_status = "Online"
                except:
                    pass
            print(f"> Checking SONIC{i+1}: {sonic_status}")
        
        # Return overall status
        return all(self.container_data[f"CONT{i+1}"]["sensor_state"] == "UP" for i in range(4))
    
    def setup_hardware(self):
        try:
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)  # Simulated
            return True
        except Exception as e:
            print(f"Error setting up dispenser hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                lgpio.gpiochip_close(self.h)
                self.h = None
            except Exception as e:
                print(f"Error cleaning up dispenser hardware: {e}")
    
    def measure_raw_data(self, trigger, echo, num_measurements=5):
        # Simulated measurement
        distance = random.uniform(2.0, 12.0)
        pulse_duration = distance / 17150.0
        return pulse_duration, distance
    
    def calculate_usable_volume(self, container, distance):
        """Calculate usable volume based on distance and calibration data"""
        if self.CALIBRATION_DATA[container]["full"] is None or self.CALIBRATION_DATA[container]["empty"] is None:
            return None
        
        full_distance = self.CALIBRATION_DATA[container]["full"]
        empty_distance = self.CALIBRATION_DATA[container]["empty"]
        
        if distance <= full_distance:
            return 425.0  # Full usable volume
        elif distance >= empty_distance:
            return 0.0    # Empty usable volume
        else:
            # Linear interpolation for usable volume
            total_distance_range = empty_distance - full_distance
            distance_from_full = distance - full_distance
            volume_fraction = 1 - (distance_from_full / total_distance_range)
            usable_volume = 425.0 * volume_fraction
            return round(usable_volume, 2)
    
    def get_container_summary(self):
        """Get summary data for all containers"""
        return self.container_data
    
    def run(self):
        if not self.setup_hardware():
            print("Failed to initialize dispenser hardware. Module not started.")
            self.running = False
            return
            
        # Perform POST check
        self.perform_post_check()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    self.reading_count += 1
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Simulate dispenser usage
                    for i in range(4):
                        container = f"CONT{i+1}"
                        # Simulate distance change
                        old_volume = self.container_data[container]["remaining_volume_ml"]
                        
                        # Simulate usage with 30% probability
                        if random.random() < 0.3:
                            usage = random.choice([0, self.usage_simulation[i]])
                            new_volume = max(0, old_volume - usage)
                            self.container_data[container]["remaining_volume_ml"] = new_volume
                            self.container_data[container]["last_volume_change"] = usage if usage > 0 else 0
                            
                            # Calculate new distance based on volume
                            full_dist = self.CALIBRATION_DATA[container]["full"]
                            empty_dist = self.CALIBRATION_DATA[container]["empty"]
                            volume_fraction = new_volume / 425.0
                            new_distance = empty_dist - volume_fraction * (empty_dist - full_dist)
                            self.container_data[container]["distance_cm"] = new_distance
                            
                            print(f"[DEBUG] Container {i+1} used {usage}ml, remaining: {new_volume}ml")
                        
                        self.container_data[container]["last_reading"] = time.time()
                    
                except Exception as e:
                    print(f"Error in dispenser module: {e}")
                
                time.sleep(SIMULATION_INTERVAL)  # Update every SIMULATION_INTERVAL seconds
            else:
                time.sleep(1)
        
        self.cleanup_hardware()


# Odor Module Implementation
class OdorModule(ModuleBase):
    def __init__(self):
        super().__init__("Odor")
        # GPIO setup - simulated
        self.MQ135_PIN = 0  # Analog pin for MQ-135
        self.DHT22_PIN = 4  # DHT22 signal pin
        self.AC_PIN = 23    # AC fan control
        self.DC_PIN = 24    # DC fan control
        self.FAN_STATUS_PIN = 25  # Fan status LED
        self.chip = None
        
        # Sensor values
        self.temperature = 0
        self.humidity = 0
        self.gas_level = 0
        self.gas_threshold = 700
        self.temp_threshold = 30
        self.humid_threshold = 70
        
        # Fan control
        self.fan_speed = 0
        self.fan_auto = True
        
        # Status
        self.status_code = 0  # 0: Normal, 1: High Gas, 2: High Temp, 3: Both
        self.odor_level = "Normal"  # Normal, Moderate, High
        
        # Simulation variables
        self.simulation_timer = 0
        
        # Initialize missing attributes
        self.aqi_change_timer = 0
        self.aqi_trend = 0
        self.aqi_history = []
        self.is_occupied = False
        self.last_exit_time = time.time()
        self.FAN_POST_EXIT_DURATION = 300  # 5 minutes
        self.fan_status = False
        self.freshener_triggered = False
        self.last_spray_time = time.time()
        
        # Initialize sensor data
        self.sensor_data = {
            f"sensor_{i+1}": {
                "temperature": random.uniform(20, 30),
                "humidity": random.uniform(40, 70),
                "aqi": random.uniform(100, 300),
                "temp_status": "Online",
                "gas_status": "Online"
            } for i in range(4)
        }
    
    def perform_post_check(self):
        """Perform Power-On Self Test to verify all sensors are working"""
        print("\nConnected to the MongoDB successfully")
        print("Initializing Odor Module")
        
        # Simulate checking gas sensors
        gas_sensors = ["GAS1", "GAS2", "GAS3", "GAS4"]
        temp_sensors = ["TEMP1", "TEMP2", "TEMP3", "TEMP4"]
        
        all_sensors_online = True
        
        # Check gas sensors
        for sensor in gas_sensors:
            # Simulate sensor check
            status = "Online" if random.random() > 0.1 else "Offline"
            print(f"> Checking {sensor}: {status}")
            if status == "Offline":
                all_sensors_online = False
        
        # Check temperature sensors
        for sensor in temp_sensors:
            # Simulate sensor check
            status = "Online" if random.random() > 0.1 else "Offline"
            print(f"> Checking {sensor}: {status}")
            if status == "Offline":
                all_sensors_online = False
        
        return all_sensors_online
    
    def setup_hardware(self):
        try:
            self.chip = lgpio.gpiochip_open(0)  # Simulated
            return True
        except Exception as e:
            print(f"Error setting up odor hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.chip:
            try:
                lgpio.gpiochip_close(self.chip)
                self.chip = None
            except Exception as e:
                print(f"Error cleaning up odor hardware: {e}")
    
    def read_sensors(self):
        """Simulate temperature, humidity and AQI readings"""
        temp = [0] * 4
        hum = [0] * 4
        aqi = [0] * 4
        
        # Update AQI trend occasionally
        self.aqi_change_timer += 1
        if self.aqi_change_timer >= 5:
            self.aqi_change_timer = 0
            self.aqi_trend = random.choice([-1, 0, 0, 1])  # More likely to be stable
        
        # Simulate sensor readings
        for i in range(4):
            # Temperature simulation (20-35°C)
            temp_change = random.uniform(-0.5, 0.5)
            new_temp = self.sensor_data[f"sensor_{i+1}"]["temperature"] + temp_change
            new_temp = max(18, min(40, new_temp))  # Keep within reasonable range
            temp[i] = new_temp
            
            # Humidity simulation (30-80%)
            hum_change = random.uniform(-1, 1)
            new_hum = self.sensor_data[f"sensor_{i+1}"]["humidity"] + hum_change
            new_hum = max(20, min(90, new_hum))  # Keep within reasonable range
            hum[i] = new_hum
            
            # AQI simulation (50-500)
            base_change = random.uniform(-10, 10)
            trend_change = 0
            if self.aqi_trend == 1:
                trend_change = random.uniform(5, 20)
            elif self.aqi_trend == -1:
                trend_change = random.uniform(-20, -5)
                
            new_aqi = self.sensor_data[f"sensor_{i+1}"]["aqi"] + base_change + trend_change
            new_aqi = max(50, min(800, new_aqi))  # Keep within reasonable range
            aqi[i] = int(new_aqi)
            
            # Update sensor data
            self.sensor_data[f"sensor_{i+1}"]["temperature"] = temp[i]
            self.sensor_data[f"sensor_{i+1}"]["humidity"] = hum[i]
            self.sensor_data[f"sensor_{i+1}"]["aqi"] = aqi[i]
        
        return temp, hum, aqi
    
    def check_occupancy(self):
        """Simulate occupancy detection"""
        # 5% chance of state change
        if random.random() < 0.05:
            old_state = self.is_occupied
            self.is_occupied = not self.is_occupied
            if old_state and not self.is_occupied:
                self.last_exit_time = time.time()
                return True  # Just vacated
        return False
    
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
        diff = self.aqi_history[-1] - self.aqi_history[-2]
        return "increasing" if diff > 5 else "decreasing" if diff < -5 else "stable"
    
    def control_fan(self, avg_aqi, avg_temp, avg_hum):
        """Simulate fan control based on AQI, temperature, humidity, and occupancy"""
        should_run = False
        if self.is_occupied:  # Presence trigger
            should_run = True
        elif time.time() - self.last_exit_time < self.FAN_POST_EXIT_DURATION:  # Post-exit
            should_run = True
        elif avg_aqi > 300:  # Primary AQI trigger
            should_run = True
        elif avg_aqi > 100 and avg_temp > 25:  # AQI and temperature trigger
            should_run = True
        
        if should_run and not self.fan_status:
            print("[DEBUG] Fan activated")
            self.fan_status = True
        elif not should_run and self.fan_status:
            print("[DEBUG] Fan deactivated")
            self.fan_status = False
    
    def control_freshener(self, avg_aqi, vacated, avg_temp=25):
        """Simulate air freshener control"""
        should_spray = False
        if (avg_aqi > 300 or vacated or time.time() - self.last_spray_time >= 2160) and not self.freshener_triggered:
            should_spray = True
        
        if should_spray:
            print("[DEBUG] Air freshener triggered")
            self.freshener_triggered = True
            self.last_spray_time = time.time()
        elif avg_aqi <= 300 and not vacated:
            self.freshener_triggered = False
    
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
            "trend": self.calculate_air_quality_trend()
        }
    
    def run(self):
        if not self.setup_hardware():
            print("Failed to initialize odor hardware. Module not started.")
            self.running = False
            return
            
        # Perform POST check
        self.perform_post_check()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    # Read sensors
                    temp, hum, aqi = self.read_sensors()
                    avg_aqi = self.calculate_avg_aqi(aqi)
                    avg_temp = sum(temp) / len(temp) if temp and all(t != 0 for t in temp) else 0
                    avg_hum = sum(hum) / len(hum) if hum and all(h != 0 for h in hum) else 0
                    
                    # Process occupancy and control devices
                    vacated = self.check_occupancy()
                    self.control_fan(avg_aqi, avg_temp, avg_hum)
                    self.control_freshener(avg_aqi, vacated, avg_temp)
                    
                except Exception as e:
                    print(f"Error in odor module: {e}")
                
                time.sleep(SIMULATION_INTERVAL)  # Update every SIMULATION_INTERVAL seconds
            else:
                time.sleep(1)  # Check for un-pause every second
        
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
        # Raspberry Pi stats - using real data for the host system
        self.system_info["raspberry_pi"]["cpu_usage"] = psutil.cpu_percent()
        self.system_info["raspberry_pi"]["memory_usage"] = psutil.virtual_memory().percent
        self.system_info["raspberry_pi"]["storage_usage"] = psutil.disk_usage('/').percent
        
        # Simulate CPU temp since Windows doesn't expose this the same way
        self.system_info["raspberry_pi"]["cpu_temp"] = random.uniform(35.0, 55.0)
        
        # Simulate Arduino stats
        self.system_info["arduino"]["cpu_temp"] = random.uniform(30.0, 45.0)
        self.system_info["arduino"]["cpu_usage"] = random.uniform(10.0, 25.0)
        self.system_info["arduino"]["memory_usage"] = random.uniform(25.0, 40.0)
        
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
class SmartRestroomDebugCLI:
    instance = None  # Class variable to hold the single instance
    
    def __init__(self):
        SmartRestroomDebugCLI.instance = self  # Assigning the instance to the class variable
        self.running = True
        self.central_hub = CentralHub()
        self.modules_running = False
        
        print("[DEBUG MODE] Starting Smart Restroom System in simulation mode")
        print("This debug version simulates hardware interactions for testing on Windows")
        
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
        """Clear the console screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def signal_handler(self, sig, frame):
        """Handle signals for graceful shutdown"""
        print("\nShutting down...")
        self.running = False
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Cleanup resources before exit"""
        self.occupancy_module.cleanup_hardware()
        self.dispenser_module.cleanup_hardware()
        self.odor_module.cleanup_hardware()
        print("Cleanup complete. Exiting...")
    
    def print_header(self):
        """Print application header"""
        self.clear_screen()
        print("=" * 80)
        print(" " * 25 + "SMART RESTROOM SYSTEM DEBUG CLI")
        print("=" * 80)
        print(" ")
        print("[SIMULATION MODE - Hardware actions are simulated]")
        
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
                        f"{data['remaining_volume_ml']:.1f}",
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
            
            # Display debug messages
            debug_messages = debug_handler.get_messages()
            if debug_messages:
                print("\nRecent Events:")
                print("-" * 80)
                for msg in debug_messages[-20:]:  # Show last 20 messages
                    print(msg)
            
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
        """Start all modules and update menu state"""
        print("\nStarting all modules...")
        self.occupancy_module.start()
        self.dispenser_module.start()
        self.odor_module.start()
        self.modules_running = True
        time.sleep(1)  # Give modules time to initialize
    
    def stop_all_modules(self):
        """Stop all modules and update menu state"""
        print("\nStopping all modules...")
        self.occupancy_module.stop()
        self.dispenser_module.stop()
        self.odor_module.stop()
        self.modules_running = False
        time.sleep(1)  # Give modules time to clean up
    
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
        print("\nThank you for using Smart Restroom System Debug CLI!")
    
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
                        f"{data['remaining_volume_ml']:.1f}",
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
                        duration = self.format_duration(entry["duration"]) if "duration" in entry else "Active"
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
                        f"{volume:.1f}",
                        f"{percentage}%",
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
            
            # Display debug messages related to this module
            debug_messages = debug_handler.get_messages()
            if debug_messages:
                filtered_messages = [msg for msg in debug_messages if name.lower() in msg.lower()]
                if filtered_messages:
                    print("\nRecent Events:")
                    print("-" * 80)
                    for msg in filtered_messages[-10:]:  # Show last 10 messages related to this module
                        print(msg)
            
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
        # Create data directory
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Start the application
        app = SmartRestroomDebugCLI()
        app.run()
    except Exception as e:
        print(f"Error: {e}")
        if 'app' in locals():
            app.cleanup()
        sys.exit(1)