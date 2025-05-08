#!/usr/bin/env python3

import time
import os
import sys
import threading
import signal
import psutil
import lgpio
import datetime
import platform
import subprocess
from collections import deque

# Constants for relay
DC_FAN_PIN = 18  # GPIO18, Pin 12 for 8RELAY-B K1 (DC Fan only)
TEMP_CHECK_INTERVAL = 5  # Seconds between temperature checks
MAX_GPIO_RETRIES = 5  # Maximum number of retries for GPIO initialization
GPIO_RETRY_DELAY = 2  # Seconds to wait between retries

# CPU Temperature thresholds (in Celsius)
TEMP_IDEAL = 50  # Fan OFF below this temperature
TEMP_WARM = 70   # Fan ON between TEMP_IDEAL and TEMP_WARM
TEMP_HIGH = 80   # High warning above this temperature
TEMP_CRITICAL = 85  # Critical warning above this temperature

# GPIO simulation flag
SIMULATE_GPIO = False  # Will be set to True if GPIO initialization fails

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
        self.start_time = time.time()
    
    def log_message(self, message, level="INFO"):
        """Print and store a log message with timestamp"""
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} [{level}] {message}"
        print(log_entry)
        self.log_queue.append(log_entry)
    
    def check_and_reset_gpio(self):
        """Check and reset GPIO pin using pinctrl"""
        try:
            # Check current pin status
            result = subprocess.run(['sudo', 'pinctrl', 'get', str(DC_FAN_PIN)], 
                                 capture_output=True, text=True)
            self.log_message(f"Current GPIO {DC_FAN_PIN} status: {result.stdout.strip()}")
            
            # Reset the pin to input mode with pull-down
            subprocess.run(['sudo', 'pinctrl', 'set', str(DC_FAN_PIN), 'ip', 'pd'], 
                         capture_output=True)
            
            # Verify reset
            result = subprocess.run(['sudo', 'pinctrl', 'get', str(DC_FAN_PIN)], 
                                 capture_output=True, text=True)
            self.log_message(f"Reset GPIO {DC_FAN_PIN} status: {result.stdout.strip()}")
            
            return True
        except Exception as e:
            self.log_message(f"Error checking/resetting GPIO: {e}", "ERROR")
            return False

    def setup_hardware(self):
        """Initialize GPIO for DC fan control with retry logic"""
        global SIMULATE_GPIO
        
        # If we're already in simulation mode, just return
        if SIMULATE_GPIO:
            self.log_message("Running in GPIO simulation mode", "WARNING")
            return True
            
        retry_count = 0
        while retry_count < MAX_GPIO_RETRIES:
            try:
                # First, check and reset the GPIO pin
                if not self.check_and_reset_gpio():
                    raise Exception("Failed to check/reset GPIO pin")
                
                # Try to open GPIO chip 0
                self.h = lgpio.gpiochip_open(0)
                if self.h is None:
                    raise Exception("Could not open GPIO chip 0")
                
                self.log_message("Successfully opened GPIO chip 0")
                
                # Configure GPIO 18 as output with initial state HIGH (relay off)
                try:
                    # First try to free the pin if it's already in use
                    try:
                        lgpio.gpio_free(self.h, DC_FAN_PIN)
                    except:
                        pass
                    
                    # Claim the pin as output
                    lgpio.gpio_claim_output(self.h, DC_FAN_PIN)
                    
                    # Set initial state to HIGH (relay off)
                    lgpio.gpio_write(self.h, DC_FAN_PIN, 1)
                    
                    self.log_message("GPIO 18 initialized successfully for DC fan control")
                    return True
                    
                except Exception as e:
                    self.log_message(f"Error configuring GPIO {DC_FAN_PIN}: {e}", "ERROR")
                    if self.h:
                        lgpio.gpiochip_close(self.h)
                        self.h = None
                    raise
                
            except Exception as e:
                retry_count += 1
                self.log_message(f"GPIO initialization attempt {retry_count} failed: {str(e)}", "ERROR")
                
                if retry_count < MAX_GPIO_RETRIES:
                    self.log_message(f"Retrying in {GPIO_RETRY_DELAY} seconds...", "WARNING")
                    time.sleep(GPIO_RETRY_DELAY)
                else:
                    self.log_message("Maximum retry attempts reached", "ERROR")
                    self.log_message("Falling back to GPIO simulation mode", "WARNING")
                    SIMULATE_GPIO = True
                    return True  # Return True so the module can run in simulation mode
        
        return True  # Return True to allow simulation mode
    
    def cleanup_hardware(self):
        """Clean up GPIO resources"""
        if self.h:
            try:
                # Ensure DC fan is off
                self.set_fan_state(False)
                
                # Release GPIO resources
                try:
                    lgpio.gpio_free(self.h, DC_FAN_PIN)
                except:
                    pass
                
                lgpio.gpiochip_close(self.h)
                self.h = None
                self.log_message("GPIO resources cleaned up")
            except Exception as e:
                self.log_message(f"Error cleaning up GPIO: {e}", "ERROR")
    
    def set_fan_state(self, state):
        """Set fan state to ON (True) or OFF (False)"""
        global SIMULATE_GPIO
        
        # If in simulation mode, just log and update internal state
        if SIMULATE_GPIO or self.h is None:
            self.fan_running = state
            self.log_message(f"DC Fan turned {'ON' if state else 'OFF'} (SIMULATION)", "WARNING")
            return True
        
        try:
            # Set GPIO pin: 0 for ON (relay activated), 1 for OFF (relay deactivated)
            lgpio.gpio_write(self.h, DC_FAN_PIN, 0 if state else 1)
            self.fan_running = state
            self.log_message(f"DC Fan turned {'ON' if state else 'OFF'}")
            return True
        except Exception as e:
            self.log_message(f"Error controlling DC fan: {e}", "ERROR")
            # Fall back to simulation mode if hardware control fails
            SIMULATE_GPIO = True
            self.fan_running = state
            return True
    
    def get_cpu_temperature(self):
        """Get current CPU temperature in Celsius"""
        try:
            # Try multiple methods to get CPU temperature
            
            # Method 1: Read from thermal_zone0 (Raspberry Pi)
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp = float(f.read().strip()) / 1000.0
                    return temp
            except (FileNotFoundError, IOError):
                pass
                
            # Method 2: Try psutil (works on many platforms)
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            if entry.current:
                                return entry.current
            except (AttributeError, KeyError):
                pass
            
            # Fallback to a simulated temperature
            self.log_message("Could not read CPU temperature, using simulated data", "WARNING")
            # Simulate a temperature between 35°C and 65°C
            return 35.0 + (time.time() % 30)
            
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
    
    def get_system_info(self):
        """Get detailed system information"""
        try:
            # Get OS information
            os_info = {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor()
            }

            # Get Raspberry Pi specific info
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    pi_model = f.read().strip()
            except:
                pi_model = "Unknown Raspberry Pi model"

            # Get CPU info
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpu_info = f.read()
                    cpu_model = [line for line in cpu_info.split('\n') if 'Model' in line][0].split(':')[1].strip()
            except:
                cpu_model = "Unknown CPU model"

            # Get memory info
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Get disk info
            disk = psutil.disk_usage('/')

            # Get network interfaces
            net_if = psutil.net_if_addrs()

            return {
                "os": os_info,
                "pi_model": pi_model,
                "cpu_model": cpu_model,
                "memory": {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent
                },
                "swap": {
                    "total": swap.total,
                    "used": swap.used,
                    "percent": swap.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "network_interfaces": list(net_if.keys())
            }
        except Exception as e:
            self.log_message(f"Error getting system info: {e}", "ERROR")
            return None

    def format_bytes(self, bytes):
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} PB"

    def get_uptime(self):
        """Get system uptime in human readable format"""
        uptime_seconds = time.time() - self.start_time
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def print_system_specs(self):
        """Print detailed system specifications"""
        self.log_message("=" * 50)
        self.log_message("System Specifications")
        self.log_message("=" * 50)
        
        sys_info = self.get_system_info()
        if sys_info:
            # OS Information
            self.log_message("\nOperating System:")
            self.log_message(f"  System: {sys_info['os']['system']}")
            self.log_message(f"  Release: {sys_info['os']['release']}")
            self.log_message(f"  Version: {sys_info['os']['version']}")
            self.log_message(f"  Architecture: {sys_info['os']['machine']}")
            
            # Hardware Information
            self.log_message("\nHardware Information:")
            self.log_message(f"  Model: {sys_info['pi_model']}")
            self.log_message(f"  CPU: {sys_info['cpu_model']}")
            
            # Memory Information
            self.log_message("\nMemory Information:")
            self.log_message(f"  Total RAM: {self.format_bytes(sys_info['memory']['total'])}")
            self.log_message(f"  Available RAM: {self.format_bytes(sys_info['memory']['available'])}")
            self.log_message(f"  Used RAM: {self.format_bytes(sys_info['memory']['used'])} ({sys_info['memory']['percent']}%)")
            self.log_message(f"  Swap Total: {self.format_bytes(sys_info['swap']['total'])}")
            self.log_message(f"  Swap Used: {self.format_bytes(sys_info['swap']['used'])} ({sys_info['swap']['percent']}%)")
            
            # Storage Information
            self.log_message("\nStorage Information:")
            self.log_message(f"  Total Storage: {self.format_bytes(sys_info['disk']['total'])}")
            self.log_message(f"  Used Storage: {self.format_bytes(sys_info['disk']['used'])} ({sys_info['disk']['percent']}%)")
            self.log_message(f"  Free Storage: {self.format_bytes(sys_info['disk']['free'])}")
            
            # Network Information
            self.log_message("\nNetwork Interfaces:")
            for interface in sys_info['network_interfaces']:
                self.log_message(f"  {interface}")
        
        self.log_message("=" * 50)

    def print_status(self):
        """Print current system status with enhanced information"""
        temp = self.last_temperature
        fan = "ON" if self.fan_running else "OFF"
        trend = self.get_temperature_trend()
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        uptime = self.get_uptime()
        
        self.log_message("\n" + "=" * 50)
        self.log_message("System Status Report")
        self.log_message("=" * 50)
        self.log_message(f"Uptime: {uptime}")
        self.log_message(f"CPU Temperature: {temp:.1f}°C ({trend})")
        self.log_message(f"CPU Usage: {cpu}%")
        self.log_message(f"Memory Usage: {self.format_bytes(mem.used)} / {self.format_bytes(mem.total)} ({mem.percent}%)")
        self.log_message(f"Storage Usage: {self.format_bytes(disk.used)} / {self.format_bytes(disk.total)} ({disk.percent}%)")
        self.log_message(f"DC Fan: {fan}")
        self.log_message("=" * 50)
    
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
        
        # Print system specifications at startup
        self.print_system_specs()
        
        self.log_message("Central Hub monitoring started")
        if SIMULATE_GPIO:
            self.log_message("Running in SIMULATION mode - hardware control disabled", "WARNING")
        
        last_temp_check = time.time()
        last_status_print = time.time()
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
    
    # Verify lgpio is available
    try:
        test_handle = lgpio.gpiochip_open(0)
        if test_handle is not None:
            lgpio.gpiochip_close(test_handle)
            print("GPIO test successful")
        else:
            print("Warning: Could not open GPIO chip 0")
            SIMULATE_GPIO = True
    except Exception as e:
        print(f"Warning: lgpio test failed: {e}")
        print("The module will run in simulation mode without hardware control")
        SIMULATE_GPIO = True
    
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
