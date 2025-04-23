import smbus
import time
import lgpio

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` to install smbus (included in adafruit-blinka).
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - I2C: Arduino Mega A4 (SDA) to GPIO2 (Pin 3), A5 (SCL) to GPIO3 (Pin 5).
#    - MQ135 sensors: A0-A3 on Arduino Mega.

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

# I2C Setup for Arduino Mega
bus = smbus.SMBus(1)  # I2C bus 1 on Pi
ARDUINO_ADDRESS = 8

def read_mq135(sensor_index=None):
    """Read raw MQ135 data from Arduino Mega over I2C."""
    try:
        data = bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 8)  # 8 bytes: 4x 2-byte values
        aqi = [(data[i*2] << 8) + data[i*2 + 1] for i in range(4)]
        if sensor_index is not None:
            return aqi[sensor_index] if 0 <= aqi[sensor_index] <= 500 else None
        return aqi
    except Exception as e:
        print(f"Error reading I2C: {e}")
        return None if sensor_index is not None else [None] * 4

def test_individual_gas(sensor_index, gas_name):
    """Test a single MQ135 sensor."""
    print(f"\nTesting {gas_name}...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            raw_value = read_mq135(sensor_index)
            if raw_value is not None:
                print(f"{gas_name} Raw Value: {raw_value} (Range: 0-500)")
            else:
                print(f"Error: No reading from {gas_name}")
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nStopped testing {gas_name}")

def test_all_gas():
    """Test all MQ135 sensors simultaneously."""
    print("\nTesting all GAS sensors...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            raw_values = read_mq135()
            for i, value in enumerate(raw_values):
                gas_name = f"GAS{i+1}"
                if value is not None:
                    print(f"{gas_name} Raw Value: {value} (Range: 0-500)")
                else:
                    print(f"Error: No reading from {gas_name}")
            print("---")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped testing all GAS sensors")

def main():
    while True:
        print("\nMQ135 Test Sensor")
        print("1. Test the GAS1")
        print("2. Test the GAS2")
        print("3. Test the GAS3")
        print("4. Test the GAS4")
        print("5. Test all of the GAS")
        print("6. Exit the test")
        choice = input("Choose Number: ")

        if choice == "1":
            test_individual_gas(0, "GAS1")
        elif choice == "2":
            test_individual_gas(1, "GAS2")
        elif choice == "3":
            test_individual_gas(2, "GAS3")
        elif choice == "4":
            test_individual_gas(3, "GAS4")
        elif choice == "5":
            test_all_gas()
        elif choice == "6":
            print("Exiting MQ135 test...")
            break
        else:
            print("Invalid choice, please try again")

if __name__ == "__main__":
    try:
        main()
    finally:
        lgpio.gpiochip_close(h)