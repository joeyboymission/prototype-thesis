import time
import lgpio
import adafruit_dht
import board

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# DHT22 Setup
dht_devices = [
    adafruit_dht.DHT22(board.D4),  # GPIO4, Pin 7
    adafruit_dht.DHT22(board.D5),  # GPIO5, Pin 29
    adafruit_dht.DHT22(board.D6),  # GPIO6, Pin 31
    adafruit_dht.DHT22(board.D12)  # GPIO12, Pin 32
]

def read_dht22(sensor_index=None):
    """Read raw temperature from DHT22 sensor(s)."""
    try:
        if sensor_index is not None:
            temp = dht_devices[sensor_index].temperature
            return temp if -40 <= temp <= 80 else None  # Valid range for DHT22
        temps = [dht.temperature if -40 <= dht.temperature <= 80 else None for dht in dht_devices]
        return temps
    except RuntimeError as e:
        print(f"Error reading DHT22: {e}")
        return None if sensor_index is not None else [None] * 4

def test_individual_temp(sensor_index, temp_name):
    """Test a single DHT22 sensor."""
    print(f"\nTesting {temp_name}...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            temp = read_dht22(sensor_index)
            if temp is not None:
                print(f"{temp_name} Temperature: {temp:.1f}°C (Range: -40 to 80°C)")
            else:
                print(f"Error: No reading from {temp_name}")
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nStopped testing {temp_name}")

def test_all_temp():
    """Test all DHT22 sensors simultaneously."""
    print("\nTesting all TEMP sensors...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            temps = read_dht22()
            for i, temp in enumerate(temps):
                temp_name = f"TEMP{i+1}"
                if temp is not None:
                    print(f"{temp_name} Temperature: {temp:.1f}°C (Range: -40 to 80°C)")
                else:
                    print(f"Error: No reading from {temp_name}")
            print("---")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped testing all TEMP sensors")

def main():
    while True:
        print("\nDHT22 Test Sensor")
        print("1. Test the TEMP1")
        print("2. Test the TEMP2")
        print("3. Test the TEMP3")
        print("4. Test the TEMP4")
        print("5. Test all of the TEMP")
        print("6. Exit the test")
        choice = input("Choose a number: ")

        if choice == "1":
            test_individual_temp(0, "TEMP1")
        elif choice == "2":
            test_individual_temp(1, "TEMP2")
        elif choice == "3":
            test_individual_temp(2, "TEMP3")
        elif choice == "4":
            test_individual_temp(3, "TEMP4")
        elif choice == "5":
            test_all_temp()
        elif choice == "6":
            print("Exiting DHT22 test...")
            break
        else:
            print("Invalid choice, please try again")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpiochip_close(h)
        for dht in dht_devices:
            dht.exit()