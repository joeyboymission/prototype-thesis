#!/usr/bin/env python3
import os
import subprocess
import serial
import time
import json
import datetime
import glob
import random
import signal
import sys
import statistics

# Try to import MongoDB
try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    from bson import ObjectId
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("MongoDB not available. Using local storage only.")

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
LOGGING_INTERVAL = 10  # seconds
DECIMAL_PRECISION = 2  # For temperature and humidity values

# Global variables
arduino_serial = None
mongo_client = None
mongo_db = None
mongo_collection = None
dht_sensors = []
running = True
sensor_data_buffer = []

# Initialize data format
def get_data_template():
    return {
        "_id": str(ObjectId()) if MONGODB_AVAILABLE else "local_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "aqi": {
            "GAS1": 0,
            "GAS2": 0,
            "GAS3": 0,
            "GAS4": 0
        },
        "dht": {
            "TEMP1": {"temp": 0.00, "hum": 0.00},
            "TEMP2": {"temp": 0.00, "hum": 0.00},
            "TEMP3": {"temp": 0.00, "hum": 0.00},
            "TEMP4": {"temp": 0.00, "hum": 0.00}
        }
    }

def log_message(message):
    """Print a timestamped log message"""
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {message}")

def scan_serial_ports():
    """Scan for available serial ports with fallback methods"""
    log_message("Scanning serial ports...")
    
    # Method 1: Try using glob (most reliable)
    try:
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
            log_message(f"Found ports using glob: {', '.join(ports)}")
            return ports
    except Exception as e:
        log_message(f"Glob scan error: {e}")
    
    # Method 2: Try direct device check
    try:
        potential_ports = [
            '/dev/ttyUSB0',
            '/dev/ttyUSB1',
            '/dev/ttyACM0',
            '/dev/ttyACM1',
            '/dev/ttyAMA0'
        ]
        
        ports = [port for port in potential_ports if os.path.exists(port)]
        if ports:
            log_message(f"Found ports using direct check: {', '.join(ports)}")
            return ports
    except Exception as e:
        log_message(f"Direct check error: {e}")
    
    # Method 3: Last resort - try subprocess with explicit paths
    try:
        result = subprocess.run(['ls', '/dev/ttyUSB0'], capture_output=True, text=True)
        if result.returncode == 0:
            log_message("Found /dev/ttyUSB0 using subprocess")
            return ['/dev/ttyUSB0']
    except Exception as e:
        log_message(f"Subprocess check error: {e}")
    
    log_message("No serial ports found using any method")
    return []

def fix_port_permissions(port):
    """Fix permission issues for serial ports"""
    log_message(f"Fixing permissions for {port}...")
    
    try:
        # Kill any processes using the port
        log_message("Killing processes using the port...")
        subprocess.run(['sudo', 'fuser', '-k', port], capture_output=True, check=False)
        time.sleep(1)
        
        # Reset USB device
        port_base = os.path.basename(port)
        if 'USB' in port_base:
            bus_device = subprocess.run(['readlink', '-f', port], capture_output=True, text=True, check=False).stdout.strip()
            if bus_device:
                usb_path = os.path.dirname(os.path.dirname(bus_device))
                if os.path.exists(os.path.join(usb_path, 'authorized')):
                    log_message("Resetting USB device...")
                    subprocess.run(['sudo', 'sh', '-c', f'echo 0 > {usb_path}/authorized'], check=False)
                    time.sleep(1)
                    subprocess.run(['sudo', 'sh', '-c', f'echo 1 > {usb_path}/authorized'], check=False)
                    time.sleep(2)
        
        # Set permissions
        log_message("Setting port permissions...")
        subprocess.run(['sudo', 'chmod', '666', port], check=False)
        
        # Add current user to dialout group
        username = os.getenv('USER', 'pi')
        log_message(f"Adding user {username} to dialout group...")
        subprocess.run(['sudo', 'usermod', '-a', '-G', 'dialout', username], check=False)
        
        return True
    except Exception as e:
        log_message(f"Error fixing permissions: {e}")
        return False

