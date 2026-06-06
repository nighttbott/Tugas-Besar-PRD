/**
 * ITB Jatinangor Parking Gate — ESP32 Smart MQTT Gate Controller
 * ─────────────────────────────────────────────────────────────
 * Dependencies:
 * - PubSubClient by Nick O'Leary
 * - ArduinoJson by Benoit Blanchon (V6 atau V7)
 * - ESP32Servo by Kevin Harrington
 * - WiFiManager by tzapu (Fitur Captive Portal / Smart Device)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <WiFiManager.h>
#include "esp_timer.h"

// ─────────────────────────────────────────────────────────────────────────────
// KONFIGURASI SMART DEVICE (DIUBAH VIA BROWSER HP NANTINYA)
// ─────────────────────────────────────────────────────────────────────────────
// Default value jika alat baru pertama kali dinyalakan.
char mqtt_server[40] = "192.168.1.38"; 
const int  mqtt_port = 1883;

// Kredensial Mosquitto (kosongkan jika allow_anonymous = true)
const char* mqtt_user = ""; 
const char* mqtt_pass = ""; 

const char* gate_id   = "G1";
const char* mqtt_topic_cmd    = "gate/G1/command";
const char* mqtt_topic_status = "gate/G1/status";
const char* client_id         = "ESP32_Gate_G1";

// ─────────────────────────────────────────────────────────────────────────────
// HARDWARE PINS
// ─────────────────────────────────────────────────────────────────────────────
static const int SERVO_PIN      = 18;
static const int BUZZER_PIN     = 19;
static const int LED_PIN        = 21;
static const int STATUS_LED_PIN = 2;  // Built-in LED

// ── Servo Configuration ──
Servo gateServo;
static const int ANGLE_CLOSED = 90;  
static const int ANGLE_OPEN   = 0; 

// ─────────────────────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────────────────────
WiFiClient espClient;
PubSubClient mqttClient(espClient);

static bool     gateOpen           = false;
static uint32_t lastConnectAttempt = 0;
static esp_timer_handle_t gateTimer = nullptr;

// ─────────────────────────────────────────────────────────────────────────────
// HARDWARE CONTROL (NON-BLOCKING)
// ─────────────────────────────────────────────────────────────────────────────

// Callback ini dipanggil saat waktu timer habis
static void IRAM_ATTR gateAutoClose(void* /*arg*/) {
    gateServo.write(ANGLE_CLOSED);
    digitalWrite(LED_PIN, LOW);
    
    // Bunyi buzzer 2 kali (Tutup)
    digitalWrite(BUZZER_PIN, HIGH); delay(50); 
    digitalWrite(BUZZER_PIN, LOW);  delay(50);
    digitalWrite(BUZZER_PIN, HIGH); delay(50);
    digitalWrite(BUZZER_PIN, LOW);
    
    gateOpen = false;
}

void openGate(uint32_t durationMs) {
    if (gateOpen) {
        Serial.println("[GATE] Already open — resetting idle timer.");
        esp_timer_stop(gateTimer);
    } else {
        gateServo.write(ANGLE_OPEN);
        digitalWrite(LED_PIN, HIGH);
        gateOpen = true;

        // Bunyi buzzer panjang 1 kali (Buka)
        digitalWrite(BUZZER_PIN, HIGH); delay(150);
        digitalWrite(BUZZER_PIN, LOW);

        Serial.println("[GATE] Gate OPENED.");
    }
    // Mulai hitung mundur penutupan (durationMs dalam Microseconds)
    esp_timer_start_once(gateTimer, (uint64_t)durationMs * 1000ULL);
}

// ─────────────────────────────────────────────────────────────────────────────
// MQTT CALLBACK & RECONNECT
// ─────────────────────────────────────────────────────────────────────────────

void mqtt_callback(char* topic, byte* payload, unsigned int length) {
    String msg;
    for (int i = 0; i < length; i++) {
        msg += (char)payload[i];
    }
    Serial.printf("[MQTT] Message arrived [%s]: %s\n", topic, msg.c_str());

    JsonDocument doc; // Otomatis menyesuaikan V6/V7
    DeserializationError err = deserializeJson(doc, msg);

    if (err) {
        Serial.printf("[JSON] Parse error: %s\n", err.c_str());
        return;
    }

    const char* action = doc["action"] | "unknown";
    if (strcmp(action, "open_gate") == 0) {
        // Ambil durasi, jika tidak ada default 5000ms
        uint32_t duration = doc["duration_ms"] | 5000;
        openGate(duration);
        
        // Blink LED Status cepat (Visual Confirmation)
        for (int i = 0; i < 3; i++) {
            digitalWrite(STATUS_LED_PIN, HIGH); delay(50);
            digitalWrite(STATUS_LED_PIN, LOW); delay(50);
        }
    }
}

