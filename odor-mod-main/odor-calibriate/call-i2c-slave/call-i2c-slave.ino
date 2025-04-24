#include <Wire.h>
#define I2C_ADDRESS 8

void setup() {
  Wire.begin(I2C_ADDRESS);          // Start I2C as slave on address 8
  Wire.onRequest(requestEvent);     // Register request handler
  Serial.begin(9600);              // Start Serial for debugging
  Serial.println("I2C Slave ready at address 0x08");
}

void loop() {
  delay(100);                      // Small delay to avoid overloading
}

void requestEvent() {
  Serial.println("Received I2C request");
  Wire.write(0xAA);               // Send single byte 0xAA (170 decimal)
  Serial.println("Sent byte: 0xAA");
}