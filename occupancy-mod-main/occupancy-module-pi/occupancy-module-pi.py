import lgpio
import time
import json
import os
from datetime import datetime

# Open GPIO chip
chip = lgpio.gpiochip_open(0)  # Open /dev/gpiochip0

# GPIO setup
SENSOR_PIN = 17  # GPIO17 for E18-D80NK signal
BUZZER_PIN = 27  # GPIO27 for buzzer control
lgpio.gpio_claim_input(chip, SENSOR_PIN, lgpio.SET_PULL_UP)  # Input with pull-up
lgpio.gpio_claim_output(chip, BUZZER_PIN)  # Output
lgpio.gpio_write(chip, BUZZER_PIN, 0)  # Buzzer off initially

# Constants
DEBOUNCE_TIME = 0.5  # 500ms debounce time
SHORT_BEEP = 0.2     # 200ms short beep
LONG_BEEP = 1.0      # 1 second long beep

# States
STATE_VACANT = "Vacant"
STATE_OCCUPIED = "Occupied"

# Variables
current_state = STATE_VACANT
visitor_count = -1  # Start at -1 per requirement
log_list = []       # Store visitor entries
current_start_time = None
last_state_change_time = time.time()

# Buzzer control functions
def beep_buzzer(duration):
    lgpio.gpio_write(chip, BUZZER_PIN, 1)  # HIGH
    time.sleep(duration)
    lgpio.gpio_write(chip, BUZZER_PIN, 0)  # LOW

def double_beep():
    beep_buzzer(SHORT_BEEP)
    time.sleep(SHORT_BEEP)
    beep_buzzer(SHORT_BEEP)

# Format duration in minutes and seconds
def format_duration(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}sec"

# Update JSON log
def update_log(file_path):
    total_visitors = len(log_list)
    average_duration = sum(e["duration"] for e in log_list) / total_visitors if total_visitors > 0 else 0
    data = {
        "visitors": log_list,
        "summary": {
            "total_visitors": total_visitors,
            "average_duration": average_duration
        },
        "current_presence": current_state == STATE_OCCUPIED
    }
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

# Load existing log if available
def load_existing_log(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
            return data.get("visitors", []), data.get("summary", {}).get("total_visitors", 0)
    return [], 0

# Main monitoring function
def monitor_occupancy(file_path):
    global current_state, visitor_count, log_list, current_start_time, last_state_change_time

    # Load existing log
    log_list, loaded_count = load_existing_log(file_path)
    if loaded_count > 0:
        visitor_count = loaded_count - 1  # Adjust for -1 start

    print("Now listening!")
    print(f"Visitor Count: {max(visitor_count, 0)}")
    print(f"Presence: {current_state}")
    print("Duration: null")

    last_sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)  # Initial sensor state

    while True:
        current_time = time.time()
        sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)

        # Check if enough time has passed for debouncing
        if (current_time - last_state_change_time) > DEBOUNCE_TIME and sensor_state != last_sensor_state:
            if current_state == STATE_VACANT and sensor_state == 0:  # HIGH to LOW: Visitor entering
                # Wait for sensor to return to HIGH before confirming entry
                pass  # Transition handled on HIGH

            elif current_state == STATE_VACANT and sensor_state == 1 and last_sensor_state == 0:
                # LOW to HIGH: Visitor has entered
                current_state = STATE_OCCUPIED
                visitor_count += 1
                current_start_time = current_time
                print("\nVisitor Count:", max(visitor_count, 0))
                print("Presence: Occupied")
                double_beep()  # Two short beeps for entry
                update_log(file_path)
                last_state_change_time = current_time

            elif current_state == STATE_OCCUPIED and sensor_state == 0:  # HIGH to LOW: Visitor exiting
                # Wait for sensor to return to HIGH before confirming exit
                pass  # Transition handled on HIGH

            elif current_state == STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0:
                # LOW to HIGH: Visitor has exited
                current_state = STATE_VACANT
                end_time = current_time
                duration = end_time - current_start_time
                formatted_duration = format_duration(duration)
                entry = {
                    "visitor_id": visitor_count,
                    "start_time": datetime.fromtimestamp(current_start_time).isoformat(),
                    "end_time": datetime.fromtimestamp(end_time).isoformat(),
                    "duration": duration
                }
                log_list.append(entry)
                print("\nVisitor Count:", max(visitor_count, 0))
                print("Presence: Vacant")
                print(f"Duration: {formatted_duration}")
                beep_buzzer(LONG_BEEP)  # One long beep for exit
                update_log(file_path)
                last_state_change_time = current_time

            last_sensor_state = sensor_state  # Update last known state

        time.sleep(0.05)  # Reduce CPU usage

# CLI Menu
def main():
    print("Occupancy Module")
    print("Select the following:")
    print("1. Active monitor listening")
    print("2. Exit")
    choice = input("Enter your choice (1 or 2): ")

    if choice == "1":
        directory = input("Please select the file directory (e.g., /home/pi/Documents, or '.' for current): ")
        if directory == '.':
            directory = os.getcwd()
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            print(f"Created directory: {directory}")
        file_path = os.path.join(directory, "occupancy_data.json")
        try:
            monitor_occupancy(file_path)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
    elif choice == "2":
        print("Exiting...")
    else:
        print("Invalid choice. Please select 1 or 2.")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpiochip_close(chip)  # Close GPIO chip on exit