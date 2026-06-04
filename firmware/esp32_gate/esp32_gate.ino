/**
 * firmware/esp32_gate/esp32_gate.ino
 *
 * ITB Jatinangor Parking Gate — ESP32 Gate Controller Firmware
 * ─────────────────────────────────────────────────────────────
 * Dependencies:
 * - ArduinoWebsockets by Gil Maimon  v0.5.x
 * - ArduinoJson by Benoit Blanchon   v7.x
 * - ESP32Servo by Kevin Harrington   (TAMBAHKAN LIBRARY INI)
 */

#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include "esp_timer.h"

using namespace websockets;

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURATION
// ─────────────────────────────────────────────────────────────────────────────
#include "esp32_gate_config.h"

// WS_URL di-build otomatis — jangan edit manual
static char WS_URL[128];

// ─────────────────────────────────────────────────────────────────────────────
// HARDWARE PINS
// ─────────────────────────────────────────────────────────────────────────────
static const int SERVO_PIN      = 18; // Menggantikan RELAY_PIN
static const int BUZZER_PIN     = 19; // Buzzer aktif
static const int LED_PIN        = 21; // LED indikator gerbang terbuka
static const int STATUS_LED_PIN = 2;  // Built-in LED

// ── Servo Configuration ──
Servo gateServo;
static const int ANGLE_CLOSED = 0;  // Sudut saat gerbang tertutup
static const int ANGLE_OPEN   = 90; // Sudut saat gerbang terbuka

// ─────────────────────────────────────────────────────────────────────────────
// TIMING & RECONNECT
// ─────────────────────────────────────────────────────────────────────────────
static const uint32_t HEARTBEAT_INTERVAL_MS = 15000;
static const uint32_t RECONNECT_BASE_MS     = 2000;
static const uint32_t RECONNECT_MAX_MS      = 30000;
static const uint32_t WIFI_TIMEOUT_MS       = 15000;

// ─────────────────────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────────────────────
WebsocketsClient wsClient;

static bool     gateOpen           = false;
static uint32_t reconnectDelay     = RECONNECT_BASE_MS;
static uint32_t lastHeartbeat      = 0;
static uint32_t lastConnectAttempt = 0;
static bool     wsConnected        = false;
static esp_timer_handle_t gateTimer = nullptr;

// ─────────────────────────────────────────────────────────────────────────────
// HARDWARE CONTROL
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Hardware timer callback — Dieksekusi di context Task (bukan ISR murni),
 * sehingga aman untuk memanggil gateServo.write() dan fungsi standar Arduino.
 */
static void IRAM_ATTR gateAutoClose(void* /*arg*/) {
    gateServo.write(ANGLE_CLOSED);
    digitalWrite(LED_PIN, LOW);
    
    // Bunyi buzzer 2 kali sebagai tanda gerbang menutup
    digitalWrite(BUZZER_PIN, HIGH);
    delay(50); 
    digitalWrite(BUZZER_PIN, LOW);
    delay(50);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(50);
    digitalWrite(BUZZER_PIN, LOW);
    
    gateOpen = false;
}

#define GATE_IDLE_CLOSE_MS 5000  // tutup setelah 5 detik tidak ada deteksi

void openGate(uint32_t durationMs) {
    // Selalu reset timer ke 5 detik dari sekarang
    // (setiap deteksi baru memperpanjang waktu buka)
    if (gateOpen) {
        Serial.println("[GATE] Already open — resetting idle timer.");
        esp_timer_stop(gateTimer);
    } else {
        // Eksekusi hardware hanya kalau gate belum terbuka
        gateServo.write(ANGLE_OPEN);
        digitalWrite(LED_PIN, HIGH);
        gateOpen = true;

        // Buzzer 1 kali panjang
        digitalWrite(BUZZER_PIN, HIGH);
        delay(150);
        digitalWrite(BUZZER_PIN, LOW);

        Serial.println("[GATE] Gate OPENED.");
    }

    Serial.printf("[GATE] Idle close in %u ms\n", GATE_IDLE_CLOSE_MS);
    esp_timer_start_once(gateTimer, (uint64_t)GATE_IDLE_CLOSE_MS * 1000ULL);
}

// ─────────────────────────────────────────────────────────────────────────────
// WEBSOCKET EVENT HANDLERS
// ─────────────────────────────────────────────────────────────────────────────
void onMessage(WebsocketsMessage msg) {
    if (msg.isEmpty()) return;

    if (msg.data() == "pong") {
        Serial.println("[WS] Heartbeat acknowledged.");
        return;
    }

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, msg.data());
    if (err) {
        Serial.printf("[WS] JSON parse error: %s\n", err.c_str());
        return;
    }

    const char* action = doc["action"] | "unknown";
    if (strcmp(action, "open_gate") == 0) {
        uint32_t duration  = 5000; // Standar sedikit lebih lama untuk servo
        const char* plate  = doc["plate"]       | "?";
        const char* gateId = doc["gate_id"]     | "?";
        
        Serial.printf("[CMD] open_gate → gate=%s plate=%s duration=%ums\n", gateId, plate, duration);
        openGate(duration);

        // Visual confirmation blink di Built-in LED
        for (int i = 0; i < 3; i++) {
            digitalWrite(STATUS_LED_PIN, HIGH);
            delay(50);
            digitalWrite(STATUS_LED_PIN, LOW);
            delay(50);
        }
    } else {
        Serial.printf("[CMD] Unknown action: %s\n", action);
    }
}

