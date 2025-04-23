import lgpio
import time
import sys

# GPIO pin for 8RELAY-B K1 (DC Fan)
K1_PIN = 20  # GPIO20, Pin 38

# Initialize lgpio handle
try:
    h = lgpio.gpiochip_open(0)  # Open GPIO chip
except Exception as e:
    print(f"Error initializing GPIO: {e}")
    sys.exit(1)

def setup_relay():
    """Set up GPIO pin for K1 relay control (active-low)."""
    try:
        lgpio.gpio_claim_output(h, K1_PIN, lgpio.SET_ACTIVE_LOW, 1)  # Initialize HIGH (relay off)
    except Exception as e:
        print(f"Error setting up K1 relay: {e}")
        sys.exit(1)

def cleanup_relay():
    """Turn off K1 relay and release GPIO pin."""
    try:
        lgpio.gpio_write(h, K1_PIN, 1)  # Relay off
        lgpio.gpiochip_close(h)
        print("DC Fan stopped. Exiting...")
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    """Run the DC fan continuously until interrupted."""
    setup_relay()
    try:
        print("Central Hub DC Fan is running! Press CTRL + C to stop.")
        lgpio.gpio_write(h, K1_PIN, 0)  # Relay on (close circuit)
        while True:
            time.sleep(1)  # Keep script running
    except KeyboardInterrupt:
        print("\nScript terminated by user.")
    except Exception as e:
        print(f"Error running DC Fan: {e}")
    finally:
        cleanup_relay()

if __name__ == "__main__":
    main()