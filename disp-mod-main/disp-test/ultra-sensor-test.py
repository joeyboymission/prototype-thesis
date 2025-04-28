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

# Function to measure raw data from ultrasonic sensor
def measure_raw_data(trigger, echo):
    # Send trigger pulse
    GPIO.output(trigger, True)
    time.sleep(0.00001)  # 10us pulse
    GPIO.output(trigger, False)
    
    # Wait for echo start
    start_time = time.time()
    while GPIO.input(echo) == 0:
        pulse_start = time.time()
        if pulse_start - start_time > 0.1:  # Timeout
            return None, None
    
    # Wait for echo end
    start_time = time.time()
    while GPIO.input(echo) == 1:
        pulse_end = time.time()
        if pulse_end - start_time > 0.1:  # Timeout
            return None, None
    
    # Calculate raw pulse duration and distance
    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150  # Speed of sound in cm/s
    distance = round(distance, 2)
    return pulse_duration, distance

# Function to test a single sensor
def test_sensor(sensor_name, trigger, echo):
    print(f"\nTesting {sensor_name}...")
    print("Press Ctrl+C to stop testing this sensor.")
    try:
        while True:
            pulse_duration, distance = measure_raw_data(trigger, echo)
            if pulse_duration is None or distance is None:
                print(f"{sensor_name}: Measurement failed (timeout or error)")
            else:
                print(f"{sensor_name}: Pulse Duration = {pulse_duration:.6f} s, Distance = {distance} cm")
            time.sleep(0.5)  # Update every 0.5 seconds for readability
    except KeyboardInterrupt:
        print(f"\nStopped testing {sensor_name}.")
        return

# Main test loop
try:
    print("Ultrasonic Sensor Test Script")
    while True:
        print("\nSelect Sensor to Test:")
        print("1. Sensor 1 (CONT1)")
        print("2. Sensor 2 (CONT2)")
        print("3. Sensor 3 (CONT3)")
        print("4. Sensor 4 (CONT4)")
        print("5. Exit Test")
        
        choice = input("Choose Number: ")
        if choice == "5":
            print("Exiting test script.")
            break
        elif choice not in ["1", "2", "3", "4"]:
            print("Invalid choice. Please select 1-4 or 5 to exit.")
            continue
        
        sensor_index = int(choice) - 1
        sensor_name = f"Sensor {choice} (CONT{choice})"
        trigger = triggers[sensor_index]
        echo = echos[sensor_index]
        
        test_sensor(sensor_name, trigger, echo)
except KeyboardInterrupt:
    print("\nTest script interrupted by user.")
finally:
    GPIO.cleanup()