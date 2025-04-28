# Smart Restroom GUI - Detailed Technical Documentation

**Version:** 1.0.0  
**Last Updated:** 2025-04-28 01:27:41 UTC  
**Author:** joeyboymission

## System Prerequisites

### Software Requirements
- Python 3.x (3.8 or higher recommended)
- Tkinter (built-in GUI package)
- psutil library (v5.9.0 or higher)
- Threading module (built-in)
- DateTime module (built-in)

### Hardware Requirements
- Minimum Resolution: 1200x800 pixels
- Recommended CPU: 1.0 GHz or faster
- Minimum RAM: 512 MB
- Storage: 50 MB free space

## Window Specifications

| Feature          | Specification                |
|------------------|------------------------------|
| Title            | "Smart Restroom System"       |
| Base Resolution  | 1200x800 pixels               |
| Resizable        | True                          |
| Window Position  | Centered on screen            |
| Window Type      | Main application window       |
| Background Color | System default                |

## GUI Layout Specifications

### Main Container

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | ttk.PanedWindow               |
| Orientation | Horizontal                    |
| Fill        | BOTH                          |
| Expand      | True                          |
| Sash Position| 300 pixels from left         |

### Left Canvas (Control Panel)

| Feature     | Specification                |
|-------------|------------------------------|
| Width       | 300 pixels                   |
| Background  | System default                |
| Layout Manager| Pack                        |

#### Section 1: Main Control

| Feature     | Specification                |
|-------------|------------------------------|
| Position    | Top of left canvas            |
| Padding     | 10px all sides                |

##### Header Component

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Smart Restroom"              |
| Font        | Arial, 24pt, bold            |
| Color       | System default                |
| Alignment   | Center                        |
| Padding     | 20px vertical                 |

##### Description Text

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "An intelligent system for restroom management." |
| Font        | System default                |
| Wrap Length | 250 pixels                   |
| Alignment   | Center                        |
| Padding     | 10px vertical                 |

##### Main Control Button

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | tk.Button                    |
| Shape       | Circular (approximated with rounded corners or custom styling) |
| Size        | Width 10 chars, Height 5 chars (approx. 150x150 pixels) |
| States      | START, STOP                  |
| Font        | Arial, 18pt, bold            |
| Padding     | 30px vertical                 |
| Command     | toggle_all_modules()         |

##### Section Separator

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | ttk.Separator                |
| Orientation | Horizontal                    |
| Padding     | 10px horizontal, 10px vertical|

#### Section 2: Central Hub

| Feature     | Specification                |
|-------------|------------------------------|
| Position    | Below separator               |
| Padding     | 10px all sides                |

##### Hub Header

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Central Hub"                |
| Font        | Arial, 20pt, bold            |
| Padding     | 10px vertical                 |
| Alignment   | Center                        |

##### Hub Description

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Check system status and condition of the Central Hub." |
| Wrap Length | 250 pixels                   |
| Padding     | 5px vertical                  |

### Controllers Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Layout      | Two equal columns             |
| Padding     | 10px vertical                 |

#### Raspberry Pi Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | ttk.LabelFrame               |
| Title       | "Raspberry Pi"               |
| Width       | 135 pixels                   |
| Position    | Left column                  |
| Padding     | 5px                         |
| Border      | 1px solid                   |
| Metrics Display| Status: UP/DOWN           |
| Last Powered| YYYY-MM-DD HH:MM:SS         |
| CPU Temp    | XX.X°C                      |
| CPU Usage   | XX.X%                       |
| Memory Usage| XX.X%                       |
| Storage Usage| XX.X%                      |
| Update Frequency| 500ms                   |
| Label Alignment| Left                     |
| Internal Padding| 5px horizontal, 2px vertical|

