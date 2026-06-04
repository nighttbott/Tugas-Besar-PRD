# 🚗 ITB Jatinangor — Smart Parking ANPR

Sistem parkir otomatis berbasis ANPR (Automatic Number Plate Recognition) dengan ESP32 gate controller, backend FastAPI, dan dashboard Next.js.

---

## Arsitektur Sistem

```
[HP Kamera Masuk]          [HP Kamera Keluar]
     ANPR Entry                 ANPR Exit
        │                          │
        └──────────┬───────────────┘
                   ▼
            [Backend FastAPI]
            ┌──────────────┐
            │  Auth, Gate  │
            │  Logic, WS   │
            └──────┬───────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
  [ESP32 G1]  [Dashboard]  [Admin Panel]
  Gate Relay   Next.js       Next.js
```

---

## Prasyarat

| Software | Versi |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| Arduino IDE | 2.x |
| IP Webcam (Android) | Play Store |

---

## Struktur Project

```
├── backend/          # FastAPI backend
├── frontend/         # Next.js dashboard + admin
├── anpr/             # ANPR edge script (kamera masuk)
├── firmware/
│   └── esp32_gate/   # Arduino firmware
├── start_all.bat     # Start semua service (Windows)
├── stop_all.bat      # Stop semua service (Windows)
└── README.md
```

---

## Setup

### 1. Clone Repository

```bash
git clone <repo-url>
cd Tugas-Besar-PRD
```

---

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

Buat file `.env`:

```env
DEBUG=True
JWT_SECRET_KEY=dev-secret-key-ganti-di-production
ANPR_KEY=local-anpr-secret
ESP32_DEVICE_KEYS={"G1":"esp32-secret-g1"}
```

Jalankan:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API docs tersedia di `http://localhost:8000/docs` (hanya saat `DEBUG=True`).

---

### 3. Frontend

```bash
cd frontend
npm install
```

Buat file `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_NIM=2021184750
```

Jalankan:

```bash
npm run dev
```

Dashboard: `http://localhost:3000`
Admin panel: `http://localhost:3000/admin`

Admin credentials:
- Username: `admin` / Password: `parkir2024`
- Username: `petugas` / Password: `gerbang123`

---

### 4. ANPR

```bash
cd anpr
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

Buat file `.env` (kamera masuk):

```env
API_ENDPOINT=http://<IP_PC>:8000/api/v1/gate/trigger
ANPR_KEY=local-anpr-secret
GATE_ID=G1
GATE_DIRECTION=entry
CAMERA_INDEX=http://<IP_HP_MASUK>:8080/video
```

Buat file `.env.exit` (kamera keluar):

```env
API_ENDPOINT=http://<IP_PC>:8000/api/v1/gate/trigger
ANPR_KEY=local-anpr-secret
GATE_ID=G1
GATE_DIRECTION=exit
CAMERA_INDEX=http://<IP_HP_KELUAR>:8080/video
```

Ganti `<IP_PC>` dengan IP komputer (cek via `ipconfig`).
Ganti `<IP_HP_*>` dengan IP HP yang menjalankan IP Webcam.

**Setup HP sebagai kamera:**
1. Install **IP Webcam** (Pas Robotics) dari Play Store
2. Buka app → tap **Start server**
3. Catat IP yang muncul (contoh: `192.168.0.105:8080`)
4. Test di browser PC: `http://192.168.0.105:8080/video`

Jalankan ANPR:

```bash
# Kamera masuk
python anpr_main.py

# Kamera keluar (terminal baru)
for /f "tokens=1,2 delims== eol=#" %a in (.env.exit) do set "%a=%b"
python anpr_main.py
```

---

### 5. ESP32

Edit file `firmware/esp32_gate/esp32_gate_config.h`:

```cpp
static const char* WIFI_SSID     = "NAMA_WIFI";
static const char* WIFI_PASSWORD = "PASSWORD_WIFI";
static const char* SERVER_IP     = "<IP_PC>";  // IP komputer backend
static const char* GATE_ID       = "G1";
static const char* DEVICE_KEY    = "esp32-secret-g1";
```

Flash via Arduino IDE:
1. Buka `firmware/esp32_gate/esp32_gate.ino`
2. Pilih board: **ESP32 Dev Module**
3. Klik **Upload**

