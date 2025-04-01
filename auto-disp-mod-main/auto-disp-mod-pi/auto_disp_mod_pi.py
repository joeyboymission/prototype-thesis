import RPi.GPIO as GPIO
import time
import json
import os

# Set GPIO mode to BCM
GPIO.setmode(GPIO.BCM)

# Define trigger and echo pins for each ultrasonic sensor
triggers = [7, 9, 11, 14]  # GPIO7, GPIO9, GPIO11, GPIO14
echos = [8, 10, 13, 15]    # GPIO8, GPIO10, GPIO13, GPIO15

# Set up GPIO pins
for trigger in triggers:
    GPIO.setup(trigger, GPIO.OUT)
for echo in echos:
    GPIO.setup(echo, GPIO.IN)

# Calibration data (only CONT1 for now; others will be added)
CALIBRATION_DATA = {
    "CONT1": {"full": 2.84, "empty": 12.67},
    "CONT2": {"full": None, "empty": None},
    "CONT3": {"full": None, "empty": None},
    "CONT4": {"full": None, "empty": None}
}

# Function to measure raw data and distance
def measure_raw_data(trigger, echo, num_measurements=5):
    distances = []
    pulse_durations = []
    for _ in range(num_measurements):
        GPIO.output(trigger, True)
        time.sleep(0.00001)
        GPIO.output(trigger, False)
        
        start_time = time.time()
        while GPIO.input(echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:
                return None, None
        
        start_time = time.time()
        while GPIO.input(echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:
                return None, None
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)
        distances.append(distance)
        pulse_durations.append(pulse_duration)
        time.sleep(0.05)
    
    if distances and pulse_durations:
        avg_distance = sum(distances) / len(distances)
        avg_pulse_duration = sum(pulse_durations) / len(pulse_durations)
        return avg_pulse_duration, avg_distance
    return None, None

# Function to calculate remaining volume in mL
def calculate_volume(container, distance):
    if CALIBRATION_DATA[container]["full"] is None or CALIBRATION_DATA[container]["empty"] is None:
        return None  # Cannot calculate without calibration data
    
    full_distance = CALIBRATION_DATA[container]["full"]
    empty_distance = CALIBRATION_DATA[container]["empty"]
    
    # Calculate liquid height
    liquid_height = empty_distance - distance
    if liquid_height < 0:
        liquid_height = 0  # Below full
    elif liquid_height > (empty_distance - full_distance):
        liquid_height = empty_distance - full_distance  # Above empty
    
    # Volume per cm of height (600 mL over the full liquid height)
    total_height = empty_distance - full_distance
    volume_per_cm = 600 / total_height  # 600 mL for the full height
    volume = liquid_height * volume_per_cm
    return round(volume, 2)

# Main monitoring function
try:
    print("Automatic Dispenser Module - Liquid Level Monitoring")
    data = {}
    
    for i in range(4):
        container = f"CONT{i+1}"
        trigger = triggers[i]
        echo = echos[i]
        
        pulse_duration, distance = measure_raw_data(trigger, echo)
        if pulse_duration is None or distance is None:
            print(f"{container}: Measurement failed (timeout or error)")
            data[container] = {
                "pulse_duration_s": None,
                "distance_cm": None,
                "remaining_volume_ml": None
            }
        else:
            volume = calculate_volume(container, distance)
            print(f"{container}: Pulse Duration = {pulse_duration:.6f} s, Distance = {distance} cm, Remaining Volume = {volume if volume is not None else 'N/A'} mL")
            data[container] = {
                "pulse_duration_s": pulse_duration,
                "distance_cm": distance,
                "remaining_volume_ml": volume
            }
    
    # Ask for file path to export data
    while True:
        file_path = input("\nWhich file path to export the data (e.g., /home/admin/data.json): ")
        try:
            # Ensure the directory exists
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
            print(f"Data exported to {file_path}")
            break
        except Exception as e:
            print(f"Error writing to file: {e}")
            print("Please try again or specify a different path.")

except KeyboardInterrupt:
    print("\nMonitoring interrupted by user.")
finally:
    GPIO.cleanup()