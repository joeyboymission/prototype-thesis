import serial
import time
import lgpio
import adafruit_dht
import board
import os
import json
from datetime import datetime
import pytz

# Define global variables at the module level
client = None
db = None
collection = None

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` (pyserial>=3.5, pymongo>=4.12.0, etc.).
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - USB: Arduino Mega to Pi (/dev/ttyUSB0).
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

# Serial Setup for Arduino Mega
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
except serial.SerialException as e:
    print(f"Error opening serial port: {e}")
    ser = None

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
        
        # Use JSON Lines format for efficiency
        with open(LOCAL_FILE, 'a') as f:
            json.dump(data, f)
            f.write('\n')  # JSON Lines format
        print(f"Data saved to local storage.")
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
    main()