ESP32 akan auto-connect ke backend setiap kali dinyalakan.

---

## Menjalankan Semua Service Sekaligus (Windows)

Edit `start_all.bat` — sesuaikan IP ANPR exit:

```bat
set CAMERA_INDEX=http://<IP_HP_KELUAR>:8080/video
```

Lalu double-click `start_all.bat` → 4 terminal terbuka otomatis.

Untuk menghentikan semua service: double-click `stop_all.bat`.

---

## Alur Sistem

### Kendaraan Masuk
1. Kamera ANPR entry deteksi plat
2. Backend cek apakah plat terdaftar
   - **Terdaftar** → gate buka, session dicatat atas nama user
   - **Tidak terdaftar** → gate tetap buka, session dicatat sebagai **Tamu**
   - **Diblokir** → gate tidak buka

### Kendaraan Keluar
1. Kamera ANPR exit deteksi plat
2. Backend cek session aktif
   - **Terdaftar + ada session** → gate buka, billing otomatis via e-wallet
   - **Tamu + sudah diizinkan admin** → gate buka
   - **Tamu + belum diizinkan** → gate tidak buka, admin harus approve dulu
   - **Tidak ada session** → gate tidak buka

### Admin Panel
- Login di `http://localhost:3000/admin`
- Lihat semua kendaraan terdaftar
- Lihat session aktif (terdaftar + tamu)
- Klik **Izinkan Keluar** untuk kendaraan tamu → pilih metode pembayaran (Cash/QRIS/Tap e-Money)
- Ubah plat nomor kendaraan

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Keterangan |
|---|---|---|
| `DEBUG` | `False` | Aktifkan dev-login & docs |
| `JWT_SECRET_KEY` | – | Secret key JWT (wajib diganti) |
| `ANPR_KEY` | `local-anpr-secret` | Shared secret ANPR |
| `ESP32_DEVICE_KEYS` | `{"G1":"esp32-secret-g1"}` | Device key per gate |
| `REDIS_URL` | `redis://localhost:6379/0` | Opsional, fallback ke memory |

### Frontend (`frontend/.env.local`)

| Variable | Keterangan |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL backend (default: `http://localhost:8000`) |
| `NEXT_PUBLIC_WS_URL` | WebSocket backend (default: `ws://localhost:8000`) |
| `NEXT_PUBLIC_NIM` | NIM user default |

### ANPR (`anpr/.env`)

| Variable | Keterangan |
|---|---|
| `API_ENDPOINT` | URL trigger backend |
| `ANPR_KEY` | Harus sama dengan backend |
| `GATE_ID` | ID gate (contoh: `G1`) |
| `GATE_DIRECTION` | `entry` atau `exit` |
| `CAMERA_INDEX` | Index kamera (`0`) atau URL IP Webcam |

---

## Auth Flow

| Client | Metode | Keterangan |
|---|---|---|
| Frontend | Auto dev-login (`DEBUG=True`) | Token JWT otomatis saat load |
| ANPR | Header `X-ANPR-KEY` | Shared secret, tidak ada JWT |
| ESP32 | Query param `?device_key=` | Static key per gate |
| Admin | Username + password → JWT | Login via `/admin` |

---

## Troubleshooting

**Backend 500 error saat sessions:**
Redis tidak jalan — sistem otomatis fallback ke in-memory. Restart backend.

**ESP32 tidak connect:**
- Pastikan `SERVER_IP` di `esp32_gate_config.h` adalah IP PC yang benar
- Pastikan PC dan ESP32 satu jaringan WiFi
- Cek firewall Windows — izinkan port 8000

**ANPR tidak deteksi plat:**
- Pastikan pencahayaan cukup
- Cek URL IP Webcam bisa diakses di browser PC
- Confidence threshold: 75% (ubah di `gate_service.py`)

**Frontend 401 Unauthorized:**
- Pastikan `DEBUG=True` di `backend/.env`
- Restart backend setelah edit `.env`

---

## Confidence Threshold

ANPR menggunakan dua confidence score:
- **YOLO** (deteksi kotak plat): minimum 25%
- **OCR** (akurasi teks): minimum **80%** — ubah di `backend/services/gate_service.py`

```python
CONFIDENCE_THRESHOLD = 0.75
```
