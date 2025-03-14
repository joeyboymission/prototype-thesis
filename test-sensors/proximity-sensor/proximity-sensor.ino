// E18-D80NK IR Infrared Obstacle Avoidance Proximity Sensor

// Define the pin for the E18-D80NK sensor
const int sensorPin = 5;
const int ledPin = 19;
const int buzzerPin = 21;

void setup() {
  // Initialize digital pins
  pinMode(sensorPin, INPUT);  // Sensor output as input
  pinMode(ledPin, OUTPUT);    // LED as output
  pinMode(buzzerPin, OUTPUT); // Buzzer as output

  // Start Serial Monitor at 9600 baud for debugging
  Serial.begin(9600);
  Serial.println("E18-D80NK IR Sensor Test Started");
}

void loop() {
  // Read the sensor value
  int sensorValue = digitalRead(sensorPin);
  
  // Check sensor state and print result
  if (sensorValue == HIGH) {
    Serial.println("No Obstacle Detected");
    digitalWrite(ledPin, LOW);  // Turn off LED
    digitalWrite(buzzerPin, LOW); // Turn off Buzzer
  } else {
    Serial.println("Obstacle Detected!");
    digitalWrite(ledPin, HIGH); // Turn on LED
    digitalWrite(buzzerPin, HIGH); // Turn on Buzzer
  }
  
  // Delay for readability (adjust as needed)
  delay(500);
}
