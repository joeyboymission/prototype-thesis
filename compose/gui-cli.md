# Smart Restroom System Debug CLI Documentation

## Overview

The Smart Restroom Debug CLI is a command-line interface tool designed for testing and simulating the Smart Restroom Monitoring System in a development environment. It provides a way to interact with the system's core modules without requiring the actual hardware, making it ideal for testing and debugging purposes.

## System Architecture

The Debug CLI simulates three main modules of the Smart Restroom Monitoring System:

1. **Occupancy Module**: Monitors and tracks restroom occupancy
2. **Dispenser Module**: Monitors soap/sanitizer dispensers' levels
3. **Odor Module**: Monitors air quality and controls ventilation

These modules are coordinated through a **Central Hub** that provides overall system monitoring and status.

## Key Components

### Debug Handler

- **Purpose**: Captures and stores debug messages for real-time monitoring
- **Features**:
  - Log message storage with timestamps
  - Enable/disable logging
  - Clear logs
  - Retrieve logged messages

### Hardware Simulation Classes

The system includes mock classes to simulate hardware interactions:

- `MockLGPIO`: Simulates GPIO operations for sensors and actuators
- `MockDHT`: Simulates temperature and humidity sensors
- `MockBoard`: Simulates board pin configurations
- `MockSMBus`: Simulates I2C bus communications
- `MockMongoClient`: Simulates MongoDB database operations

### Module Base Class

All modules inherit from `ModuleBase`, which provides:

- Thread management for background operations
- Standardized start/stop/pause functionality
- Status reporting
- Common interface for module operations

## Module Implementations

### Occupancy Module

**Purpose**: Simulates occupancy detection and tracking.

**Features**:
- Visitor count tracking
- Visitor duration tracking
- Entry/exit event simulation
- Status reporting (vacant/occupied)
- MongoDB integration (simulated)
- Local JSON data storage

**Key Methods**:
- `perform_post_check()`: System check at startup
- `setup_hardware()`: Initialize sensors (simulated)
- `format_duration()`: Format time values
- `update_log()`: Track visitor data
- `get_summary()`: Get occupancy status information

### Dispenser Module

**Purpose**: Simulates monitoring of fluid dispensers.

**Features**:
- Container level monitoring
- Usage simulation
- Volume calculation
- Calibration data management
- Multiple container support

**Key Methods**:
- `measure_raw_data()`: Simulate distance measurements
- `calculate_usable_volume()`: Convert measurements to volume
- `get_container_summary()`: Get dispenser status information

### Odor Module

**Purpose**: Simulates air quality monitoring and fan control.

**Features**:
- Temperature/humidity monitoring
- Air quality index (AQI) calculation
- Fan control based on occupancy and air quality
- Air freshener triggering
- Trend analysis

**Key Methods**:
- `read_sensors()`: Simulate sensor readings
- `calculate_avg_aqi()`: Calculate air quality index
- `calculate_air_quality_trend()`: Track AQI changes over time
- `control_fan()`: Manage fan operation
- `control_freshener()`: Manage freshener operation

## Central Hub

**Purpose**: Coordinates all modules and provides system-wide monitoring.

**Features**:
- Module registration
- System resource monitoring
- Status reporting for all modules

**Key Methods**:
- `register_module()`: Add modules to the hub
- `update_system_info()`: Gather system metrics
- `get_modules_status()`: Report module statuses

## CLI Interface

The `SmartRestroomDebugCLI` class provides the interactive interface for the system.

### Main Menu

| Option | Description |
|--------|-------------|
| 1. View System Dashboard | Display real-time system status |
| 2. Start All Modules / View All Data | Start modules or view data if already running |
| 3. Stop All Modules | Stop all running modules |
| 4. Occupancy Module Control | Control occupancy module |
| 5. Dispenser Module Control | Control dispenser module |
| 6. Odor Module Control | Control odor module |
| 7. Exit | Exit the application |

### Module Control Menu

Each module has a dedicated control menu with options:

| Option | Description |
|--------|-------------|
| 1. View Module Data / Start Module | View data (if running) or start module (if stopped) |
| 2. Stop Module | Stop the module |
| 3. Pause/Resume Module | Toggle pause state |
| 4. Return to Main Menu | Go back to main menu |

### Dashboard View

The system dashboard shows:

- System information (CPU, memory, storage usage)
- Module status summary
- Key metrics from each running module
- Auto-refresh functionality

### Data Log View

Displays real-time data from all running modules:

- Occupancy status and history
- Dispenser levels and usage
- Air quality metrics and fan status
- Recent system events
- Auto-refresh functionality

## Key User Interface Functions

| Function | Description |
|----------|-------------|
| `main_menu()` | Display and handle main menu options |
| `module_menu()` | Control specific modules |
| `display_dashboard()` | Show system-wide status |
| `view_data_log()` | Display combined module data |
| `view_module_data()` | Show detailed data for a specific module |
| `start_all_modules()` | Initialize and start all modules |
| `stop_all_modules()` | Stop all active modules |

## Data Refresh Mechanism

The CLI implements a smart refresh system that:

1. Automatically updates data at defined intervals (5 seconds by default)
2. Allows manual refresh through user input
3. Handles key presses without blocking the display
4. Provides clean exit options from any view

## Simulation Parameters

The simulation system uses these default parameters:

- `SIMULATION_INTERVAL`: 5 seconds between data updates
- Occupancy state changes: Random intervals between 30-120 seconds
- Dispenser usage: 30% probability per interval with various amounts
- Air quality fluctuation: Random with occasional "bad air" events (10% probability)
- Temperature range: 20-35°C with small fluctuations
- Humidity range: 30-80% with small fluctuations

## Startup Sequence

1. The system checks for required directories and creates them if needed
2. Module instances are created and registered with the central hub
3. Signal handlers are set up for graceful shutdown
4. The main menu is displayed
5. Modules are started on demand or when "Start All Modules" is selected

## Shutdown Sequence

1. All modules are stopped
2. Hardware resources are cleaned up (simulated)
3. Final status is displayed
4. The application exits

## Error Handling

The CLI includes comprehensive error handling:

- Try/except blocks around critical operations
- Graceful degradation when components are unavailable
- Clean shutdown on Ctrl+C or termination signals
- Debug logging of errors
- User-friendly error messages

## Implementation Notes

- The CLI is compatible with both Windows and Linux/Unix environments
- Input timeouts are implemented differently based on OS (msvcrt vs. select)
- The tabulate library is used for creating formatted tables
- Color output is used for status indicators (green for online, red for offline)
- All simulated data remains within realistic ranges for the actual hardware
