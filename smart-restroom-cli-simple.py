#!/usr/bin/env python3

import os
import sys
import time
import signal
import importlib
import threading
from datetime import datetime
import platform

# Add module paths to sys.path if not already included
script_dir = os.path.dirname(os.path.abspath(__file__))
for module_dir in ["disp-mod-main", "occupancy-mod-main", "odor-mod-main", "central-hub-mod"]:
    module_path = os.path.join(script_dir, module_dir)
    if module_path not in sys.path:
        sys.path.append(module_path)

# Try to import modules - handle import errors gracefully
try:
    from disp_mod_main import DispenserModule
    DISPENSER_MODULE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import Dispenser Module: {e}")
    DISPENSER_MODULE_AVAILABLE = False

try:
    from occu_mod_main import OccupancyModule
    OCCUPANCY_MODULE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import Occupancy Module: {e}")
    OCCUPANCY_MODULE_AVAILABLE = False

try:
    from odor_mod_main import OdorModule
    ODOR_MODULE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import Odor Module: {e}")
    ODOR_MODULE_AVAILABLE = False

try:
    from cen_mod_main import CentralHubModule
    CENTRAL_HUB_MODULE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import Central Hub Module: {e}")
    CENTRAL_HUB_MODULE_AVAILABLE = False

# Check if we're running on Raspberry Pi
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Constants
DATA_DIR = "/home/admin/Documents/local-data" if is_raspberry_pi else "local-data"
LOG_FILE = os.path.join(DATA_DIR, "smart-restroom-cli.log")
MONITOR_INTERVAL = 5  # seconds

