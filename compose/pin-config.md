# Pin Configuration

## Occupancy Module
- E18-D80NK Proximity Sensor: GPIO17 (Pin 11)
- Buzzer: GPIO27 (Pin 13)

## Odor Module
### DHT22 Temperature/Humidity Sensors
- TEMP1: GPIO4 (Pin 7)
- TEMP2: GPIO5 (Pin 29) 
- TEMP3: GPIO6 (Pin 31)
- TEMP4: GPIO12 (Pin 32)

### Relays
- 8RELAY-B K2 (Exhaust Fan): GPIO23 (Pin 16)
- 8RELAY-B K3 (Air Freshener): GPIO24 (Pin 18)

### Other
- Arduino Mega: Serial communication over USB (no GPIO pins used)

## Dispenser Module
### HC-SR04 Ultrasonic Sensors
- SONIC1 (CONT1): 
  - Trigger: GPIO7 (Pin 26)
  - Echo: GPIO8 (Pin 24)
- SONIC2 (CONT2):
  - Trigger: GPIO9 (Pin 21)
  - Echo: GPIO10 (Pin 19)
- SONIC3 (CONT3):
  - Trigger: GPIO11 (Pin 23)
  - Echo: GPIO13 (Pin 33)
- SONIC4 (CONT4):
  - Trigger: GPIO14 (Pin 8)
  - Echo: GPIO15 (Pin 10)

## Central Hub
### Relays
- 8RELAY-B K1 (DC Fan): GPIO20 (Pin 38)
- 8RELAY-B K2 (Exhaust Fan): GPIO23 (Pin 16)
- 8RELAY-B K3 (Air Freshener): GPIO24 (Pin 18)

## GPIO Pin Summary
### Used Pins
GPIO4, GPIO5, GPIO6, GPIO7, GPIO8, GPIO9, GPIO10, GPIO11, GPIO12, GPIO13, GPIO14, GPIO15, GPIO17, GPIO20, GPIO23, GPIO24, GPIO27

### Available Pins
GPIO2, GPIO3, GPIO16, GPIO21, GPIO25, GPIO26