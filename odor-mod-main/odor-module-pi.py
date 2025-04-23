import time
import board
import busio
import adafruit_dht
import smbus
import lgpio
from pymongo import MongoClient

# MongoDB Atlas connection setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
client = MongoClient(MONGO_URI)
db = client['Smart_Cubicle']
collection = db['dispenser_resource']

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

FAN_RELAY_PIN = 23  # 8RELAY-B K2 for exhaust fan
FRESHENER_RELAY_PIN = 22  # 8RELAY-A K1 for air freshener
SENSOR_PIN = 17  # Occupancy sensor (E18-D80NK)

# Configure GPIO pins
lgpio.gpio_claim_output(h, FAN_RELAY_PIN)
lgpio.gpio_claim_output(h, FRESHENER_RELAY_PIN)
lgpio.gpio_claim_input(h, SENSOR_PIN, pull=lgpio.PUD_UP)  # Pull-up for occupancy sensor
lgpio.gpio_write(h, FAN_RELAY_PIN, 0)  # Fan off initially
lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # Freshener off initially

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
last_time = time.time()

def read_sensors():
    """Read temperature, humidity from DHT22 and AQI from Arduino Mega."""
    temp = [0] * 4
    hum = [0] * 4
    aqi = [0] * 4
    for i, dht in enumerate(dht_devices):
        try:
            temp[i] = dht.temperature
            hum[i] = dht.humidity
        except RuntimeError:
            temp[i], hum[i] = 0, 0
    try:
        # Read 8 bytes from Mega (4x 2-byte AQI values)
        data = bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 8)
        for i in range(4):
            aqi[i] = (data[i*2] << 8) + data[i*2 + 1]  # Combine MSB and LSB (0-500)
    except Exception as e:
        print(f"Error reading I2C from Mega: {e}")
        aqi = [0] * 4  # Default to 0 on error
    return temp, hum, aqi

def calculate_avg_aqi(aqi):
    """Calculate average AQI from sensor readings."""
    return sum(aqi) / len(aqi)

def check_occupancy():
    """Check occupancy status using E18-D80NK sensor."""
    global is_occupied, last_sensor_state
    current_sensor_state = lgpio.gpio_read(h, SENSOR_PIN)
    if current_sensor_state != last_sensor_state and time.time() - last_time > 1.0:
        if current_sensor_state == 0:  # LOW = Occupied
            is_occupied = True
        else:  # HIGH = Vacant
            is_occupied = False
        last_sensor_state = current_sensor_state
        return not is_occupied  # True if just vacated
    return False

def control_fan(avg_aqi):
    """Control exhaust fan based on AQI."""
    global fan_status
    if avg_aqi > 200 and not fan_status:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # HIGH to activate relay
        fan_status = True
        print("Fan ON")
    elif avg_aqi <= 200 and fan_status:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 0)  # LOW to deactivate
        fan_status = False
        print("Fan OFF")

def control_freshener(avg_aqi, vacated):
    """Control air freshener based on AQI or occupancy."""
    global freshener_triggered
    if (avg_aqi > 300 or vacated) and not freshener_triggered:
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 1)  # HIGH to activate relay
        time.sleep(0.5)  # 500ms pulse to simulate button press
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # LOW to deactivate
        freshener_triggered = True
        print("Air Freshener Triggered")
    elif avg_aqi <= 300 and not vacated:
        freshener_triggered = False

def log_data(temp, hum, aqi):
    """Log sensor data to MongoDB."""
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sensors": {
            "temp1": {"temperature": temp[0], "humidity": hum[0]},
            "temp2": {"temperature": temp[1], "humidity": hum[1]},
            "temp3": {"temperature": temp[2], "humidity": hum[2]},
            "temp4": {"temperature": temp[3], "humidity": hum[3]},
            "gas1": {"aqi": aqi[0]},
            "gas2": {"aqi": aqi[1]},
            "gas3": {"aqi": aqi[2]},
            "gas4": {"aqi": aqi[3]}
        },
        "fan_status": "on" if fan_status else "off",
        "freshener_status": "triggered" if freshener_triggered else "off",
        "occupancy_status": "occupied" if is_occupied else "vacant"
    }
    try:
        collection.insert_one(data)
        print("Data logged to MongoDB")
    except Exception as e:
        print(f"Error logging to MongoDB: {e}")

try:
    while True:
        temp, hum, aqi = read_sensors()
        avg_aqi = calculate_avg_aqi(aqi)
        vacated = check_occupancy()
        control_fan(avg_aqi)
        control_freshener(avg_aqi, vacated)
        log_data(temp, hum, aqi)
        
        print(f"Avg AQI: {avg_aqi:.2f}, Occupancy: {'occupied' if is_occupied else 'vacant'}")
        time.sleep(10)

except KeyboardInterrupt:
    print("Shutting down...")
finally:
    lgpio.gpiochip_close(h)
    for dht in dht_devices:
        dht.exit()
    client.close()  # Close MongoDB connection