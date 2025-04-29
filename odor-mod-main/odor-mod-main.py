import os
import subprocess
import re
import serial
import time
import json
import datetime
import collections
import glob

# Try to import hardware dependencies with fallbacks
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available")

# Add DHT sensor setup with proper error handling
DHT_AVAILABLE = False
try:
    import board
    import adafruit_dht
    # Check if we can initialize DHT sensors - will fail if libgpiod isn't installed
    try:
        # Try initializing a single sensor first to check if hardware works
        test_sensor = adafruit_dht.DHT22(board.D4)
        test_temp = test_sensor.temperature  # Test read - will fail if hardware/drivers missing
        DHT_AVAILABLE = True
        print("DHT sensors available and working")
    except Exception as e:
        print(f"DHT sensors not available: {e}")
        print("Make sure libgpiod is installed: sudo apt install libgpiod2")
        DHT_AVAILABLE = False
except ImportError:
    print("Warning: adafruit_dht library not available")
    DHT_AVAILABLE = False

# MongoDB Connection Setup
MONGODB_AVAILABLE = False
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    
    # Custom JSON encoder for MongoDB ObjectId
    class MongoJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, '__str__'):
                return str(obj)
            return super().default(obj)
    
    MONGODB_AVAILABLE = True
    print("MongoDB libraries available")
except ImportError:
    print("Warning: pymongo not available. Using local storage only.")
    
    class MongoJSONEncoder(json.JSONEncoder):
        pass

# Global variables
client = None
db = None
collection = None
ser = None
log_queue = collections.deque(maxlen=20)
dht_sensors = []  # Will hold DHT sensor objects if available

# GPIO simulation if hardware is not available
class GPIOSimulator:
    def __init__(self):
        print("Using GPIO simulator")
        
    def gpio_write(self, h, pin, state):
        print(f"GPIO Write: Pin {pin} set to {state}")
        
    def gpio_claim_output(self, h, pin, initial=0):
        print(f"GPIO Claim: Pin {pin} as output with initial {initial}")
        
    def gpiochip_open(self, chip):
        print(f"GPIO Chip: Opening chip {chip}")
        return 0
        
    def gpiochip_close(self, h):
        print(f"GPIO Chip: Closing handle {h}")
        
    def gpio_free(self, h, pin):
        print(f"GPIO Free: Pin {pin} on handle {h}")

# Use real or simulated GPIO
if GPIO_AVAILABLE:
    try:
        import lgpio
    except ImportError:
        print("lgpio not available, using simulator")
        lgpio = GPIOSimulator()
else:
    lgpio = GPIOSimulator()

# Settings
GPIO_CHIP = 0
FAN_PIN = 23
FRESHENER_PIN = 22
h = lgpio.gpiochip_open(GPIO_CHIP)
lgpio.gpio_claim_output(h, FAN_PIN, 0)
lgpio.gpio_claim_output(h, FRESHENER_PIN, 0)

BAUD_RATE = 9600
SERIAL_TIMEOUT = 2

# MongoDB connection settings
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

# Local file storage
DATA_DIR = "/home/admin/Documents/local-data"
LOCAL_FILE = os.path.join(DATA_DIR, "odor-data.json")
os.makedirs(DATA_DIR, exist_ok=True)

# Control timing
FAN_EXIT_DELAY = 5
FRESHENER_EXIT_DELAY = 5
SPRAY_DURATION = 1
fan_timer = 0
freshener_timer = 0
last_spray = 0

def get_timestamp():
    return datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    timestamped_msg = f"{get_timestamp()} {message}"
    log_queue.append(timestamped_msg)
    print(timestamped_msg)

def display_log_window(clear=True):
    if clear:
        os.system('cls' if os.name == 'nt' else 'clear')
    
    print("\n" + "=" * 80)
    print("Recent Log Messages:")
    print("-" * 80)
    
    for msg in log_queue:
        print(msg)
    
    remaining_lines = 20 - len(log_queue)
    for _ in range(remaining_lines):
        print("")

def find_arduino_serial_port():
    global ser
    
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
        ser = None
    
    # Find all available USB serial ports
    ports = glob.glob('/dev/ttyUSB*')
    if not ports:
        ports = glob.glob('/dev/ttyACM*')
    
    if not ports:
        log_message("No USB serial ports found.")
        return None
    
    # Try each port
    for port in ports:
        try:
            log_message(f"Trying to connect to {port}...")
            test_ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
            time.sleep(2)
            test_ser.reset_input_buffer()
            
            # Send test request and check response
            test_ser.write(b'r')
            line = test_ser.readline().decode('utf-8', errors='ignore').strip()
            
            if ',' in line:
                values = line.split(',')
                if len(values) == 4:  # For MQ135 sensors
                    log_message(f"Arduino found on {port}")
                    ser = test_ser
                    return port
            test_ser.close()
        except Exception as e:
            log_message(f"Failed to connect to {port}: {e}")
    
    log_message("No working Arduino connection found.")
    return None

