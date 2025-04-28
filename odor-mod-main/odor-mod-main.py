import time
import board
import adafruit_dht
import smbus
import lgpio
from pymongo import MongoClient
import logging

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` to install adafruit-circuitpython-dht, adafruit-blinka, pymongo.
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - DHT22 sensors: GPIO4 (Pin 7), GPIO5 (Pin 29), GPIO6 (Pin 31), GPIO12 (Pin 32).
#    - E18-D80NK: GPIO17 (Pin 11, with 10kΩ/15kΩ voltage divider).
#    - 8RELAY-B: K2 (exhaust fan, GPIO23, Pin 16), K3 (air freshener, GPIO22, Pin 15).
#    - I2C: Arduino Mega A4 (SDA) to GPIO2 (Pin 3), A5 (SCL) to GPIO3 (Pin 5).

# Setup logging to file
logging.basicConfig(filename='odor_module.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# MongoDB Atlas connection setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/bet5_project?retryWrites=true&w=majority&appName=SmartRestroomWeb"
client = MongoClient(MONGO_URI)
db = client['bet5_project']
collection = db['odor_module']

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

FAN_RELAY_PIN = 23  # 8RELAY-B K2 for exhaust fan
FRESHENER_RELAY_PIN = 22  # 8RELAY-B K3 for air freshener
SENSOR_PIN = 17  # Occupancy sensor (E18-D80NK, temporary)

# Configure GPIO pins
lgpio.gpio_claim_output(h, FAN_RELAY_PIN)
lgpio.gpio_claim_output(h, FRESHENER_RELAY_PIN)
lgpio.gpio_claim_input(h, SENSOR_PIN, pull=lgpio.PUD_UP)  # Pull-up for occupancy sensor
lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # Fan off (active-low)
lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 1)  # Freshener off (active-low)

# DHT22 Setup
dht_devices = [
    adafruit_dht.DHT22(board.D4),  # GPIO4
    adafruit_dht.DHT22(board.D5),  # GPIO5
    adafruit_dht.DHT22(board.D6),  # GPIO6
    adafruit_dht.DHT22(board.D12)  # GPIO12
]

# I2C Setup for Arduino Mega (MQ135 readings)
bus = smbus.SMBus(1)  # I2C bus 1 on Pi
ARDUINO_ADDRESS = 8

# Global variables
fan_status = False
freshener_triggered = False
is_occupied = False
last_sensor_state = 1  # 1 = HIGH (no detection) with pull-up
last_exit_time = time.time()
last_spray_time = time.time()
aqi_history = []  # For air_quality_trend
FAN_POST_EXIT_DURATION = 1200  # 20 minutes
last_time = time.time()  # For debouncing

def read_sensors():
    """Read temperature, humidity from DHT22 and AQI from Arduino Mega with retries."""
    temp = [0] * 4
    hum = [0] * 4
    aqi = [0] * 4
    for i, dht in enumerate(dht_devices):
        try:
            temp[i] = dht.temperature
            hum[i] = dht.humidity
        except RuntimeError as e:
            logging.error(f"DHT22 {i+1} read error: {e}")
            temp[i], hum[i] = 0, 0
    for attempt in range(3):  # Retry I2C up to 3 times
        try:
            data = bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 8)
            for i in range(4):
                aqi[i] = (data[i*2] << 8) + data[i*2 + 1]  # Combine MSB and LSB (0-500)
            break
        except Exception as e:
            logging.error(f"I2C read attempt {attempt+1} failed: {e}")
            if attempt == 2:
                aqi = [0] * 4  # Default on final failure
            time.sleep(0.1)
    return temp, hum, aqi

def calculate_avg_aqi(aqi):
    """Calculate average AQI and update history for trend."""
    global aqi_history
    avg_aqi = sum(aqi) / len(aqi) if aqi else 0
    aqi_history.append(avg_aqi)
    if len(aqi_history) > 10:  # Keep last 10 readings
        aqi_history.pop(0)
    return avg_aqi

def calculate_air_quality_trend():
    """Calculate AQI trend (increasing, decreasing, stable)."""
    if len(aqi_history) < 2:
        return "unknown"
    diff = aqi_history[-1] - aqi_history[-2]
    return "increasing" if diff > 5 else "decreasing" if diff < -5 else "stable"

def check_occupancy():
    """Check occupancy status using E18-D80NK sensor (temporary)."""
    global is_occupied, last_sensor_state, last_exit_time, last_time
    current_sensor_state = lgpio.gpio_read(h, SENSOR_PIN)
    if current_sensor_state != last_sensor_state and time.time() - last_time > 1.0:
        if current_sensor_state == 0:  # LOW = Occupied
            is_occupied = True
        else:  # HIGH = Vacant
            is_occupied = False
            last_exit_time = time.time()  # Record exit time
        last_sensor_state = current_sensor_state
        last_time = time.time()
        return not is_occupied  # True if just vacated
    return False

def control_fan(avg_aqi, avg_temp, avg_hum):
    """Control exhaust fan based on AQI, temperature, humidity, and occupancy."""
    global fan_status, last_exit_time
    should_run = False
    if is_occupied:  # Presence trigger
        should_run = True
    elif time.time() - last_exit_time < FAN_POST_EXIT_DURATION:  # 20-min post-exit
        should_run = True
    elif avg_aqi > 300:  # Primary AQI trigger
        should_run = True
    elif avg_aqi > 100 and avg_temp > 25:  # AQI and temperature trigger
        should_run = True
    elif avg_aqi > 150 and avg_temp > 30:  # Severe AQI and temperature
        should_run = True
    elif avg_hum > 60 and avg_aqi > 100:  # Humidity amplifies odor
        should_run = True

    if should_run and not fan_status:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 0)  # LOW to activate (active-low)
        fan_status = True
        print("Fan ON")
    elif not should_run and fan_status:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # HIGH to deactivate
        fan_status = False
        print("Fan OFF")

def control_freshener(avg_aqi, vacated):
    """Control air freshener based on AQI, vacancy, or 36-min timer."""
    global freshener_triggered, last_spray_time
    should_spray = False
    if (avg_aqi > 300 or vacated or time.time() - last_spray_time >= 2160) and not freshener_triggered:
        should_spray = True
    elif avg_aqi > 150 and avg_temp > 30:  # Additional trigger for high temp
        should_spray = True

    if should_spray:
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # LOW to activate (active-low)
        time.sleep(0.5)  # 500ms pulse
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 1)  # HIGH to deactivate
        freshener_triggered = True
        last_spray_time = time.time()
        print("Air Freshener Triggered")
    elif avg_aqi <= 300 and not vacated:
        freshener_triggered = False

def log_data(temp, hum, aqi, avg_aqi, avg_temp, avg_hum):
    """Log sensor data to MongoDB."""
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "temperature": avg_temp,
        "humidity": avg_hum,
        "gas_level": aqi,  # List of 4 AQI values
        "air_quality_index": avg_aqi,
        "fan_status": "on" if fan_status else "off",
        "air_freshener_status": "triggered" if freshener_triggered else "off",
        "occupancy_status": "occupied" if is_occupied else "vacant",
        "average_gas_level": avg_aqi,
        "air_quality_trend": calculate_air_quality_trend(),
        "critical_event": avg_aqi > 300
    }
    try:
        collection.insert_one(data)
        print("Data logged to MongoDB")
    except Exception as e:
        logging.error(f"MongoDB logging error: {e}")

try:
    while True:
        temp, hum, aqi = read_sensors()
        avg_aqi = calculate_avg_aqi(aqi)
        avg_temp = sum(temp) / len(temp) if temp else 0
        avg_hum = sum(hum) / len(hum) if hum else 0
        vacated = check_occupancy()
        control_fan(avg_aqi, avg_temp, avg_hum)
        control_freshener(avg_aqi, vacated)
        log_data(temp, hum, aqi, avg_aqi, avg_temp, avg_hum)
        
        print(f"Avg AQI: {avg_aqi:.2f}, Avg Temp: {avg_temp:.1f}°C, Avg Hum: {avg_hum:.1f}%, Occupancy: {'occupied' if is_occupied else 'vacant'}")
        time.sleep(10)

except KeyboardInterrupt:
    print("Shutting down...")
finally:
    lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # Ensure fan off
    lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 1)  # Ensure freshener off
    lgpio.gpiochip_close(h)
    for dht in dht_devices:
        dht.exit()
    client.close()
    logging.info("Program terminated")