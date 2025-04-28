import serial
import time
import lgpio
import adafruit_dht
import board
import os
import json
import glob
import subprocess
import signal
from datetime import datetime
import pytz

# Define global variables at the module level
client = None
db = None
collection = None
ser = None  # Global serial connection

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    from bson import ObjectId
    MONGODB_AVAILABLE = True
    
    # Create a custom JSON encoder to handle MongoDB ObjectId
    class MongoJSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, ObjectId):
                return str(obj)  # Convert ObjectId to string
            return super().default(obj)
            
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")
    
    # Fallback encoder if MongoDB is not available
    class MongoJSONEncoder(json.JSONEncoder):
        pass

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` (pyserial>=3.5, pymongo>=4.12.0, etc.).
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - USB: Arduino Mega to Pi (/dev/ttyUSB*).
#    - DHT22: TEMP1-TEMP4 on GPIO4,5,6,12.
#    - 8RELAY-B: K2 (Exhaust Fan, GPIO23), K3 (Air Freshener, GPIO22).
#    - Common GND (e.g., Pi Pin 6 to Arduino GND).
# 4. Run with sudo: `sudo python3 odor-mod-main.py`.

# GPIO Setup
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)
FAN_PIN = 23      # GPIO23, Exhaust Fan (220V, 60W)
FRESHENER_PIN = 22  # GPIO22, Air Freshener (3.3V, <0.33W)
lgpio.gpio_claim_output(h, FAN_PIN, 0)      # Active HIGH
lgpio.gpio_claim_output(h, FRESHENER_PIN, 0)  # Active HIGH

# Serial communication settings
BAUD_RATE = 9600
SERIAL_TIMEOUT = 2

def find_arduino_serial_port():
    """Scan for available serial ports and find Arduino Mega."""
    global ser
    
    # Close any existing serial connection
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
        ser = None
    
    # Find all available USB serial ports
    ports = glob.glob('/dev/ttyUSB*')
    if not ports:
        ports = glob.glob('/dev/ttyACM*')  # Sometimes Arduino shows up as ACM
    
    if not ports:
        print("No USB serial ports found.")
        return None
    
    print(f"Found {len(ports)} potential serial ports: {ports}")
    
    # Try to release any busy ports using fuser
    for port in ports:
        try:
            # Check if port is in use
            result = subprocess.run(['fuser', port], capture_output=True, text=True)
            if result.stdout.strip():
                pids = result.stdout.strip().split()
                for pid in pids:
                    print(f"Port {port} is in use by process {pid}. Attempting to terminate...")
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"Successfully terminated process {pid}")
                        # Wait a moment for the port to be released
                        time.sleep(1)
                    except Exception as e:
                        print(f"Failed to terminate process {pid}: {e}")
        except Exception as e:
            print(f"Error checking port usage: {e}")
    
    # Try each port to find Arduino Mega
    for port in ports:
        try:
            print(f"Trying to connect to {port}...")
            test_ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
            
            # Wait for Arduino to initialize after connection
            time.sleep(2)
            
            # Flush any initial data
            test_ser.reset_input_buffer()
            
            # Wait for a valid reading (timeout after 5 attempts)
            attempts = 5
            while attempts > 0:
                test_ser.write(b'r')  # Optional: send a request byte
                line = test_ser.readline().decode('utf-8').strip()
                print(f"Received: {line}")
                
                # Check if the data looks like our expected format (comma-separated values)
                if ',' in line:
                    try:
                        values = line.split(',')
                        if len(values) == 4:  # We expect 4 values from MQ135 sensors
                            print(f"Arduino Mega found on {port}")
                            ser = test_ser
                            return port
                    except Exception:
                        pass
                
                attempts -= 1
                time.sleep(0.5)
            
            # If we reach here, this port didn't work
            test_ser.close()
            
        except Exception as e:
            print(f"Failed to connect to {port}: {e}")
    
    print("No working Arduino connection found.")
    return None

# DHT22 Setup
dht_pins = [board.D4, board.D5, board.D6, board.D12]  # GPIO4,5,6,12
dht_sensors = [adafruit_dht.DHT22(pin) for pin in dht_pins]

# MongoDB Setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

def check_mongo_connection():
    global client, db, collection
    if not MONGODB_AVAILABLE:
        print("MongoDB support not available, using local storage only.")
        return False
        
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client["Smart_Cubicle"]
        collection = db["odor_module"]
        print("Connected to MongoDB successfully.")
        return True
    except Exception as e:
        print(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
        client = None
        db = None
        collection = None
        return False

# Initialize MongoDB connection
check_mongo_connection()

# Local Fallback Setup
LOCAL_DIR = "/home/admin/Documents/local-data"
LOCAL_FILE = os.path.join(LOCAL_DIR, "odor-data.json")
os.makedirs(LOCAL_DIR, exist_ok=True)  # Create directory if it doesn't exist

# Air Freshener Timing
last_spray = 0
SPRAY_INTERVAL = 36 * 60  # 36 minutes in seconds
SPRAY_DURATION = 1        # 1 second spray

def read_mq135():
    """Read AQI from Arduino Mega over serial."""
    if ser is None:
        return [0] * 4
        
    try:
        ser.flush()  # Clear buffer
        line = ser.readline().decode('utf-8').strip()
        if line:
            try:
                aqi_values = [int(x) for x in line.split(',')]
                if len(aqi_values) == 4 and all(0 <= x <= 500 for x in aqi_values):
                    return aqi_values
            except ValueError:
                print(f"Invalid serial data: {line}")
        return [0] * 4
    except Exception as e:
        print(f"Serial error: {e}")
        return [0] * 4

def read_dht22():
    """Read temperature and humidity from DHT22 sensors."""
    readings = []
    for i, sensor in enumerate(dht_sensors):
        try:
            temp = sensor.temperature
            hum = sensor.humidity
            readings.append({"temp": temp, "hum": hum})
        except Exception as e:
            print(f"DHT22 {i+1} error: {e}")
            readings.append({"temp": 0, "hum": 0})
    return readings

def control_fan(aqi_values):
    """Control exhaust fan based on AQI."""
    max_aqi = max(aqi_values)
    lgpio.gpio_write(h, FAN_PIN, 1 if max_aqi > 300 else 0)

def control_freshener(aqi_values):
    """Control air freshener based on AQI or timer."""
    global last_spray
    current_time = time.time()
    max_aqi = max(aqi_values)
    if max_aqi > 300 or (current_time - last_spray) >= SPRAY_INTERVAL:
        lgpio.gpio_write(h, FRESHENER_PIN, 1)
        time.sleep(SPRAY_DURATION)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        last_spray = current_time

# Save to local JSON
def save_to_local_json(data):
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(LOCAL_FILE), exist_ok=True)
        
        # Check if the file exists and read existing data
        existing_data = []
        if os.path.exists(LOCAL_FILE):
            try:
                with open(LOCAL_FILE, "r") as f:
                    existing_data = json.load(f)
                print(f"Found existing data file with {len(existing_data)} records")
            except json.JSONDecodeError:
                print("Existing file found but couldn't be parsed. Creating new file.")
                existing_data = []
        else:
            print(f"Creating new data file: {LOCAL_FILE}")
        
        # Append new data
        existing_data.append(data)
        
        # Write back all data to file
        temp_file = LOCAL_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, LOCAL_FILE)
        print(f"Data saved to local storage. Total records: {len(existing_data)}")
        return True
    except Exception as e:
        print(f"Local logging error: {e}")
        return False

def log_data(aqi_values, dht_readings):
    """Log data to both MongoDB and local JSON file simultaneously."""
    global client, db, collection
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "timestamp": timestamp,
        "aqi": {f"GAS{i+1}": aqi_values[i] for i in range(4)},
        "dht": {f"TEMP{i+1}": dht_readings[i] for i in range(4)}
    }
    
    # Always save to local storage first
    save_to_local_json(data)
    
    # Then try to save to MongoDB if available
    if collection is not None:
        try:
            collection.insert_one(data)
            print("Data also saved to MongoDB successfully.")
        except Exception as e:
            print(f"MongoDB logging error: {e}. Data saved locally only.")
            client = None
            db = None
            collection = None
    
    return True

def start_monitoring():
    """Start the continuous monitoring process."""
    global ser
    
    # Ensure we have a serial connection
    if ser is None:
        port = find_arduino_serial_port()
        if port is None:
            print("Could not find Arduino Mega. Please check connection and try again.")
            return
    
    print("Odor Module Running...")
    print("Press CTRL+C to return to menu")
    try:
        while True:
            aqi_values = read_mq135()
            dht_readings = read_dht22()
            control_fan(aqi_values)
            control_freshener(aqi_values)
            log_data(aqi_values, dht_readings)
            print(f"AQI: {aqi_values}, DHT: {[r['temp'] for r in dht_readings]}")
            
            # If we lose connection, try to reconnect
            if sum(aqi_values) == 0:  # Likely no data is being received
                print("No AQI data received. Attempting to reconnect...")
                find_arduino_serial_port()
            
            time.sleep(5)  # Update every 5 seconds
    except KeyboardInterrupt:
        print("\nMonitoring stopped. Returning to menu...")
    finally:
        # Turn off outputs when stopping monitoring
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)

def main():
    """Main CLI menu function."""
    try:
        while True:
            print("\n" + "="*50)
            print("Odor Module")
            print("="*50)
            print("1. Start the Module")
            print("2. Exit the Program")
            
            choice = input("\nEnter your choice (1-2): ")
            
            if choice == "1":
                start_monitoring()
            elif choice == "2":
                print("Exiting program...")
                break
            else:
                print("Invalid choice. Please select 1 or 2.")
    finally:
        # Clean up hardware resources
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        lgpio.gpiochip_close(h)
        if ser:
            ser.close()
        if client:
            client.close()

if __name__ == "__main__":
    print("Initializing Odor Module...")
    port = find_arduino_serial_port()
    if port:
        print(f"Successfully connected to Arduino Mega on {port}")
    else:
        print("Warning: Could not find Arduino Mega. Module will start but AQI readings may not work.")
        print("Please check connections and restart if needed.")
    main()