#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

// ── Configuration ────────────────────────────────────────────────────────────
const char* ssid        = "YOUR_WIFI_SSID";
const char* password    = "YOUR_WIFI_PASSWORD";

const char* mqtt_server = "192.168.1.X"; // Ganti dengan IP Broker MQTT Anda
const int   mqtt_port   = 1883;
const char* mqtt_user   = "";            // Kosongkan jika tidak ada
const char* mqtt_pass   = "";            // Kosongkan jika tidak ada
const char* mqtt_topic  = "gate/G1/command";
const char* client_id   = "ESP32_Gate_G1";

// ── Pins & Hardware ──────────────────────────────────────────────────────────
const int SERVO_PIN = 18; // Ganti dengan pin PWM servo Anda
Servo gateServo;

// ── State Variables ──────────────────────────────────────────────────────────
WiFiClient espClient;
PubSubClient client(espClient);

bool isGateOpen = false;
unsigned long gateOpenTime = 0;
unsigned long gateDuration = 0;


void setup_wifi() {
    delay(10);
    Serial.println();
    Serial.print("Connecting to WiFi: ");
    Serial.println(ssid);

    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("");
    Serial.println("WiFi connected.");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
}

void mqtt_callback(char* topic, byte* payload, unsigned int length) {
    Serial.print("Message arrived [");
    Serial.print(topic);
    Serial.print("] ");
    
    // Convert payload to String
    String message;
    for (int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    Serial.println(message);

    // Parse JSON
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, message);

    if (error) {
        Serial.print("deserializeJson() failed: ");
        Serial.println(error.c_str());
        return;
    }

    const char* action = doc["action"];
    long duration_ms = doc["duration_ms"];
    
    if (action != nullptr && String(action) == "open_gate") {
        Serial.print("Opening gate for ");
        Serial.print(duration_ms);
        Serial.println(" ms.");
        
        gateServo.write(90); // Buka gate (sudut 90 derajat)
        
        isGateOpen = true;
        gateDuration = duration_ms;
        gateOpenTime = millis();
    }
}

void reconnect() {
    // Loop until we're reconnected
    while (!client.connected()) {
        Serial.print("Attempting MQTT connection...");
        // Attempt to connect
        if (client.connect(client_id, mqtt_user, mqtt_pass)) {
            Serial.println("connected");
            // Once connected, publish an announcement and resubscribe
            client.subscribe(mqtt_topic);
            Serial.print("Subscribed to ");
            Serial.println(mqtt_topic);
        } else {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5 seconds");
            // Wait 5 seconds before retrying (blocking is ok here because we are disconnected)
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    
    gateServo.attach(SERVO_PIN);
    gateServo.write(0); // Posisi awal tertutup (0 derajat)

    setup_wifi();
    
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(mqtt_callback);
}

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    
    // Proses incoming messages dan keep-alive MQTT
    client.loop();

    // ── Pendekatan Non-Blocking untuk menutup gate ──────────────────────────
    if (isGateOpen) {
        // Cek apakah waktu sudah lewat dari durasi yang ditentukan
        if (millis() - gateOpenTime >= gateDuration) {
            Serial.println("Closing gate automatically.");
            gateServo.write(0); // Tutup gate
            isGateOpen = false;
        }
    }
}