bool connectMQTT() {
    Serial.print("[MQTT] Attempting connection...");
    
    // Safety: Tutup gerbang jika MQTT mati mendadak
    if (gateOpen) {
        esp_timer_stop(gateTimer);
        gateAutoClose(nullptr);
    }

    // Setup LWT (Last Will and Testament)
    // Jika ESP32 terputus tidak wajar, broker akan otomatis mem-publish "offline" ke topik status
    if (mqttClient.connect(client_id, mqtt_user, mqtt_pass, mqtt_topic_status, 1, true, "offline")) {
        Serial.println("CONNECTED");
        
        // Publikasi status aktif (Retained)
        mqttClient.publish(mqtt_topic_status, "online", true);

        mqttClient.subscribe(mqtt_topic_cmd);
        Serial.printf("[MQTT] Subscribed to %s\n", mqtt_topic_cmd);
        digitalWrite(STATUS_LED_PIN, HIGH); // Tanda berhasil konek semua
        return true;
    } else {
        Serial.printf("FAILED (rc=%d)\n", mqttClient.state());
        digitalWrite(STATUS_LED_PIN, LOW);
        return false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SETUP & WIFIMANAGER (CAPTIVE PORTAL)
// ─────────────────────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("\n\n=== ITB Jatinangor SMART Parking Gate ===");

    // ── Init Pin Output ──
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(LED_PIN, OUTPUT);
    pinMode(STATUS_LED_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(LED_PIN, LOW);
    digitalWrite(STATUS_LED_PIN, LOW);

    // ── Init PWM Servo Anti-Jitter ──
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    gateServo.setPeriodHertz(50); 
    gateServo.attach(SERVO_PIN, 500, 2400); 
    gateServo.write(ANGLE_CLOSED); 

    // ── Init Hardware Timer ──
    esp_timer_create_args_t timerArgs = {};
    timerArgs.callback        = &gateAutoClose;
    timerArgs.name            = "gate_timer";
    timerArgs.dispatch_method = ESP_TIMER_TASK; 
    esp_timer_create(&timerArgs, &gateTimer);

    // ── WiFiManager Captive Portal ──
    WiFiManager wm;
    // Parameter Khusus: Kotak teks agar Anda bisa memasukkan IP Docker Server di HP!
    WiFiManagerParameter custom_mqtt_server("server", "MQTT Server IP (Docker)", mqtt_server, 40);
    wm.addParameter(&custom_mqtt_server);

    Serial.println("[WiFi] Starting Captive Portal...");
    // Jika gagal konek ke WiFi terakhir, buat Hotspot bernama "Gerbang_ITB_Setup"
    bool res = wm.autoConnect("Gerbang_ITB_Setup"); 

    if(!res) {
        Serial.println("[WiFi] Failed to connect / Timeout. Restarting...");
        delay(3000);
        ESP.restart();
    } 
    
    // Simpan IP yang baru Anda ketikkan dari HP
    strcpy(mqtt_server, custom_mqtt_server.getValue());

    Serial.println("[WiFi] CONNECTED!");
    Serial.print("[WiFi] IP: "); Serial.println(WiFi.localIP());
    Serial.printf("[WiFi] Saved MQTT IP: %s\n", mqtt_server);

    // ── Init MQTT ──
    mqttClient.setServer(mqtt_server, mqtt_port);
    mqttClient.setCallback(mqtt_callback);
    
    connectMQTT();
}

// ─────────────────────────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
    // Reconnect MQTT secara Non-Blocking (Tidak menghentikan proses lain)
    if (!mqttClient.connected()) {
        uint32_t now = millis();
        if (now - lastConnectAttempt >= 5000) {
            lastConnectAttempt = now;
            connectMQTT();
        }
    } else {
        mqttClient.loop();
    }

    // Efek Blink pelan jika gerbang sedang terbuka
    if (gateOpen && mqttClient.connected()) {
        if ((millis() / 500) % 2 == 0) digitalWrite(STATUS_LED_PIN, HIGH);
        else digitalWrite(STATUS_LED_PIN, LOW);
    }
}