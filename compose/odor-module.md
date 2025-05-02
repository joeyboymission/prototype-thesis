# Odor Module Documentation

## Overview
This module is designed to:
- Collect data from MQ135 (gas/odor) and DHT22 (temperature/humidity) sensors
- Store collected data in both remote (MongoDB) and local (JSON file) databases
- Operate as a streamlined backend service without a complex GUI

## Hardware Configuration
The odor sensing system uses:
- Arduino Mega with MQ135 gas sensors connected to analog inputs
- DHT22 temperature/humidity sensors
- USB connection between Arduino Mega and Raspberry Pi via serial communication

## Setup Requirements
1. **Serial Communication**:
   - Arduino Mega operates as a slave device to the Raspberry Pi master
   - Arduino code broadcasts sensor data continuously
   - Use `ls /dev/tty*` to scan for available USB ports
   - Permissions for USB ports must be properly configured
   - May need to free the serial connection: `sudo lsof /dev/ttyUSB` and `sudo systemctl restart serial-getty@ttyUSB`

## Running the Module
Execute the command `python odor-mod-main.py` to launch the monitoring system.

### Startup Sequence
The script follows this sequence during startup:
1. Scan for Arduino using `ls /dev/tty*` (default port is `USB0`)
2. Verify and set permissions for read/write access to the USB port
3. Free the serial connection if needed (kill other processes, restart services)
4. Check database connectivity (will use both remote and local if online, local-only if remote is offline)
5. For the remote database (MongoDB) the collection name is `odor_module` and the database name is `Smart_Cubicle`
6. Check local storage folder named `local-data` that is located on the `/home/admin/Documents/local-data` to save the `odor-data.json` file, if the folder does not exist, create it. If the file does not exist, create it.
7. Initialize temperature and odor sensors
8. Begin data collection and logging

The initialization would look like this as an example
```
Checking the connection to Database..
Database Connected Succesfully!
Restored the last previous updated data from: Remote and Local
Checking the Serial Connection (Gas Sensor)..
Serial Connection Established!
Checking Temperature Sensor Connection..
Temperature Sensor Connection Established!
The sensors are ready!
```

### Data Format
All sensor readings are logged with:
- Timestamp format: `[YYYY-MM-DD HH:MM:SS]`
- Gas readings: `ODOR [GAS1: value | GAS2: value | GAS3: value | GAS4: value | GAS5: value]`
- Temperature readings: `TEMP [TEMP1: value | TEMP2: value | TEMP3: value | TEMP4: value]`
- Gas values follow Air Quality Index units
- Temperature values are in Celsius

### Fault Tolerance
- If a sensor fails (returns null or zero), the script calculates the average from working sensors
- Failed sensors are marked with an asterisk in the log (e.g., `*GAS2:`)
- If a serial connection fails, the script implements fault recovery: Scan, Permission fixing, Kill and Restart. Sudo commands for linux

### Data Logging
- Readings are recorded every 10 seconds (configurable for production deployment)
- Before saving, the script calculates the average of readings since the last save
- Data is saved to both remote (MongoDB) and local databases when possible
- Data follows the JSON format specified in `odor-data-format.json`

```
{
    "_id": "ObjectId()",
    "timestamp": "YYYY-MM-DD HH:MM:SS",
    "aqi": {
        "GAS1": 0,
        "GAS2": 0,
        "GAS3": 0,
        "GAS4": 0
    },
    "dht": {
        "TEMP1": {
            "temp": 0.0,
            "hum": 0.0
        },
        "TEMP2": {
            "temp": 0.0,
            "hum": 0.0
        },
        "TEMP3": {
            "temp": 0.0,
            "hum": 0.0
        },
        "TEMP4": {
            "temp": 0.0,
            "hum": 0.0
        }
    }
}
```
where the:
"_id": - thi is the mongoDB unique identifier, this will generate automatically by the mongodb but still sync or relfect this to the local database
"timestamp": - data and time of the reading make sure to follow stritly the formatting ``
"aqi": - air quiality index readings
"GAS1" to "GAS4": values from the four MQ135 gas sensors
"dht": - temperature and humidity reading from the DHT22 sensors
"TEMP1" to "TEMP4": four sensors locations
"temp": temperature in celcius
"hum": humidity percentage

make sure the if the value from the have a decimal reading, make sure it is 2 decimal point


### Success Output Format
When data is successfully saved:
```
Status: DATA SAVED TO REMOTE AND LOCAL
Odor Data: [GAS1] | [GAS2] | [GAS3] | [GAS4]
Temp Data: [TEMP1] | [TEMP2] | [TEMP3] | [TEMP4]
```

### Termination
- The monitoring process can be stopped with CTRL+C
- Upon termination, final data is saved to the available databases (remote and local)
