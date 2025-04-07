import RPi.GPIO as GPIO
import time

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

# Function to measure distance using ultrasonic sensor
def measure_distance(trigger, echo, num_measurements=5):
    distances = []
    for _ in range(num_measurements):
        GPIO.output(trigger, True)
        time.sleep(0.00001)
        GPIO.output(trigger, False)
        
        start_time = time.time()
        while GPIO.input(echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:
                return None
        
        start_time = time.time()
        while GPIO.input(echo) == 1:
            pulse_end = time.time()
            if pulse_end - start_time > 0.5:
                return None
        
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound = 343 m/s, distance in cm
        distance = round(distance, 2)
        distances.append(distance)
        time.sleep(0.05)
    
    if distances:
        return sum(distances) / len(distances)
    return None

# Function to calibrate a single container with 3 runs
def calibrate_container(container_name, trigger, echo):
    print(f"\nCalibrating {container_name}...")
    full_distances = []
    empty_distances = []
    
    for run in range(1, 4):
        print(f"\n{run}{'st' if run == 1 else 'nd' if run == 2 else 'rd'} CALIBRATION")
        print(f"Calibrating {container_name}...")
        
        input(f"Set {container_name} to FULL (500 mL physical, 425 mL usable) and press Enter: ")
        full_distance = measure_distance(trigger, echo)
        if full_distance is None:
            print(f"Failed to measure full distance on run {run}.")
            return None
        print(f"{container_name} Full Distance: {full_distance} cm")
        full_distances.append(full_distance)
        
        input(f"Set {container_name} to EMPTY (75 mL physical, 0 mL usable) and press Enter: ")
        empty_distance = measure_distance(trigger, echo)
        if empty_distance is None:
            print(f"Failed to measure empty distance on run {run}.")
            return None
        print(f"{container_name} Empty Distance: {empty_distance} cm")
        empty_distances.append(empty_distance)
    
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
        print("5. All Containers")
        print("6. Exit Calibration")
        
        choice = input("Choose Number: ")
        if choice == "6":
            break
        elif choice == "5":
            # Calibrate all containers sequentially
            for i in range(4):
                container = f"CONT{i+1}"
                trigger = triggers[i]
                echo = echos[i]
                data = calibrate_container(container, trigger, echo)
                if data:
                    calibration_data[container] = data
                else:
                    print(f"Calibration failed for {container}. Retry if needed.")
        elif choice in ["1", "2", "3", "4"]:
            container_index = int(choice) - 1
            container = f"CONT{container_index + 1}"
            trigger = triggers[container_index]
            echo = echos[container_index]
            data = calibrate_container(container, trigger, echo)
            if data:
                calibration_data[container] = data
            else:
                print(f"Calibration failed for {container}. Retry if needed.")
        else:
            print("Invalid choice. Please select 1-6.")
        
        # Display current results
        if calibration_data:
            print("\nCurrent Calibration Results:")
            for cont, values in calibration_data.items():
                print(f"{cont}: Full = {values['full']} cm, Empty = {values['empty']} cm")
    
    # Final results
    if calibration_data:
        print("\nFinal Calibration Results:")
        for container, data in calibration_data.items():
            print(f"{container}: Full = {data['full']} cm, Empty = {data['empty']} cm")
        print("Calibration completed. Update these values in 'auto_disp_mod_pi.py' under CALIBRATION_DATA.")
    else:
        print("No containers calibrated.")
except KeyboardInterrupt:
    print("\nCalibration interrupted by user.")
finally:
    GPIO.cleanup()