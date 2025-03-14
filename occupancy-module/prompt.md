Occupancy Module Requirements:

The proximity sensor behavior:
No detect = HIGH
Detect = LOW
At the initial run the sensor will output HIGH by default, therefore it will trigger the system registered as `Occupied` which is not it is the sensor fault. What if the first outuput of the sensor will avoid then it returns to the general instructions.

1. Visitor Counting:
- The IR sensor will track the number of visitors in the cubicle
- When a visitor enters, the count increments by 1
- When the same visitor exits, the count remains unchanged (no increment)

1. Occupancy Detection:
- The IR sensor monitors if the cubicle is occupied or vacant
- Initial state shows "Vacant" on serial monitor
- When visitor enters: Status changes to "Occupied" 
- When visitor exits: Status changes back to "Vacant"

1. Buzzer Notification:
- When the cubicle is occupied the buzzer will beep twice
- When the cubicle is vacant the buzzer will beep long once


Maintained Counting Strategy:
Kept the visitorCount = -1 initialization to offset the initial reading
Counter will show correctly from 0 when first actual visitor enters
Initial State:
Ensures LED starts OFF
Maintains "Vacant" status at startup
No buzzer sound on initialization
The behavior will now be:
On startup:
Status: Vacant
LED: OFF
Count: Shows 0 (internally -1)
Ignores initial HIGH state from sensor
First actual detection:
Will only respond after the first HIGH state is properly registered
Maintains vacant state until first person enters
Normal operation:
Counts visitors correctly starting from 0
Proper LED indication
Correct buzzer patterns for entry/exit