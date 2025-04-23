import time
import lgpio

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# Relay pin for air freshener (8RELAY-B K3)
FRESHENER_RELAY_PIN = 22  # GPIO22, Pin 15

# Configure GPIO pin
lgpio.gpio_claim_output(h, FRESHENER_RELAY_PIN)
lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # Relay off initially (HIGH for active-low)

def trigger_air_freshener():
    """Trigger air freshener relay for 500ms."""
    try:
        print("Triggering Air Freshener (500ms pulse)...")
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 1)  # LOW to activate relay (active-low)
        time.sleep(0.5)  # 500ms pulse
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # HIGH to deactivate
        print("Air Freshener triggered successfully")
    except Exception as e:
        print(f"Error triggering Air Freshener: {e}")

def test_air_freshener():
    """Test air freshener relay with repeated triggers."""
    print("\nTesting Air Freshener (GPIO22, 8RELAY-B K3)...")
    print("Each trigger sends a 500ms pulse")
    print("Press Ctrl+C to stop")
    try:
        while True:
            trigger_air_freshener()
            time.sleep(5)  # Wait 5 seconds between triggers for safety
    except KeyboardInterrupt:
        print("\nStopped testing Air Freshener")

def main():
    while True:
        print("\nAir Freshener Test Menu")
        print("1. Test Air Freshener (K3)")
        print("2. Exit")
        choice = input("Choose a number: ")

        if choice == "1":
            test_air_freshener()
        elif choice == "2":
            print("Exiting Air Freshener test...")
            break
        else:
            print("Invalid choice, please try again")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpio_write(h, FRESHENER_RELAY_PIN, 0)  # Ensure relay is off
        lgpio.gpiochip_close(h)
        print("GPIO cleanup complete")