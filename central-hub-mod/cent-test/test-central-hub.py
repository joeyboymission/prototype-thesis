#!/usr/bin/env python3
"""
Central Hub Module Test Script
This script tests the GPIO, temperature sensing, and data storage functionality
of the Central Hub Module without running the full application.
"""

import os
import sys
import time
import json
import lgpio
import psutil

print("\n=== Central Hub Module Test Script ===")

# Test 1: Check if running as root (required for GPIO access)
print("\n[Test 1] Checking user permissions:")
try:
    is_root = os.geteuid() == 0
    if is_root:
        print("✓ Running as root - You have permissions to access GPIO")
    else:
        print("✗ Not running as root - This may cause GPIO permission issues")
        print("  Suggestion: Try running with 'sudo python3 test-central-hub.py'")
except AttributeError:
    print("? Unable to determine root status (non-Unix system)")
    is_root = False

# Test 2: Check if lgpio module is working
print("\n[Test 2] Testing lgpio module:")
try:
    # Try initializing lgpio
    chip_list = []
    for chip_num in range(3):  # Try chips 0, 1, 2
        try:
            h = lgpio.gpiochip_open(chip_num)
            chip_info = lgpio.gpio_get_chip_info(h)
            num_lines = lgpio.gpio_get_chip_info(h)[3]
            print(f"✓ Successfully opened GPIO chip {chip_num}: {chip_info[1]}, {num_lines} lines")
            chip_list.append(chip_num)
            lgpio.gpiochip_close(h)
        except Exception as e:
            print(f"✗ Could not open GPIO chip {chip_num}: {str(e)}")
    
    if not chip_list:
        print("✗ No GPIO chips could be accessed. Hardware control will not work.")
        print("  Suggestion: Check if lgpio is installed properly")
except Exception as e:
    print(f"✗ lgpio test failed with error: {str(e)}")

# Test 3: Check temperature reading
print("\n[Test 3] Testing temperature sensing:")

# Method 1: Try thermal_zone0 (Raspberry Pi)
try:
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
        temp = float(f.read().strip()) / 1000.0
        print(f"✓ Method 1 (thermal_zone0): Temperature = {temp:.1f}°C")
except (FileNotFoundError, IOError):
    print("✗ Method 1 (thermal_zone0): File not found or inaccessible")

# Method 2: Try psutil
try:
    temps = psutil.sensors_temperatures()
    if temps:
        print("✓ Method 2 (psutil): Found temperature sensors:")
        for name, entries in temps.items():
            for i, entry in enumerate(entries):
                print(f"  - {name} #{i}: {entry.current:.1f}°C")
    else:
        print("✗ Method 2 (psutil): No temperature sensors found")
except AttributeError:
    print("✗ Method 2 (psutil): Not supported on this system/version")
except Exception as e:
    print(f"✗ Method 2 (psutil) error: {str(e)}")

# Test 4: Test data directory creation
print("\n[Test 4] Testing data directory:")
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, "central-hub-data")
json_file = os.path.join(data_dir, "test-data.json")

try:
    os.makedirs(data_dir, exist_ok=True)
    print(f"✓ Created/accessed data directory: {data_dir}")
    
    # Try writing to file
    test_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test": "successful"
    }
    
    with open(json_file, "w") as f:
        json.dump(test_data, f, indent=2)
    print(f"✓ Successfully wrote to file: {json_file}")
    
    # Try reading from file
    with open(json_file, "r") as f:
        data = json.load(f)
    print(f"✓ Successfully read from file: {json_file}")
    
except Exception as e:
    print(f"✗ Data directory/file access error: {str(e)}")

# Summary
print("\n=== Test Summary ===")
print(f"Root access:      {'Yes' if is_root else 'No'}")
print(f"GPIO chips:       {', '.join(map(str, chip_list)) if chip_list else 'None available'}")
print(f"Data directory:   {'Accessible' if os.path.exists(data_dir) else 'Not accessible'}")

print("\nNext steps:")
if not is_root and not chip_list:
    print(" 1. Try running with 'sudo python3 test-central-hub.py'")
    print(" 2. Ensure lgpio is properly installed: 'sudo apt install python3-lgpio libgpiod2'")
    print(" 3. If problems persist, the module will run in simulation mode without hardware control")
elif not chip_list:
    print(" 1. GPIO access issues detected. The module will run in simulation mode")
    print(" 2. System monitoring features will still work without hardware control")
else:
    print(" 1. Tests passed! The module should run correctly")
    print(" 2. Run the main module with: 'sudo python3 cen-mod-main.py'")

print("\nTest completed.") 