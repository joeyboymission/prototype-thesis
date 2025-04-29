import os
import subprocess
import serial
import time
import json
import datetime
import collections
import glob
import random

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
    DHT_AVAILABLE = True
    print("DHT sensors available")
except ImportError:
    print("Warning: adafruit_dht library not available")
    DHT_AVAILABLE = False

# MongoDB Connection Setup
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
    
    # Custom JSON encoder for MongoDB ObjectId
    class MongoJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, '__str__'):
                return str(obj)
            return super().default(obj)
    
    print("MongoDB libraries available")
except ImportError as e:
    MONGODB_AVAILABLE = False
    print(f"Warning: MongoDB not available: {e}. Using local storage only.")
    
    # Fallback encoder if MongoDB is not available
    class MongoJSONEncoder(json.JSONEncoder):
        pass

# Global variables
client = None
db = None
collection = None
ser = None
log_queue = collections.deque(maxlen=20)
dht_sensors = []

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
        
    def gpio_claim_input(self, h, pin, pull_up_down=None):
        print(f"GPIO Claim: Pin {pin} as input with pull_up_down {pull_up_down}")
        
    def gpio_read(self, h, pin):
        print(f"GPIO Read: Pin {pin}")
        return 0  # Simulate no occupancy

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
BUZZER_PIN = 27  # Added buzzer pin
PROXIMITY_PIN = 17  # Added proximity sensor pin
h = lgpio.gpiochip_open(GPIO_CHIP)
lgpio.gpio_claim_output(h, FAN_PIN, 1)  # Initialize fan OFF (active-low: HIGH = OFF)
lgpio.gpio_claim_output(h, FRESHENER_PIN, 1)  # Initialize freshener OFF (active-low: HIGH = OFF)
lgpio.gpio_claim_output(h, BUZZER_PIN, 0)  # Initialize buzzer OFF
lgpio.gpio_claim_input(h, PROXIMITY_PIN, lgpio.SET_PULL_UP)  # Initialize proximity sensor with pull-up

BAUD_RATE = 9600
SERIAL_TIMEOUT = 5
SERIAL_WRITE_TIMEOUT = 2

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

# Buzzer settings
SHORT_BEEP = 0.2  # 200ms
LONG_BEEP = 1.0   # 1s

# Proximity sensor settings
DEBOUNCE_TIME = 0.5  # 500ms debounce time
last_sensor_state = None
last_state_change_time = time.time()
current_state = "Vacant"  # Initial state

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

def fix_port_permissions(port):
    """Fix permission issues for serial ports"""
    try:
        log_message(f"Fixing permissions for {port}...")
        # Add current user to dialout group (common serial port group)
        username = os.getenv('USER', 'pi')  # Default to 'pi' if USER env var not found
        subprocess.run(["sudo", "usermod", "-a", "-G", "dialout", username], 
                      capture_output=True, check=False)
        
        # Change ownership and permissions of the port
        subprocess.run(["sudo", "chown", f"{username}:dialout", port], 
                      capture_output=True, check=False)
        subprocess.run(["sudo", "chmod", "660", port], 
                      capture_output=True, check=False)
        
        log_message(f"Fixed permissions for {port}")
        return True
    except Exception as e:
        log_message(f"Error fixing permissions: {e}")
        return False

def scan_serial_ports():
    """Scan for all available serial ports"""
    # Find all potential serial ports
    usb_ports = glob.glob('/dev/ttyUSB*')
    acm_ports = glob.glob('/dev/ttyACM*')
    all_ports = usb_ports + acm_ports
    
    if not all_ports:
        log_message("No USB serial ports found.")
        return []
    
    log_message(f"Found potential serial ports: {', '.join(all_ports)}")
    return all_ports

def check_port_permissions(port):
    """Check if we have permission to access the port"""
    try:
        # Try to open the port to check permissions
        test_ser = serial.Serial(port, BAUD_RATE, timeout=1)
        test_ser.close()
        return True
    except PermissionError:
        log_message(f"Permission denied for {port}")
        return False
    except Exception as e:
        log_message(f"Error checking port {port}: {e}")
        return False

