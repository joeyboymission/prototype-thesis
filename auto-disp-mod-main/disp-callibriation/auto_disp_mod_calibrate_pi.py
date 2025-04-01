import RPi.GPIO as GPIO
import time

# Set GPIO mode to BCM
GPIO.setmode(GPIO.BCM)

# Define trigger and echo pins for each ultrasonic sensor
# SONIC1: CONT1, SONIC2: CONT2, SONIC3: CONT3, SONIC4: CONT4
triggers = [7, 9, 11, 14]  # GPIO7, GPIO9, GPIO11, GPIO14
echos = [8, 10, 13, 15]    # GPIO8, GPIO10, GPIO13, GPIO15

# Set up GPIO pins
for trigger in triggers:
    GPIO.setup(trigger, GPIO.OUT)
for echo in echos:
    GPIO.setup(echo, GPIO.IN)

# Function to measure distance using ultrasonic sensor
def measure_distance(trigger, echo, num_measurements=5):
    distances = []
    for _ in range(num_measurements):
        # Send trigger pulse
        GPIO.output(trigger, True)
        time.sleep(0.00001)  # 10us pulse
        GPIO.output(trigger, False)
        
        # Wait for echo start
        start_time = time.time()
        while GPIO.input(echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.1:  # Timeout
                return None
        
        # Wait for echo end
        start_time = time.time()
        while GPIO.input(echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.1:  # Timeout
                return None
        
        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound in cm/s
        distance = round(distance, 2)
        distances.append(distance)
        time.sleep(0.05)  # Small delay between measurements
    
    if distances:
        avg_distance = sum(distances) / len(distances)
        return avg_distance
    else:
        return None

# Function to calibrate a single container with 3 runs
def calibrate_container(container_name, trigger, echo):
    print(f"\nCalibrating {container_name}...")
    full_distances = []
    empty_distances = []
    
    for run in range(1, 4):
        print(f"\n{run}{'st' if run == 1 else 'nd' if run == 2 else 'rd'} CALIBRATION")
        print(f"Calibrating {container_name}...")
        
        # Full measurement
        input(f"Set {container_name} to FULL (600ml) and press Enter: ")
        full_distance = measure_distance(trigger, echo)
        if full_distance is None:
            print(f"Failed to measure full distance on run {run}.")
            return None
        print(f"{container_name} Full Distance: {full_distance} cm")
        full_distances.append(full_distance)
        
        # Empty measurement
        input(f"Set {container_name} to EMPTY (0ml) and press Enter: ")
        empty_distance = measure_distance(trigger, echo)
        if empty_distance is None:
            print(f"Failed to measure empty distance on run {run}.")
            return None
        print(f"{container_name} Empty Distance: {empty_distance} cm")
        empty_distances.append(empty_distance)
    
    # Calculate averages
    avg_full = round(sum(full_distances) / len(full_distances), 2)
    avg_empty = round(sum(empty_distances) / len(empty_distances), 2)
    
    if avg_empty <= avg_full:
        print(f"Error: Average empty distance ({avg_empty} cm) should be greater than average full distance ({avg_full} cm) for {container_name}.")
        return None
    
    print(f"\n{container_name} Average Results:")
    print(f"Full Distance (avg of 3 runs): {avg_full} cm")
    print(f"Empty Distance (avg of 3 runs): {avg_empty} cm")
    return {"full": avg_full, "empty": avg_empty}

# Main calibration loop
try:
    calibration_data = {}
    while True:
        print("\nSelect Container to Calibrate:")
        print("1. Container 1")
        print("2. Container 2")
        print("3. Container 3")
        print("4. Container 4")
        print("5. Exit Calibration")
        
        choice = input("Choose Number: ")
        if choice == "5":
            break
        elif choice not in ["1", "2", "3", "4"]:
            print("Invalid choice. Please select 1-4 or 5 to exit.")
            continue
        
        container_index = int(choice) - 1
        container = f"CONT{container_index + 1}"
        trigger = triggers[container_index]
        echo = echos[container_index]
        
        data = calibrate_container(container, trigger, echo)
        if data:
            calibration_data[container] = data
        else:
            print(f"Calibration failed for {container}. Retry if needed.")
        
        # Display current results
        print("\nCurrent Calibration Results:")
        for cont, values in calibration_data.items():
            print(f"{cont}: Full = {values['full']} cm, Empty = {values['empty']} cm")
    
    # Final results
    if calibration_data:
        print("\nFinal Calibration Results:")
        for container, data in calibration_data.items():
            print(f"{container}: Full = {data['full']} cm, Empty = {data['empty']} cm")
        print("Calibration completed. Please note these values for use in 'auto_disp_mod_pi.py'.")
    else:
        print("No containers calibrated.")
except KeyboardInterrupt:
    print("\nCalibration interrupted by user.")
finally:
    GPIO.cleanup()