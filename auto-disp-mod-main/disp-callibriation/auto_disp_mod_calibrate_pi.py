import lgpio
import time

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

# Function to measure distance for a single sensor
def measure_distance(trigger, echo, num_measurements=5):
    distances = []
    for _ in range(num_measurements):
        lgpio.gpio_write(h, trigger, 1)  # Trigger high
        time.sleep(0.00001)              # 10us pulse
        lgpio.gpio_write(h, trigger, 0)  # Trigger low
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 0:
            pulse_start = time.time()
            if pulse_start - start_time > 0.5:
                return None
        
        start_time = time.time()
        while lgpio.gpio_read(h, echo) == 1:
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

# Function to calibrate a single container with 3 runs (used for individual calibration)
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

# Function to calibrate all containers simultaneously
def calibrate_all_containers():
    print("\nCalibrating ALL...")
    # Store distances for each run
    all_full_distances = {f"CONT{i+1}": [] for i in range(4)}
    all_empty_distances = {f"CONT{i+1}": [] for i in range(4)}
    
    for run in range(1, 4):
        print(f"\n{run}{'st' if run == 1 else 'nd' if run == 2 else 'rd'} CALIBRATION")
        print("Calibrating CONT1, CONT2, CONT3, and CONT4...")
        
        # Measure full distances for all containers
        input("Set ALL CONT to FULL (500 mL physical, 425 mL usable) and press Enter: ")
        for i in range(4):
            container = f"CONT{i+1}"
            trigger = triggers[i]
            echo = echos[i]
            full_distance = measure_distance(trigger, echo)
            if full_distance is None:
                print(f"Failed to measure full distance for {container} on run {run}.")
                return None
            print(f"{container} Full Distance: {full_distance} cm")
            all_full_distances[container].append(full_distance)
        
        # Measure empty distances for all containers
        input("Set ALL CONT to EMPTY (75 mL physical, 0 mL usable) and press Enter: ")
        for i in range(4):
            container = f"CONT{i+1}"
            trigger = triggers[i]
            echo = echos[i]
            empty_distance = measure_distance(trigger, echo)
            if empty_distance is None:
                print(f"Failed to measure empty distance for {container} on run {run}.")
                return None
            print(f"{container} Empty Distance: {empty_distance} cm")
            all_empty_distances[container].append(empty_distance)
    
    # Calculate averages for each container
    calibration_data = {}
    for i in range(4):
        container = f"CONT{i+1}"
        avg_full = round(sum(all_full_distances[container]) / len(all_full_distances[container]), 2)
        avg_empty = round(sum(all_empty_distances[container]) / len(all_empty_distances[container]), 2)
        
        if avg_empty <= avg_full:
            print(f"Error: Average empty distance ({avg_empty} cm) should be greater than average full distance ({avg_full} cm) for {container}.")
            return None
        
        print(f"\n{container} Average Results:")
        print(f"Full Distance (avg of 3 runs): {avg_full} cm")
        print(f"Empty Distance (avg of 3 runs): {avg_empty} cm")
        calibration_data[container] = {"full": avg_full, "empty": avg_empty}
    
    return calibration_data

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
            # Calibrate all containers simultaneously
            data = calibrate_all_containers()
            if data:
                calibration_data.update(data)
            else:
                print("Calibration failed for one or more containers. Retry if needed.")
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
except Exception as e:
    print(f"\nAn error occurred: {e}")
finally:
    # Cleanup GPIO pins and close chip
    for pin in triggers + echos:
        lgpio.gpio_free(h, pin)
    lgpio.gpiochip_close(h)