#### Arduino Uno Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | ttk.LabelFrame               |
| Title       | "Arduino Uno"                |
| Width       | 135 pixels                   |
| Position    | Right column                 |
| Padding     | 5px                         |
| Border      | 1px solid                   |
| Metrics Display| Status: UP/DOWN           |
| Last Powered| YYYY-MM-DD HH:MM:SS         |
| CPU Temp    | XX.X°C                      |
| CPU Usage   | XX.X%                       |
| Memory Usage| XX.X%                       |
| Flash Usage | XX.X%                       |
| Update Frequency| 500ms                   |
| Label Alignment| Left                     |
| Internal Padding| 5px horizontal, 2px vertical|

### Right Canvas (Module Displays)

| Feature     | Specification                |
|-------------|------------------------------|
| Width       | 900 pixels                   |
| Background  | System default                |
| Layout      | Vertical stack                |

#### Common Module Frame Properties

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | ttk.LabelFrame               |
| Width       | Fill parent                  |
| Padding     | 10px horizontal, 5px vertical|
| Border      | 1px solid                   |

#### Common Control Button Properties

| Feature     | Specification                |
|-------------|------------------------------|
| Size        | System default (approx. 80x30 pixels) |
| Padding     | 2px horizontal               |
| Position    | Top-left of module frame     |
| Layout      | Horizontal arrangement       |
| Styles      | START, PAUSE, RESTART       |

##### 1. Occupancy Module Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Height      | ~266 pixels (1/3 of right canvas) |

###### Title Component

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Occupancy Module"           |
| Font        | Arial, 16pt, bold            |
| Padding     | 5px vertical                 |

###### Description Text

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Tracks visitor entries and exits in the restroom cubicle." |
| Wrap Length | 400 pixels                   |
| Padding     | 5px vertical                 |

###### Cubicle Display

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | tk.Canvas                    |
| Size        | 200x100 pixels               |
| Border      | 2px solid black              |
| States      | VACANT, OCCUPIED             |
| Text Font   | Arial, 14pt, bold            |
| Text Alignment| Center                     |
| Padding     | 5px vertical                 |

###### Sensor Status

| Feature     | Specification                |
|-------------|------------------------------|
| Format      | "Sensor: ONLINE/OFFLINE"     |
| States      | ONLINE, OFFLINE              |
| Padding     | 5px vertical                 |

###### Statistics Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Layout      | Vertical stack               |
| Padding     | 5px                         |
| Metrics     | Total Visitors, Recent Duration, Average Duration |

##### 2. Odor Module Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Height      | ~266 pixels (1/3 of right canvas) |

###### Title Component

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Odor Module"                |
| Font        | Arial, 16pt, bold            |
| Padding     | 5px vertical                 |

###### Description Text

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Monitors air quality and climate for a fresh environment." |
| Wrap Length | 400 pixels                   |
| Padding     | 5px vertical                 |

### Sensors Display Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Layout      | Horizontal arrangement       |
| Padding     | 5px                         |
| Number of Sensor Pairs | 4              |

#### Individual Sensor Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Width       | ~220 pixels                  |
| Border      | 1px solid                   |
| Components  | GAS Sensor, TEMP Sensor      |

