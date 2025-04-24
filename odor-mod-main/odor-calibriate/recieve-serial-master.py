import serial
import time

# Prerequisites:
# 1. Install pyserial:
#    Run `sudo pip3 install pyserial`.
# 2. Connect hardware:
#    - USB: Arduino Mega to Pi (/dev/ttyUSB0).
#    - MQ135 sensors: A0-A3 on Arduino Mega.
# 3. Run with sudo: `sudo python3 receive-serial-master.py`.

# Serial Setup
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600

def read_serial():
    """Read AQI values from Arduino over serial."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
            ser.flush()  # Clear buffer
            print("Reading serial data... Press Ctrl+C to stop")
            while True:
                line = ser.readline().decode('utf-8').strip()
                if line:
                    try:
                        aqi_values = [int(x) for x in line.split(',')]
                        if len(aqi_values) == 4:
                            for i, value in enumerate(aqi_values):
                                print(f"GAS{i+1} AQI: {value} (Range: 0-500)")
                            print("---")
                    except ValueError:
                        print(f"Invalid data: {line}")
                time.sleep(1)
    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        print("\nStopped reading serial data")

if __name__ == "__main__":
    read_serial()