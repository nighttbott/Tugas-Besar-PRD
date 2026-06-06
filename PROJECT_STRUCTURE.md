# ANPR Parking Gate System — ITB Jatinangor
## Project Structure (Docker + PostgreSQL + MQTT)

Berikut adalah struktur direktori dari sistem SiParkir beserta penjelasan fungsi utama dari setiap file dan folder.

```
anpr-parking/
│
├── .gitignore                               # Daftar file/folder yang tidak diunggah ke Git (seperti .env, node_modules, data database lokal).
├── PROJECT_STRUCTURE.md                     # File ini: Menjelaskan peta dan fungsi setiap komponen dalam proyek.
├── README.md                                # Panduan utama untuk instalasi, deployment, dan cara menjalankan proyek.
├── docker-compose.yml                       # File orkestrasi Docker yang merangkai 5 layanan (Database, Redis, MQTT, Backend API, Web Frontend).
├── start_otomatis.bat                       # Skrip otomatisasi Windows (1-klik) untuk mencari IP laptop, mengatur .env, dan menyalakan seluruh sistem.
│
├── backend/                                 # 🧠 SERVER API (Python FastAPI)
│   ├── main.py                              # Titik masuk utama aplikasi FastAPI. Mengatur CORS, siklus hidup server, dan mendaftarkan semua rute.
│   ├── requirements.txt                     # Daftar pustaka Python yang dibutuhkan (fastapi, asyncpg, sqlalchemy, aiomqtt, dll).
│   ├── Dockerfile                           # Skrip konfigurasi untuk membangun wadah (container) Docker backend berbasis Linux yang ringan.
│   ├── .env.example                         # Contoh format file rahasia (.env) untuk kunci keamanan dan URL database.
│   │
│   ├── core/                                # Komponen Inti Server
│   │   ├── config.py                        # Pengaturan aplikasi terpusat (Pydantic-settings) mengambil nilai dari .env.
│   │   ├── security.py                      # Sistem keamanan: enkripsi/dekripsi JWT untuk user dan validasi X-ANPR-KEY untuk kamera.
│   │   ├── database_sql.py                  # Konfigurasi ORM SQLAlchemy dan mesin asinkron (asyncpg) untuk terhubung ke PostgreSQL.
│   │   ├── database.py                      # Konfigurasi in-memory Redis: mengatur sesi parkir aktif dan Atomic Cooldown untuk mencegah spam gerbang.
│   │   └── mqtt_manager.py                  # Manajer MQTT asinkron: Menerbitkan perintah buka gerbang ke ESP32 dan mendengarkan status Online/Offline (LWT) dari ESP32.
│   │
│   ├── models/                              # Struktur Data (Database & API)
│   │   ├── domain.py                        # Skema tabel database PostgreSQL (Tabel Vehicle, EWallet, History).
│   │   └── gate.py                          # Skema validasi Pydantic untuk input/output API khusus rute gerbang.
│   │
│   ├── routers/                             # Pengelompokan Rute API (Endpoints)
│   │   ├── gate.py                          # Rute yang diakses oleh kamera ANPR (trigger), publik (status gerbang), dan WebSockets (Live Feed ke dasbor).
│   │   ├── vehicles.py                      # Rute untuk mahasiswa mendaftarkan kendaraan, mengelola E-Wallet, dan melihat riwayat parkirnya.
│   │   └── admin.py                         # Rute eksklusif petugas untuk memverifikasi STNK, melihat semua data, dan memindahkan kepemilikan kendaraan.
│   │
│   └── services/                            # Logika Bisnis (Aturan Sistem)
│       ├── gate_service.py                  # Logika utama saat kendaraan tiba:
│       │                                    #   1. Mengecek akurasi AI ≥ 75%.
│       │                                    #   2. Mencegah pemindaian beruntun (Cooldown 10 detik).
│       │                                    #   3. Mengecek status terdaftar di PostgreSQL dan persetujuan satpam.
│       │                                    #   4. (Masuk) Membuat sesi, (Keluar) Memotong saldo GoPay dan memindahkan ke histori.
│       └── ws_manager.py                    # Manajer WebSockets yang bertugas menyiarkan kejadian gerbang secara real-time ke layar web pengguna yang tepat.
│
├── frontend/                                # 💻 ANTARMUKA WEB (Next.js 14 & React Query)
│   ├── package.json                         # Daftar pustaka Node.js yang dibutuhkan.
│   ├── next.config.mjs                      # Konfigurasi Next.js (mengaktifkan mode standalone untuk kompilasi Docker).
│   ├── Dockerfile                           # Skrip konfigurasi multi-stage untuk membangun gambar Docker website produksi yang sangat kecil.
│   │
│   ├── app/                                 # Halaman Web Utama
│   │   ├── globals.css                      # Pusat seluruh desain tampilan. Menampung grid Bootstrap dan class utama `.site-container`.
│   │   ├── layout.tsx                       # Kerangka HTML utama yang membungkus semua halaman web.
│   │   ├── providers.tsx                    # Mengaktifkan TanStack (React) Query untuk cache data.
│   │   ├── parkir/                          # Halaman Dashboard Mahasiswa (http://localhost:3000/).
│   │   └── admin/                           # Halaman Panel Petugas Keamanan (http://localhost:3000/admin).
│   │
│   ├── components/                          # Potongan Antarmuka (Reusable Components)
│   │   └── parking/                         
│   │       ├── HistoryTable.tsx             # Tabel riwayat keluar/masuk kendaraan, termasuk metode pembayaran dan akurasi OCR.
│   │       ├── ParkingStatus.tsx            # Menampilkan kendaraan yang sedang di dalam dan status MQTT gerbang.
│   │       ├── VehicleCard.tsx              # Kotak informasi kendaraan milik mahasiswa beserta opsi tambah E-Wallet.
│   │       └── TabMenu.tsx                  # Navigasi tab (Kendaraan, Status, Riwayat, Tarif).
│   │
│   ├── hooks/                               # Pengambil Data Otomatis (Custom Hooks)
│   │   ├── useParkingSessions.ts            # Meminta data kendaraan di dalam parkiran setiap 30 detik.
│   │   ├── useParkingHistory.ts             # Meminta data riwayat parkir setiap 60 detik.
│   │   ├── useVehicles.ts                   # Meminta daftar kendaraan pengguna.
│   │   ├── useAddVehicle.ts                 # Mengirim data kendaraan baru dan mereset cache agar web langsung ter-update.
│   │   └── useGateEvents.ts                 # Menyadap jalur WebSockets untuk memunculkan notifikasi Live Feed.
│   │
│   └── lib/api.ts                           # Kumpulan fungsi fetch (pemanggil API) dan penyimpanan token JWT di browser.
│
├── anpr/                                    # 📷 KECERDASAN BUATAN (Python Edge Script)
│   ├── anpr_main.py                         # Skrip yang berjalan di laptop. Menggunakan YOLOv8 untuk mencari plat, OCR untuk membaca teks, lalu mengirimnya ke Backend.
│   ├── requirements.txt                     # Kebutuhan library AI (ultralytics, opencv, dll).
│   └── .env                                 # File rahasia yang memuat IP Server dan ANPR_KEY. (Otomatis diisi oleh skrip start_otomatis.bat).
│
├── firmware/                                # 🛠 PERANGKAT KERAS IOT (C++ Arduino)
│   └── esp32_gate/
│       └── esp32_mqtt_gate.ino              # Kode yang ditanam (flash) ke chip ESP32. 
│                                            # Memiliki fitur Smart Device (Captive Portal), koneksi MQTT, dan algoritma penggerak Motor Servo yang presisi.
│
└── mosquitto/                               # 📬 SERVER PESAN (MQTT Broker)
    └── config/
        └── mosquitto.conf                   # Mengatur agar mosquitto menerima koneksi di port 1883 tanpa hambatan (khusus pengembangan lokal).
```