##### GAS Sensor:

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | tk.Canvas                    |
| Size        | 50x50 pixels                 |
| Shape       | Circle                       |
| Color       | Gray (#808080)               |
| Texture     | Screen pattern (simulated via fill color) |
| Status Format| "GAS: ONLINE/OFFLINE"       |
| ONLINE      | Text Color: #00FF00 (Green) |
| OFFLINE     | Text Color: #FF0000 (Red)   |
| Reading Format| "AQI: [0-500]"             |

##### TEMP Sensor:

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | tk.Canvas                    |
| Size        | 30x60 pixels                 |
| Shape       | Rectangle                    |
| Color       | Cream-white (#FFFDD0)        |
| Texture     | Screen pattern (simulated via fill color) |
| Status Format| "TEMP: ONLINE/OFFLINE"      |
| ONLINE      | Text Color: #00FF00 (Green) |
| OFFLINE     | Text Color: #FF0000 (Red)   |
| Reading Format| Temp: [XX.X]°C, Humidity: [XX.X]% |

##### 3. Dispenser Module Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Height      | ~266 pixels (1/3 of right canvas) |

###### Title Component

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Dispenser Module"           |
| Font        | Arial, 16pt, bold            |
| Padding     | 5px vertical                 |

###### Description Text

| Feature     | Specification                |
|-------------|------------------------------|
| Text        | "Monitors liquid levels in four containers." |
| Wrap Length | 400 pixels                   |
| Padding     | 5px vertical                 |

### Containers Display Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Layout      | Horizontal arrangement       |
| Padding     | 5px                         |
| Number of Containers | 4                  |

#### Individual Container Frame

| Feature     | Specification                |
|-------------|------------------------------|
| Width       | ~220 pixels                  |
| Border      | 1px solid                   |
| Components  | Volume Bar, Information Display|

##### Volume Bar:

| Feature     | Specification                |
|-------------|------------------------------|
| Type        | tk.Canvas                    |
| Size        | 50x100 pixels                |
| Fill Color  | Blue (#0000FF)               |
| Empty Height| 10 pixels                    |
| Full Height | 90 pixels                    |
| Scale       | Linear (425 mL = 90 pixels)  |

##### Information Display:

| Feature     | Specification                |
|-------------|------------------------------|
| Format      | Status: ONLINE/OFFLINE, Volume: [XXX]mL, Type: [Liquid X], Last: [XX]mL, Time: [HH:MM:SS] |
| Status Colors| ONLINE: Text Color: #00FF00 (Green), OFFLINE: Text Color: #FF0000 (Red) |
| Update Frequency| 500ms                   |

## Thread Management Specifications

### ModuleBase Class

| Feature     | Specification                |
|-------------|------------------------------|
| Thread Type | Daemon                       |
| Lock Type   | threading.Lock()             |
| Methods     | start(), pause(), restart(), run() |

## Update Frequencies

| Feature          | Frequency |
|------------------|-----------|
| GUI Refresh       | 500ms     |
| Sensor Data       | 1000ms    |
| System Stats      | 500ms     |

## Data Ranges and Limits

### Sensor Ranges

| Module | Parameter | Range |
|--------|-----------|--------|
| Occupancy | Visitor Count | 0 to MAX_INT |
| Occupancy | Duration | 0 to 86400 seconds (24h) |
| Odor | AQI | 0 to 500 |
| Odor | Temperature | -20°C to 100°C |
| Odor | Humidity | 0% to 100% |
| Dispenser | Volume | 0 to 425 mL |
| Dispenser | Dispense Amount | 5 to 20 mL |

### System Metrics

| Metric | Range |
|--------|--------|
| CPU Temperature | 0°C to 100°C |
| CPU Usage | 0% to 100% |
| Memory Usage | 0% to 100% |
| Storage/Flash Usage | 0% to 100% |

## Error Handling

### Recovery Mechanisms
- **Thread Crash Recovery**: Log errors and restart threads as needed
- **Sensor Timeout Detection**: Simulate 10% chance of "OFFLINE" status; log failures
- **Data Range Validation**: Ensure values stay within specified ranges
- **Connection Loss Management**: Display "OFFLINE" for affected sensors; attempt reconnection

## Future Enhancements

### Planned Features
1. **Data Logging System**
   - Store sensor data in local database or MongoDB
   - Historical data retention

2. **Remote Management Interface**
   - Network-based control
   - Remote monitoring capabilities

3. **Alert Configuration Panel**
   - User-defined thresholds for alerts
   - Customizable notification system

4. **Historical Data Visualization**
   - Trend analysis
   - AQI history charts
   - Usage patterns

5. **Predictive Maintenance**
   - Sensor failure prediction
   - Hardware maintenance forecasting
   - Usage pattern analysis

