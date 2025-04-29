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

def get_timestamp():
    """Return formatted timestamp string [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    """Print a message with timestamp"""
    print(f"{get_timestamp()} {message}")

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
        log_message("No USB serial ports found.")
        return None
    
    log_message(f"Found {len(ports)} potential serial ports: {ports}")
    
    # Try to release any busy ports using both fuser and systemctl restart commands
    for port in ports:
        port_base = os.path.basename(port)
        try:
            # First attempt to restart the getty service for this port
            try:
                restart_cmd = f"sudo systemctl restart serial-getty@{port_base}.service"
                log_message(f"Restarting serial service: {restart_cmd}")
                subprocess.run(restart_cmd, shell=True, timeout=5)
                time.sleep(1)  # Wait for the service to restart
            except Exception as e:
                log_message(f"Service restart attempt (non-critical): {e}")
            
            # Check if port is in use with fuser
            result = subprocess.run(['sudo', 'fuser', port], capture_output=True, text=True)
            if result.stdout.strip():
                pids = result.stdout.strip().split()
                for pid in pids:
                    log_message(f"Port {port} is in use by process {pid}. Attempting to terminate...")
                    try:
                        kill_cmd = f"sudo kill -9 {pid}"
                        log_message(f"Running: {kill_cmd}")
                        subprocess.run(kill_cmd, shell=True, timeout=5)
                        log_message(f"Successfully terminated process {pid}")
                        # Wait a moment for the port to be released
                        time.sleep(1)
                    except Exception as e:
                        log_message(f"Failed to terminate process {pid}: {e}")
            
            # Set permissions on the port to ensure we can access it
            try:
                subprocess.run(['sudo', 'chmod', '666', port], timeout=5)
                log_message(f"Set permissions on {port} to 666 (read-write for everyone)")
                time.sleep(0.5)
            except Exception as e:
                log_message(f"Failed to set permissions: {e}")
                
        except Exception as e:
            log_message(f"Error checking/managing port usage: {e}")
    
    # Try each port to find Arduino Mega
    for port in ports:
        try:
            log_message(f"Trying to connect to {port}...")
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
                log_message(f"Received: {line}")
                
                # Check if the data looks like our expected format (comma-separated values)
                if ',' in line:
                    try:
                        values = line.split(',')
                        if len(values) == 4:  # We expect 4 values from MQ135 sensors
                            log_message(f"Arduino Mega found on {port}")
                            ser = test_ser
                            return port
                    except Exception:
                        pass
                
                attempts -= 1
                time.sleep(0.5)
            
            # If we reach here, this port didn't work
            test_ser.close()
            
        except Exception as e:
            log_message(f"Failed to connect to {port}: {e}")
    
    log_message("No working Arduino connection found.")
    return None

# DHT22 Setup
dht_pins = [board.D4, board.D5, board.D6, board.D12]  # GPIO4,5,6,12
dht_sensors = [adafruit_dht.DHT22(pin) for pin in dht_pins]

# MongoDB Setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"

def check_mongo_connection():
    global client, db, collection
    if not MONGODB_AVAILABLE:
        log_message("MongoDB support not available, using local storage only.")
        return False
        
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client["Smart_Cubicle"]
        collection = db["odor_module"]
        log_message("Connected to MongoDB successfully.")
        return True
    except Exception as e:
        log_message(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
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

def perform_post_check():
    """Perform Power-On Self Test to verify all components are working"""
    log_message("Starting POST (Power-On Self Test) for Odor Module")
    test_results = {
        "arduino_connection": False,
        "dht_sensors": [False] * 4,
        "fan_control": False,
        "freshener_control": False,
        "local_storage": False,
        "mongodb_connection": False
    }
    
    # Test Arduino connection
    if ser is not None:
        try:
            ser.reset_input_buffer()
            ser.write(b'r')
            line = ser.readline().decode('utf-8').strip()
            if ',' in line and len(line.split(',')) == 4:
                test_results["arduino_connection"] = True
                log_message("✓ Arduino MQ135 sensors responding")
            else:
                log_message("✗ Arduino not responding correctly")
        except Exception as e:
            log_message(f"✗ Arduino test failed: {e}")
    else:
        log_message("✗ Arduino not connected")
    
    # Test DHT22 sensors
    for i, sensor in enumerate(dht_sensors):
        try:
            temp = sensor.temperature
            hum = sensor.humidity
            if temp is not None and hum is not None:
                test_results["dht_sensors"][i] = True
                log_message(f"✓ DHT22 #{i+1} working: {temp}°C, {hum}%")
            else:
                log_message(f"✗ DHT22 #{i+1} not reading properly")
        except Exception as e:
            log_message(f"✗ DHT22 #{i+1} test failed: {e}")
    
    # Test fan control (briefly activate)
    try:
        lgpio.gpio_write(h, FAN_PIN, 1)
        time.sleep(0.5)
        lgpio.gpio_write(h, FAN_PIN, 0)
        test_results["fan_control"] = True
        log_message("✓ Exhaust fan control working")
    except Exception as e:
        log_message(f"✗ Fan control test failed: {e}")
    
    # Test air freshener control (briefly activate)
    try:
        lgpio.gpio_write(h, FRESHENER_PIN, 1)
        time.sleep(0.2)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        test_results["freshener_control"] = True
        log_message("✓ Air freshener control working")
    except Exception as e:
        log_message(f"✗ Air freshener control test failed: {e}")
    
    # Check local storage
    try:
        os.makedirs(os.path.dirname(LOCAL_FILE), exist_ok=True)
        existing_data = []
        if os.path.exists(LOCAL_FILE):
            with open(LOCAL_FILE, 'r') as f:
                existing_data = json.load(f)
            log_message(f"✓ Local storage accessible with {len(existing_data)} existing records")
        else:
            log_message("✓ Local storage accessible (no existing data file)")
        test_results["local_storage"] = True
    except Exception as e:
        log_message(f"✗ Local storage test failed: {e}")
    
    # Check MongoDB connectivity
    if collection is not None:
        try:
            collection.find_one()
            test_results["mongodb_connection"] = True
            log_message("✓ MongoDB connection active")
        except Exception as e:
            log_message(f"✗ MongoDB connection test failed: {e}")
    else:
        log_message("✗ MongoDB not connected, using local storage only")
    
    # Return overall result
    all_okay = (
        test_results["arduino_connection"] and
        any(test_results["dht_sensors"]) and
        test_results["fan_control"] and
        test_results["freshener_control"] and
        test_results["local_storage"]
        # We don't require MongoDB to be working
    )
    
    if all_okay:
        log_message("POST completed successfully. All essential systems operational.")
    else:
        log_message("POST completed with errors. Some systems may not function properly.")
    
    return all_okay

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
                log_message(f"Invalid serial data: {line}")
        return [0] * 4
    except Exception as e:
        log_message(f"Serial error: {e}")
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
            log_message(f"DHT22 {i+1} error: {e}")
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
                log_message(f"Found existing data file with {len(existing_data)} records")
            except json.JSONDecodeError:
                log_message("Existing file found but couldn't be parsed. Creating new file.")
                existing_data = []
        else:
            log_message(f"Creating new data file: {LOCAL_FILE}")
        
        # Append new data
        existing_data.append(data)
        
        # Write back all data to file
        temp_file = LOCAL_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(existing_data, f, indent=2, cls=MongoJSONEncoder)
        os.replace(temp_file, LOCAL_FILE)
        log_message(f"Data saved to local storage. Total records: {len(existing_data)}")
        return True
    except Exception as e:
        log_message(f"Local logging error: {e}")
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
            log_message("Data also saved to MongoDB successfully.")
        except Exception as e:
            log_message(f"MongoDB logging error: {e}. Data saved locally only.")
            client = None
            db = None
            collection = None
    
    return True

def display_options():
    """Display options menu during monitoring"""
    print("\n" + "=" * 80)
    print("Options:")
    print("1. Refresh Data Log Now")
    print("2. Return to Main Menu")
    print("=" * 80)
    print("\nAuto-refresh in 5 seconds...")

def start_monitoring():
    """Start the continuous monitoring process."""
    global ser
    
    # Ensure we have a serial connection
    if ser is None:
        port = find_arduino_serial_port()
        if port is None:
            log_message("Could not find Arduino Mega. Please check connection and try again.")
            return
    
    # Run POST check
    perform_post_check()
    
    log_message("Odor Module Running...")
    log_message("Press CTRL+C to return to menu")
    
    import select
    import sys
    
    try:
        last_display_time = time.time()
        display_width = 80
        
        while True:
            current_time = time.time()
            
            # Read and process sensor data
            aqi_values = read_mq135()
            dht_readings = read_dht22()
            control_fan(aqi_values)
            control_freshener(aqi_values)
            log_data(aqi_values, dht_readings)
            
            # Format the display line
            temp_summary = ", ".join([f"TEMP{i+1}: {r['temp']:.1f}°C" for i, r in enumerate(dht_readings)])
            aqi_summary = ", ".join([f"GAS{i+1}: {val}" for i, val in enumerate(aqi_values)])
            fan_status = "ON" if max(aqi_values) > 300 else "OFF"
            status_line = f"{get_timestamp()} AQI: [{aqi_summary}] | {temp_summary} | Fan: {fan_status}"
            
            # Truncate if too long
            if len(status_line) > display_width:
                status_line = status_line[:display_width-3] + "..."
                
            # Display the status
            print(status_line)
            
            # If we lose connection, try to reconnect
            if sum(aqi_values) == 0:  # Likely no data is being received
                log_message("No AQI data received. Attempting to reconnect...")
                find_arduino_serial_port()
            
            # Display options menu periodically
            if current_time - last_display_time >= 5:
                display_options()
                last_display_time = current_time
            
            # Check for keyboard input (non-blocking)
            if select.select([sys.stdin], [], [], 0)[0]:
                choice = sys.stdin.readline().strip()
                if choice == "1":
                    log_message("Manual refresh triggered")
                    last_display_time = current_time
                    continue
                elif choice == "2":
                    log_message("Returning to main menu...")
                    break
            
            time.sleep(1)  # Check for input more frequently
    except KeyboardInterrupt:
        log_message("\nMonitoring stopped. Returning to menu...")
    finally:
        # Turn off outputs when stopping monitoring
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)

def main():
    """Main CLI menu function."""
    try:
        while True:
            print("\n" + "="*80)
            print("╔═══════════════════════════════════════════════════╗")
            print("║              SMART RESTROOM SYSTEM                ║")
            print("║                  ODOR MODULE                      ║")
            print("╚═══════════════════════════════════════════════════╝")
            print("="*80)
            print("1. Start the Module")
            print("2. Exit the Program")
            
            choice = input("\nEnter your choice (1-2): ")
            
            if choice == "1":
                start_monitoring()
            elif choice == "2":
                log_message("Exiting program...")
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
    log_message("Initializing Odor Module...")
    port = find_arduino_serial_port()
    if port:
        log_message(f"Successfully connected to Arduino Mega on {port}")
    else:
        log_message("Warning: Could not find Arduino Mega. Module will start but AQI readings may not work.")
        log_message("Please check connections and restart if needed.")
    main()