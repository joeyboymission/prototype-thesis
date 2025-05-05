#!/usr/bin/env python3
import time
import os
import sys
import lgpio

# GPIO Chip
GPIO_CHIP = 0
h = None  # GPIO handle

# Define trigger and echo pins for each ultrasonic sensor
# SONIC1: CONT1, SONIC2: CONT2, SONIC3: CONT3, SONIC4: CONT4
TRIGGERS = [7, 9, 11, 14]  # GPIO7, GPIO9, GPIO11, GPIO14
ECHOS = [8, 10, 13, 15]    # GPIO8, GPIO10, GPIO13, GPIO15

def setup_gpio():
    """Initialize GPIO for ultrasonic sensors"""
    global h
    
    try:
        print("Initializing GPIO...")
        h = lgpio.gpiochip_open(GPIO_CHIP)
        
        # Setup trigger pins as output
        for trigger in TRIGGERS:
            lgpio.gpio_claim_output(h, trigger)
            
        # Setup echo pins as input
        for echo in ECHOS:
            lgpio.gpio_claim_input(h, echo)
            
        print("GPIO initialized successfully")
        return True
    except Exception as e:
        print(f"Error initializing GPIO: {e}")
        return False

def cleanup_gpio():
    """Clean up GPIO resources"""
    global h
    if h is not None:
        for pin in TRIGGERS + ECHOS:
            try:
                lgpio.gpio_free(h, pin)
            except:
                pass
        try:
            lgpio.gpiochip_close(h)
        except:
            pass
        print("GPIO resources cleaned up")

def measure_distance(trigger, echo, num_measurements=5):
    """Measure distance using ultrasonic sensor with multiple readings for accuracy"""
    global h
    distances = []
    
    for _ in range(num_measurements):
        try:
            lgpio.gpio_write(h, trigger, 1)  # Trigger high
            time.sleep(0.00001)              # 10us pulse
            lgpio.gpio_write(h, trigger, 0)  # Trigger low
            
            # Wait for echo to go high
            start_time = time.time()
            while lgpio.gpio_read(h, echo) == 0:
                pulse_start = time.time()
                if pulse_start - start_time > 0.5:  # Timeout after 0.5s
                    return None, None
            
            # Wait for echo to go low
            start_time = time.time()
            while lgpio.gpio_read(h, echo) == 1:
                pulse_end = time.time()
                if pulse_end - start_time > 0.5:  # Timeout after 0.5s
                    return None, None
            
            # Calculate distance
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # Speed of sound: 343 m/s -> 17150 cm/s
            distances.append(round(distance, 2))
            
            time.sleep(0.05)  # Short delay between measurements
        except Exception as e:
            print(f"Error during measurement: {e}")
            return None, None
    
    # Remove outliers and average
    if distances:
        if len(distances) > 2:
            # Remove min and max values
            distances.remove(min(distances))
            distances.remove(max(distances))
        
        # Average the remaining values
        avg_distance = sum(distances) / len(distances)
        return pulse_duration, avg_distance
    
    return None, None

def test_sensor(sensor_name, trigger, echo):
    """Test a single sensor with continuous readings"""
    print(f"\nTesting {sensor_name}...")
    print("Press Ctrl+C to stop testing this sensor.")
    try:
        while True:
            pulse_duration, distance = measure_distance(trigger, echo)
            if pulse_duration is None or distance is None:
                print(f"{sensor_name}: Measurement failed (timeout or error)")
            else:
                print(f"{sensor_name}: Pulse Duration = {pulse_duration:.6f} s, Distance = {distance:.2f} cm")
            time.sleep(0.5)  # Update every 0.5 seconds for readability
    except KeyboardInterrupt:
        print(f"\nStopped testing {sensor_name}.")
        return

def test_all_sensors():
    """Test all sensors simultaneously and display readings in a tabular format"""
    print("\nTesting All Sensors...")
    print("Press Ctrl+C to stop testing.")
    
    try:
        # Print header
        print("\n{:<15} {:<15} {:<15}".format("Sensor", "Distance (cm)", "Status"))
        print("-" * 45)
        
        while True:
            results = []
            
            # Measure distance for all sensors
            for i, (trigger, echo) in enumerate(zip(TRIGGERS, ECHOS)):
                sensor_name = f"CONT{i+1}"
                _, distance = measure_distance(trigger, echo)
                
                if distance is None:
                    status = "ERROR"
                    distance_str = "N/A"
                else:
                    status = "OK"
                    distance_str = f"{distance:.2f}"
                
                results.append((sensor_name, distance_str, status))
            
            # Clear previous output (works in most terminals)
            print("\033[4A", end="")  # Move cursor up 4 lines
            
            # Print header again
            print("\n{:<15} {:<15} {:<15}".format("Sensor", "Distance (cm)", "Status"))
            print("-" * 45)
            
            # Print results
            for sensor_name, distance_str, status in results:
                status_color = "\033[92m" if status == "OK" else "\033[91m"  # Green for OK, Red for ERROR
                print("{:<15} {:<15} {}{}{}".format(
                    sensor_name, distance_str, status_color, status, "\033[0m"))
            
            time.sleep(0.5)  # Update every 0.5 seconds
            
    except KeyboardInterrupt:
        print("\n\nStopped testing all sensors.")
        return

def main():
    """Main test loop"""
    print("Ultrasonic Sensor Test Script")
    
    # Initialize GPIO
    if not setup_gpio():
        print("Failed to initialize GPIO. Exiting.")
        return
    
    try:
        while True:
            print("\nSelect Option:")
            print("1. Test Sensor 1 (CONT1)")
            print("2. Test Sensor 2 (CONT2)")
            print("3. Test Sensor 3 (CONT3)")
            print("4. Test Sensor 4 (CONT4)")
            print("5. Test All Sensors Simultaneously")
            print("6. Exit Test")
            
            choice = input("Choose Number: ")
            if choice == "6":
                print("Exiting test script.")
                break
            elif choice == "5":
                test_all_sensors()
            elif choice not in ["1", "2", "3", "4"]:
                print("Invalid choice. Please select 1-6.")
                continue
            else:
                sensor_index = int(choice) - 1
                sensor_name = f"Sensor {choice} (CONT{choice})"
                trigger = TRIGGERS[sensor_index]
                echo = ECHOS[sensor_index]
                
                test_sensor(sensor_name, trigger, echo)
    
    except KeyboardInterrupt:
        print("\nTest script interrupted by user.")
    finally:
        cleanup_gpio()

if __name__ == "__main__":
    main()