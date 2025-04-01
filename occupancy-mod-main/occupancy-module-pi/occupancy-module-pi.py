import RPi.GPIO as GPIO
import time
import json
from datetime import datetime

# GPIO setup
GPIO.setmode(GPIO.BCM)
SENSOR_PIN = 17  # GPIO17 for E18-D80NK signal
BUZZER_PIN = 27  # GPIO27 for buzzer control
GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Pull-up, assuming LOW on detection
GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.output(BUZZER_PIN, GPIO.LOW)  # Buzzer off initially

# Constants
DEBOUNCE_DELAY = 1.0  # 1 second debounce
SHORT_BEEP = 0.2  # 200ms short beep
BEEP_PAUSE = 0.2  # 200ms pause between beeps
LONG_BEEP = 1.0   # 1 second long beep

# Variables
visitor_count = 0  # Start at 0, no offset needed
is_occupied = False
last_sensor_state = GPIO.HIGH  # HIGH means no detection (adjust if sensor behaves differently)
last_detection_time = 0
log_list = []  # Store visitor entries

# Function to control buzzer
def beep_buzzer(duration):
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    time.sleep(duration)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

def double_beep():
    beep_buzzer(SHORT_BEEP)
    time.sleep(BEEP_PAUSE)
    beep_buzzer(SHORT_BEEP)

# Function to update JSON log
def update_log():
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
    with open("occupancy_data.json", "w") as f:
        json.dump(data, f, indent=4)

# Main loop
try:
    print("=== Occupancy Module Started ===")
    print("System Ready!")
    print("Current Status: Vacant")
    print("Visitor Count: 0")
    print("==============================")

    current_start_time = None
    while True:
        current_sensor_state = GPIO.input(SENSOR_PIN)
        current_time = time.time()

        # Check for state change with debounce
        if (current_sensor_state != last_sensor_state and 
            (current_time - last_detection_time) > DEBOUNCE_DELAY):
            
            if current_sensor_state == GPIO.LOW:  # Object detected
                if not is_occupied:
                    # Someone enters
                    is_occupied = True
                    visitor_count += 1
                    current_start_time = current_time
                    print("\n--- Status Change Detected ---")
                    print("Status: Occupied")
                    print(f"Visitor Count: {visitor_count}")
                    double_beep()  # Two short beeps
                    update_log()  # Update JSON immediately for real-time status
            else:  # No object detected
                if is_occupied:
                    # Someone leaves
                    is_occupied = False
                    end_time = current_time
                    duration = end_time - current_start_time
                    entry = {
                        "visitor_id": visitor_count,
                        "start_time": datetime.fromtimestamp(current_start_time).isoformat(),
                        "end_time": datetime.fromtimestamp(end_time).isoformat(),
                        "duration": duration
                    }
                    log_list.append(entry)
                    print("\n--- Status Change Detected ---")
                    print("Status: Vacant")
                    print(f"Visitor Count: {visitor_count}")
                    beep_buzzer(LONG_BEEP)  # One long beep
                    update_log()  # Update JSON with new entry

            last_sensor_state = current_sensor_state
            last_detection_time = current_time

        # Small delay to prevent CPU overload
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nExiting...")
finally:
    GPIO.cleanup()  # Reset GPIO pins on exit