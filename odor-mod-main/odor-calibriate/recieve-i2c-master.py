import smbus2
import time

# Prerequisites:
# 1. Install smbus2 from requirements.txt:
#    Run `sudo pip3 install -r requirements.txt` (smbus2>=0.5.0).
# 2. Connect hardware:
#    - I2C: Arduino Mega A4 (SDA) to GPIO2 (Pin 3), A5 (SCL) to GPIO3 (Pin 5).
#    - Common GND (e.g., Pi Pin 6 to Arduino GND).
#    - USB: Arduino Mega to Pi for Serial debugging.
# 3. Run with sudo: `sudo python3 receive-i2c-master.py`.

# I2C Setup
bus = smbus2.SMBus(1)  # I2C bus 1 on Pi
ARDUINO_ADDRESS = 8    # Expected Arduino I2C address

def scan_i2c():
    """Scan I2C bus for devices (mimics i2cdetect)."""
    print("Scanning I2C bus...")
    detected = []
    for address in range(3, 120):  # Valid I2C addresses: 0x03 to 0x77
        try:
            bus.read_byte(address)
            detected.append(address)
            print(f"Device found at address 0x{address:02X}")
        except:
            pass
    return detected

def read_arduino():
    """Read 1 byte from Arduino at address 8."""
    try:
        data = bus.read_byte(ARDUINO_ADDRESS)
        print(f"Read from address 0x{ARDUINO_ADDRESS:02X}: 0x{data:02X} ({data} decimal)")
        return data
    except Exception as e:
        print(f"Error reading from address 0x{ARDUINO_ADDRESS:02X}: {e}")
        return None

def main():
    print("I2C Master Test Script")
    # Step 1: Scan for devices
    devices = scan_i2c()
    if ARDUINO_ADDRESS in devices:
        print(f"Arduino detected at address 0x{ARDUINO_ADDRESS:02X}")
    else:
        print(f"No device found at address 0x{ARDUINO_ADDRESS:02X}")
    
    # Step 2: Test reading from Arduino
    print("\nTesting read from Arduino...")
    for _ in range(3):  # Try 3 times
        result = read_arduino()
        if result is not None:
            break
        time.sleep(1)
    
    print("\nTest complete. Check Arduino Serial Monitor for debug output.")

if __name__ == "__main__":
    try:
        main()
    finally:
        bus.close()