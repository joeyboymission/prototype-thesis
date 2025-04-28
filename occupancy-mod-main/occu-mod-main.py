import lgpio
import time
import json
import os
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionError, ServerSelectionTimeoutError

# GPIO setup
SENSOR_PIN = 17  # E18-D80NK signal
BUZZER_PIN = 27  # Buzzer control
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(chip, SENSOR_PIN, lgpio.SET_PULL_UP)
lgpio.gpio_claim_output(chip, BUZZER_PIN)
lgpio.gpio_write(chip, BUZZER_PIN, 0)

# MongoDB setup
MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
mongo_collection = None

def check_mongo_connection():
    global mongo_collection
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client['Smart_Cubicle']
        mongo_collection = db['occupancy_data']
        print("Connected to MongoDB successfully.")
        return True
    except (ConnectionError, ServerSelectionTimeoutError) as e:
        print(f"Warning: Failed to connect to MongoDB: {e}. Falling back to local JSON.")
        mongo_collection = None
        return False

# Initialize MongoDB connection
check_mongo_connection()

# Constants
DEBOUNCE_TIME = 0.5  # 500ms
SHORT_BEEP = 0.2     # 200ms
LONG_BEEP = 1.0      # 1s
DATA_DIR = "/home/admin/Documents/local-data"
JSON_FILE = os.path.join(DATA_DIR, "occupancy-data.json")

# States
STATE_VACANT = "Vacant"
STATE_OCCUPIED = "Occupied"

# Variables
current_state = STATE_VACANT
visitor_count = -1
log_list = []
current_start_time = None
last_state_change_time = time.time()

# Buzzer control
def beep_buzzer(duration):
    lgpio.gpio_write(chip, BUZZER_PIN, 1)
    time.sleep(duration)
    lgpio.gpio_write(chip, BUZZER_PIN, 0)

def double_beep():
    beep_buzzer(SHORT_BEEP)
    time.sleep(SHORT_BEEP)
    beep_buzzer(SHORT_BEEP)

# Format duration
def format_duration(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}sec"

# JSON handling
def read_json(file_path):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading JSON: {e}")
    return {"visitors": [], "summary": {"total_visitors": 0, "average_duration": 0}, "current_presence": False}

def write_json(file_path, data):
    temp_file = file_path + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, file_path)
    except IOError as e:
        print(f"Error writing JSON: {e}")

# MongoDB handling
def update_mongo(entry):
    if mongo_collection is None:
        print("MongoDB unreachable, saving to local JSON only.")
        return
    try:
        mongo_collection.insert_one(entry)
    except (ConnectionError, ServerSelectionTimeoutError) as e:
        print(f"Error updating MongoDB: {e}. Saving to local JSON only.")
        global mongo_collection
        mongo_collection = None

# Load initial state
def load_initial_state(file_path):
    global current_state, visitor_count, log_list, current_start_time
    data = read_json(file_path)
    log_list = data.get("visitors", [])
    if log_list:
        visitor_count = max(entry["visitor_id"] for entry in log_list)
        ongoing_visit = next((entry for entry in log_list if "end_time" not in entry), None)
        if ongoing_visit:
            current_state = STATE_OCCUPIED
            current_start_time = float(ongoing_visit["start_time"])
    else:
        visitor_count = -1

# Update JSON and MongoDB logs
def update_log(file_path, new_entry=None):
    if new_entry:
        log_list.append(new_entry)
        update_mongo(new_entry)
    
    total_visitors = len([e for e in log_list if "end_time" in e])
    completed_visits = [e for e in log_list if "end_time" in e]
    average_duration = sum(e["duration"] for e in completed_visits) / total_visitors if total_visitors > 0 else 0
    data = {
        "visitors": log_list,
        "summary": {
            "total_visitors": total_visitors,
            "average_duration": average_duration
        },
        "current_presence": current_state == STATE_OCCUPIED
    }
    write_json(file_path, data)

# Monitor occupancy
def monitor_occupancy(file_path):
    global current_state, visitor_count, log_list, current_start_time, last_state_change_time
    
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Load initial state
    load_initial_state(file_path)
    print("Now listening!")
    print(f"Visitor Count: {max(visitor_count, 0)}")
    print(f"Presence: {current_state}")
    print("Duration: null" if current_start_time is None else format_duration(time.time() - current_start_time))

    last_sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)
    detection_start = None

    while True:
        current_time = time.time()
        sensor_state = lgpio.gpio_read(chip, SENSOR_PIN)

        if (current_time - last_state_change_time) > DEBOUNCE_TIME and sensor_state != last_sensor_state:
            if current_state == STATE_VACANT and sensor_state == 0:
                detection_start = current_time
            elif current_state == STATE_VACANT and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                if (current_time - detection_start) < 2:  # Ensure full cycle within 2s
                    current_state = STATE_OCCUPIED
                    visitor_count += 1
                    current_start_time = current_time
                    new_entry = {
                        "visitor_id": visitor_count,
                        "start_time": current_time,
                        "start_time_iso": datetime.fromtimestamp(current_time).isoformat()
                    }
                    print("\nVisitor Count:", max(visitor_count, 0))
                    print("Presence: Occupied")
                    double_beep()
                    update_log(file_path, new_entry)
                    last_state_change_time = current_time
                    detection_start = None

            elif current_state == STATE_OCCUPIED and sensor_state == 0:
                detection_start = current_time
            elif current_state == STATE_OCCUPIED and sensor_state == 1 and last_sensor_state == 0 and detection_start:
                if (current_time - detection_start) < 2:
                    current_state = STATE_VACANT
                    end_time = current_time
                    duration = end_time - current_start_time
                    formatted_duration = format_duration(duration)
                    for entry in log_list:
                        if entry["visitor_id"] == visitor_count and "end_time" not in entry:
                            entry["end_time"] = end_time
                            entry["duration"] = duration
                            entry["end_time_iso"] = datetime.fromtimestamp(end_time).isoformat()
                            update_mongo({
                                "visitor_id": entry["visitor_id"],
                                "start_time": entry["start_time"],
                                "start_time_iso": entry["start_time_iso"],
                                "end_time": end_time,
                                "end_time_iso": entry["end_time_iso"],
                                "duration": duration
                            })
                            break
                    print("\nVisitor Count:", max(visitor_count, 0))
                    print("Presence: Vacant")
                    print(f"Duration: {formatted_duration}")
                    beep_buzzer(LONG_BEEP)
                    update_log(file_path)
                    last_state_change_time = current_time
                    detection_start = None

            last_sensor_state = sensor_state

        time.sleep(0.05)

# CLI Menu
def main():
    print("Occupancy Module")
    print("Select the following:")
    print("1. Active monitor listening")
    print("2. Exit")
    choice = input("Enter your choice (1 or 2): ")

    if choice == "1":
        try:
            monitor_occupancy(JSON_FILE)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
        except PermissionError as e:
            print(f"Permission error accessing {DATA_DIR}: {e}. Try running with sudo.")
    elif choice == "2":
        print("Exiting...")
    else:
        print("Invalid choice. Please select 1 or 2.")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpiochip_close(chip)
        if mongo_collection is not None:
            client.close()