# Simulated sensor readings for testing
def get_simulated_readings():
    import random
    # Simulate air quality readings (0-500 range)
    aqi_values = [random.randint(0, 500) for _ in range(4)]
    
    # Simulate temperature/humidity readings
    dht_readings = [
        {"temp": round(random.uniform(20, 40), 1), "hum": round(random.uniform(40, 90), 1)}
        for _ in range(4)
    ]
    
    return aqi_values, dht_readings

# Read from MQ135 sensors
def read_mq135():
    if ser is None:
        log_message("No Arduino connection, using simulated data")
        return get_simulated_readings()[0]
    
    try:
        ser.write(b'r')  # Send request byte
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        
        if ',' in line:
            values = [int(val.strip()) for val in line.split(',')]
            if len(values) == 4:
                return values
    except Exception as e:
        log_message(f"Error reading MQ135: {e}")
    
    # Return simulated data if real reading fails
    return get_simulated_readings()[0]

# Read from DHT22 sensors
def read_dht22():
    if not DHT_AVAILABLE or not dht_sensors:
        return get_simulated_readings()[1]
    
    readings = []
    for i, sensor in enumerate(dht_sensors):
        try:
            temperature = sensor.temperature
            humidity = sensor.humidity
            if temperature is not None and humidity is not None:
                readings.append({"temp": temperature, "hum": humidity})
            else:
                readings.append({"temp": 0, "hum": 0})
        except Exception as e:
            log_message(f"DHT sensor {i} read error: {e}")
            readings.append({"temp": 0, "hum": 0})
    
    # If we don't have enough readings, pad with simulated data
    while len(readings) < 4:
        readings.append({"temp": round(random.uniform(20, 40), 1), "hum": round(random.uniform(40, 90), 1)})
    
    return readings

def check_mongo_connection():
    """Properly try to connect to MongoDB with better error handling"""
    global client, db, collection, MONGODB_AVAILABLE
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
        
    try:
        log_message("Connecting to MongoDB...")
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test if we can actually reach the server
        db = client["Smart_Cubicle"]
        collection = db["odor_module"]
        log_message("Connected to MongoDB successfully.")
        return True
    except Exception as e:
        log_message(f"Warning: Failed to connect to MongoDB: {e}. Using local storage only.")
        client = None
        db = None
        collection = None
        return False

def check_occupancy_status():
    try:
        occupancy_file = os.path.join(DATA_DIR, "occupancy-data.json")
        if not os.path.exists(occupancy_file):
            return False
            
        with open(occupancy_file, "r") as f:
            data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                latest = data[-1]
                return "end_time" not in latest
            return False
    except Exception as e:
        log_message(f"Error reading occupancy data: {e}")
        return False

def control_fan(aqi_values, dht_readings):
    global fan_timer
    current_time = time.time()
    is_occupied = check_occupancy_status()
    
    if is_occupied:
        lgpio.gpio_write(h, FAN_PIN, 1)
        fan_timer = current_time + FAN_EXIT_DELAY
    elif current_time < fan_timer:
        lgpio.gpio_write(h, FAN_PIN, 1)
    else:
        lgpio.gpio_write(h, FAN_PIN, 0)

def control_freshener(aqi_values):
    global last_spray, freshener_timer
    current_time = time.time()
    is_occupied = check_occupancy_status()
    
    if not is_occupied and current_time >= freshener_timer:
        lgpio.gpio_write(h, FRESHENER_PIN, 1)
        time.sleep(SPRAY_DURATION)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        last_spray = current_time
        freshener_timer = float('inf')

def save_to_local_json(data):
    try:
        os.makedirs(os.path.dirname(LOCAL_FILE), exist_ok=True)
        
        existing_data = []
        if os.path.exists(LOCAL_FILE):
            try:
                with open(LOCAL_FILE, "r") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                log_message("Creating new data file (existing file corrupt)")
        
        existing_data.append(data)
        
        temp_file = LOCAL_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, cls=MongoJSONEncoder)
        os.replace(temp_file, LOCAL_FILE)
        log_message(f"Saved to local storage ({len(existing_data)} records)")
        return True
    except Exception as e:
        log_message(f"Local storage error: {e}")
        return False

def log_data(aqi_values, dht_readings):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    data = {
        "timestamp": timestamp,
        "aqi": {
            "GAS1": aqi_values[0],
            "GAS2": aqi_values[1],
            "GAS3": aqi_values[2],
            "GAS4": aqi_values[3]
        },
        "dht": {
            "TEMP1": {
                "temp": round(dht_readings[0]['temp'], 1),
                "hum": round(dht_readings[0]['hum'], 1)
            },
            "TEMP2": {
                "temp": round(dht_readings[1]['temp'], 1),
                "hum": round(dht_readings[1]['hum'], 1)
            },
            "TEMP3": {
                "temp": round(dht_readings[2]['temp'], 1),
                "hum": round(dht_readings[2]['hum'], 1)
            },
            "TEMP4": {
                "temp": round(dht_readings[3]['temp'], 1),
                "hum": round(dht_readings[3]['hum'], 1)
            }
        }
    }
    
    # Always save locally first
    save_to_local_json(data)
    
    # Try MongoDB if available
    if collection is not None:
        try:
            collection.insert_one(data)
            log_message("Data also saved to MongoDB")
        except Exception as e:
            log_message(f"MongoDB error: {e}")
            collection = None

