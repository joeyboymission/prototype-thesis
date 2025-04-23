import lgpio
import time
import sys

# GPIO pin assignments for 8RELAY-B
RELAY_PINS = {
    'K1': 20,  # Central Hub DC Fan (GPIO20, Pin 38)
    'K2': 23,  # AC Exhaust Fan (GPIO23, Pin 16)
    'K3': 22,  # Air Freshener (GPIO22, Pin 15)
    'K4': None, 'K5': None, 'K6': None, 'K7': None, 'K8': None  # Unassigned
}

# Initialize lgpio handle
try:
    h = lgpio.gpiochip_open(0)  # Open GPIO chip
except Exception as e:
    print(f"Error initializing GPIO: {e}")
    sys.exit(1)

def setup_relays():
    """Set up GPIO pins for relay control (active-low)."""
    try:
        for key, pin in RELAY_PINS.items():
            if pin is not None:
                lgpio.gpio_claim_output(h, pin, lgpio.SET_ACTIVE_LOW, 1)  # Initialize HIGH (relay off)
    except Exception as e:
        print(f"Error setting up relays: {e}")
        sys.exit(1)

def cleanup_relays():
    """Turn off all relays and release GPIO pins."""
    try:
        for key, pin in RELAY_PINS.items():
            if pin is not None:
                lgpio.gpio_write(h, pin, 1)  # Relay off
        lgpio.gpiochip_close(h)
    except Exception as e:
        print(f"Error during cleanup: {e}")

def test_fan(channel, name):
    """Test fan (K1 or K2) with continuous operation until interrupted."""
    while True:
        print(f"\n{name} Test")
        print("1. Turn On the Fan")
        print("2. Return to the Main Menu")
        choice = input("Select an option (1-2): ")

        if choice == '1':
            try:
                print("\nFan is running now!")
                print("Press CTRL + C to terminate the test")
                lgpio.gpio_write(h, RELAY_PINS[channel], 0)  # Relay on
                while True:
                    time.sleep(1)  # Keep fan running
            except KeyboardInterrupt:
                lgpio.gpio_write(h, RELAY_PINS[channel], 1)  # Relay off
                print("\nFan test terminated.")
            except Exception as e:
                print(f"Error during fan test: {e}")
                lgpio.gpio_write(h, RELAY_PINS[channel], 1)  # Ensure relay off
        elif choice == '2':
            break
        else:
            print("Invalid option. Please select 1 or 2.")

def test_air_freshener():
    """Test air freshener (K3) with a 500ms spray pulse."""
    while True:
        print("\nAir Freshener Test")
        print("1. Trigger the spray")
        print("2. Return to the Main Menu")
        choice = input("Select an option (1-2): ")

        if choice == '1':
            try:
                print("Triggering air freshener spray...")
                lgpio.gpio_write(h, RELAY_PINS['K3'], 0)  # Relay on
                time.sleep(0.5)  # 500ms pulse
                lgpio.gpio_write(h, RELAY_PINS['K3'], 1)  # Relay off
                print("Spray triggered successfully!")
            except Exception as e:
                print(f"Error during air freshener test: {e}")
                lgpio.gpio_write(h, RELAY_PINS['K3'], 1)  # Ensure relay off
        elif choice == '2':
            break
        else:
            print("Invalid option. Please select 1 or 2.")

def test_unused_channel(channel):
    """Handle unused channels (K4-K8)."""
    try:
        print(f"\nAssign some components/modules!")
        print(f"This channel ({channel}) is not been used please update the script")
        print("Press CTRL + C to return to the Main Menu")
        while True:
            time.sleep(1)  # Wait for CTRL+C
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")

def main_menu():
    """Display main menu and handle user selections."""
    setup_relays()
    try:
        while True:
            print("\nTest 8 Channel Relay")
            print("1. K1 - Central Hub Exhaust Fan")
            print("2. K2 - AC Exhaust Fan")
            print("3. K3 - Air Freshener")
            print("4. K4")
            print("5. K5")
            print("6. K6")
            print("7. K7")
            print("8. K8")
            print("9. Exit the Program")
            choice = input("Select an option (1-9): ")

            if choice == '1':
                test_fan('K1', "Central Hub Exhaust Fan")
            elif choice == '2':
                test_fan('K2', "AC Exhaust Fan")
            elif choice == '3':
                test_air_freshener()
            elif choice in ['4', '5', '6', '7', '8']:
                test_unused_channel(f"K{choice}")
            elif choice == '9':
                print("Exiting program...")
                break
            else:
                print("Invalid option. Please select 1-9.")
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    finally:
        cleanup_relays()

if __name__ == "__main__":
    main_menu()