def find_arduino_serial_port():
    """Find and connect to Arduino on available serial ports"""
    global ser
    
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
        ser = None
    
    # Scan for available ports
    all_ports = scan_serial_ports()
    
    if not all_ports:
        log_message("No USB serial ports available.")
        return None
    
    # Try each port to find Arduino
    for port in all_ports:
        try:
            log_message(f"Trying to connect to {port}...")
            
            # Check permissions and fix if needed
            if not check_port_permissions(port):
                fix_port_permissions(port)
            
            # Try to open the port
            test_ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT, write_timeout=SERIAL_WRITE_TIMEOUT)
            time.sleep(2)
            test_ser.reset_input_buffer()
            
            # Send test request and check response
            test_ser.write(b'r')
            time.sleep(0.5)  # Give Arduino time to respond
            
            line = test_ser.readline().decode('utf-8', errors='ignore').strip()
            log_message(f"Received from {port}: '{line}'")
            
            if ',' in line:
                values = line.split(',')
                if len(values) == 4:  # For MQ135 sensors
                    log_message(f"Arduino found on {port}")
                    ser = test_ser
                    return port
            
            # Not the right device, close it
            test_ser.close()
            log_message(f"Port {port} is not connected to Arduino")
        except Exception as e:
            log_message(f"Failed to connect to {port}: {e}")
    
    log_message("No working Arduino connection found.")
    return None

# Simulated sensor readings for testing
def get_simulated_readings():
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
    global ser
    
    # If no Arduino connection, try to reestablish it before falling back to simulation
    if ser is None:
        log_message("No Arduino connection, attempting to reconnect...")
        port = find_arduino_serial_port()
        if port is None:
            log_message("Could not reconnect to Arduino, using simulated data")
            return get_simulated_readings()[0]
    
    try:
        # Make sure serial port is working properly before reading
        if ser and not ser.isOpen():
            log_message("Serial port closed, reopening...")
            ser = serial.Serial(ser.port, BAUD_RATE, timeout=SERIAL_TIMEOUT, write_timeout=SERIAL_WRITE_TIMEOUT)
            time.sleep(1)
        
        # Clear any garbage data by reading before sending request
        ser.reset_input_buffer()
        
        # Send request byte
        ser.write(b'r')
        time.sleep(0.5)  # Give Arduino time to respond
        
        # Read response
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        log_message(f"Arduino response: {line}")
        
        if ',' in line:
            values = [int(val.strip()) for val in line.split(',')]
            if len(values) == 4:
                return values
            else:
                log_message(f"Invalid reading format (got {len(values)} values, expected 4)")
        else:
            log_message(f"Invalid reading format (no comma found)")
    except Exception as e:
        log_message(f"Error reading MQ135: {e}")
        # Try to clean up the port for next time
        if ser is not None:
            try:
                port_name = ser.port
                ser.close()
            except:
                pass
            ser = None
    
    # Return simulated data if real reading fails
    return get_simulated_readings()[0]

# Read from DHT22 sensors
def read_dht22():
    """Read DHT22 sensors with improved error handling"""
    if not DHT_AVAILABLE or not dht_sensors:
        return get_simulated_readings()[1]
    
    readings = []
    
    for i, sensor in enumerate(dht_sensors):
        try:
            # Add a small delay between readings (DHT sensors need time between readings)
            time.sleep(0.2)
            
            temperature = sensor.temperature
            humidity = sensor.humidity
            
            # Validate the readings (sometimes we get zeros or extreme values)
            if (temperature is not None and humidity is not None and
                -40 <= temperature <= 80 and 0 <= humidity <= 100):  # Valid range for DHT22
                readings.append({"temp": round(temperature, 1), 
                                "hum": round(humidity, 1)})
            else:
                # Invalid reading, use simulated data
                readings.append({
                    "temp": round(random.uniform(20, 35), 1), 
                    "hum": round(random.uniform(40, 70), 1)
                })
        except Exception as e:
            log_message(f"DHT sensor {i} error: {e}")
            # Use simulated data on error
            readings.append({
                "temp": round(random.uniform(20, 35), 1), 
                "hum": round(random.uniform(40, 70), 1)
            })
    
    # If we don't have enough readings, pad with simulated data
    while len(readings) < 4:
        readings.append({
            "temp": round(random.uniform(20, 35), 1), 
            "hum": round(random.uniform(40, 70), 1)
        })
    
    return readings

