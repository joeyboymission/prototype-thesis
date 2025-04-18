import lgpio
import time
from datetime import datetime
from pymongo import MongoClient

# MongoDB Atlas connection setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
client = MongoClient(MONGO_URI)
db = client['Smart_Cubicle']
collection = db['dispenser_resource']

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# Define trigger and echo pins for each ultrasonic sensor
triggers = [7, 9, 11, 14]  # GPIO7, GPIO9, GPIO11, GPIO14
echos = [8, 10, 13, 15]    # GPIO8, GPIO10, GPIO13, GPIO15

# Set up GPIO pins
for trigger in triggers:
    lgpio.gpio_claim_output(h, trigger)
for echo in echos:
    lgpio.gpio_claim_input(h, echo)

# Calibration data (only CONT1 for now; others will be added)
CALIBRATION_DATA = {
    "CONT1": {"full": 2.84, "empty": 12.67},
    "CONT2": {"full": 2.37, "empty": 12.21},
    "CONT3": {"full": 2.23, "empty": 12.33},
    "CONT4": {"full": 2.91, "empty": 12.88}
}

# Function to measure raw data and distance
def measure_raw_data(trigger, echo, num_measurements=5):
    distances = []
    pulse_durations = []
    for _ in range(num_measurements):
        lgpio.gpio_write(h, trigger, 1)  # Trigger high
        time.sleep(0.00001)              # 10us pulse
        lgpio.gpio_write(h, trigger, 0)  # Trigger low
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:
                return None, None
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:
                return None, None
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound in cm/s
        distance = round(distance, 2)
        distances.append(distance)
        pulse_durations.append(pulse_duration)
        time.sleep(0.05)
    
    if distances and pulse_durations:
        avg_distance = sum(distances) / len(distances)
        avg_pulse_duration = sum(pulse_durations) / len(pulse_durations)
        return avg_pulse_duration, avg_distance
    return None, None

# Function to calculate usable volume in mL
def calculate_usable_volume(container, distance):
    if CALIBRATION_DATA[container]["full"] is None or CALIBRATION_DATA[container]["empty"] is None:
        return None  # Cannot calculate without calibration data
    
    full_distance = CALIBRATION_DATA[container]["full"]
    empty_distance = CALIBRATION_DATA[container]["empty"]
    
    if distance <= full_distance:
        return 425.0  # Full usable volume
    elif distance >= empty_distance:
        return 0.0  # Empty usable volume
    else:
        # Linear interpolation for usable volume
        total_distance_range = empty_distance - full_distance
        distance_from_full = distance - full_distance
        volume_fraction = 1 - (distance_from_full / total_distance_range)
        usable_volume = 425.0 * volume_fraction
        return round(usable_volume, 2)

# Main monitoring function
try:
    print("Automatic Dispenser Module - Liquid Level Monitoring")
    reading_count = 0
    previous_volumes = {}

    while True:
        reading_count += 1
        current_reading = {}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\nReading {reading_count} ({timestamp})")
        
        for i in range(4):
            container = f"CONT{i+1}"
            trigger = triggers[i]
            echo = echos[i]
            
            pulse_duration, distance = measure_raw_data(trigger, echo)
            if pulse_duration is None or distance is None:
                print(f"{container}: Measurement failed (timeout or error)")
                current_reading[container] = {
                    "distance_cm": None,
                    "remaining_volume_ml": None
                }
            else:
                volume = calculate_usable_volume(container, distance)
                amount_used = None
                if reading_count > 1 and container in previous_volumes and previous_volumes[container] is not None and volume is not None:
                    amount_used = round(previous_volumes[container] - volume, 2)
                    if amount_used < 0:
                        amount_used = 0
                
                print(f"{container}: Pulse Duration = {pulse_duration:.6f} s, Distance = {distance} cm, Remaining Volume = {volume if volume is not None else 'N/A'} mL", end="")
                if amount_used is not None:
                    print(f", Amount Used: {amount_used} mL")
                else:
                    print()
                
                current_reading[container] = {
                    "distance_cm": distance,
                    "remaining_volume_ml": volume
                }
            
            previous_volumes[container] = volume
        
        # Save to MongoDB Atlas
        reading_doc = {
            "reading": reading_count,
            "timestamp": timestamp,
            "data": current_reading
        }
        collection.insert_one(reading_doc)
        print(f"Reading {reading_count} saved to MongoDB Atlas")
        
        # Ask if the user wants to read again
        while True:
            choice = input("\nDo you want to read the measurements again? (Y/N): ").strip().upper()
            if choice in ["Y", "N"]:
                break
            print("Please enter 'Y' or 'N'.")
        
        if choice == "N":
            break

except KeyboardInterrupt:
    print("\nMonitoring interrupted by user.")
except Exception as e:
    print(f"\nAn error occurred: {e}")
finally:
    # Cleanup GPIO pins and close chip
    for pin in triggers + echos:
        lgpio.gpio_free(h, pin)
    lgpio.gpiochip_close(h)
    client.close()