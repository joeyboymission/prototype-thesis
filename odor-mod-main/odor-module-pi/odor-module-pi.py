import time
import json
import board
import busio
import adafruit_dht
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import RPi.GPIO as GPIO

# GPIO Setup
GPIO.setmode(GPIO.BCM)
FAN_RELAY_PIN = 23  # 8RELAY-B K2 for exhaust fan
FRESHENER_RELAY_PIN = 22  # 8RELAY-A K1 for air freshener
GPIO.setup(FAN_RELAY_PIN, GPIO.OUT)
GPIO.setup(FRESHENER_RELAY_PIN, GPIO.OUT)
GPIO.output(FAN_RELAY_PIN, GPIO.LOW)  # Fan off initially
GPIO.output(FRESHENER_RELAY_PIN, GPIO.LOW)  # Freshener off initially

# DHT22 Setup
dht_devices = [
    adafruit_dht.DHT22(board.D4),  # GPIO4
    adafruit_dht.DHT22(board.D5),  # GPIO5
    adafruit_dht.DHT22(board.D6),  # GPIO6
    adafruit_dht.DHT22(board.D12)  # GPIO12
]

# ADS1115 Setup (I2C on GPIO2 SDA, GPIO3 SCL)
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
channels = [AnalogIn(ads, ADS.P0), AnalogIn(ads, ADS.P1),
           AnalogIn(ads, ADS.P2), AnalogIn(ads, ADS.P3)]  # GAS1-GAS4

# Occupancy integration (simplified for this module)
SENSOR_PIN = 17  # From Occupancy Module
GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
is_occupied = False
last_sensor_state = GPIO.HIGH

fan_status = False
freshener_triggered = False

def read_sensors():
    temp = [0] * 4
    hum = [0] * 4
    aqi = [0] * 4
    for i, dht in enumerate(dht_devices):
        try:
            temp[i] = dht.temperature
            hum[i] = dht.humidity
        except RuntimeError:
            temp[i], hum[i] = 0, 0
    for i, chan in enumerate(channels):
        aqi[i] = (chan.value / 32767) * 500  # Map 0-5V to 0-500 AQI
    return temp, hum, aqi

def calculate_avg_aqi(aqi):
    return sum(aqi) / len(aqi)

def check_occupancy():
    global is_occupied, last_sensor_state
    current_sensor_state = GPIO.input(SENSOR_PIN)
    if current_sensor_state != last_sensor_state and time.time() - last_time > 1.0:
        if current_sensor_state == GPIO.LOW:  # Occupied
            is_occupied = True
        else:  # Vacant
            is_occupied = False
        last_sensor_state = current_sensor_state
        return not is_occupied  # True if just vacated
    return False

def control_fan(avg_aqi):
    global fan_status
    if avg_aqi > 200 and not fan_status:
        GPIO.output(FAN_RELAY_PIN, GPIO.HIGH)
        fan_status = True
        print("Fan ON")
    elif avg_aqi <= 200 and fan_status:
        GPIO.output(FAN_RELAY_PIN, GPIO.LOW)
        fan_status = False
        print("Fan OFF")

def control_freshener(avg_aqi, vacated):
    global freshener_triggered
    if (avg_aqi > 300 or vacated) and not freshener_triggered:  # Very Poor AQI or just vacated
        GPIO.output(FRESHENER_RELAY_PIN, GPIO.HIGH)
        time.sleep(0.5)  # Simulate button press for 500ms
        GPIO.output(FRESHENER_RELAY_PIN, GPIO.LOW)
        freshener_triggered = True
        print("Air Freshener Triggered")
    elif avg_aqi <= 300 and not vacated:
        freshener_triggered = False

def log_data(temp, hum, aqi):
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
    with open("/home/pi/odor_data.json", "w") as f:
        json.dump(data, f, indent=4)

last_time = time.time()
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
    GPIO.cleanup()
    for dht in dht_devices:
        dht.exit()