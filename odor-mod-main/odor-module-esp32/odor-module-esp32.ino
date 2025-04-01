#include <DHT.h>
#include <Wire.h>
#include <Adafruit_ADS1x15.h>
#include <ArduinoJson.h>
#include <FS.h>
#include <SPIFFS.h>

#define DHT_TYPE DHT22
#define TEMP1_PIN 13
#define TEMP2_PIN 14
#define TEMP3_PIN 15
#define TEMP4_PIN 16
#define FAN_RELAY_PIN 23
#define FRESHENER_RELAY_PIN 19
#define SENSOR_PIN 17  // Occupancy sensor

DHT dht1(TEMP1_PIN, DHT_TYPE);
DHT dht2(TEMP2_PIN, DHT_TYPE);
DHT dht3(TEMP3_PIN, DHT_TYPE);
DHT dht4(TEMP4_PIN, DHT_TYPE);
Adafruit_ADS1115 ads;

float temp[4], hum[4], aqi[4];
int fanStatus = 0, freshenerTriggered = 0, isOccupied = 0, lastSensorState = HIGH;

void setup() {
  Serial.begin(115200);
  pinMode(FAN_RELAY_PIN, OUTPUT);
  pinMode(FRESHENER_RELAY_PIN, OUTPUT);
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  digitalWrite(FAN_RELAY_PIN, LOW);
  digitalWrite(FRESHENER_RELAY_PIN, LOW);

  dht1.begin();
  dht2.begin();
  dht3.begin();
  dht4.begin();

  Wire.begin(21, 22);
  if (!ads.begin()) {
    Serial.println("Failed to initialize ADS1115");
    while (1);
  }

  if (!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
    return;
  }
}

void readSensors() {
  temp[0] = dht1.readTemperature();
  hum[0] = dht1.readHumidity();
  temp[1] = dht2.readTemperature();
  hum[1] = dht2.readHumidity();
  temp[2] = dht3.readTemperature();
  hum[2] = dht3.readHumidity();
  temp[3] = dht4.readTemperature();
  hum[3] = dht4.readHumidity();

  aqi[0] = map(ads.readADC_SingleEnded(0), 0, 32767, 0, 500);
  aqi[1] = map(ads.readADC_SingleEnded(1), 0, 32767, 0, 500);
  aqi[2] = map(ads.readADC_SingleEnded(2), 0, 32767, 0, 500);
  aqi[3] = map(ads.readADC_SingleEnded(3), 0, 32767, 0, 500);
}

float calculateAvgAQI() {
  float sum = 0;
  for (int i = 0; i < 4; i++) sum += aqi[i];
  return sum / 4;
}

int checkOccupancy() {
  int currentSensorState = digitalRead(SENSOR_PIN);
  if (currentSensorState != lastSensorState && millis() - lastTime > 1000) {
    if (currentSensorState == LOW) isOccupied = 1;
    else {
      isOccupied = 0;
      lastSensorState = currentSensorState;
      return 1;  // Just vacated
    }
    lastSensorState = currentSensorState;
  }
  return 0;
}

void controlFan(float avgAQI) {
  if (avgAQI > 200 && !fanStatus) {
    digitalWrite(FAN_RELAY_PIN, HIGH);
    fanStatus = 1;
    Serial.println("Fan ON");
  } else if (avgAQI <= 200 && fanStatus) {
    digitalWrite(FAN_RELAY_PIN, LOW);
    fanStatus = 0;
    Serial.println("Fan OFF");
  }
}

void controlFreshener(float avgAQI, int vacated) {
  if ((avgAQI > 300 || vacated) && !freshenerTriggered) {
    digitalWrite(FRESHENER_RELAY_PIN, HIGH);
    delay(500);  // 500ms pulse
    digitalWrite(FRESHENER_RELAY_PIN, LOW);
    freshenerTriggered = 1;
    Serial.println("Air Freshener Triggered");
  } else if (avgAQI <= 300 && !vacated) {
    freshenerTriggered = 0;
  }
}

void logData() {
  StaticJsonDocument<512> doc;
  doc["timestamp"] = "2025-03-30T12:00:00Z"; // Add RTC for real time
  JsonObject sensors = doc.createNestedObject("sensors");
  sensors["temp1"]["temperature"] = temp[0];
  sensors["temp1"]["humidity"] = hum[0];
  sensors["temp2"]["temperature"] = temp[1];
  sensors["temp2"]["humidity"] = hum[1];
  sensors["temp3"]["temperature"] = temp[2];
  sensors["temp3"]["humidity"] = hum[2];
  sensors["temp4"]["temperature"] = temp[3];
  sensors["temp4"]["humidity"] = hum[3];
  sensors["gas1"]["aqi"] = aqi[0];
  sensors["gas2"]["aqi"] = aqi[1];
  sensors["gas3"]["aqi"] = aqi[2];
  sensors["gas4"]["aqi"] = aqi[3];
  doc["fan_status"] = fanStatus ? "on" : "off";
  doc["freshener_status"] = freshenerTriggered ? "triggered" : "off";
  doc["occupancy_status"] = isOccupied ? "occupied" : "vacant";

  File file = SPIFFS.open("/odor_data.json", FILE_WRITE);
  if (file) {
    serializeJson(doc, file);
    file.close();
  }
}

unsigned long lastTime = 0;
void loop() {
  readSensors();
  float avgAQI = calculateAvgAQI();
  int vacated = checkOccupancy();
  controlFan(avgAQI);
  controlFreshener(avgAQI, vacated);
  logData();

  Serial.print("Avg AQI: "); Serial.println(avgAQI);
  delay(10000);
}