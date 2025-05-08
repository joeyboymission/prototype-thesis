#!/usr/bin/env python3

import time
import os
import sys
import json
import threading
import signal
import psutil
from datetime import datetime
from collections import deque
import platform
from bson import ObjectId

# Check if we're running on Raspberry Pi for hardware-specific imports
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Try to import hardware-specific libraries
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("Warning: lgpio not available. Hardware features will be simulated.")

# Try to import MongoDB libraries, but have a fallback if not available
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

# GPIO pins from pin-config.md
K1_PIN = 20  # 8RELAY-B K1 (DC Fan): GPIO20 (Pin 38)
K2_PIN = 23  # 8RELAY-B K2 (Exhaust Fan): GPIO23 (Pin 16) - shared with odor module
K3_PIN = 24  # 8RELAY-B K3 (Air Freshener): GPIO24 (Pin 18) - shared with odor module

# Temperature check interval
TEMP_CHECK_INTERVAL = 5  # Seconds between temperature checks

# CPU Temperature thresholds (in Celsius)
TEMP_IDEAL = 50  # Fan OFF below this temperature
TEMP_WARM = 70   # Fan ON between TEMP_IDEAL and TEMP_WARM
TEMP_HIGH = 80   # High warning above this temperature
TEMP_CRITICAL = 85  # Critical warning above this temperature

# Data storage - Use absolute path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "central-hub-data")
JSON_FILE = os.path.join(DATA_DIR, "central-hub-data.json")

# GPIO simulation flag
SIMULATE_GPIO = False  # Will be set to True if GPIO initialization fails

# Base module class for common functionality
class ModuleBase:
    def __init__(self, name):
        self.name = name
        self.running = False
        self.paused = False
        self.thread = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
    
    def start(self):
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
        status_str = "stopped"
        if self.running:
            status_str = "paused" if self.paused else "running"
        return status_str
    
    def run(self):
        # To be implemented by subclasses
        pass