# Debug handler to capture module logs
class DebugHandler:
    def __init__(self, file_path=None, max_entries=100):
        self.logs = []
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.file_path = file_path
        
        # Create directory for log file if specified
        if file_path:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Clear existing log file
            with open(file_path, 'w') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Smart Restroom CLI Log Started\n")
    
    def log(self, message):
        """Add a log message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        
        with self.lock:
            print(log_entry)
            self.logs.append(log_entry)
            
            # Trim logs if they exceed max_entries
            if len(self.logs) > self.max_entries:
                self.logs = self.logs[-self.max_entries:]
            
            # Write to file if specified
            if self.file_path:
                try:
                    with open(self.file_path, 'a') as f:
                        f.write(log_entry + "\n")
                except Exception as e:
                    print(f"Error writing to log file: {e}")
    
    def get_recent_logs(self, count=10):
        """Get the most recent log entries"""
        with self.lock:
            return self.logs[-count:] if self.logs else []

class SmartRestroomCLI:
    def __init__(self):
        """Initialize the Smart Restroom CLI"""
        # Create the debug handler for logging
        self.debug_handler = DebugHandler(LOG_FILE)
        self.debug_handler.log("Initializing Smart Restroom CLI")
        
        # Create data directory if it doesn't exist
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Module references
        self.dispenser_module = None
        self.occupancy_module = None
        self.odor_module = None
        self.central_hub = None
        
        # Control flags
        self.running = False
        self.stop_event = threading.Event()
        
    def initialize_modules(self):
        """Initialize all modules in the correct order"""
        self.debug_handler.log("Starting module initialization")
        
        # 1. Dispenser Module
        if DISPENSER_MODULE_AVAILABLE:
            try:
                self.debug_handler.log("Initializing Dispenser Module...")
                self.dispenser_module = DispenserModule()
                self.dispenser_module.start()
                self.debug_handler.log("Dispenser Module initialized successfully")
            except Exception as e:
                self.debug_handler.log(f"Error initializing Dispenser Module: {e}")
        
        # 2. Occupancy Module
        if OCCUPANCY_MODULE_AVAILABLE:
            try:
                self.debug_handler.log("Initializing Occupancy Module...")
                self.occupancy_module = OccupancyModule()
                self.occupancy_module.start()
                self.debug_handler.log("Occupancy Module initialized successfully")
            except Exception as e:
                self.debug_handler.log(f"Error initializing Occupancy Module: {e}")
        
        # 3. Odor Module
        if ODOR_MODULE_AVAILABLE:
            try:
                self.debug_handler.log("Initializing Odor Module...")
                self.odor_module = OdorModule()
                self.odor_module.start()
                self.debug_handler.log("Odor Module initialized successfully")
            except Exception as e:
                self.debug_handler.log(f"Error initializing Odor Module: {e}")
        
        # 4. Central Hub Module
        if CENTRAL_HUB_MODULE_AVAILABLE:
            try:
                self.debug_handler.log("Initializing Central Hub Module...")
                self.central_hub = CentralHubModule()
                
                # Register other modules with the central hub
                if self.dispenser_module:
                    self.central_hub.register_module("dispenser", self.dispenser_module)
                if self.occupancy_module:
                    self.central_hub.register_module("occupancy", self.occupancy_module)
                if self.odor_module:
                    self.central_hub.register_module("odor", self.odor_module)
                
                self.central_hub.start()
                self.debug_handler.log("Central Hub Module initialized successfully")
            except Exception as e:
                self.debug_handler.log(f"Error initializing Central Hub Module: {e}")
        
        self.debug_handler.log("Module initialization completed")
        
    def print_module_status(self):
        """Print the status of all modules"""
        self.debug_handler.log("=================")
        self.debug_handler.log("Module Status")
        self.debug_handler.log("=================")
        
        # Dispenser status
        if self.dispenser_module:
            status = self.dispenser_module.status()
            self.debug_handler.log(f"Dispenser Module: {status}")
        else:
            self.debug_handler.log("Dispenser Module: Not available")
        
        # Occupancy status
        if self.occupancy_module:
            status = self.occupancy_module.status()
            self.debug_handler.log(f"Occupancy Module: {status}")
        else:
            self.debug_handler.log("Occupancy Module: Not available")
        
        # Odor status
        if self.odor_module:
            status = self.odor_module.status()
            self.debug_handler.log(f"Odor Module: {status}")
        else:
            self.debug_handler.log("Odor Module: Not available")
        
        # Central Hub status
        if self.central_hub:
            status = self.central_hub.status()
            self.debug_handler.log(f"Central Hub Module: {status}")
        else:
            self.debug_handler.log("Central Hub Module: Not available")
        
        self.debug_handler.log("=================")
    
    def format_dispenser_data(self):
        """Format dispenser data for display"""
        if not self.dispenser_module:
            return "Dispenser Module: Not available"
        
        try:
            container_data = self.dispenser_module.get_container_summary()
            parts = []
            
            for i in range(1, 5):
                container = f"CONT{i}"
                if container in container_data:
                    data = container_data[container]
                    distance = data.get("distance_cm", 0)
                    volume = data.get("remaining_volume_ml", 0)
                    percentage = int((volume / 1000) * 100) if volume else 0  # Assuming 1000ml is full
                    parts.append(f"{container}: {distance:.2f} cm {volume:.2f} ml {percentage}%")
            
            return "Dispenser Module | " + " | ".join(parts)
        except Exception as e:
            return f"Dispenser Module: Error formatting data ({e})"
    
    def format_occupancy_data(self):
        """Format occupancy data for display"""
        if not self.occupancy_module:
            return "Occupancy Module: Not available"
        
        try:
            cubicle_data = self.occupancy_module.get_cubicle_summary()
            occupied_count = 0
            
            for i in range(1, 4):
                cubicle = f"CUB{i}"
                if cubicle in cubicle_data and cubicle_data[cubicle]["status"] == "OCCUPIED":
                    occupied_count += 1
            
            presence = "Occupied" if occupied_count > 0 else "Vacant"
            return f"Occupancy Module | Number of Occupied: {occupied_count} | Presence: {presence}"
        except Exception as e:
            return f"Occupancy Module: Error formatting data ({e})"
    
    def format_odor_data(self):
        """Format odor data for display"""
        if not self.odor_module:
            return "Odor Module: Not available"
        
        try:
            sensor_data = self.odor_module.get_sensor_summary()
            value = sensor_data.get("value", 0)
            status = sensor_data.get("status", "UNKNOWN")
            fan_state = sensor_data.get("fan_state", "OFF")
            occupancy = sensor_data.get("occupancy", "VACANT")
            
            return f"Odor Module | AQI: {value} | Air Quality: {status} | Fan: {fan_state} | Occupancy: {occupancy}"
        except Exception as e:
            return f"Odor Module: Error formatting data ({e})"
    
    def print_status_update(self):
        """Print status update for all modules"""
        try:
            # Format and print data from each module
            dispenser_data = self.format_dispenser_data()
            occupancy_data = self.format_occupancy_data()
            odor_data = self.format_odor_data()
            
            self.debug_handler.log(dispenser_data)
            self.debug_handler.log(occupancy_data)
            self.debug_handler.log(odor_data)
            
            # System info if central hub is available
            if self.central_hub and hasattr(self.central_hub, 'get_system_health'):
                sys_health = self.central_hub.get_system_health()
                self.debug_handler.log(f"System Health | Uptime: {sys_health.get('system_uptime', 0)}s | MongoDB: {sys_health.get('mongodb_status', 'unknown')}")
        
        except Exception as e:
            self.debug_handler.log(f"Error printing status update: {e}")
    
    def start(self):
        """Start the Smart Restroom CLI"""
        self.running = True
        
        # Initialize modules
        self.initialize_modules()
        
        # Print initial module status
        self.print_module_status()
        
        # Main monitoring loop
        self.debug_handler.log("Starting to log and monitor all of the data")
        try:
            while self.running and not self.stop_event.is_set():
                # Print status update
                self.print_status_update()
                
                # Sleep for the monitoring interval
                time.sleep(MONITOR_INTERVAL)
        
        except KeyboardInterrupt:
            self.debug_handler.log("Keyboard interrupt received, shutting down...")
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop all modules and exit"""
        self.running = False
        self.debug_handler.log("Shutting down Smart Restroom CLI...")
        
        # Stop modules in reverse order
        if self.central_hub:
            try:
                self.central_hub.stop()
                self.debug_handler.log("Central Hub Module stopped")
            except Exception as e:
                self.debug_handler.log(f"Error stopping Central Hub Module: {e}")
        
        if self.odor_module:
            try:
                self.odor_module.stop()
                self.debug_handler.log("Odor Module stopped")
            except Exception as e:
                self.debug_handler.log(f"Error stopping Odor Module: {e}")
        
        if self.occupancy_module:
            try:
                self.occupancy_module.stop()
                self.debug_handler.log("Occupancy Module stopped")
            except Exception as e:
                self.debug_handler.log(f"Error stopping Occupancy Module: {e}")
        
        if self.dispenser_module:
            try:
                self.dispenser_module.stop()
                self.debug_handler.log("Dispenser Module stopped")
            except Exception as e:
                self.debug_handler.log(f"Error stopping Dispenser Module: {e}")
        
        self.debug_handler.log("Smart Restroom CLI shutdown complete")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    if cli:
        cli.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start CLI
    cli = SmartRestroomCLI()
    cli.start()
