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

# Mock classes to replace hardware-dependent libraries
class MockLGPIO:
    def gpiochip_open(self, chip):
        print(f"[DEBUG] GPIO chip {chip} opened")
        return chip
    
    def gpiochip_close(self, handle):
        print(f"[DEBUG] GPIO chip {handle} closed")
    
    def gpio_claim_output(self, handle, pin):
        print(f"[DEBUG] GPIO pin {pin} claimed as output")
    
    def gpio_claim_input(self, handle, pin, pull=None):
        print(f"[DEBUG] GPIO pin {pin} claimed as input with pull={pull}")
    
    def gpio_write(self, handle, pin, value):
        print(f"[DEBUG] GPIO pin {pin} set to {value}")
    
    def gpio_read(self, handle, pin):
        # Simulate random sensor readings
        return random.choice([0, 1])
    
    def gpio_free(self, handle, pin):
        print(f"[DEBUG] GPIO pin {pin} freed")
    
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
        print(f"[DEBUG] Accessing collection: {collection_name}")
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
        self.GPIO_CHIP = 0
        self.h = None
        self.FAN_RELAY_PIN = 23
        self.FRESHENER_RELAY_PIN = 22
        self.SENSOR_PIN = 17
        
        # DHT22 sensors - simulated
        self.dht_devices = None
        self.dht_pins = [4, 5, 6, 12]
        
        # I2C - simulated
        self.bus = MockSMBus(1)
        self.ARDUINO_ADDRESS = 8
        
        # Module state
        self.fan_status = False
        self.freshener_triggered = False
        self.is_occupied = False
        self.last_sensor_state = 1
        self.last_exit_time = time.time()
        self.last_spray_time = time.time()
        self.aqi_history = []
        self.FAN_POST_EXIT_DURATION = 1200
        self.last_time = time.time()
        
        # Sensor data
        self.sensor_data = {
            f"sensor_{i+1}": {
                "temperature": random.uniform(20, 35),
                "humidity": random.uniform(30, 80),
                "aqi": random.randint(50, 500),
                "temp_status": "UP",
                "gas_status": "UP"
            } for i in range(4)
        }
        
        # MongoDB collection - simulated
        self.mongo_collection = None
        
        # Simulation values
        self.aqi_trend = 0  # 0: stable, 1: increasing, -1: decreasing
        self.aqi_change_timer = 0
    
    def setup_hardware(self):
        try:
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)  # Simulated
            self.dht_devices = [MockDHT(pin) for pin in self.dht_pins]
            return True
        except Exception as e:
            print(f"Error setting up odor hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                lgpio.gpiochip_close(self.h)
                self.h = None
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
    def __init__(self):
        self.running = True
        self.central_hub = CentralHub()
        
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
    
    def signal_handler(self, sig, frame):
        print("\nShutting down Smart Restroom System...")
        self.cleanup()
        sys.exit(0)
    
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self):
        """Print application header"""
        self.clear_screen()
        print("=" * 80)
        print(" " * 25 + "SMART RESTROOM SYSTEM DEBUG CLI")
        print("=" * 80)
        print(" ")
        print("[SIMULATION MODE - Hardware actions are simulated]")
        print(" ")
    
    def print_system_status(self):
        """Print system status information"""
        print("\n=== SYSTEM STATUS ===\n")
        
        # Update system info
        sys_info = self.central_hub.update_system_info()
        rpi = sys_info["raspberry_pi"]
        arduino = sys_info["arduino"]
        
        # Print Raspberry Pi info
        print("Raspberry Pi (Simulated):")
        print(f"  Status      : {rpi['status']}")
        print(f"  CPU Temp    : {rpi['cpu_temp']:.1f}°C")
        print(f"  CPU Usage   : {rpi['cpu_usage']:.1f}%")
        print(f"  Memory Usage: {rpi['memory_usage']:.1f}%")
        print(f"  Storage     : {rpi['storage_usage']:.1f}%")
        
        # Print Arduino info
        print("\nArduino (Simulated):")
        print(f"  Status      : {arduino['status']}")
        print(f"  CPU Temp    : {arduino['cpu_temp']:.1f}°C")
        print(f"  CPU Usage   : {arduino['cpu_usage']:.1f}%")
        print(f"  Memory Usage: {arduino['memory_usage']:.1f}%")
        
        # Print modules status
        modules_status = self.central_hub.get_modules_status()
        print("\nModules Status:")
        for module, status in modules_status.items():
            print(f"  {module.capitalize()} Module: {status.upper()}")
    
    def print_occupancy_status(self):
        """Print occupancy module status"""
        running = self.occupancy_module.running
        status_text = "" if running else " (NOT RUNNING)"
        
        print(f"\n=== OCCUPANCY MODULE{status_text} ===\n")
        
        if running:
            summary = self.occupancy_module.get_summary()
            
            # Bold status with color
            status_color = "\033[1;31m" if summary["status"] == "Occupied" else "\033[1;32m"
            reset_color = "\033[0m"
            print(f"Status: {status_color}{summary['status']}{reset_color}")
            
            # Visitor stats
            print(f"Total Visitors   : {summary['total_visitors']}")
            print(f"Average Duration : {summary['avg_duration']}")
            print(f"Current Duration : {summary['current_duration']}")
            print(f"Sensor State     : {summary['sensor_state']}")
        else:
            # Display default values when not running
            print("Sensor Status    : DOWN")
            print("Total Visitors   : -")
            print("Recent Duration  : -")
            print("Average Duration : -")
    
    def print_dispenser_status(self):
        """Print dispenser module status"""
        running = self.dispenser_module.running
        status_text = "" if running else " (NOT RUNNING)"
        
        print(f"\n=== DISPENSER MODULE{status_text} ===\n")
        
        if running:
            container_data = self.dispenser_module.get_container_summary()
            
            # Create table header
            headers = ["Container", "Volume (mL)", "Percentage", "Sensor", "Last Used"]
            table = []
            
            # Add data for each container
            for i, (container, data) in enumerate(container_data.items(), 1):
                volume = data["remaining_volume_ml"]
                percentage = int((volume / 425) * 100) if volume is not None else 0
                status = data["sensor_state"]
                last_used = f"{data['last_volume_change']} mL"
                
                table.append([f"Container {i}", 
                             f"{volume if volume is not None else 'N/A'}", 
                             f"{percentage}%", 
                             status, 
                             last_used])
            
            print(tabulate(table, headers, tablefmt="grid"))
        else:
            # Display detailed container information when not running
            container_types = ["Soap", "Hand Sanitizer", "Lotion", "Alcohol"]
            
            for i in range(1, 5):
                print(f"Container {i}")
                print(f"Status  : DOWN")
                print(f"Volume  : -")
                print(f"Type    : {container_types[i-1]}")
                print(f"Last Used: -")
                print(f"Recent  : -")
                print()
    
    def print_odor_status(self):
        """Print odor module status"""
        running = self.odor_module.running
        status_text = "" if running else " (NOT RUNNING)"
        
        print(f"\n=== ODOR MODULE{status_text} ===\n")
        
        if running:
            summary = self.odor_module.get_sensor_summary()
            
            # Display averages
            print(f"Average Temperature: {summary['avg_temp']:.1f}°C")
            print(f"Average Humidity   : {summary['avg_hum']:.1f}%")
            print(f"Average AQI        : {summary['avg_aqi']:.1f}")
            print(f"AQI Trend          : {summary['trend'].upper()}")
            print(f"Fan Status         : {summary['fan_status']}")
            print(f"Freshener Status   : {summary['freshener_status']}")
            print(f"Occupancy          : {summary['occupancy']}")
            
            # Create table for sensor values
            headers = ["Sensor", "Temperature", "Humidity", "AQI", "Temp Sensor", "Gas Sensor"]
            table = []
            
            for i in range(1, 5):
                sensor = summary["sensors"][f"sensor_{i}"]
                table.append([
                    f"Sensor {i}",
                    f"{sensor['temperature']:.1f}°C",
                    f"{sensor['humidity']:.1f}%",
                    f"{sensor['aqi']}",
                    sensor['temp_status'],
                    sensor['gas_status']
                ])
            
            print("\nSensor Readings:")
            print(tabulate(table, headers, tablefmt="grid"))
        else:
            # Display detailed sensor information when not running
            for i in range(1, 5):
                print(f"Sensor {i}")
                print("GAS")
                print("Status: DOWN")
                print("AQI   : -")
                print()
                print("TEMP")
                print("Status   : DOWN")
                print("Temp     : -")
                print("Humidity : -")
                print()
    
    def display_dashboard(self):
        """Display system dashboard"""
        while self.running:
            self.print_header()
            self.print_system_status()
            self.print_occupancy_status()
            self.print_dispenser_status()
            self.print_odor_status()
            
            print("\nPress Ctrl+C to access main menu")
            try:
                time.sleep(5)  # Update every 5 seconds
            except KeyboardInterrupt:
                break
    
    def start_all_modules(self):
        """Start all modules"""
        print("\nStarting all modules...")
        self.occupancy_module.start()
        self.dispenser_module.start()
        self.odor_module.start()
        input("\nPress Enter to continue...")
    
    def stop_all_modules(self):
        """Stop all modules"""
        print("\nStopping all modules...")
        self.occupancy_module.stop()
        self.dispenser_module.stop()
        self.odor_module.stop()
        input("\nPress Enter to continue...")
    
    def module_menu(self, module, name):
        """Show control menu for a specific module"""
        module_name = name.capitalize()
        
        while True:
            self.print_header()
            print(f"\n=== {module_name} Module Control ===\n")
            print(f"Current Status: {module.status().upper()}")
            print("\n1. Start Module")
            print("2. Stop Module")
            print("3. Pause/Resume Module")
            print("4. Return to Main Menu")
            
            choice = input("\nEnter your choice (1-4): ")
            
            if choice == "1":
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
            print("\nMAIN MENU\n")
            print("1. View System Dashboard")
            print("2. Start All Modules")
            print("3. Stop All Modules")
            print("4. Occupancy Module Control")
            print("5. Dispenser Module Control")
            print("6. Odor Module Control")
            print("7. Exit")
            
            choice = input("\nEnter your choice (1-7): ")
            
            if choice == "1":
                self.display_dashboard()
            elif choice == "2":
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
    
    def cleanup(self):
        """Clean up resources and stop all modules"""
        print("\nCleaning up resources...")
        self.occupancy_module.stop()
        self.dispenser_module.stop()
        self.odor_module.stop()
        
        print("[DEBUG] MongoDB connection would be closed here")
    
    def run(self):
        """Run the application"""
        self.main_menu()
        print("\nThank you for using Smart Restroom System Debug CLI!")


# Main entry point
if __name__ == "__main__":
    try:
        # Create data directory
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Print welcome message
        print("\nWelcome to Smart Restroom System DEBUG CLI")
        print("This is a simulation version for Windows testing")
        print("Initializing components, please wait...\n")
        
        # Start the application
        app = SmartRestroomDebugCLI()
        app.run()
    except Exception as e:
        print(f"Error: {e}")
        if 'app' in locals():
            app.cleanup()
        sys.exit(1)