def check_mongo_connection():
    """Connect to MongoDB if available"""
    global client, db, collection, MONGODB_AVAILABLE
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
    
    try:
        log_message("Attempting to connect to MongoDB...")
        # Use timeout to avoid hanging
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection with explicit ping
        client.admin.command('ping')
        
        # If we got here, connection worked
        db = client["Smart_Cubicle"]
        collection = db["odor_module"]
        log_message("Connected to MongoDB successfully!")
        return True
    except Exception as e:
        log_message(f"MongoDB connection error: {e}")
        client = None
        db = None
        collection = None
        return False

def check_occupancy_status():
    """Check occupancy status directly from proximity sensor"""
    global current_state, last_sensor_state, last_state_change_time
    
    try:
        # Read the proximity sensor (active-low: LOW = Occupied, HIGH = Vacant)
        sensor_state = lgpio.gpio_read(h, PROXIMITY_PIN)
        current_time = time.time()
        
        # Apply debounce logic
        if (current_time - last_state_change_time) > DEBOUNCE_TIME and sensor_state != last_sensor_state:
            if current_state == "Vacant" and sensor_state == 0:  # Sensor detected someone
                current_state = "Occupied"
                log_message("Occupancy detected!")
                # Beep buzzer to indicate occupancy
                beep_buzzer(SHORT_BEEP)
                last_state_change_time = current_time
            elif current_state == "Occupied" and sensor_state == 1:  # Sensor no longer detects anyone
                current_state = "Vacant"
                log_message("Occupancy ended.")
                # Beep buzzer to indicate vacancy
                beep_buzzer(LONG_BEEP)
                last_state_change_time = current_time
            
            last_sensor_state = sensor_state
        
        return current_state == "Occupied"
    except Exception as e:
        log_message(f"Error reading proximity sensor: {e}")
        return False

def beep_buzzer(duration):
    """Beep the buzzer for the specified duration"""
    try:
        lgpio.gpio_write(h, BUZZER_PIN, 1)
        time.sleep(duration)
        lgpio.gpio_write(h, BUZZER_PIN, 0)
    except Exception as e:
        log_message(f"Error controlling buzzer: {e}")

def control_fan(aqi_values, dht_readings):
    global fan_timer
    current_time = time.time()
    is_occupied = check_occupancy_status()
    
    if is_occupied:
        lgpio.gpio_write(h, FAN_PIN, 0)  # Turn fan ON (active-low: LOW = ON)
        fan_timer = current_time + FAN_EXIT_DELAY  # Set timer for 5 seconds after occupancy ends
    elif current_time < fan_timer:
        lgpio.gpio_write(h, FAN_PIN, 0)  # Keep fan ON during the exit delay period (active-low: LOW = ON)
    else:
        lgpio.gpio_write(h, FAN_PIN, 1)  # Turn fan OFF after the exit delay period (active-low: HIGH = OFF)

def control_freshener(aqi_values):
    global last_spray, freshener_timer
    current_time = time.time()
    is_occupied = check_occupancy_status()
    
    if not is_occupied and current_time >= freshener_timer:
        lgpio.gpio_write(h, FRESHENER_PIN, 0)  # Turn freshener ON (active-low: LOW = ON)
        time.sleep(SPRAY_DURATION)
        lgpio.gpio_write(h, FRESHENER_PIN, 1)  # Turn freshener OFF (active-low: HIGH = OFF)
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
    """Log sensor data to local JSON and MongoDB if available"""
    global collection, client, db
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
        },
        "occupancy": current_state  # Add occupancy status to the data
    }
    
    # Always save locally first
    save_to_local_json(data)
    
    # Try MongoDB if available
    if collection is not None:
        try:
            result = collection.insert_one(data)
            log_message(f"Data also saved to MongoDB (ID: {result.inserted_id})")
            return True
        except Exception as e:
            log_message(f"MongoDB error: {e}")
            # Reset MongoDB connection on error
            collection = None
            db = None
            client = None
            
            # Try to reconnect
            check_mongo_connection()
    
    return True