def try_connect_port(port, retries=3):
    """Try to connect to a port with multiple retries"""
    global arduino_serial
    
    for attempt in range(retries):
        try:
            log_message(f"Connection attempt {attempt + 1} for {port}...")
            
            # Try to open the port
            ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
            
            # Test communication
            ser.write(b'R')  # Send read command
            time.sleep(0.1)
            response = ser.readline().decode().strip()
            
            if response and ',' in response:  # Verify data format
                values = response.split(',')
                if len(values) == 4:  # Expect 4 sensor values
                    log_message(f"Successfully connected to Arduino on {port}")
                    return ser
            
            ser.close()
            log_message("Invalid response from device")
            
        except serial.SerialException as e:
            log_message(f"Connection error: {e}")
            
            if attempt < retries - 1:
                log_message("Attempting to fix permissions...")
                if fix_port_permissions(port):
                    time.sleep(2)  # Wait for permissions to take effect
                else:
                    log_message("Failed to fix permissions")
            
        except Exception as e:
            log_message(f"Unexpected error: {e}")
        
        if attempt < retries - 1:
            log_message(f"Retrying in 2 seconds...")
            time.sleep(2)
    
    return None

def connect_to_arduino():
    """Find and connect to Arduino on available serial ports"""
    global arduino_serial
    
    ports = scan_serial_ports()
    
    if not ports:
        log_message("No serial ports found. Please check if:")
        log_message("1. The Arduino is properly connected via USB")
        log_message("2. You have the necessary permissions")
        log_message("3. The USB cable is working")
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
        # Try to connect with retries and permission fixing
        ser = try_connect_port(port)
        if ser:
            arduino_serial = ser
            return True
    
    log_message("Could not find Arduino on any port")
    return False

def read_gas_sensors():
    """Read data from MQ135 gas sensors via Arduino"""
    if not arduino_serial:
        log_message("Error: No Arduino connection")
        return [None] * 4
    
    try:
        # Send read command
        arduino_serial.write(b'R')
        time.sleep(0.1)
        
        # Read response
        response = arduino_serial.readline().decode().strip()
        if not response:
            raise Exception("No response from Arduino")
        
        # Parse and validate values
        values = []
        for val in response.split(','):
            try:
                value = int(val)
                # Validate range (0-500 is valid range for MQ135)
                if 0 <= value <= 500:
                    values.append(value)
                else:
                    values.append(None)
            except ValueError:
                values.append(None)
        
        # Ensure we have 4 values
        while len(values) < 4:
            values.append(None)
        
        return values[:4]  # Return only first 4 values
        
    except Exception as e:
        log_message(f"Error reading gas sensors: {e}")
        # Attempt to reconnect on error
        if "device disconnected" in str(e).lower() or "port is closed" in str(e).lower():
            log_message("Attempting to reconnect to Arduino...")
            if connect_to_arduino():
                log_message("Successfully reconnected to Arduino")
                return read_gas_sensors()  # Try reading again
        return [None] * 4

def setup_dht_sensors():
    """Initialize DHT22 sensors"""
    global dht_sensors, DHT_AVAILABLE
    
    if not DHT_AVAILABLE:
        log_message("DHT sensor library not available, using simulated data.")
        return False
    
    dht_sensors = []
    
    # Define pins mapping for Raspberry Pi
    pin_mapping = [
        {"name": "DHT1", "pin": board.D4},
        {"name": "DHT2", "pin": board.D17},
        {"name": "DHT3", "pin": board.D27},
        {"name": "DHT4", "pin": board.D22}
    ]
    
    log_message("Initializing DHT22 temperature sensors...")
    
    for item in pin_mapping:
        try:
            log_message(f"Initializing {item['name']} on pin {item['pin']}")
            sensor = adafruit_dht.DHT22(item['pin'])
            # Test read to verify it works
            try:
                test_temp = sensor.temperature
                test_hum = sensor.humidity
                if test_temp is not None and test_hum is not None:
                    dht_sensors.append(sensor)
                    log_message(f"Successfully initialized {item['name']}")
                else:
                    log_message(f"Invalid readings from {item['name']}, skipping")
            except Exception as e:
                log_message(f"Error testing {item['name']}: {e}")
        except Exception as e:
            log_message(f"Failed to initialize {item['name']}: {e}")
    
    # Report status
    active_count = len(dht_sensors)
    if active_count == 0:
        log_message("No DHT sensors initialized, using simulated data")
        return False
    else:
        log_message(f"Initialized {active_count} DHT sensors")
        return True

def connect_to_mongodb():
    """Connect to MongoDB"""
    global mongo_client, mongo_db, mongo_collection
    
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
    
    try:
        log_message("Connecting to MongoDB...")
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.admin.command('ping')
        
        mongo_db = mongo_client["Smart_Cubicle"]
        mongo_collection = mongo_db["odor_module"]
        
        # Check if collection exists and has data
        if mongo_collection.count_documents({}) > 0:
            log_message("Found existing data in remote database")
            latest_doc = mongo_collection.find_one(sort=[("timestamp", -1)])
            if latest_doc:
                log_message(f"Latest remote reading from: {latest_doc['timestamp']}")
        
        log_message("Connected to MongoDB successfully!")
        return True
    except Exception as e:
        log_message(f"MongoDB connection error: {e}")
        mongo_client = None
        mongo_db = None
        mongo_collection = None
        return False

