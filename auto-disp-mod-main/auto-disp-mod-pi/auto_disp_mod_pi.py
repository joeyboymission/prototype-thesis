import RPi.GPIO as GPIO
import time
import json
import os
from datetime import datetime

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
    readings = []  # Store all readings for JSON export
    reading_count = 0
    previous_volumes = {}  # To track volume changes for "Amount Used"

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
                volume = calculate_volume(container, distance)
                # Calculate Amount Used (only from second reading onward)
                amount_used = None
                if reading_count > 1 and container in previous_volumes and previous_volumes[container] is not None and volume is not None:
                    amount_used = round(previous_volumes[container] - volume, 2)
                    if amount_used < 0:
                        amount_used = 0  # Ignore negative usage (e.g., due to noise)
                
                # Print the reading
                print(f"{container}: Pulse Duration = {pulse_duration:.6f} s, Distance = {distance} cm, Remaining Volume = {volume if volume is not None else 'N/A'} mL", end="")
                if amount_used is not None:
                    print(f", Amount Used: {amount_used} mL")
                else:
                    print()  # New line if no Amount Used
                
                current_reading[container] = {
                    "distance_cm": distance,
                    "remaining_volume_ml": volume
                }
            
            # Update previous volume for the next reading
            previous_volumes[container] = volume
        
        readings.append({
            "reading": reading_count,
            "timestamp": timestamp,
            "data": current_reading
        })
        
        # Ask if the user wants to read again
        while True:
            choice = input("\nDo you want to read the measurements again? (Y/N): ").strip().upper()
            if choice in ["Y", "N"]:
                break
            print("Please enter 'Y' or 'N'.")
        
        if choice == "N":
            break
    
    # Export data to JSON
    if readings:
        while True:
            file_path = input("\nWhich file path to export the data (e.g., /home/admin/data.json): ")
            try:
                directory = os.path.dirname(file_path)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory)
                with open(file_path, "w") as f:
                    json.dump(readings, f, indent=4)
                print(f"Data exported to {file_path}")
                break
            except Exception as e:
                print(f"Error writing to file: {e}")
                print("Please try again or specify a different path.")
    else:
        print("No readings to export.")

except KeyboardInterrupt:
    print("\nMonitoring interrupted by user.")
finally:
    GPIO.cleanup()