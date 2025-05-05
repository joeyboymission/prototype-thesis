#!/usr/bin/env python3

import os
import sys
import time
import signal
from datetime import datetime
import json
import threading
from collections import deque
import importlib
import argparse
import traceback
import psutil
from tabulate import tabulate
import platform

# Check if we're running on Raspberry Pi
is_raspberry_pi = platform.machine().startswith('arm') or platform.machine().startswith('aarch')
print(f"Detected platform: {platform.machine()} - {'Raspberry Pi' if is_raspberry_pi else 'Non-Raspberry Pi'}")

# Set up path to modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "disp-mod-main"))
sys.path.append(os.path.join(current_dir, "occupancy-mod-main"))
sys.path.append(os.path.join(current_dir, "odor-mod-main"))
sys.path.append(os.path.join(current_dir, "central-hub-mod"))

# Import module files
try:
    # Import the modules from their respective files
    from disp_mod_main import DispenserModule
    from occu_mod_main import OccupancyModule
    from odor_mod_main import OdorModule
    from cen_mod_main import CentralHubModule
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Please check that the module files are in the correct directories and properly named.")
    print("Trying alternative import paths...")
    
    # Can't directly import with dashes in directory names, so we'll use individual imports
    print("Attempting individual imports...")
    
    # Try importing each module individually
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "disp-mod-main"))
        from disp_mod_main import DispenserModule
        print("Imported DispenserModule")
    except ImportError as e_disp:
        print(f"Failed to import DispenserModule: {e_disp}")
        DispenserModule = None
        
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "occupancy-mod-main"))
        from occu_mod_main import OccupancyModule
        print("Imported OccupancyModule")
    except ImportError as e_occu:
        print(f"Failed to import OccupancyModule: {e_occu}")
        OccupancyModule = None
        
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "odor-mod-main"))
        from odor_mod_main import OdorModule
        print("Imported OdorModule")
    except ImportError as e_odor:
        print(f"Failed to import OdorModule: {e_odor}")
        OdorModule = None
        
    try:
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "central-hub-mod"))
        from cen_mod_main import CentralHubModule
        print("Imported CentralHubModule")
    except ImportError as e_hub:
        print(f"Failed to import CentralHubModule: {e_hub}")
        CentralHubModule = None
    
    if not any([DispenserModule, OccupancyModule, OdorModule, CentralHubModule]):
        print("All module imports failed. Exiting.")
        sys.exit(1)

# Global variables
modules = {
    'dispenser': None,
    'occupancy': None,
    'odor': None,
    'central_hub': None
}