def read_temp_sensors():
    """Read data from DHT22 temperature sensors"""
    if not DHT_AVAILABLE or not dht_sensors:
        # Return simulated data if no sensors available
        log_message("No DHT sensors available, using simulated temperature data")
        return [
            {"temp": round(random.uniform(20, 35), DECIMAL_PRECISION), 
             "hum": round(random.uniform(40, 80), DECIMAL_PRECISION)}
            for _ in range(4)
        ]
    
    readings = []
    
    for i, sensor in enumerate(dht_sensors):
        try:
            time.sleep(0.2)  # DHT sensors need time between readings
            
            temperature = sensor.temperature
            humidity = sensor.humidity
            
            # Validate readings
            if (temperature is not None and humidity is not None and
                -40 <= temperature <= 80 and 0 <= humidity <= 100):
                readings.append({
                    "temp": round(temperature, DECIMAL_PRECISION),
                    "hum": round(humidity, DECIMAL_PRECISION)
                })
            else:
                # Use simulated data for invalid readings
                readings.append({
                    "temp": round(random.uniform(20, 35), DECIMAL_PRECISION),
                    "hum": round(random.uniform(40, 80), DECIMAL_PRECISION)
                })
                log_message(f"DHT sensor {i+1} gave invalid reading, using simulated data")
        except Exception as e:
            log_message(f"DHT sensor {i+1} error: {e}")
            # Use simulated data on error
            readings.append({
                "temp": round(random.uniform(20, 35), DECIMAL_PRECISION),
                "hum": round(random.uniform(40, 80), DECIMAL_PRECISION)
            })
    
    # If we don't have enough readings, pad with simulated data
    while len(readings) < 4:
        readings.append({
            "temp": round(random.uniform(20, 35), DECIMAL_PRECISION),
            "hum": round(random.uniform(40, 80), DECIMAL_PRECISION)
        })
    
    return readings

def fix_sensor_data(gas_values, temp_readings):
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
                log_message(f"*GAS{i+1}: Fixed with average {round(avg_gas)}")
    
    # Fix temperature values
    valid_temps = [r["temp"] for r in temp_readings if r["temp"] > 0]
    valid_hums = [r["hum"] for r in temp_readings if r["hum"] > 0]
    
    if valid_temps:
        avg_temp = sum(valid_temps) / len(valid_temps)
        for i in range(len(fixed_temp)):
            if fixed_temp[i]["temp"] <= 0:
                fixed_temp[i]["temp"] = round(avg_temp, DECIMAL_PRECISION)
                log_message(f"*TEMP{i+1}: Fixed temperature with average {round(avg_temp, DECIMAL_PRECISION)}")
    
    if valid_hums:
        avg_hum = sum(valid_hums) / len(valid_hums)
        for i in range(len(fixed_temp)):
            if fixed_temp[i]["hum"] <= 0:
                fixed_temp[i]["hum"] = round(avg_hum, DECIMAL_PRECISION)
                log_message(f"*TEMP{i+1}: Fixed humidity with average {round(avg_hum, DECIMAL_PRECISION)}")
    
    return fixed_gas, fixed_temp

def save_to_local_storage(data):
    """Save data to local JSON file"""
    try:
        # Ensure the directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        existing_data = []
        if os.path.exists(LOCAL_FILE):
            try:
                with open(LOCAL_FILE, "r") as f:
                    existing_data = json.load(f)
                    if existing_data:
                        log_message(f"Found {len(existing_data)} existing records in local storage")
                        latest = existing_data[-1]
                        log_message(f"Latest local reading from: {latest['timestamp']}")
            except json.JSONDecodeError:
                log_message("Creating new data file (existing file corrupt)")
        else:
            log_message("Creating new local data file")
        
        # Ensure data has the correct format
        if not isinstance(existing_data, list):
            existing_data = []
        
        existing_data.append(data)
        
        # Use atomic write to prevent corruption
        temp_file = LOCAL_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2)
        os.replace(temp_file, LOCAL_FILE)
        
        return True
    except Exception as e:
        log_message(f"Local storage error: {e}")
        return False

