#!/usr/bin/env python3

import time
import os
import sys
import json
import threading
import signal
import psutil
import lgpio
import datetime
from collections import deque

# Constants for DC exhaust fan
K1_PIN = 20  # GPIO20, Pin 38 for 8RELAY-B K1 (DC Fan)
TEMP_CHECK_INTERVAL = 5  # Seconds between temperature checks

# CPU Temperature thresholds (in Celsius)
TEMP_IDEAL = 50  # Fan OFF below this temperature
TEMP_WARM = 70   # Fan ON between TEMP_IDEAL and TEMP_WARM
TEMP_HIGH = 80   # High warning above this temperature
TEMP_CRITICAL = 85  # Critical warning above this temperature

# Data storage
DATA_DIR = "central-hub-data"
JSON_FILE = os.path.join(DATA_DIR, "central-hub-data.json")

class CentralHubModule:
    def __init__(self):
        self.name = "Central Hub"
        self.running = False
        self.paused = False
        self.thread = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # GPIO handle
        self.h = None
        
        # System state
        self.fan_running = False
        self.last_temperature = 0
        self.temperature_history = deque(maxlen=60)  # Keep last 60 readings (5 minutes at 5-second intervals)
        self.log_queue = deque(maxlen=100)  # Keep last 100 log messages
        
        # Initialize data directory
        os.makedirs(DATA_DIR, exist_ok=True)
    
    def log_message(self, message, level="INFO"):
        """Print and store a log message with timestamp"""
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} [{level}] {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
    def setup_hardware(self):
        """Initialize GPIO for DC fan control"""
        try:
            self.h = lgpio.gpiochip_open(0)  # Open GPIO chip
            # Set up K1 relay pin (active-low)
            lgpio.gpio_claim_output(self.h, K1_PIN, lgpio.SET_ACTIVE_LOW, 1)  # Initialize HIGH (relay off)
            self.log_message("GPIO initialized successfully for DC fan control")
            return True
        except Exception as e:
            self.log_message(f"Error initializing GPIO: {e}", "ERROR")
            return False
    
    def cleanup_hardware(self):
        """Clean up GPIO resources"""
        if self.h:
            try:
                # Ensure DC fan is off
                self.set_fan_state(False)
                
                # Release GPIO resources
                lgpio.gpio_free(self.h, K1_PIN)
                lgpio.gpiochip_close(self.h)
                self.h = None
                self.log_message("GPIO resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up GPIO: {e}", "ERROR")
    
    def set_fan_state(self, state):
        """Set fan state to ON (True) or OFF (False)"""
        if self.h is None:
            self.log_message("Error: GPIO not initialized for fan control", "ERROR")
            return False
        
        try:
            # Set GPIO pin: 0 for ON (relay activated), 1 for OFF (relay deactivated)
            lgpio.gpio_write(self.h, K1_PIN, 0 if state else 1)
            self.fan_running = state
            self.log_message(f"DC Exhaust Fan turned {'ON' if state else 'OFF'}")
            return True
        except Exception as e:
            self.log_message(f"Error controlling DC fan: {e}", "ERROR")
            return False
    
    def get_cpu_temperature(self):
        """Get current CPU temperature in Celsius"""
        try:
            # Read temperature from system file (Raspberry Pi specific)
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                return temp
        except Exception as e:
            self.log_message(f"Error reading CPU temperature: {e}", "ERROR")
            # Fallback to a simulated temperature for testing
            return 45.0  # Default fallback temperature
    
    def manage_cooling(self, temperature):
        """Manage cooling based on current temperature"""
        # Store temperature in history
        self.temperature_history.append(temperature)
        
        # Log appropriate message based on temperature range
        if temperature >= TEMP_CRITICAL:
            self.log_message(f"CRITICAL TEMPERATURE ALERT: {temperature:.1f}°C - System may shut down soon!", "CRITICAL")
        elif temperature >= TEMP_HIGH:
            self.log_message(f"HIGH TEMPERATURE WARNING: {temperature:.1f}°C - Consider additional cooling", "WARNING")
        elif temperature >= TEMP_IDEAL:
            self.log_message(f"System temperature: {temperature:.1f}°C - Under load, fan active", "INFO")
        else:
            self.log_message(f"System temperature: {temperature:.1f}°C - Normal operation", "INFO")
        
        # Control fan based on temperature thresholds
        if temperature >= TEMP_IDEAL and not self.fan_running:
            # Turn fan ON when exceeding TEMP_IDEAL
            self.set_fan_state(True)
        elif temperature < TEMP_IDEAL and self.fan_running:
            # Turn fan OFF when below TEMP_IDEAL
            self.set_fan_state(False)
    
    def get_system_stats(self):
        """Get comprehensive system statistics"""
        stats = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu": {
                "temperature": self.last_temperature,
                "usage": psutil.cpu_percent(interval=0.1),
                "frequency": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            },
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "percent": psutil.virtual_memory().percent,
            },
            "disk": {
                "total": psutil.disk_usage('/').total,
                "used": psutil.disk_usage('/').used,
                "percent": psutil.disk_usage('/').percent,
            },
            "fan": {
                "status": "ON" if self.fan_running else "OFF",
                "run_time": 0,  # Would need to track actual run time
            },
            "network": {
                "bytes_sent": psutil.net_io_counters().bytes_sent,
                "bytes_recv": psutil.net_io_counters().bytes_recv,
            }
        }
        return stats
    
    def save_system_stats(self, stats):
        """Save system statistics to JSON file"""
        try:
            # Load existing data
            existing_data = []
            if os.path.exists(JSON_FILE):
                try:
                    with open(JSON_FILE, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    self.log_message("Creating new data file (existing file corrupt)", "WARNING")
            
            # Append new data
            existing_data.append(stats)
            
            # Keep only the latest 1000 entries
            if len(existing_data) > 1000:
                existing_data = existing_data[-1000:]
            
            # Save data atomically
            temp_file = JSON_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_file, JSON_FILE)
            
            return True
        except Exception as e:
            self.log_message(f"Error saving system stats: {e}", "ERROR")
            return False
    
    def get_temperature_trend(self):
        """Get temperature trend based on recent readings"""
        if len(self.temperature_history) < 2:
            return "stable"
        
        # Get average of first and last 5 readings
        if len(self.temperature_history) >= 10:
            first_avg = sum(list(self.temperature_history)[:5]) / 5
            last_avg = sum(list(self.temperature_history)[-5:]) / 5
            diff = last_avg - first_avg
            
            if diff > 1.0:
                return "rising"
            elif diff < -1.0:
                return "falling"
        
        return "stable"
    
    def print_status(self):
        """Print current system status"""
        temp = self.last_temperature
        fan = "ON" if self.fan_running else "OFF"
        trend = self.get_temperature_trend()
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        
        message = f"System Status: CPU Temp: {temp:.1f}°C ({trend}) | "
        message += f"CPU Usage: {cpu}% | Memory: {mem}% | Fan: {fan}"
        self.log_message(message)
    
    def start(self):
        """Start the central hub monitoring"""
        with self.lock:
            if not self.running:
                self.running = True
                self.paused = False
                self.stop_event.clear()
                self.thread = threading.Thread(target=self.run)
                self.thread.daemon = True
                self.thread.start()
                print(f"{self.name} module started")
                return True
            else:
                print(f"{self.name} module is already running")
                return False
    
    def stop(self):
        """Stop the central hub monitoring"""
        with self.lock:
            if self.running:
                print(f"Stopping {self.name} module...")
                self.running = False
                self.stop_event.set()
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=2)
                print(f"{self.name} module stopped")
                return True
            else:
                print(f"{self.name} module is not running")
                return False
    
    def pause(self):
        """Pause/unpause the central hub monitoring"""
        with self.lock:
            if self.running:
                self.paused = not self.paused
                status = "paused" if self.paused else "resumed"
                print(f"{self.name} module {status}")
                return True
            else:
                print(f"{self.name} module is not running")
                return False
    
    def status(self):
        """Get current module status"""
        status_str = "stopped"
        if self.running:
            status_str = "paused" if self.paused else "running"
        return status_str
    
    def run(self):
        """Main monitoring loop"""
        if not self.setup_hardware():
            self.log_message("Failed to initialize hardware. Module not started.", "ERROR")
            self.running = False
            return
        
        self.log_message("Central Hub monitoring started")
        last_temp_check = time.time()
        last_stats_save = time.time()
        last_status_print = time.time()
        stats_save_interval = 60  # Save stats every minute
        status_print_interval = 30  # Print status every 30 seconds
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                current_time = time.time()
                
                # Check temperature at regular intervals
                if current_time - last_temp_check >= TEMP_CHECK_INTERVAL:
                    # Get current CPU temperature
                    temperature = self.get_cpu_temperature()
                    self.last_temperature = temperature
                    
                    # Manage cooling based on temperature
                    self.manage_cooling(temperature)
                    
                    last_temp_check = current_time
                
                # Save system stats at regular intervals
                if current_time - last_stats_save >= stats_save_interval:
                    stats = self.get_system_stats()
                    self.save_system_stats(stats)
                    last_stats_save = current_time
                
                # Print status at regular intervals
                if current_time - last_status_print >= status_print_interval:
                    self.print_status()
                    last_status_print = current_time
                
                # Small delay to prevent CPU overuse
                time.sleep(0.1)
            else:
                # When paused, just check occasionally
                time.sleep(1)
        
        # Clean up hardware when stopping
        self.cleanup_hardware()
        self.log_message("Central Hub monitoring stopped")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nStopping Central Hub Module...")
    if central_hub:
        central_hub.stop()
    sys.exit(0)

# Set up signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    print("Starting Central Hub Module...")
    central_hub = CentralHubModule()
    
    # Start monitoring
    central_hub.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    finally:
        # Ensure clean shutdown
        if central_hub:
            central_hub.stop()
    
    print("Central Hub Module exited normally.")