---

## Token & Security Architecture

Sistem ini memusatkan keamanan pada sisi Backend (Server) untuk mencegah peretasan melalui jaringan Wi-Fi lokal.

### 1. Kunci Sesi Web (JWT_SECRET_KEY)
Berfungsi sebagai stempel digital. Digunakan oleh FastAPI untuk men-*generate* tiket *login* bagi Mahasiswa dan Admin.
- **Lokasi:** `backend/.env`
- Frontend akan otomatis menerima JWT (JSON Web Token) saat pengguna berhasil *login* dan menyimpannya di memori browser.

### 2. Kunci Keamanan Kamera (ANPR_KEY)
Berfungsi layaknya kata sandi mesin. Mencegah orang asing menembak API pembuka gerbang dari laptop mereka sendiri.
- **Lokasi:** `backend/.env` **dan** `anpr/.env` (Kedua file ini harus memiliki kunci yang sama persis).
- Dikirim secara tersembunyi oleh skrip kamera ANPR melalui header HTTP `X-ANPR-KEY`.

### 3. Keamanan Alat IoT & Pelacakan Status Wasiat (MQTT LWT)
Alat fisik ESP32 **TIDAK** menggunakan token JWT agar proses mikrokontroler tetap ringan. Status alat ini dijaga oleh protokol MQTT.
- Saat menyala, ESP32 berteriak `"online"` ke Broker Mosquitto (Topik: `gate/{gate_id}/status`).
- ESP32 juga mendaftarkan surat wasiat atau *Last Will and Testament (LWT)* berisikan `"offline"`.
- Jika ESP32 mati lampu, dicabut, atau jaringan putusnya, Broker Mosquitto akan mewujudkan wasiat tersebut dengan otomatis menyiarkan pesan `"offline"`. Ini memungkinkan Backend dan Website langsung tahu status *real-time*-nya.

---

## E-Wallet & Autodebit Flow

Alur transaksi yang serba otomatis (Frictionless Payment):
1. Kendaraan terdeteksi oleh kamera di gerbang keluar (`exit`).
2. Server mencari tiket masuk kendaraan tersebut di penyimpanan memori berkecepatan tinggi (Redis).
3. Server menghitung durasi parkir ke dalam bentuk Jam.
4. Server memeriksa daftar E-Wallet (GoPay, OVO, dll) yang didaftarkan mahasiswa.
5. Jika Saldo mencukupi, sistem langsung memotong saldo (Autodebit).
6. Informasi dipindahkan ke tabel riwayat (History) di PostgreSQL dengan keterangan metode pembayaran (`paid_provider`).
7. Jika Saldo kurang, gerbang tetap tertutup (ditolak) dan layar petugas akan menunjukkan notifikasi untuk pembayaran tunai secara manual.

---

## CSS Alignment System

Semua letak antarmuka web (Navbar, Breadcrumb, dan Tabel) dikendalikan oleh satu kelas utama yaitu `.site-container` di dalam file `globals.css`. 
Saat ini menggunakan `max-width: 95%` sehingga desain UI (antarmuka) otomatis membentang elegan pada monitor resolusi tinggi (seperti layar komputer di pos keamanan) tanpa menyisakan ruang kosong yang kaku di sisi kiri-kanan.