def setup_dht_sensors():
    """Initialize DHT sensors with proper error handling"""
    global dht_sensors, DHT_AVAILABLE
    dht_sensors = []
    
    if not DHT_AVAILABLE:
        log_message("DHT sensor support not available")
        return False
    
    # Define pins mapping - using the same pins as in the test script
    pin_mapping = [
        {"name": "DHT1", "pin": board.D4},  # GPIO4, Pin 7
        {"name": "DHT2", "pin": board.D5},  # GPIO5, Pin 29
        {"name": "DHT3", "pin": board.D6},  # GPIO6, Pin 31
        {"name": "DHT4", "pin": board.D12}  # GPIO12, Pin 32
    ]
    
    # Initialize GPIO using lgpio (same as test script)
    try:
        import lgpio
        GPIO_CHIP = 0
        h = lgpio.gpiochip_open(GPIO_CHIP)
        log_message("GPIO initialized with lgpio")
    except Exception as e:
        log_message(f"Error initializing GPIO: {e}")
    
    for item in pin_mapping:
        try:
            log_message(f"Trying to initialize {item['name']} on pin {item['pin']}")
            sensor = adafruit_dht.DHT22(item['pin'])
            # Test read to verify it works
            try:
                test_temp = sensor.temperature
                test_hum = sensor.humidity
                if test_temp is not None and test_hum is not None:
                    dht_sensors.append(sensor)
                    log_message(f"Successfully initialized {item['name']} on pin {item['pin']}")
                else:
                    log_message(f"Invalid readings from {item['name']}, skipping")
            except Exception as e:
                log_message(f"Error testing {item['name']}: {e}")
        except Exception as e:
            log_message(f"Failed to initialize {item['name']}: {e}")
    
    # Report status
    active_count = len(dht_sensors)
    if active_count == 0:
        log_message("No DHT sensors could be initialized, using simulated data")
        DHT_AVAILABLE = False
    else:
        log_message(f"Initialized {active_count} DHT sensors")
    
    return DHT_AVAILABLE

def start_monitoring():
    """Main monitoring loop"""
    global last_display_time, last_log_time
    
    last_display_time = time.time()
    last_log_time = time.time()
    
    log_message("Starting continuous monitoring. Press Ctrl+C to stop.")
    log_message("Reading sensors and saving data every 5 seconds...")
    
    # Initialize fan and freshener to OFF state (active-low: HIGH = OFF)
    lgpio.gpio_write(h, FAN_PIN, 1)
    lgpio.gpio_write(h, FRESHENER_PIN, 1)
    
    # Initialize buzzer to OFF state
    lgpio.gpio_write(h, BUZZER_PIN, 0)
    
    # Test buzzer with a short beep
    beep_buzzer(SHORT_BEEP)
    
    try:
        while True:
            current_time = time.time()
            
            # Read sensors
            aqi_values = read_mq135()
            dht_readings = read_dht22()
            
            # Check if we have valid readings from both sensors
            valid_gas = all(val > 0 for val in aqi_values)
            valid_temp = all(reading["temp"] is not None and -40 <= reading["temp"] <= 80 for reading in dht_readings)
            
            # Control fan and freshener
            control_fan(aqi_values, dht_readings)
            control_freshener(aqi_values)
            
            # Display data at intervals
            if current_time - last_display_time >= 10:
                # Display data
                temp_summary = ", ".join([f"T{i+1}: {round(dht_readings[i]['temp'], 1)}C" for i in range(len(dht_readings))])
                aqi_summary = ", ".join([f"GAS{i+1}: {val}" for i, val in enumerate(aqi_values)])
                is_occupied = check_occupancy_status()
                status_line = f"AQI: [{aqi_summary}] | {temp_summary} | Occupied: {is_occupied}"
                log_message(status_line)
                
                last_display_time = current_time
            
            # Log data at 5-second intervals if both sensors are working
            if current_time - last_log_time >= 5:
                if valid_gas and valid_temp:
                    log_message("Logging data to local and remote databases...")
                    log_data(aqi_values, dht_readings)
                    last_log_time = current_time
                else:
                    # If sensors aren't working, try to reconnect
                    if not valid_gas:
                        log_message("Gas sensors not working, attempting to reconnect...")
                        # Try to reconnect to Arduino
                        port = find_arduino_serial_port()
                        if port:
                            log_message(f"Reconnected to Arduino on {port}")
                        else:
                            log_message("Failed to reconnect to Arduino")
                    
                    if not valid_temp:
                        log_message("Temperature sensors not working, attempting to reconnect...")
                        # Try to reinitialize DHT sensors
                        setup_dht_sensors()
            
            # Small delay to prevent CPU overuse
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        log_message("Monitoring stopped by user")
    finally:
        # Turn off outputs (active-low: HIGH = OFF)
        lgpio.gpio_write(h, FAN_PIN, 1)
        lgpio.gpio_write(h, FRESHENER_PIN, 1)
        lgpio.gpio_write(h, BUZZER_PIN, 0)
        
        # Clean up DHT resources
        for sensor in dht_sensors:
            try:
                sensor.exit()
            except:
                pass

