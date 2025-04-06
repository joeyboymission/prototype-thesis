import lgpio as LGPIO
import time
import json
import os
from datetime import datetime

# GPIO setup
LGPIO.gpio_set_mode(LGPIO.BCM)
SENSOR_PIN = 17  # GPIO17 for E18-D80NK signal
BUZZER_PIN = 27  # GPIO27 for buzzer control
LGPIO.gpio_setup(SENSOR_PIN, LGPIO.IN, pull_up_down=LGPIO.PUD_UP)  # Pull-up, LOW on detection
LGPIO.gpio_setup(BUZZER_PIN, LGPIO.OUT)
LGPIO.gpio_write(BUZZER_PIN, LGPIO.LOW)  # Buzzer off initially

# Constants
DEBOUNCE_DELAY = 1.0  # 1 second debounce
SHORT_BEEP = 0.2  # 200ms short beep
BEEP_PAUSE = 0.2  # 200ms pause between beeps
LONG_BEEP = 1.0   # 1 second long beep

# Variables
visitor_count = 0
is_occupied = False
last_sensor_state = LGPIO.HIGH  # HIGH means no detection
last_detection_time = 0
log_list = []  # Store visitor entries
current_start_time = None

# Function to control buzzer
def beep_buzzer(duration):
    LGPIO.gpio_write(BUZZER_PIN, LGPIO.HIGH)
    time.sleep(duration)
    LGPIO.gpio_write(BUZZER_PIN, LGPIO.LOW)

def double_beep():
    beep_buzzer(SHORT_BEEP)
    time.sleep(BEEP_PAUSE)
    beep_buzzer(SHORT_BEEP)

# Function to format duration in minutes and seconds
def format_duration(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}sec"

# Function to update JSON log
def update_log(file_path):
    total_visitors = len(log_list)
    average_duration = sum(e["duration"] for e in log_list) / total_visitors if total_visitors > 0 else 0
    data = {
        "visitors": log_list,
        "summary": {
            "total_visitors": total_visitors,
            "average_duration": average_duration
        },
        "current_presence": is_occupied
    }
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

# Function to load existing log if file exists
def load_existing_log(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
            return data.get("visitors", []), data.get("summary", {}).get("total_visitors", 0)
    return [], 0

# Main monitoring function
def monitor_occupancy(file_path):
    global visitor_count, is_occupied, last_sensor_state, last_detection_time, log_list, current_start_time

    # Load existing log if available
    log_list, visitor_count = load_existing_log(file_path)

    print("Now listening!")
    print(f"Visitor Count: {visitor_count}")
    print("Presence: Vacant")
    print("Duration: null")

    while True:
        current_sensor_state = LGPIO.gpio_read(SENSOR_PIN)
        current_time = time.time()

        # Check for state change with debounce
        if (current_sensor_state != last_sensor_state and
            (current_time - last_detection_time) > DEBOUNCE_DELAY):

            if current_sensor_state == LGPIO.LOW:  # Object detected
                if not is_occupied:
                    # Someone enters
                    is_occupied = True
                    visitor_count += 1
                    current_start_time = current_time
                    print("\nVisitor Count:", visitor_count)
                    print("Presence: Occupied")
                    double_beep()  # Two short beeps
                    update_log(file_path)  # Update JSON for real-time status
            else:  # No object detected
                if is_occupied:
                    # Someone leaves
                    is_occupied = False
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
                    print("\nVisitor Count:", visitor_count)
                    print("Presence: Vacant")
                    print(f"Duration: {formatted_duration}")
                    beep_buzzer(LONG_BEEP)  # One long beep
                    update_log(file_path)  # Update JSON with new entry

            last_sensor_state = current_sensor_state
            last_detection_time = current_time

        time.sleep(0.05)  # Prevent CPU overload

# CLI Menu
def main():
    print("Occupancy Module")
    print("Select the following:")
    print("1. Active monitor listening")
    print("2. Exit")
    choice = input("Enter your choice (1 or 2): ")

    if choice == "1":
        directory = input("Please select the file directory (e.g., /home/pi/Documents, or '.' for current directory): ")
        # Use current directory if '.' is entered
        if directory == '.':
            directory = os.getcwd()
        # Create directory if it doesn't exist
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"Created directory: {directory}")
            except Exception as e:
                print(f"Error: Could not create directory {directory}. {e}")
                return
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
        LGPIO.gpio_reset()  # Reset GPIO pins on exit
