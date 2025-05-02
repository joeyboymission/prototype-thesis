import serial
import time
import lgpio
import glob
import os
import subprocess

# Prerequisites:
# 1. Install dependencies from requirements.txt:
#    Run `pip install -r requirements.txt` to install pyserial.
# 2. Install lgpio library:
#    Run `sudo apt install python3-lgpio` for RPi-LGPIO.
# 3. Connect hardware:
#    - USB: Arduino Mega to Raspberry Pi USB port
#    - MQ135 sensors: A0-A3 on Arduino Mega.

# Serial communication settings
BAUD_RATE = 9600
SERIAL_TIMEOUT = 5
arduino_serial = None

# GPIO setup using lgpio
GPIO_CHIP = 0
h = lgpio.gpiochip_open(GPIO_CHIP)

def scan_serial_ports():
    """Scan for available serial ports with fallback methods"""
    print("Scanning serial ports...")
    
    # Method 1: Try using glob (most reliable)
    try:
        # Common USB-Serial patterns
        patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*',
            '/dev/ttyAMA*',
            'COM[0-9]*'  # For Windows
        ]
        
        ports = []
        for pattern in patterns:
            ports.extend(glob.glob(pattern))
        
        if ports:
            print(f"Found ports using glob: {', '.join(ports)}")
            return ports
    except Exception as e:
        print(f"Glob scan error: {e}")
    
    # Method 2: Try direct device check
    try:
        potential_ports = [
            '/dev/ttyUSB0',
            '/dev/ttyUSB1',
            '/dev/ttyACM0',
            '/dev/ttyACM1',
            '/dev/ttyAMA0'
        ]
        
        ports = [port for port in potential_ports if os.path.exists(port)]
        if ports:
            print(f"Found ports using direct check: {', '.join(ports)}")
            return ports
    except Exception as e:
        print(f"Direct check error: {e}")
    
    # Method 3: Last resort - try subprocess with explicit paths
    try:
        result = subprocess.run(['ls', '/dev/ttyUSB0'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Found /dev/ttyUSB0 using subprocess")
            return ['/dev/ttyUSB0']
    except Exception as e:
        print(f"Subprocess check error: {e}")
    
    print("No serial ports found using any method")
    return []

def fix_port_permissions(port):
    """Fix permission issues for serial ports"""
    print(f"Fixing permissions for {port}...")
    
    try:
        # Kill any processes using the port
        print("Killing processes using the port...")
        subprocess.run(['sudo', 'fuser', '-k', port], capture_output=True, check=False)
        time.sleep(1)
        
        # Reset USB device
        port_base = os.path.basename(port)
        if 'USB' in port_base:
            bus_device = subprocess.run(['readlink', '-f', port], capture_output=True, text=True, check=False).stdout.strip()
            if bus_device:
                usb_path = os.path.dirname(os.path.dirname(bus_device))
                if os.path.exists(os.path.join(usb_path, 'authorized')):
                    print("Resetting USB device...")
                    subprocess.run(['sudo', 'sh', '-c', f'echo 0 > {usb_path}/authorized'], check=False)
                    time.sleep(1)
                    subprocess.run(['sudo', 'sh', '-c', f'echo 1 > {usb_path}/authorized'], check=False)
                    time.sleep(2)
        
        # Set permissions
        print("Setting port permissions...")
        subprocess.run(['sudo', 'chmod', '666', port], check=False)
        
        # Add current user to dialout group
        username = os.getenv('USER', 'pi')
        print(f"Adding user {username} to dialout group...")
        subprocess.run(['sudo', 'usermod', '-a', '-G', 'dialout', username], check=False)
        
        return True
    except Exception as e:
        print(f"Error fixing permissions: {e}")
        return False

def try_connect_port(port, retries=3):
    """Try to connect to a port with multiple retries"""
    for attempt in range(retries):
        try:
            print(f"Connection attempt {attempt + 1} for {port}...")
            
            # Try to open the port
            ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
            time.sleep(2)  # Wait for Arduino reset
            
            # Flush any existing data
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Send test command multiple times
            for _ in range(3):
                ser.write(b'T')  # Test command
                time.sleep(0.1)
                response = ser.readline().decode().strip()
                
                if response == "READY":
                    print(f"Arduino found on {port}")
                    return ser
                
                # If we get any data, this might be the right port but wrong mode
                if response:
                    print(f"Got response but not ready signal: {response}")
                    return ser
                
            ser.close()
            
        except Exception as e:
            print(f"Connection error on {port}: {e}")
            
            if attempt < retries - 1:
                print("Fixing permissions and retrying...")
                fix_port_permissions(port)
                time.sleep(2)
            
    return None

def connect_to_arduino():
    """Find and connect to Arduino on available serial ports"""
    global arduino_serial
    
    # Close existing connection if any
    if arduino_serial:
        arduino_serial.close()
        arduino_serial = None
    
    # Scan for available ports
    ports = scan_serial_ports()
    
    if not ports:
        print("No serial ports found. Please check if:")
        print("1. The Arduino is properly connected via USB")
        print("2. You have the necessary permissions")
        print("3. The USB cable is working")
        return False
    
    # Sort ports to prioritize USB0
    ports = sorted(ports, key=lambda x: (
        0 if 'USB0' in x else
        1 if 'USB' in x else
        2 if 'ACM0' in x else
        3 if 'ACM' in x else
        4
    ))
    
    for port in ports:
        # Try to connect with retries and permission fixing
        ser = try_connect_port(port)
        if ser:
            arduino_serial = ser
            return True
    
    print("Could not find Arduino on any port")
    return False

def read_mq135(sensor_index=None):
    """Read raw MQ135 data from Arduino via Serial."""
    if not arduino_serial:
        print("Error: No Arduino connection")
        return None if sensor_index is not None else [None] * 4
    
    try:
        # Send read command
        arduino_serial.write(b'R')  # Read command
        time.sleep(0.1)
        
        # Read response
        response = arduino_serial.readline().decode().strip()
        if not response:
            raise Exception("No response from Arduino")
        
        # Parse values
        values = [int(x) for x in response.split(',')]
        if len(values) != 4:
            raise Exception("Invalid data format")
        
        # Validate values
        values = [v if 0 <= v <= 500 else None for v in values]
        
        if sensor_index is not None:
            return values[sensor_index]
        return values
        
    except Exception as e:
        print(f"Error reading Serial: {e}")
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
    # Initialize Arduino connection
    if not connect_to_arduino():
        print("Error: Could not connect to Arduino")
        return
        
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
        if arduino_serial:
            arduino_serial.close()
        lgpio.gpiochip_close(h)