# Central Hub Module Implementation
class CentralHubModule(ModuleBase):
    def __init__(self):
        super().__init__("Central Hub")
        # Configuration
        self.MODULE_CHECK_INTERVAL = 30  # Seconds between module status checks
        self.SYNC_INTERVAL = 300         # Seconds between data synchronization
        
        # MongoDB settings
        self.MONGO_URI = "mongodb+srv://SmartUser:NewPass123%21@smartrestroomweb.ucrsk.mongodb.net/Smart_Cubicle?retryWrites=true&w=majority&appName=SmartRestroomWeb"
        
        # Local storage settings
        self.DATA_DIR = "/home/admin/Documents/local-data"
        self.LOCAL_FILE = os.path.join(self.DATA_DIR, "hub-status.json")
        
        # Module references (to be set from outside)
        self.dispenser_module = None
        self.occupancy_module = None
        self.odor_module = None
        
        # Global variables
        self.mongo_client = None       # MongoDB client
        self.mongo_db = None           # MongoDB database
        self.mongo_collection = None   # MongoDB collection
        self.reading_counter = 0       # Reading counter
        self.log_queue = deque(maxlen=50)  # Keep last 50 log messages
        
        # System health status
        self.system_health = {
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "modules": {
                "dispenser": {"status": "unknown", "last_check": None},
                "occupancy": {"status": "unknown", "last_check": None},
                "odor": {"status": "unknown", "last_check": None}
            },
            "mongodb_status": "unknown",
            "system_uptime": 0,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # If we're on Windows, adjust the paths
        if os.name == 'nt':
            self.DATA_DIR = "local-data"
            self.LOCAL_FILE = os.path.join(self.DATA_DIR, "hub-status.json")
    
    def get_data_template(self):
        """Initialize data format for hub status update"""
        return {
            "_id": str(ObjectId()) if MONGODB_AVAILABLE else f"local_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "reading": self.reading_counter + 1,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "system_health": self.system_health,
                "module_status": {
                    "dispenser": self.get_module_status(self.dispenser_module),
                    "occupancy": self.get_module_status(self.occupancy_module),
                    "odor": self.get_module_status(self.odor_module)
                }
            }
        }

    def log_message(self, message):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {message}"
        print(log_entry)
        self.log_queue.append(log_entry)

    def initialize_storage(self):
        """Initialize storage system and check existing data"""
        self.log_message("Checking the connection to Database...")
        
        # Create local data directory if it doesn't exist
        if not os.path.exists(self.DATA_DIR):
            self.log_message(f"Creating local data directory: {self.DATA_DIR}")
            try:
                os.makedirs(self.DATA_DIR, exist_ok=True)
            except Exception as e:
                self.log_message(f"Error creating data directory: {e}")
                return False
        
        # Check local file
        if os.path.exists(self.LOCAL_FILE):
            try:
                with open(self.LOCAL_FILE, "r") as f:
                    data = json.load(f)
                    if data:
                        latest = data[-1]
                        self.reading_counter = latest["reading"]
                        self.log_message(f"Found {len(data)} existing records in local storage")
                        self.log_message(f"Latest reading number: {self.reading_counter}")
            except Exception as e:
                self.log_message(f"Error reading local data file: {e}")
        else:
            self.log_message("Local data file does not exist, will create when first data is saved")
        
        return True

    def connect_to_mongodb(self):
        """Connect to MongoDB and restore latest state"""
        global MONGODB_AVAILABLE
        
        if not MONGODB_AVAILABLE:
            self.log_message("MongoDB support not available, using local storage only.")
            self.system_health["mongodb_status"] = "unavailable"
            return False
        
        try:
            self.log_message("Checking the connection to Database...")
            self.mongo_client = MongoClient(self.MONGO_URI, serverSelectionTimeoutMS=5000)
            # Test connection
            self.mongo_client.admin.command('ping')
            
            self.mongo_db = self.mongo_client["Smart_Cubicle"]
            self.mongo_collection = self.mongo_db["hub_status"]  # Using the correct collection name
            
            # Check if collection exists and has data
            if self.mongo_collection.count_documents({}) > 0:
                self.log_message("Found existing data in remote database")
                latest_doc = self.mongo_collection.find_one(sort=[("timestamp", -1)])
                if latest_doc:
                    self.reading_counter = latest_doc.get("reading", 0)
                    self.log_message(f"Latest remote reading number: {self.reading_counter}")
            
            self.system_health["mongodb_status"] = "connected"
            self.log_message("Database Connected Successfully!")
            return True
        except Exception as e:
            self.log_message(f"MongoDB connection error: {e}")
            self.mongo_client = None
            self.mongo_db = None
            self.mongo_collection = None
            self.system_health["mongodb_status"] = "failed"
            return False

    def save_to_mongodb(self, data):
        """Save data to MongoDB"""
        if not MONGODB_AVAILABLE or self.mongo_collection is None:
            return False
        
        try:
            self.mongo_collection.insert_one(data)
            return True
        except Exception as e:
            self.log_message(f"Error saving to MongoDB: {e}")
            return False

    def save_to_local_storage(self, data):
        """Save data to local JSON file"""
        try:
            # Ensure the directory exists
            os.makedirs(self.DATA_DIR, exist_ok=True)
            
            existing_data = []
            if os.path.exists(self.LOCAL_FILE):
                try:
                    with open(self.LOCAL_FILE, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    self.log_message("Creating new data file (existing file corrupt)")
            
            # Ensure data has the correct format
            if not isinstance(existing_data, list):
                existing_data = []
            
            existing_data.append(data)
            
            # Use atomic write to prevent corruption
            temp_file = self.LOCAL_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_file, self.LOCAL_FILE)
            
            return True
        except Exception as e:
            self.log_message(f"Local storage error: {e}")
            return False

    def save_hub_data(self, hub_data):
        """Save hub status data to both MongoDB and local storage"""
        mongodb_success = self.save_to_mongodb(hub_data)
        local_success = self.save_to_local_storage(hub_data)
        
        # Report overall status
        if mongodb_success and local_success:
            self.log_message("Status: DATA SAVED TO REMOTE AND LOCAL")
        elif local_success:
            self.log_message("Status: DATA SAVED TO LOCAL ONLY")
        else:
            self.log_message("Status: FAILED TO SAVE DATA")
            
        return mongodb_success or local_success

    def get_module_status(self, module):
        """Get status information from a module"""
        if module is None:
            return {
                "status": "not_connected",
                "details": "Module not connected"
            }
        
        try:
            status = module.status()
            
            # Get additional module-specific data if available
            if hasattr(module, 'get_container_summary') and callable(getattr(module, 'get_container_summary')):
                details = module.get_container_summary()
            elif hasattr(module, 'get_cubicle_summary') and callable(getattr(module, 'get_cubicle_summary')):
                details = module.get_cubicle_summary()
            elif hasattr(module, 'get_sensor_summary') and callable(getattr(module, 'get_sensor_summary')):
                details = module.get_sensor_summary()
            else:
                details = f"Module is {status}"
            
            return {
                "status": status,
                "details": details
            }
        except Exception as e:
            return {
                "status": "error",
                "details": f"Error getting status: {str(e)}"
            }

    def update_module_status(self):
        """Update the status of all connected modules"""
        self.log_message("Checking status of all modules...")
        
        # Update dispenser module status
        if self.dispenser_module:
            status = self.get_module_status(self.dispenser_module)
            self.system_health["modules"]["dispenser"] = {
                "status": status["status"],
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message(f"Dispenser module status: {status['status']}")
        else:
            self.system_health["modules"]["dispenser"] = {
                "status": "not_connected",
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message("Dispenser module not connected")
        
        # Update occupancy module status
        if self.occupancy_module:
            status = self.get_module_status(self.occupancy_module)
            self.system_health["modules"]["occupancy"] = {
                "status": status["status"],
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message(f"Occupancy module status: {status['status']}")
        else:
            self.system_health["modules"]["occupancy"] = {
                "status": "not_connected",
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message("Occupancy module not connected")
        
        # Update odor module status
        if self.odor_module:
            status = self.get_module_status(self.odor_module)
            self.system_health["modules"]["odor"] = {
                "status": status["status"],
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message(f"Odor module status: {status['status']}")
        else:
            self.system_health["modules"]["odor"] = {
                "status": "not_connected",
                "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.log_message("Odor module not connected")
        
        # Update system health timestamp
        self.system_health["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate system uptime
        start_time = datetime.strptime(self.system_health["start_time"], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        uptime_seconds = (now - start_time).total_seconds()
        self.system_health["system_uptime"] = int(uptime_seconds)

    def get_system_health(self):
        """Get the current system health status"""
        return self.system_health

    def get_recent_logs(self, count=20):
        """Get recent log messages"""
        return list(self.log_queue)[-count:]

    def run(self):
        """Main function for central hub operation"""
        # Initialize storage system
        if not self.initialize_storage():
            self.log_message("Failed to initialize storage system")
            self.running = False
            return
        
        # Connect to MongoDB
        mongodb_connected = self.connect_to_mongodb()
        if not mongodb_connected:
            self.log_message("No MongoDB connection. Using local storage only.")
        
        self.log_message("Central Hub monitoring started")
        
        # Initial status check
        self.update_module_status()
        
        # Save initial status
        initial_data = self.get_data_template()
        self.save_hub_data(initial_data)
        self.reading_counter += 1
        
        # Main monitoring loop
        last_check_time = time.time()
        last_sync_time = time.time()
        
        while self.running and not self.stop_event.is_set():
            if not self.paused:
                try:
                    current_time = time.time()
                    
                    # Check module status at regular intervals
                    if current_time - last_check_time >= self.MODULE_CHECK_INTERVAL:
                        self.update_module_status()
                        last_check_time = current_time
                    
                    # Sync and save data at regular intervals
                    if current_time - last_sync_time >= self.SYNC_INTERVAL:
                        self.log_message("Syncing system status...")
                        
                        # Update MongoDB connection status
                        if self.mongo_client is None and MONGODB_AVAILABLE:
                            self.log_message("Attempting to reconnect to MongoDB...")
                            self.connect_to_mongodb()
                        
                        # Create and save status data
                        hub_data = self.get_data_template()
                        self.save_hub_data(hub_data)
                        self.reading_counter += 1
                        
                        last_sync_time = current_time
                except Exception as e:
                    self.log_message(f"Error in central hub: {e}")
                
                time.sleep(1)  # Short sleep to avoid CPU overhead
            else:
                time.sleep(1)  # Check for un-pause every second
        
        # Save final status before exit
        self.log_message("Saving final status before exit...")
        
        # Update module status one last time
        self.update_module_status()
        
        # Create and save final status
        final_data = self.get_data_template()
        self.save_hub_data(final_data)
        
        # Disconnect from MongoDB
        if self.mongo_client:
            try:
                self.mongo_client.close()
                self.log_message("Disconnected from MongoDB")
            except:
                pass

    def register_module(self, module_type, module):
        """Register a module with the central hub"""
        if module_type.lower() == 'dispenser':
            self.dispenser_module = module
            self.log_message("Dispenser module registered")
        elif module_type.lower() == 'occupancy':
            self.occupancy_module = module
            self.log_message("Occupancy module registered")
        elif module_type.lower() == 'odor':
            self.odor_module = module
            self.log_message("Odor module registered")
        else:
            self.log_message(f"Unknown module type: {module_type}")
            return False
        return True

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
    print("Central Hub Module - Starting in standalone mode...")
    try:
        # Handle Ctrl+C gracefully
        def signal_handler(signum, frame):
            if central_hub_module.running:
                central_hub_module.stop()
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Create and start module
        central_hub_module = CentralHubModule()
        central_hub_module.start()
        
        # Keep the script running
        while central_hub_module.running:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
