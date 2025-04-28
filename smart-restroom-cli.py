#!/usr/bin/env python3

import time
import os
import sys
import json
import threading
import signal
import lgpio
from datetime import datetime
import board
import adafruit_dht
import smbus
import psutil
from pymongo import MongoClient
from pymongo.errors import ConnectionError
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
        self.visitor_count = -1
        self.log_list = []
        self.current_start_time = None
        self.last_state_change_time = time.time()
        self.detection_start = None
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['occupancy_data']
        else:
            self.mongo_collection = None
        
        # Local data storage
        self.DATA_DIR = "/home/admin/Documents/local-data"
        self.JSON_FILE = os.path.join(self.DATA_DIR, "occupancy-data.json")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Constants
        self.DEBOUNCE_TIME = 0.5  # 500ms
        self.SHORT_BEEP = 0.2     # 200ms
        self.LONG_BEEP = 1.0      # 1s
    
    def setup_hardware(self):
        try:
            self.chip = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_input(self.chip, self.SENSOR_PIN, lgpio.SET_PULL_UP)
            lgpio.gpio_claim_output(self.chip, self.BUZZER_PIN)
            lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)
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
        if self.chip:
            try:
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 1)
                time.sleep(duration)
                lgpio.gpio_write(self.chip, self.BUZZER_PIN, 0)
            except Exception as e:
                print(f"Error controlling buzzer: {e}")
    
    def double_beep(self):
        self.beep_buzzer(self.SHORT_BEEP)
        time.sleep(self.SHORT_BEEP)
        self.beep_buzzer(self.SHORT_BEEP)
    
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
        temp_file = self.JSON_FILE + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=4)
            os.replace(temp_file, self.JSON_FILE)
        except IOError as e:
            print(f"Error writing JSON: {e}")
    
    def update_mongo(self, entry):
        if self.mongo_collection is None:
            return
        try:
            self.mongo_collection.insert_one(entry)
        except Exception as e:
            print(f"Error updating MongoDB: {e}")
    
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
            self.visitor_count = -1
    
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
        last_sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    sensor_state = lgpio.gpio_read(self.chip, self.SENSOR_PIN)
                    
                    # Process sensor state changes
                    if (current_time - self.last_state_change_time) > self.DEBOUNCE_TIME and sensor_state != last_sensor_state:
                        if self.current_state == self.STATE_VACANT and sensor_state == 0:
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_VACANT and sensor_state == 1 and last_sensor_state == 0 and self.detection_start:
                            if (current_time - self.detection_start) < 2:  # Ensure full cycle within 2s
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
                                self.last_state_change_time = current_time
                                self.detection_start = None
                                
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 0:
                            self.detection_start = current_time
                        elif self.current_state == self.STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0 and self.detection_start:
                            if (current_time - self.detection_start) < 2:
                                self.current_state = self.STATE_VACANT
                                end_time = current_time
                                duration = end_time - self.current_start_time
                                for entry in self.log_list:
                                    if entry["visitor_id"] == self.visitor_count and "end_time" not in entry:
                                        entry["end_time"] = end_time
                                        entry["duration"] = duration
                                        entry["end_time_iso"] = datetime.fromtimestamp(end_time).isoformat()
                                        self.update_mongo({
                                            "visitor_id": entry["visitor_id"],
                                            "start_time": entry["start_time"],
                                            "start_time_iso": entry["start_time_iso"],
                                            "end_time": end_time,
                                            "end_time_iso": entry["end_time_iso"],
                                            "duration": duration
                                        })
                                        break
                                self.beep_buzzer(self.LONG_BEEP)
                                self.update_log()
                                self.last_state_change_time = current_time
                                self.detection_start = None
                                
                        last_sensor_state = sensor_state
                except Exception as e:
                    print(f"Error in occupancy module: {e}")
            
            time.sleep(0.05)
        
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
                "sensor_state": "DOWN"
            } for i in range(4)
        }
        
        self.reading_count = 0
    
    def setup_hardware(self):
        try:
            self.h = lgpio.gpiochip_open(self.GPIO_CHIP)
            # Set up GPIO pins
            for trigger in self.triggers:
                lgpio.gpio_claim_output(self.h, trigger)
            for echo in self.echos:
                lgpio.gpio_claim_input(self.h, echo)
            return True
        except Exception as e:
            print(f"Error setting up dispenser hardware: {e}")
            return False
    
    def cleanup_hardware(self):
        if self.h:
            try:
                # Cleanup GPIO pins
                for pin in self.triggers + self.echos:
                    lgpio.gpio_free(self.h, pin)
                lgpio.gpiochip_close(self.h)
                self.h = None
            except Exception as e:
                print(f"Error cleaning up dispenser hardware: {e}")
    
    def measure_raw_data(self, trigger, echo, num_measurements=5):
        """Measure distance using ultrasonic sensor with multiple readings for accuracy"""
        if not self.h:
            return None, None
        
        distances = []
        pulse_durations = []
        for _ in range(num_measurements):
            try:
                lgpio.gpio_write(self.h, trigger, 1)  # Trigger high
                time.sleep(0.00001)                  # 10us pulse
                lgpio.gpio_write(self.h, trigger, 0)  # Trigger low
                
                start_time = time.time()
                while lgpio.gpio_read(self.h, echo) == 0:
                    pulse_start = time.time()
                    if pulse_start - start_time > 0.5:
                        return None, None
                
                start_time = time.time()
                while lgpio.gpio_read(self.h, echo) == 1:
                    pulse_end = time.time()
                    if pulse_end - start_time > 0.5:
                        return None, None
                
                pulse_duration = pulse_end - pulse_start
                distance = pulse_duration * 17150  # Speed of sound in cm/s
                distance = round(distance, 2)
                distances.append(distance)
                pulse_durations.append(pulse_duration)
                time.sleep(0.05)
            except Exception as e:
                print(f"Error measuring distance: {e}")
                return None, None
        
        if distances and pulse_durations:
            avg_distance = sum(distances) / len(distances)
            avg_pulse_duration = sum(pulse_durations) / len(pulse_durations)
            return avg_pulse_duration, avg_distance
        return None, None
    
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
        
        previous_volumes = {container: None for container in self.container_data}
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    self.reading_count += 1
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    current_reading = {}
                    
                    for i in range(4):
                        container = f"CONT{i+1}"
                        trigger = self.triggers[i]
                        echo = self.echos[i]
                        
                        pulse_duration, distance = self.measure_raw_data(trigger, echo)
                        self.container_data[container]["sensor_state"] = "UP" if pulse_duration is not None else "DOWN"
                        
                        if pulse_duration is None or distance is None:
                            self.container_data[container]["distance_cm"] = None
                            self.container_data[container]["remaining_volume_ml"] = None
                            current_reading[container] = {
                                "distance_cm": None,
                                "remaining_volume_ml": None
                            }
                        else:
                            volume = self.calculate_usable_volume(container, distance)
                            amount_used = None
                            if previous_volumes[container] is not None and volume is not None:
                                amount_used = round(previous_volumes[container] - volume, 2)
                                if amount_used < 0:  # Refill or measurement error
                                    amount_used = 0
                            
                            self.container_data[container]["distance_cm"] = distance
                            self.container_data[container]["remaining_volume_ml"] = volume
                            self.container_data[container]["last_reading"] = time.time()
                            if amount_used is not None and amount_used > 0:
                                self.container_data[container]["last_volume_change"] = amount_used
                            
                            current_reading[container] = {
                                "distance_cm": distance,
                                "remaining_volume_ml": volume
                            }
                            previous_volumes[container] = volume
                    
                    # Save to MongoDB Atlas
                    if self.mongo_collection:
                        reading_doc = {
                            "reading": self.reading_count,
                            "timestamp": timestamp,
                            "data": current_reading
                        }
                        try:
                            self.mongo_collection.insert_one(reading_doc)
                        except Exception as e:
                            print(f"Error updating MongoDB: {e}")
                except Exception as e:
                    print(f"Error in dispenser module: {e}")
                
                time.sleep(10)  # Update every 10 seconds
            else:
                time.sleep(1)  # Check for un-pause every second
        
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
        
        # I2C setup
        self.bus = None
        self.ARDUINO_ADDRESS = 8
        
        # Module state
        self.fan_status = False
        self.freshener_triggered = False
        self.is_occupied = False
        self.last_sensor_state = 1  # 1 = HIGH (no detection) with pull-up
        self.last_exit_time = time.time()
        self.last_spray_time = time.time()
        self.aqi_history = []
        self.FAN_POST_EXIT_DURATION = 1200  # 20 minutes
        self.last_time = time.time()  # For debouncing
        
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
        
        # MongoDB collection
        if db:
            self.mongo_collection = db['odor_module']
        else:
            self.mongo_collection = None
    
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
                    print(f"Failed to initialize DHT22 on pin {pin}: {e}")
                    self.dht_devices.append(None)
            
            # Setup I2C for Arduino communication
            try:
                self.bus = smbus.SMBus(1)  # I2C bus 1 on RPi
                return True
            except Exception as e:
                print(f"Failed to initialize I2C: {e}")
                return False
        except Exception as e:
            print(f"Error setting up odor hardware: {e}")
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
            except Exception as e:
                print(f"Error cleaning up odor hardware: {e}")
    
    def read_sensors(self):
        """Read temperature, humidity from DHT22 and AQI from Arduino Mega"""
        temp = [0] * 4
        hum = [0] * 4
        aqi = [0] * 4
        
        # Read DHT22 sensors
        for i, dht in enumerate(self.dht_devices):
            if dht:
                try:
                    t = dht.temperature
                    h = dht.humidity
                    if t is not None and h is not None:
                        temp[i] = t
                        hum[i] = h
                        self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "UP"
                    else:
                        self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
                except Exception as e:
                    self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
            else:
                self.sensor_data[f"sensor_{i+1}"]["temp_status"] = "DOWN"
        
        # Read Arduino MQ135 sensors via I2C
        if self.bus:
            for attempt in range(3):  # Retry I2C up to 3 times
                try:
                    data = self.bus.read_i2c_block_data(self.ARDUINO_ADDRESS, 0, 8)
                    for i in range(4):
                        aqi[i] = (data[i*2] << 8) + data[i*2 + 1]  # Combine MSB and LSB
                        self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "UP"
                    break
                except Exception as e:
                    if attempt == 2:
                        for i in range(4):
                            self.sensor_data[f"sensor_{i+1}"]["gas_status"] = "DOWN"
                    time.sleep(0.1)
        
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
            else:  # HIGH = Vacant
                self.is_occupied = False
                self.last_exit_time = current_time  # Record exit time
            self.last_sensor_state = current_sensor_state
            self.last_time = current_time
            return not self.is_occupied  # True if just vacated
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
        """Control exhaust fan based on AQI, temperature, humidity, and occupancy"""
        if not self.h:
            return
        
        should_run = False
        if self.is_occupied:  # Presence trigger
            should_run = True
        elif time.time() - self.last_exit_time < self.FAN_POST_EXIT_DURATION:  # Post-exit
            should_run = True
        elif avg_aqi > 300:  # Primary AQI trigger
            should_run = True
        elif avg_aqi > 100 and avg_temp > 25:  # AQI and temperature trigger
            should_run = True
        elif avg_aqi > 150 and avg_temp > 30:  # Severe AQI and temperature
            should_run = True
        elif avg_hum > 60 and avg_aqi > 100:  # Humidity amplifies odor
            should_run = True
        
        if should_run and not self.fan_status:
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 0)  # LOW to activate (active-low)
            self.fan_status = True
        elif not should_run and self.fan_status:
            lgpio.gpio_write(self.h, self.FAN_RELAY_PIN, 1)  # HIGH to deactivate
            self.fan_status = False
    
    def control_freshener(self, avg_aqi, vacated, avg_temp=25):
        """Control air freshener based on AQI, vacancy, or timer"""
        if not self.h:
            return
        
        should_spray = False
        if (avg_aqi > 300 or vacated or time.time() - self.last_spray_time >= 2160) and not self.freshener_triggered:
            should_spray = True
        elif avg_aqi > 150 and avg_temp > 30:  # Additional trigger for high temp
            should_spray = True
        
        if should_spray:
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 0)  # LOW to activate (active-low)
            time.sleep(0.5)  # 500ms pulse
            lgpio.gpio_write(self.h, self.FRESHENER_RELAY_PIN, 1)  # HIGH to deactivate
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
                    
                    # Log data to MongoDB
                    if self.mongo_collection:
                        data = {
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "temperature": avg_temp,
                            "humidity": avg_hum,
                            "gas_level": [self.sensor_data[f"sensor_{i+1}"]["aqi"] for i in range(4)],
                            "air_quality_index": avg_aqi,
                            "fan_status": "on" if self.fan_status else "off",
                            "air_freshener_status": "triggered" if self.freshener_triggered else "off",
                            "occupancy_status": "occupied" if self.is_occupied else "vacant",
                            "average_gas_level": avg_aqi,
                            "air_quality_trend": self.calculate_air_quality_trend(),
                            "critical_event": avg_aqi > 300
                        }
                        try:
                            self.mongo_collection.insert_one(data)
                        except Exception as e:
                            print(f"Error logging to MongoDB: {e}")
                except Exception as e:
                    print(f"Error in odor module: {e}")
                
                time.sleep(10)  # Update every 10 seconds
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
    def __init__(self):
        self.running = True
        self.central_hub = CentralHub()
        
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
        print(" " * 25 + "SMART RESTROOM SYSTEM CLI")
        print("=" * 80)
        print(" ")
    
    def print_system_status(self):
        """Print system status information"""
        print("\n=== SYSTEM STATUS ===\n")
        
        # Update system info
        sys_info = self.central_hub.update_system_info()
        rpi = sys_info["raspberry_pi"]
        arduino = sys_info["arduino"]
        
        # Print Raspberry Pi info
        print("Raspberry Pi:")
        print(f"  Status      : {rpi['status']}")
        print(f"  CPU Temp    : {rpi['cpu_temp']:.1f}°C")
        print(f"  CPU Usage   : {rpi['cpu_usage']:.1f}%")
        print(f"  Memory Usage: {rpi['memory_usage']:.1f}%")
        print(f"  Storage     : {rpi['storage_usage']:.1f}%")
        
        # Print Arduino info
        print("\nArduino:")
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
        if not self.occupancy_module.running:
            print("\n=== OCCUPANCY MODULE (NOT RUNNING) ===\n")
            return
        
        print("\n=== OCCUPANCY MODULE ===\n")
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
    
    def print_dispenser_status(self):
        """Print dispenser module status"""
        if not self.dispenser_module.running:
            print("\n=== DISPENSER MODULE (NOT RUNNING) ===\n")
            return
        
        print("\n=== DISPENSER MODULE ===\n")
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
    
    def print_odor_status(self):
        """Print odor module status"""
        if not self.odor_module.running:
            print("\n=== ODOR MODULE (NOT RUNNING) ===\n")
            return
        
        print("\n=== ODOR MODULE ===\n")
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
        
        if mongo_client:
            mongo_client.close()
            print("MongoDB connection closed")
    
    def run(self):
        """Run the application"""
        self.main_menu()
        print("\nThank you for using Smart Restroom System!")

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
