// SMART RESTROOM: PREVENTIVE MAINTENANCE SYSTEM USING MACHINE LEARNING ALGORITHM
// Module Name: Occupancy Detection
// Description: This module detects the cubicle occupancy and the count of how many visitor when in the specific cubicle


// Add I2C Display libraries
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Define the pin for the E18-D80NK sensor
const int sensorPin = 5;
const int ledPin = 19;
const int buzzerPin = 2;
const int SDA_PIN = 21;
const int SCL_PIN = 22;

// Variables for tracking occupancy and count
int visitorCount = -1;  // Initialize as -1 as offset when the system is initialized
bool isOccupied = false;  // Initialize as vacant
bool lastSensorState = HIGH;  // HIGH means no obstacle
unsigned long lastDetectionTime = 0;
const unsigned long DEBOUNCE_DELAY = 1000;  // 1 second debounce

// Buzzer timing constants
const int SHORT_BEEP = 200;   // 200ms for short beep
const int BEEP_PAUSE = 200;   // 200ms pause between beeps
const int LONG_BEEP = 1000;   // 1 second for long beep

// Initialize LCD (0x27 is the default I2C address, adjust if needed)
LiquidCrystal_I2C lcd(0x27, 16, 2);  // 16x2 LCD display

void setup() {
  // Initialize digital pins
  pinMode(sensorPin, INPUT);   // Sensor output as input
  pinMode(ledPin, OUTPUT);     // LED as output
  pinMode(buzzerPin, OUTPUT);  // Buzzer as output

  // Initialize I2C Display
  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  
  // Display startup message on LCD
  lcd.setCursor(0, 0);
  lcd.print("System Starting");
  lcd.setCursor(0, 1);
  lcd.print("Please Wait...");

  // Ensure initial states are correct
  digitalWrite(ledPin, LOW);     // LED off initially (Vacant)
  digitalWrite(buzzerPin, LOW);  // Buzzer off initially

  // Start Serial Monitor at 9600 baud for debugging
  Serial.begin(9600);
  Serial.println("\n=== E18-D80NK IR Sensor System Started ===");
  Serial.println("Initializing...");
  delay(1000);  // Short delay for system stabilization
  
  // Display initial status
  Serial.println("System Ready!");
  Serial.println("Current Status: Vacant");
  Serial.println("Visitor Count: 0");
  Serial.println("=====================================");

  // Update LCD with initial status
  updateDisplay();
}

// Function to make the buzzer beep
void beepBuzzer(int duration) {
  digitalWrite(buzzerPin, HIGH);
  delay(duration);
  digitalWrite(buzzerPin, LOW);
}

// Function for double beep
void doubleBeep() {
  beepBuzzer(SHORT_BEEP);
  delay(BEEP_PAUSE);
  beepBuzzer(SHORT_BEEP);
}

// New function to update both Serial and LCD display
void updateDisplay() {
  // Update LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(isOccupied ? "Status: OCCUPIED" : "Status: VACANT");
  lcd.setCursor(0, 1);
  lcd.print("Visitors: ");
  lcd.print(visitorCount);
  
  // Update Serial (existing code remains in place)
}

void loop() {
  // Read the sensor value
  int currentSensorState = digitalRead(sensorPin);
  unsigned long currentTime = millis();
  
  // Check for sensor state change with debounce
  if (currentSensorState != lastSensorState && 
      (currentTime - lastDetectionTime) > DEBOUNCE_DELAY) {
    
    // Object detected (LOW state)
    if (currentSensorState == LOW) {
      if (!isOccupied) {
        // Someone entering the cubicle
        isOccupied = true;
        visitorCount++;
        Serial.println("\n--- Status Change Detected ---");
        Serial.println("Status: Occupied");
        Serial.print("Visitor Count: ");
        Serial.println(visitorCount);
        digitalWrite(ledPin, HIGH);
        doubleBeep();  // Two short beeps when occupied
        updateDisplay();  // Update both displays
      } else {
        // Someone leaving the cubicle
        isOccupied = false;
        Serial.println("\n--- Status Change Detected ---");
        Serial.println("Status: Vacant");
        digitalWrite(ledPin, LOW);
        beepBuzzer(LONG_BEEP);  // One long beep when vacant
        updateDisplay();  // Update both displays
      }
      lastDetectionTime = currentTime;
    }
    
    lastSensorState = currentSensorState;
  }
  
  // Small delay to prevent reading too frequently
  delay(50);
}

