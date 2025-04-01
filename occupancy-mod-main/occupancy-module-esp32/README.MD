# Occupancy Module

## Project Description
SMART RESTROOM: PREVENTIVE MAINTENANCE SYSTEM USING MACHINE LEARNING ALGORITHM

This module handles occupancy detection and visitor counting for restroom cubicles. It provides real-time monitoring of cubicle occupancy status and maintains a count of visitors. The system uses an infrared sensor to detect entry and exit events, with LED indication and audio feedback through a buzzer.

## Features
- Real-time occupancy detection
- Visitor counting
- LED status indication
- Audio feedback for status changes
- Debounce protection for reliable detection

## Hardware Requirements
- E18-D80NK IR Infrared Obstacle Avoidance Proximity Sensor
- Active Buzzer
- LED (Status Indicator)
- Arduino-compatible microcontroller
- Connecting wires

## Wiring Configuration
### E18-D80NK Infrared Obstacle Avoidance Proximity Sensor
- Brown = VCC (5V DC power supply)
- Black = Output Signal (NPN normally high)
- Blue = GND (Ground)

Adjustment Screw
This adjusts the sensitivity and distance of the sensor (3cm to 80cm range)
- Clockwise = Decreases detection distance
- Counter-clockwise = Increases detection distance

### Buzzer
Long Prong - Anode
Short Prong - Cathode

### LED
Long Prong - Anod
Short Prong - Cathod

## Pin Connections
- Pin 5  - E18-D80NK Sensor Input
- Pin 19 - LED Status Indicator Output
- Pin 21 - Buzzer Output

## Setup Instructions
1. Connect the hardware components according to the pin connections specified above
2. Upload the provided code to your Arduino-compatible board
3. The system will initialize with:
   - LED OFF (indicating vacant state)
   - Buzzer OFF
   - Initial visitor count set to 0
4. The system will output status messages through Serial Monitor at 9600 baud

## Usage Examples
The system provides different feedback for various states:

### Visual Indicators
- LED ON: Cubicle is occupied
- LED OFF: Cubicle is vacant

### Audio Indicators
- Double Short Beep: Someone enters the cubicle (becomes occupied)
- Single Long Beep: Someone exits the cubicle (becomes vacant)

### Serial Monitor Output
The system provides real-time status updates through the Serial Monitor:
```
=== E18-D80NK IR Sensor System Started ===
Initializing...
System Ready!
Current Status: Vacant
Visitor Count: 0
=====================================
```

## System Behavior
- Debounce protection: 1-second delay between readings to prevent false triggers
- Visitor counting: Increments when someone enters the cubicle
- Status tracking: Maintains current occupancy state
- Audio feedback: Different beep patterns for entry and exit events

## Technical Details
- Operating voltage: 5V
- Serial communication: 9600 baud
- Debounce delay: 1000ms
- Short beep duration: 200ms
- Long beep duration: 1000ms
- Sensor polling delay: 50ms

## Contributors
- Joey Boy Mission