void onEvent(WebsocketsEvent event, String data) {
    switch (event) {
        case WebsocketsEvent::ConnectionOpened:
            Serial.println("[WS] Connected to backend.");
            wsConnected    = true;
            reconnectDelay = RECONNECT_BASE_MS; 
            digitalWrite(STATUS_LED_PIN, HIGH);
            break;
            
        case WebsocketsEvent::ConnectionClosed:
            Serial.println("[WS] Connection closed. Will reconnect...");
            wsConnected = false;
            digitalWrite(STATUS_LED_PIN, LOW);
            
            // Safety: tutup gerbang jika koneksi terputus tiba-tiba
            if (gateOpen) {
                esp_timer_stop(gateTimer);
                gateServo.write(ANGLE_CLOSED);
                digitalWrite(LED_PIN, LOW);
                digitalWrite(BUZZER_PIN, LOW);
                gateOpen = false;
                Serial.println("[SAFETY] Gate closed on WS disconnect.");
            }
            break;
            
        case WebsocketsEvent::GotPing:
            wsClient.pong();
            break;
            
        default:
            break;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// WIFI
// ─────────────────────────────────────────────────────────────────────────────
bool connectWiFi() {
    Serial.printf("[WiFi] Connecting to %s ...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_TIMEOUT_MS) {
            Serial.println("[WiFi] Timeout.");
            return false;
        }
        delay(250);
        Serial.print(".");
    }

    Serial.printf("\n[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
}

bool connectWebSocket() {
    Serial.printf("[WS] Connecting to %s\n", WS_URL);
    wsClient.onMessage(onMessage);
    wsClient.onEvent(onEvent);
    // wsClient.setHandshakeTimeout(5);
    
    if (!wsClient.connect(WS_URL)) {
        Serial.println("[WS] Connection failed.");
        return false;
    }
    return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("\n\n=== ITB Jatinangor Parking Gate Controller ===");

    // ── Periferal Output Init ──
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(LED_PIN, OUTPUT);
    pinMode(STATUS_LED_PIN, OUTPUT);
    
    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(LED_PIN, LOW);
    digitalWrite(STATUS_LED_PIN, LOW);

    // Konfigurasi Timer PWM untuk Servo (Penting untuk ESP32)
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    gateServo.setPeriodHertz(50); // Servo standar 50Hz
    gateServo.attach(SERVO_PIN, 500, 2400); 
    gateServo.write(ANGLE_CLOSED); // Pastikan gerbang tertutup saat boot

    // ── Hardware Timer Init ──
    esp_timer_create_args_t timerArgs = {};
    timerArgs.callback        = &gateAutoClose;
    timerArgs.name            = "gate_timer";
    timerArgs.dispatch_method = ESP_TIMER_TASK; // Sangat penting agar aman memanipulasi PWM/Servo
    esp_timer_create(&timerArgs, &gateTimer);

    // ── WiFi & WebSocket ──
    while (!connectWiFi()) {
        Serial.println("[WiFi] Retrying in 5s...");
        delay(5000);
    }
    snprintf(WS_URL, sizeof(WS_URL),
        "ws://%s:8000/ws/esp32/%s?device_key=%s",
        SERVER_IP, GATE_ID, DEVICE_KEY);
    connectWebSocket();
}

// ─────────────────────────────────────────────────────────────────────────────
// LOOP
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        wsConnected = false;
        Serial.println("[WiFi] Lost connection. Reconnecting...");
        connectWiFi();
        return;
    }

    if (!wsConnected) {
        uint32_t now = millis();
        if (now - lastConnectAttempt >= reconnectDelay) {
            lastConnectAttempt = now;
            if (!connectWebSocket()) {
                reconnectDelay = min(reconnectDelay * 2, RECONNECT_MAX_MS);
                Serial.printf("[WS] Retry in %u ms.\n", reconnectDelay);
            }
        }
        return;
    }

    wsClient.poll();

    uint32_t now = millis();
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeat = now;
        wsClient.send("ping");
    }

    // LED Built-in berkedip cepat jika gerbang sedang terbuka
    if (gateOpen) {
        if ((now / 100) % 2 == 0) {
            digitalWrite(STATUS_LED_PIN, HIGH);
        } else {
            digitalWrite(STATUS_LED_PIN, LOW);
        }
    }
}