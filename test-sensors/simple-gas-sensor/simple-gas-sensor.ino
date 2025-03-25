// Include Libraries
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Pin Definitions
const int sensorPin = 4;      // MQ135 sensor pin
const int alarmPin = 2;       // Buzzer pin
const int ledPin = 19;        // Single LED pin
const int SDA_PIN = 21;       // I2C SDA pin
const int SCL_PIN = 22;       // I2C SCL pin

// AQI Thresholds
const int POOR_THRESHOLD = 2500;
const int VERY_POOR_THRESHOLD = 3500;
const int SEVERE_THRESHOLD = 4095;

// Alert timing constants (in milliseconds)
const int POOR_DELAY = 500;        // 0.5 seconds
const int VERY_POOR_DELAY = 250;   // 0.25 seconds
const int SEVERE_DELAY = 100;      // 0.1 seconds

// Global variables and defines
int sensorData;
String aqiCategory;
int aqiValue;
unsigned long lastAlertTime = 0;
int currentDelay = POOR_DELAY;

// Function for dynamic alert pattern
void alertPattern(int delayTime) {
  unsigned long currentTime = millis();
  if (currentTime - lastAlertTime >= delayTime) {
    lastAlertTime = currentTime;
    
    // Toggle LED and buzzer
    digitalWrite(ledPin, !digitalRead(ledPin));
    digitalWrite(alarmPin, digitalRead(ledPin));
  }
}

// Function to determine AQI category and value
void calculateAQI(int rawValue) {
  if (rawValue <= POOR_THRESHOLD) {
    aqiCategory = "Poor";
    aqiValue = map(rawValue, 2001, POOR_THRESHOLD, 201, 300);
    currentDelay = POOR_DELAY;
  } else if (rawValue <= VERY_POOR_THRESHOLD) {
    aqiCategory = "Very Poor";
    aqiValue = map(rawValue, POOR_THRESHOLD + 1, VERY_POOR_THRESHOLD, 301, 400);
    currentDelay = VERY_POOR_DELAY;
  } else {
    aqiCategory = "Severe";
    aqiValue = map(rawValue, VERY_POOR_THRESHOLD + 1, SEVERE_THRESHOLD, 401, 500);
    currentDelay = SEVERE_DELAY;
  }
}

void setup()
{  
  Serial.begin(9600);
  
  // Initialize I2C Display
  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  
  pinMode(sensorPin, INPUT);
  pinMode(alarmPin, OUTPUT);
  pinMode(ledPin, OUTPUT);

  // Display Initial Message both I2C and Serial Monitor
  lcd.setCursor(0,0);
  lcd.print("Air Quality");
  lcd.setCursor(0,1);
  lcd.print("Monitoring");
  Serial.println("Air Quality Monitoring System");
  Serial.println("----------------------------");
  delay(2500);
  lcd.clear();                    
}

unsigned long previousMillis = 0;
const long interval = 500;

void loop()
{
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    sensorData = analogRead(sensorPin);
    calculateAQI(sensorData);

    // Display on LCD
    lcd.setCursor(0,0);
    lcd.print("AQI: ");
    lcd.print(aqiValue);
    lcd.print(" ");
    lcd.print(aqiCategory);
    
    // Scroll the category if it's too long
    if (aqiCategory.length() > 8) {
      delay(2000);
      lcd.clear();
      lcd.setCursor(0,0);
      lcd.print("Raw: ");
      lcd.print(sensorData);
      lcd.setCursor(0,1);
      lcd.print(aqiCategory);
    }

    // Print detailed information to Serial Monitor
    Serial.println("----------------------------");
    Serial.print("Raw Value: ");
    Serial.println(sensorData);
    Serial.print("AQI Category: ");
    Serial.println(aqiCategory);
    Serial.print("AQI Value: ");
    Serial.println(aqiValue);

    // Dynamic alert system based on AQI category
    if (sensorData > POOR_THRESHOLD) {  // Alert for Poor and above
      alertPattern(currentDelay);
      Serial.print("Alert Level: ");
      Serial.println(aqiCategory);
    } else {
      digitalWrite(ledPin, LOW);
      digitalWrite(alarmPin, LOW);
      Serial.println("Status: Normal");
    }
  }
}