#define NUM_SENSORS 4  // Number of MQ135 sensors

// Calibration constants (same as original)
const float R0 = 10.0;  // Sensor resistance in clean air (kOhms, placeholder)
const float RL = 10.0;  // Load resistor (kOhms, typical for MQ135)
const float AQI_MIN = 0.0;
const float AQI_MAX = 500.0;
const float ANALOG_MIN = 0.0;
const float ANALOG_MAX = 1023.0;

int sensorPins[] = {A0, A1, A2, A3};  // MQ135 sensors on A0-A3
uint16_t aqiValues[NUM_SENSORS];  // AQI values (0-500) for each sensor

void setup() {
  Serial.begin(9600);  // Start Serial at 9600 baud
  Serial.println("Serial Slave ready");
  for (int i = 0; i < NUM_SENSORS; i++) {
    pinMode(sensorPins[i], INPUT);  // Set sensor pins as input
  }
}

void loop() {
  // Read and process MQ135 sensor data
  for (int i = 0; i < NUM_SENSORS; i++) {
    int rawValue = analogRead(sensorPins[i]);  // Read analog value (0-1023)
    if (rawValue < 0 || rawValue > 1023) {
      rawValue = 0;  // Handle invalid readings
    }
    
    // Convert raw value to AQI (simplified linear mapping)
    float voltage = (rawValue / ANALOG_MAX) * 5.0;  // Convert to voltage (5V)
    float rs = ((5.0 * RL) / voltage) - RL;  // Sensor resistance
    float ratio = rs / R0;  // Resistance ratio
    float aqi = mapFloat(ratio, 0.1, 10.0, AQI_MAX, AQI_MIN);  // Map to AQI
    aqiValues[i] = (uint16_t)constrain(aqi, AQI_MIN, AQI_MAX); // Clamp and store
  }
  
  // Send AQI values as comma-separated string
  Serial.print(aqiValues[0]);
  for (int i = 1; i < NUM_SENSORS; i++) {
    Serial.print(",");
    Serial.print(aqiValues[i]);
  }
  Serial.println();  // Newline to mark end of data
  
  delay(200);  // Update every 200ms to match original
}

// Helper function to map float values
float mapFloat(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}