def main():
    # Scan for available ports
    log_message("Scanning for available serial ports...")
    all_ports = scan_serial_ports()
    
    if not all_ports:
        log_message("No serial ports found. Please connect an Arduino and try again.")
        return
    
    # Try connecting to Arduino
    log_message("Attempting to find Arduino...")
    port = find_arduino_serial_port()
    
    if port:
        log_message(f"Arduino connected on {port}")
    else:
        log_message("No Arduino found. Will run with simulated MQ135 data.")
    
    # Setup DHT sensors
    log_message("Setting up DHT sensors...")
    setup_dht_sensors()
    
    # Try connecting to MongoDB
    db_connected = check_mongo_connection()
    if db_connected:
        log_message("MongoDB connection active - data will be sent to both local and remote storage")
    else:
        log_message("Using local storage only")
    
    # Initialize fan and freshener to OFF state (active-low: HIGH = OFF)
    lgpio.gpio_write(h, FAN_PIN, 1)
    lgpio.gpio_write(h, FRESHENER_PIN, 1)
    lgpio.gpio_write(h, BUZZER_PIN, 0)
    
    try:
        while True:
            print("\n" + "="*80)
            print("╔═══════════════════════════════════════════════════╗")
            print("║              SMART RESTROOM SYSTEM                ║")
            print("║                  ODOR MODULE                      ║")
            print("╚═══════════════════════════════════════════════════╝")
            print("="*80)
            print("1. Start Monitoring")
            print("2. Re-scan Serial Ports")
            print("3. Exit Program")
            
            choice = input("\nEnter choice (1-3): ")
            
            if choice == "1":
                start_monitoring()
            elif choice == "2":
                log_message("Re-scanning serial ports...")
                all_ports = scan_serial_ports()
                port = find_arduino_serial_port()
                if port:
                    log_message(f"Arduino reconnected on {port}")
                else:
                    log_message("No Arduino found. Will run with simulated MQ135 data.")
            elif choice == "3":
                log_message("Exiting...")
                break
            else:
                print("Invalid choice")
    finally:
        # Cleanup
        log_message("Performing cleanup...")
        # Turn off outputs (active-low: HIGH = OFF)
        lgpio.gpio_write(h, FAN_PIN, 1)
        lgpio.gpio_write(h, FRESHENER_PIN, 1)
        lgpio.gpio_write(h, BUZZER_PIN, 0)
        lgpio.gpiochip_close(h)
        
        if ser:
            try:
                ser.close()
                log_message(f"Closed serial port {ser.port}")
            except:
                pass
            
        if client:
            try:
                client.close()
                log_message("Closed MongoDB connection")
            except:
                pass
        
        # Make sure all DHT sensors are properly closed
        for sensor in dht_sensors:
            try:
                sensor.exit()
            except:
                pass

if __name__ == "__main__":
    log_message("Odor Module Starting...")
    main()