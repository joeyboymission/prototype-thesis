import lgpio
import time

# Open GPIO chip
chip = lgpio.gpiochip_open(0)  # Open /dev/gpiochip0

# GPIO setup for proximity sensor
# Note: E18-D80NK operates at 5V, but Raspberry Pi GPIO is 3.3V.
# Use a voltage divider (e.g., 2kΩ and 1kΩ resistors) to step down the 5V signal to 3.3V for GPIO17.
SENSOR_PIN = 17  # GPIO17 for E18-D80NK signal
lgpio.gpio_claim_input(chip, SENSOR_PIN, lgpio.SET_PULL_UP)  # Set as input with pull-up

# Variables
detection_count = 0
last_sensor_state = 1  # 1 means HIGH (no detection)

# Function to monitor proximity sensor
def monitor_proximity():
    global detection_count, last_sensor_state
    print("Proximity Test")
    print("Item Detected: 0", end="", flush=True)
    try:
        while True:
            current_sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)
            if current_sensor_state != last_sensor_state:
                if current_sensor_state == 0:  # Object detected (LOW)
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
        lgpio.gpiochip_close(chip)  # Close the GPIO chip on exit