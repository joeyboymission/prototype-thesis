import time
import lgpio

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` (no specific Python dependencies for this script).
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - 8RELAY-B K2 (exhaust fan): GPIO23 (Pin 16).

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# Relay pin for exhaust fan (8RELAY-B K2)
FAN_RELAY_PIN = 23  # GPIO23, Pin 16

# Configure GPIO pin
lgpio.gpio_claim_output(h, FAN_RELAY_PIN)
lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # Relay off initially (HIGH for active-low)

def toggle_fan(state):
    """Toggle exhaust fan relay on or off (active-low: LOW = ON, HIGH = OFF)."""
    try:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 0 if state else 1)  # LOW to activate (ON), HIGH to deactivate (OFF)
        print(f"Exhaust Fan {'ON' if state else 'OFF'} (GPIO23 = {'LOW' if state else 'HIGH'})")
    except Exception as e:
        print(f"Error toggling Exhaust Fan: {e}")

def test_exhaust_fan():
    """Test exhaust fan relay with manual toggle."""
    print("\nTesting Exhaust Fan (GPIO23, 8RELAY-B K2)...")
    print("Relay is active-low: GPIO LOW = Fan ON, GPIO HIGH = Fan OFF")
    print("Press Ctrl+C to stop")
    fan_state = False
    try:
        while True:
            toggle_fan(fan_state)
            time.sleep(10)  # Run for 10 seconds before toggling
            fan_state = not fan_state
    except KeyboardInterrupt:
        print("\nStopped testing Exhaust Fan")
        toggle_fan(False)  # Ensure fan is off

def main():
    while True:
        print("\nExhaust Fan Test Menu")
        print("1. Test Exhaust Fan (K2)")
        print("2. Exit")
        choice = input("Choose a number: ")

        if choice == "1":
            test_exhaust_fan()
        elif choice == "2":
            print("Exiting Exhaust Fan test...")
            break
        else:
            print("Invalid choice, please try again")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 1)  # Ensure relay is off (fan OFF)
        lgpio.gpiochip_close(h)
        print("GPIO cleanup complete")