def setup_dht_sensors():
    """Initialize DHT sensors with proper error handling"""
    global dht_sensors
    dht_sensors = []
    
    if not DHT_AVAILABLE:
        log_message("DHT sensor support not available")
        return False
    
    # Define pins mapping
    pin_mapping = [
        {"name": "DHT1", "pin": board.D4},
        {"name": "DHT2", "pin": board.D5},
        {"name": "DHT3", "pin": board.D6},
        {"name": "DHT4", "pin": board.D12}
    ]
    
    # Try to initialize each sensor
    for sensor_def in pin_mapping:
        try:
            sensor = adafruit_dht.DHT22(sensor_def["pin"])
            dht_sensors.append(sensor)
            log_message(f"Initialized {sensor_def['name']} on pin {sensor_def['pin']}")
        except Exception as e:
            log_message(f"Failed to initialize {sensor_def['name']}: {e}")
    
    if not dht_sensors:
        log_message("No DHT sensors could be initialized")
        return False
        
    log_message(f"Initialized {len(dht_sensors)} DHT sensors")
    return True

def start_monitoring():
    global fan_timer, freshener_timer, last_spray
    
    # Initialize timers
    fan_timer = 0
    freshener_timer = 0
    last_spray = 0
    
    log_message("Starting monitoring...")
    log_message("Press CTRL+C to return to menu")
    
    # Initialize DHT sensors
    setup_result = setup_dht_sensors()
    if not setup_result:
        log_message("Warning: Using simulated DHT sensor data")
    
    try:
        last_log_time = time.time()
        last_display_time = time.time()
        
        while True:
            current_time = time.time()
            
            # Get sensor readings
            aqi_values = read_mq135()
            dht_readings = read_dht22()
            
            # Update controls
            control_fan(aqi_values, dht_readings)
            control_freshener(aqi_values)
            
            # Update freshener timer on occupancy change
            if not check_occupancy_status():
                freshener_timer = current_time + FRESHENER_EXIT_DELAY
            
            # Log data every 30 seconds
            if current_time - last_log_time >= 30:
                log_data(aqi_values, dht_readings)
                last_log_time = current_time
            
            # Display current readings
            if current_time - last_display_time >= 1:
                display_log_window()
                
                # Format status line
                temp_summary = ", ".join([f"TEMP{i+1}: {r['temp']:.1f}°C" for i, r in enumerate(dht_readings)])
                aqi_summary = ", ".join([f"GAS{i+1}: {val}" for i, val in enumerate(aqi_values)])
                is_occupied = check_occupancy_status()
                status_line = f"AQI: [{aqi_summary}] | {temp_summary} | Occupied: {is_occupied}"
                log_message(status_line)
                
                last_display_time = current_time
            
            # Menu options
            print("\n" + "=" * 80)
            print("Options: [1] Refresh [2] Log Data Now [3] Return to Menu")
            print("=" * 80)
            
            # Wait for input with timeout
            import select
            import sys
            
            ready, _, _ = select.select([sys.stdin], [], [], 1)
            if ready:
                choice = input().strip()
                if choice == "1":
                    log_message("Manual refresh")
                    continue
                elif choice == "2":
                    log_message("Manual data logging")
                    log_data(aqi_values, dht_readings)
                elif choice == "3":
                    log_message("Returning to menu")
                    break
            
            time.sleep(0.1)
    except KeyboardInterrupt:
        log_message("Monitoring stopped")
    finally:
        # Turn off outputs
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        
        # Clean up DHT resources
        for sensor in dht_sensors:
            try:
                sensor.exit()
            except:
                pass

def main():
    # Try connecting to MongoDB
    db_connected = check_mongo_connection()
    if db_connected:
        log_message("MongoDB connection active - data will be sent to both local and remote storage")
    else:
        log_message("Using local storage only")
    
    try:
        while True:
            print("\n" + "="*80)
            print("╔═══════════════════════════════════════════════════╗")
            print("║              SMART RESTROOM SYSTEM                ║")
            print("║                  ODOR MODULE                      ║")
            print("╚═══════════════════════════════════════════════════╝")
            print("="*80)
            print("1. Start Monitoring")
            print("2. Exit Program")
            
            choice = input("\nEnter choice (1-2): ")
            
            if choice == "1":
                start_monitoring()
            elif choice == "2":
                log_message("Exiting...")
                break
            else:
                print("Invalid choice")
    finally:
        # Cleanup
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        lgpio.gpiochip_close(h)
        
        if ser:
            ser.close()
            
        if client:
            client.close()

if __name__ == "__main__":
    log_message("Odor Module Starting...")
    port = find_arduino_serial_port()
    main()