import serial
import time
import lgpio
import adafruit_dht
import board
import pymongo
from datetime import datetime
import pytz

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
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)

# DHT22 Setup
dht_pins = [board.D4, board.D5, board.D6, board.D12]  # GPIO4,5,6,12
dht_sensors = [adafruit_dht.DHT22(pin) for pin in dht_pins]

# MongoDB Setup
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["bet5_project"]
collection = db["odor_module"]

# Air Freshener Timing
last_spray = 0
SPRAY_INTERVAL = 36 * 60  # 36 minutes in seconds
SPRAY_DURATION = 1        # 1 second spray

def read_mq135():
    """Read AQI from Arduino Mega over serial."""
    try:
        ser.flush()  # Clear buffer
        line = ser.readline().decode('utf-8').strip()
        if line:
            aqi_values = [int(x) for x in line.split(',')]
            if len(aqi_values) == 4:
                return [max(0, min(500, x)) for x in aqi_values]  # Clamp to 0-500
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

def log_data(aqi_values, dht_readings):
    """Log data to MongoDB."""
    timestamp = datetime.now(pytz.UTC).isoformat()
    data = {
        "timestamp": timestamp,
        "aqi": {f"GAS{i+1}": aqi_values[i] for i in range(4)},
        "dht": {f"TEMP{i+1}": dht_readings[i] for i in range(4)}
    }
    collection.insert_one(data)

def main():
    print("Odor Module Running...")
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
        print("\nStopping Odor Module...")
    finally:
        lgpio.gpio_write(h, FAN_PIN, 0)
        lgpio.gpio_write(h, FRESHENER_PIN, 0)
        lgpio.gpiochip_close(h)
        ser.close()
        client.close()

if __name__ == "__main__":
    main()