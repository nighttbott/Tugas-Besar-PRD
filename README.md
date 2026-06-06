# 🚗 ITB Jatinangor — Smart Parking ANPR

Sistem parkir otomatis berbasis ANPR (Automatic Number Plate Recognition) terintegrasi dengan ESP32 (Smart Device via WiFiManager), backend FastAPI (Microservices), database PostgreSQL, dan dashboard Next.js (React Query). Seluruh infrastruktur dide-deploy menggunakan Docker.

---

## Arsitektur Sistem

```
[Kamera Web / HP]
       │
   (YOLOv8 + OCR)
    ANPR Python
       │ (HTTP REST API)
       ▼
 ┌───────────┐     (MQTT Pub/Sub)     ┌───────────────┐
 │ FastAPI   │ ◄────────────────────► │ Eclipse MQTT  │
 │ Backend   │                        │ Broker        │
 └─┬───────┬─┘                        └───────┬───────┘
   │       │                                  │
   ▼       ▼                                  ▼
[Redis] [Postgres]                     [ESP32 Smart Gate]
 Cache   Database                         Motor Servo
```

---

## Prasyarat

- **Docker Desktop** (Windows/Mac) atau **Docker Engine** (Linux)
- **Python 3.10+** (Hanya untuk menjalankan Kamera ANPR Edge di laptop/PC)
- **Arduino IDE** (Hanya untuk flash awal ke ESP32)
- Jaringan Wi-Fi/Mobile Hotspot (untuk menyambungkan laptop dan ESP32)

---

## Struktur Project

```
├── anpr/             # ANPR edge script (kamera masuk/keluar)
├── backend/          # FastAPI backend (API & MQTT Manager)
├── frontend/         # Next.js dashboard + admin (React Query)
├── firmware/         # Kode C++ (Arduino) untuk ESP32 dengan Captive Portal
├── mosquitto/        # Konfigurasi MQTT Broker
├── docker-compose.yml# Orkestrasi Docker (DB, Redis, MQTT, Web, API)
├── start_otomatis.bat# Script 1-klik untuk Windows
└── README.md
```

---

## Setup & Deployment

Sistem ini didesain agar sangat mudah dijalankan menggunakan **Docker Compose** dan **Skrip Otomatisasi (Windows)**.

### 1. Buat Kunci Keamanan (Hanya Sekali)
Buka terminal dan buat 2 buah kunci rahasia (64 karakter hex):
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Salin hasilnya dan tempelkan ke dalam file:
- `backend/.env` (Variabel `JWT_SECRET_KEY` dan `ANPR_KEY`)
- `anpr/.env` (Variabel `ANPR_KEY`)

### 2. Jalankan Sistem (Metode Otomatis - Windows)
Cukup klik ganda (2x) file `start_otomatis.bat` di root proyek.
Skrip ini akan:
1. Melacak IP Wi-Fi/Hotspot Anda secara otomatis.
2. Memperbarui `anpr/.env` agar mengarah ke IP Anda.
3. Menyalakan seluruh *container* Docker (`docker compose up -d`).
4. Menjalankan skrip kamera (ANPR) Python.

### 3. Flash ESP32 (Metode Captive Portal)
1. Buka `firmware/esp32_gate/esp32_mqtt_gate.ino` di Arduino IDE.
2. *Upload* ke ESP32 menggunakan kabel USB (pastikan Anda telah menginstal library `PubSubClient`, `ArduinoJson`, `ESP32Servo`, dan `WiFiManager`).
3. Setelah sukses, cabut kabel USB dan berikan daya melalui Powerbank/Adaptor.
4. Buka Wi-Fi HP Anda, cari hotspot bernama **Gerbang_ITB_Setup**.
5. Sambungkan dan layar konfigurasi akan muncul. Masukkan Wi-Fi kampus/Hotspot Anda beserta **IP Laptop Docker Anda** di kolom MQTT Server.
6. Tekan Save. ESP32 siap digunakan tanpa perlu dicolok ke laptop lagi!

---

## Akses Aplikasi
- **Dashboard Mahasiswa:** `http://localhost:3000`
- **Dashboard Admin:** `http://localhost:3000/admin`
  - Akun Default: `admin` / `parkir2024`
- **API Docs (Swagger):** `http://localhost:8000/docs`

---

## Fitur Utama
1. **Frictionless Entry:** Kendaraan terdaftar otomatis masuk. Kendaraan tidak dikenal dicatat sebagai tamu dan perlu izin keluar.
2. **Auto-Debit:** Integrasi dengan E-Wallet. Biaya otomatis terpotong saat mobil terdeteksi keluar.
3. **Smart Hardware:** ESP32 dilindungi oleh MQTT Last Will and Testament (LWT). Jika kabel ESP32 dicabut, status gerbang di web otomatis berubah menjadi **Offline** secara *real-time*.
4. **Anti-Spam:** Perlindungan "Double Trigger" menggunakan sistem Atomic Cooldown dari Redis.
5. **Real-time Feed:** Mahasiswa dapat memantau notifikasi gerbang langsung dari dashboard mereka. Admin dapat memantau seluruh lalu lintas kampus.
