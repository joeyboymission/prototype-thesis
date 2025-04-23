import time
import lgpio

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# Relay pin for exhaust fan (8RELAY-B K2)
FAN_RELAY_PIN = 23  # GPIO23, Pin 16

# Configure GPIO pin
lgpio.gpio_claim_output(h, FAN_RELAY_PIN)
lgpio.gpio_write(h, FAN_RELAY_PIN, 0)  # Relay off initially (HIGH for active-low)

def toggle_fan(state):
    """Toggle exhaust fan relay on or off."""
    try:
        lgpio.gpio_write(h, FAN_RELAY_PIN, 1 if state else 0)  # LOW to activate (active-low)
        print(f"Exhaust Fan {'ON' if state else 'OFF'}")
    except Exception as e:
        print(f"Error toggling Exhaust Fan: {e}")

def test_exhaust_fan():
    """Test exhaust fan relay with manual toggle."""
    print("\nTesting Exhaust Fan (GPIO23, 8RELAY-B K2)...")
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
        lgpio.gpio_write(h, FAN_RELAY_PIN, 0)  # Ensure relay is off
        lgpio.gpiochip_close(h)
        print("GPIO cleanup complete")