#include <Wire.h>

#define I2C_ADDRESS 8  // I2C slave address
#define SENSOR_PINS {A0, A1, A2, A3}  // MQ135 sensors on A0-A3
#define NUM_SENSORS 4

// Calibration constants (adjust based on mq135-test.py results)
const float R0 = 10.0;  // Sensor resistance in clean air (kOhms, placeholder)
const float RL = 10.0;  // Load resistor (kOhms, typical for MQ135)
const float AQI_MIN = 0.0;
const float AQI_MAX = 500.0;
const float ANALOG_MIN = 0.0;
const float ANALOG_MAX = 1023.0;

int sensorPins[] = SENSOR_PINS;
uint16_t aqiValues[NUM_SENSORS];  // AQI values (0-500) for each sensor

void setup() {
  // Initialize I2C as slave on A4 (SDA), A5 (SCL)
  Wire.begin(I2C_ADDRESS);
  Wire.onRequest(requestEvent);  // Register I2C request handler
  
  // Initialize serial for debugging (optional)
  Serial.begin(9600);
  
  // Set sensor pins as input
  for (int i = 0; i < NUM_SENSORS; i++) {
    pinMode(sensorPins[i], INPUT);
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
    // Note: Replace with proper calibration formula if available
    float voltage = (rawValue / ANALOG_MAX) * 5.0;  // Convert to voltage (5V reference)
    float rs = ((5.0 * RL) / voltage) - RL;  // Sensor resistance
    float ratio = rs / R0;  // Resistance ratio
    float aqi = mapFloat(ratio, 0.1, 10.0, AQI_MAX, AQI_MIN);  // Map to AQI (0-500)
    
    // Clamp AQI to valid range
    aqi = constrain(aqi, AQI_MIN, AQI_MAX);
    aqiValues[i] = (uint16_t)aqi;  // Store as 16-bit integer
  }
  
  // Optional: Print AQI values for debugging
  Serial.print("AQI: ");
  for (int i = 0; i < NUM_SENSORS; i++) {
    Serial.print(aqiValues[i]);
    Serial.print(" ");
  }
  Serial.println();
  
  delay(100);  // Update every 100ms
}

// I2C request handler: Send 8 bytes (4 sensors x 2 bytes)
void requestEvent() {
  uint8_t buffer[8];
  for (int i = 0; i < NUM_SENSORS; i++) {
    buffer[i*2] = (aqiValues[i] >> 8) & 0xFF;  // MSB
    buffer[i*2 + 1] = aqiValues[i] & 0xFF;     // LSB
  }
  Wire.write(buffer, 8);  // Send 8 bytes to Pi
}

// Helper function to map float values
float mapFloat(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}