def save_to_mongodb(data):
    """Save data to MongoDB"""
    global mongo_collection
    
    if not MONGODB_AVAILABLE or mongo_collection is None:
        return False
    
    try:
        # Convert _id string to ObjectId for MongoDB
        if '_id' in data and isinstance(data['_id'], str):
            if data['_id'].startswith("local_"):
                # Generate new ObjectId for local IDs
                data['_id'] = ObjectId()
            else:
                # Convert string ID to ObjectId
                data['_id'] = ObjectId(data['_id'])
        
        result = mongo_collection.insert_one(data)
        return True
    except Exception as e:
        log_message(f"MongoDB error: {e}")
        # Try to reconnect
        connect_to_mongodb()
        return False

def buffer_sensor_data(gas_values, temp_readings):
    """Add sensor data to buffer for averaging"""
    global sensor_data_buffer
    
    sensor_data_buffer.append({
        "gas": gas_values,
        "temp": temp_readings
    })
    
    # Keep buffer size reasonable
    if len(sensor_data_buffer) > 10:
        sensor_data_buffer.pop(0)

def calculate_average_from_buffer():
    """Calculate average values from buffered sensor data"""
    global sensor_data_buffer
    
    if not sensor_data_buffer:
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
    for data in sensor_data_buffer:
        # Sum gas values
        for i in range(4):
            avg_gas[i] += data["gas"][i]
        
        # Sum temperature and humidity
        for i in range(4):
            avg_temp[i]["temp"] += data["temp"][i]["temp"]
            avg_temp[i]["hum"] += data["temp"][i]["hum"]
    
    # Calculate averages
    buffer_len = len(sensor_data_buffer)
    for i in range(4):
        avg_gas[i] = round(avg_gas[i] / buffer_len)
        avg_temp[i]["temp"] = round(avg_temp[i]["temp"] / buffer_len, DECIMAL_PRECISION)
        avg_temp[i]["hum"] = round(avg_temp[i]["hum"] / buffer_len, DECIMAL_PRECISION)
    
    return {"gas": avg_gas, "temp": avg_temp}

def log_sensor_data(gas_values, temp_readings):
    """Log all sensor data"""
    gas_str = f"ODOR [GAS1: {gas_values[0]} | GAS2: {gas_values[1]} | GAS3: {gas_values[2]} | GAS4: {gas_values[3]}]"
    temp_str = f"TEMP ["
    
    for i, reading in enumerate(temp_readings):
        temp_str += f"TEMP{i+1}: {reading['temp']}°C | "
    temp_str = temp_str.rstrip(" | ") + "]"
    
    log_message(f"{gas_str} {temp_str}")

def save_sensor_data(gas_values, temp_readings):
    """Save sensor data to database(s)"""
    data = get_data_template()
    
    # Fill in gas values
    for i in range(4):
        data["aqi"][f"GAS{i+1}"] = gas_values[i]
    
    # Fill in temp values
    for i in range(4):
        data["dht"][f"TEMP{i+1}"]["temp"] = temp_readings[i]["temp"]
        data["dht"][f"TEMP{i+1}"]["hum"] = temp_readings[i]["hum"]
    
    # Save to local storage first
    local_saved = save_to_local_storage(data)
    
    # Try saving to MongoDB if available
    remote_saved = save_to_mongodb(data)
    
    # Log result according to the updated format
    if local_saved and remote_saved:
        log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
    elif local_saved:
        log_message("Status: DATA SAVED TO LOCAL ONLY")
    else:
        log_message("Status: FAILED TO SAVE DATA")
    
    log_message(f"Odor Data: {gas_values[0]} | {gas_values[1]} | {gas_values[2]} | {gas_values[3]}")
    log_message(f"Temp Data: {temp_readings[0]['temp']} | {temp_readings[1]['temp']} | {temp_readings[2]['temp']} | {temp_readings[3]['temp']}")

def signal_handler(sig, frame):
    """Handle Ctrl+C to cleanly exit the program"""
    global running
    print("\nStopping...")
    running = False