def get_timestamp():
    """Return current timestamp string"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(message):
    """Print a log message with timestamp"""
    print(f"{get_timestamp()} {message}")

def display_module_status():
    """Display the current status of all modules"""
    headers = ["Module", "Status", "Details"]
    rows = []

    for name, module in modules.items():
        if module is not None:
            status = module.status()
            rows.append([name.capitalize(), status, ""])
        else:
            rows.append([name.capitalize(), "Not loaded", ""])

    print("\nModule Status:")
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print()

def display_system_info():
    """Display system resource usage and hardware info"""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    print("\nSystem Information:")
    print(f"CPU Usage: {cpu_percent}%")
    print(f"Memory: {memory.percent}% used ({memory.used // (1024 * 1024)} MB / {memory.total // (1024 * 1024)} MB)")
    print(f"Disk: {disk.percent}% used ({disk.used // (1024 * 1024 * 1024)} GB / {disk.total // (1024 * 1024 * 1024)} GB)")
    
    # Show hostname and platform info if available
    try:
        print(f"Host: {platform.node()}")
        print(f"Platform: {platform.platform()}")
    except:
        pass
    print()

def display_recent_logs(module_name, count=10):
    """Display recent logs from a specific module"""
    module = modules.get(module_name)
    
    if module is None:
        print(f"\nModule '{module_name}' is not loaded")
        return
    
    if hasattr(module, 'get_recent_logs') and callable(getattr(module, 'get_recent_logs')):
        logs = module.get_recent_logs(count)
        
        print(f"\nRecent logs from {module_name.capitalize()} module:")
        for log in logs:
            print(log)
    else:
        print(f"\nThe {module_name} module does not provide log access")

def initialize_modules(args):
    """Initialize and start the selected modules"""
    global modules
    
    try:
        # Create central hub module first
        if args.all or args.central_hub:
            log_message("Initializing Central Hub Module...")
            if CentralHubModule is not None:
                modules['central_hub'] = CentralHubModule()
            else:
                log_message("CentralHubModule is not available - skipping")
        
        # Initialize dispenser module if selected
        if args.all or args.dispenser:
            log_message("Initializing Dispenser Module...")
            if DispenserModule is not None:
                modules['dispenser'] = DispenserModule()
                
                # Register with central hub if available
                if modules['central_hub']:
                    modules['central_hub'].register_module('dispenser', modules['dispenser'])
            else:
                log_message("DispenserModule is not available - skipping")
        
        # Initialize occupancy module if selected
        if args.all or args.occupancy:
            log_message("Initializing Occupancy Module...")
            if OccupancyModule is not None:
                modules['occupancy'] = OccupancyModule()
                
                # Register with central hub if available
                if modules['central_hub']:
                    modules['central_hub'].register_module('occupancy', modules['occupancy'])
            else:
                log_message("OccupancyModule is not available - skipping")
        
        # Initialize odor module if selected
        if args.all or args.odor:
            log_message("Initializing Odor Module...")
            if OdorModule is not None:
                modules['odor'] = OdorModule()
                
                # Register with central hub if available
                if modules['central_hub']:
                    modules['central_hub'].register_module('odor', modules['odor'])
            else:
                log_message("OdorModule is not available - skipping")
        
        # Start all initialized modules
        for name, module in modules.items():
            if module is not None:
                log_message(f"Starting {name.capitalize()} Module...")
                module.start()
        
        log_message("Initialization complete")
        return True
        
    except Exception as e:
        log_message(f"Error initializing modules: {e}")
        log_message(traceback.format_exc())
        return False

def stop_modules():
    """Stop all running modules"""
    for name, module in modules.items():
        if module is not None:
            log_message(f"Stopping {name.capitalize()} Module...")
            module.stop()
    
    log_message("All modules stopped")

def pause_modules():
    """Pause all running modules"""
    for name, module in modules.items():
        if module is not None:
            log_message(f"Pausing {name.capitalize()} Module...")
            module.pause()
    
    log_message("All modules paused")

def resume_modules():
    """Resume all paused modules"""
    for name, module in modules.items():
        if module is not None:
            log_message(f"Resuming {name.capitalize()} Module...")
            module.pause()  # Calling pause again toggles to resume
    
    log_message("All modules resumed")

def display_help():
    """Display help information for the interactive CLI"""
    print("\nAvailable Commands:")
    print("  status      - Display module status")
    print("  system      - Display system information")
    print("  logs [module] [count] - Display recent logs from a module (default: 10 logs)")
    print("  pause       - Pause all modules")
    print("  resume      - Resume all modules")
    print("  stop        - Stop all modules and exit")
    print("  help        - Display this help information")
    print()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Smart Restroom Monitoring System")
    parser.add_argument('--all', action='store_true', help='Start all modules')
    parser.add_argument('--dispenser', action='store_true', help='Start dispenser module')
    parser.add_argument('--occupancy', action='store_true', help='Start occupancy module')
    parser.add_argument('--odor', action='store_true', help='Start odor module')
    parser.add_argument('--central-hub', action='store_true', help='Start central hub module')
    parser.add_argument('--non-interactive', action='store_true', help='Run in non-interactive mode')
    
    args = parser.parse_args()
    
    # If no specific modules were selected, enable all by default
    if not (args.all or args.dispenser or args.occupancy or args.odor or args.central_hub):
        args.all = True
    
    return args

def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals"""
    print("\nReceived termination signal. Stopping modules...")
    stop_modules()
    sys.exit(0)

def interactive_cli():
    """Run the interactive command-line interface"""
    display_help()
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd == 'status':
                display_module_status()
            elif cmd == 'system':
                display_system_info()
            elif cmd.startswith('logs'):
                parts = cmd.split()
                if len(parts) > 1:
                    module_name = parts[1]
                    count = int(parts[2]) if len(parts) > 2 else 10
                    display_recent_logs(module_name, count)
                else:
                    print("Usage: logs [module] [count]")
            elif cmd == 'pause':
                pause_modules()
            elif cmd == 'resume':
                resume_modules()
            elif cmd == 'stop' or cmd == 'exit' or cmd == 'quit':
                stop_modules()
                break
            elif cmd == 'help':
                display_help()
            elif cmd == '':
                # Do nothing for empty input
                pass
            else:
                print(f"Unknown command: {cmd}")
                display_help()
        
        except KeyboardInterrupt:
            print("\nStopping modules and exiting...")
            stop_modules()
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    """Main function to start the application"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Display banner
    print("\n" + "=" * 80)
    print("                Smart Restroom Monitoring System")
    print("=" * 80)
    
    # Initialize modules
    if not initialize_modules(args):
        log_message("Failed to initialize modules. Exiting.")
        sys.exit(1)
    
    # Display initial status
    display_module_status()
    
    # Interactive mode unless --non-interactive was specified
    if not args.non_interactive:
        try:
            interactive_cli()
        except Exception as e:
            log_message(f"Error in interactive CLI: {e}")
            log_message(traceback.format_exc())
    else:
        # In non-interactive mode, just keep the main thread alive
        log_message("Running in non-interactive mode. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log_message("Received keyboard interrupt")
        finally:
            stop_modules()
    
    log_message("Application exited")

if __name__ == "__main__":
    main()
