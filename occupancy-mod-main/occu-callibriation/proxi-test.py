import RPi.GPIO as GPIO
import time

# GPIO setup for proximity sensor
SENSOR_PIN = 17  # GPIO17 for proximity sensor signal
GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Pull-up, LOW on detection

# Variables
detection_count = 0
last_sensor_state = GPIO.HIGH  # HIGH means no detection

# Function to monitor proximity sensor
def monitor_proximity():
    global detection_count, last_sensor_state
    print("Proximity Test")
    print("Item Detected: 0", end="", flush=True)
    try:
        while True:
            current_sensor_state = GPIO.input(SENSOR_PIN)
            if current_sensor_state != last_sensor_state:
                if current_sensor_state == GPIO.LOW:  # Object detected
                    detection_count += 1
                    print(f"\rItem Detected: {detection_count}", end="", flush=True)
                last_sensor_state = current_sensor_state
            time.sleep(0.1)  # Small delay to prevent rapid counting
    except KeyboardInterrupt:
        print("\nTest stopped by user.")

# CLI Menu
def main():
    while True:
        print("\nProximity Test")
        print("1. Test Proximity")
        print("2. Exit the Test")
        choice = input("Select an option (1 or 2): ")

        if choice == "1":
            monitor_proximity()
        elif choice == "2":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select 1 or 2.")

if __name__ == "__main__":
    try:
        main()
    finally:
        GPIO.cleanup()  # Reset GPIO pins on exit