def print_initialization_example():
    """Display initialization example"""
    print("""
[2023-07-15 14:30:45] === Odor Module Starting ===
[2023-07-15 14:30:45] Scanning serial ports...
[2023-07-15 14:30:45] Found ports: /dev/ttyUSB0, /dev/ttyACM0
[2023-07-15 14:30:45] Trying to connect to /dev/ttyUSB0...
[2023-07-15 14:30:47] Received from /dev/ttyUSB0: '125,230,156,187'
[2023-07-15 14:30:47] Arduino found on /dev/ttyUSB0
[2023-07-15 14:30:47] Initializing DHT22 temperature sensors...
[2023-07-15 14:30:47] Initializing DHT1 on pin D4
[2023-07-15 14:30:48] Successfully initialized DHT1
[2023-07-15 14:30:48] Initializing DHT2 on pin D17
[2023-07-15 14:30:49] Successfully initialized DHT2
[2023-07-15 14:30:49] Initializing DHT3 on pin D27
[2023-07-15 14:30:50] Error testing DHT3: Device not found
[2023-07-15 14:30:50] Initializing DHT4 on pin D22
[2023-07-15 14:30:51] Successfully initialized DHT4
[2023-07-15 14:30:51] Initialized 3 DHT sensors
[2023-07-15 14:30:51] Connecting to MongoDB...
[2023-07-15 14:30:52] Connected to MongoDB successfully!
[2023-07-15 14:30:52] Starting continuous monitoring. Press Ctrl+C to stop.
""")

def initialize_storage():
    """Initialize storage system and check existing data"""
    log_message("Checking storage system...")
    
    # Create local data directory if it doesn't exist
    if not os.path.exists(DATA_DIR):
        log_message(f"Creating local data directory: {DATA_DIR}")
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception as e:
            log_message(f"Error creating data directory: {e}")
            return False
    
    # Check local file
    if not os.path.exists(LOCAL_FILE):
        log_message("Local data file does not exist, will create when first data is saved")
    else:
        try:
            with open(LOCAL_FILE, "r") as f:
                data = json.load(f)
                log_message(f"Found {len(data)} existing records in local storage")
                if data:
                    latest = data[-1]
                    log_message(f"Latest local reading from: {latest['timestamp']}")
        except Exception as e:
            log_message(f"Error reading local data file: {e}")
    
    return True

def main():
    global running
    
    # Setup signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    log_message("=== Odor Module Starting ===")
    
    # Initialize storage system
    if not initialize_storage():
        log_message("Failed to initialize storage system")
        return
    
    # Connect to MongoDB first
    mongodb_connected = connect_to_mongodb()
    if mongodb_connected:
        log_message("MongoDB connected. Data will be saved to remote and local storage.")
    else:
        log_message("No MongoDB connection. Data will be saved to local storage only.")
    
    # Initial setup
    arduino_connected = connect_to_arduino()
    if not arduino_connected:
        log_message("Warning: No Arduino connection. Using simulated gas data.")
    
    dht_available = setup_dht_sensors()
    if not dht_available:
        log_message("Warning: No DHT sensors available. Using simulated temperature data.")
    
    log_message("Starting continuous monitoring. Press Ctrl+C to stop.")
    
    last_log_time = time.time()
    last_save_time = time.time()
    
    # Main loop
    while running:
        current_time = time.time()
        
        # Read sensor data frequently but log less often
        if current_time - last_log_time >= 5:  # Read every 5 seconds
            # Read sensors
            gas_values = read_gas_sensors()
            temp_readings = read_temp_sensors()
            
            # Fix any invalid sensor data
            gas_values, temp_readings = fix_sensor_data(gas_values, temp_readings)
            
            # Buffer the data for averaging
            buffer_sensor_data(gas_values, temp_readings)
            
            # Log current readings
            log_sensor_data(gas_values, temp_readings)
            
            last_log_time = current_time
        
        # Save buffered/averaged data at the specified interval
        if current_time - last_save_time >= LOGGING_INTERVAL:  # Save every 10 seconds
            # Calculate average from buffer
            avg_data = calculate_average_from_buffer()
            
            if avg_data:
                # Save the averaged data
                save_sensor_data(avg_data["gas"], avg_data["temp"])
            
            last_save_time = current_time
        
        # Small delay to prevent CPU overuse
        time.sleep(0.1)
    
    # When stopping, save final data
    avg_data = calculate_average_from_buffer()
    if avg_data:
        log_message("Saving final data before exit...")
        save_sensor_data(avg_data["gas"], avg_data["temp"])
    
    # Clean up before exit
    log_message("Cleaning up...")
    
    # Close Arduino connection
    if arduino_serial:
        try:
            arduino_serial.close()
            log_message("Closed Arduino serial connection")
        except:
            pass
    
    # Close DHT sensors
    for sensor in dht_sensors:
        try:
            sensor.exit()
        except:
            pass
    
    # Close MongoDB connection
    if mongo_client:
        try:
            mongo_client.close()
            log_message("Closed MongoDB connection")
        except:
            pass
    
    log_message("Final data saved. Exiting.")

if __name__ == "__main__":
    main()