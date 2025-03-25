// Define the analog pin for MQ135 gas sensor
const int MQ135_PIN = 4;

void setup() {
  // Initialize serial communication at 9600 baud rate
  Serial.begin(9600);
  
  // Print header for data
  Serial.println("MQ135 Gas Sensor Raw Data");
  Serial.println("------------------------");
}

void loop() {
  // Read the raw value from the sensor
  int rawValue = analogRead(MQ135_PIN);
  
  // Print the raw value
  Serial.print("Raw Value: ");
  Serial.println(rawValue);
  
  // Add a small delay between readings (1 second)
  delay(1000);
}
