#!/usr/bin/env python3
import time
import json
import os
import signal
import sys
from datetime import datetime
from collections import deque
import threading
from bson import ObjectId
import platform

# Check if we're running on Raspberry Pi for hardware-specific imports
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Try to import hardware-specific libraries
try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    print("Warning: lgpio not available. Hardware features will be simulated.")

# Try to import MongoDB libraries
try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("Warning: pymongo not available. Using local storage only.")

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