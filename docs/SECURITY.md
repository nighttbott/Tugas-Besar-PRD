# Security Architecture — Smart Parking ANPR

Sistem keamanan pada arsitektur SiParkir telah diperbarui untuk mendukung lingkungan *Production-Ready* berbasis **Docker, PostgreSQL, dan MQTT Protocol**.

## Threat Model & Mitigasi

| Ancaman (Threat) | Teknik Mitigasi |
|------------------|-----------------|
| **Network Replay Attack (LAN)** | Penggunaan `Redis Cooldown` yang bersifat *Atomic* (`SETNX`). Backend akan memblokir tembakan API ganda yang dikirim dalam jendela waktu 10 detik, melindungi motor servo dari kerusakan akibat spam. |
| **SQL Injection & XSS** | Seluruh data yang masuk ke Backend melalui validasi ketat Pydantic dan diproses menggunakan ORM `SQLAlchemy 2.0` yang melakukan *parameterized queries* ke PostgreSQL secara otomatis. |
| **Fake ANPR Triggering** | Rute `/api/v1/gate/trigger` tidak dapat diakses publik. Setiap permintaan wajib menyertakan *header* `X-ANPR-KEY` yang berisi token hex 64-karakter yang hanya diketahui oleh mesin Edge Camera dan Server. |
| **Data Loss & Corruption** | Migrasi dari *flat-file* (JSON) ke **PostgreSQL**. Semua perubahan saldo e-wallet dan catatan histori parkir disimpan menggunakan transaksi ACID. Jika server mati di tengah proses, `db.rollback()` memastikan data tidak korup. |
| **Unresponsive Hardware (Offline)** | Diimplementasikannya **MQTT Last Will and Testament (LWT)**. Jika ESP32 mati lampu, dicabut, atau kehilangan Wi-Fi, Broker MQTT akan langsung menyiarkan status "offline" ke seluruh sistem tanpa perlu campur tangan manual. |

---

## Token & Kredensial

Sistem ini menggunakan dua jenis kunci rahasia utama yang didefinisikan dalam *environment variables* (Tidak boleh di-*commit* ke repositori Git).

### 1. `JWT_SECRET_KEY` (Web Dashboard Auth)
Digunakan oleh aplikasi untuk menerbitkan JSON Web Token (JWT).
- **Penggunaan:** Mahasiswa (*dashboard_user*) dan Petugas (*parking_admin*).
- **Algoritma:** HS256.
- **TTL (Time to Live):** Otomatis kadaluarsa dalam 8 jam.

### 2. `ANPR_KEY` (Edge-to-Server Auth)
Kunci statis berbasis *Shared-Secret* untuk komunikasi mesin-ke-mesin.
- Ditaruh di `backend/.env` dan `anpr/.env`.
- Dikirimkan pada *Header* HTTP: `X-ANPR-KEY: <token>`.

---

## Keamanan Data Sensitif

Semua data sensitif disimpan dalam struktur yang terisolasi:
1.  **Kredensial Docker:** File `.env` untuk *backend*, *frontend*, dan *anpr* secara eksplisit dikecualikan dari Git menggunakan `.gitignore`.
2.  **Volume Persisten:** Penyimpanan data fisik untuk PostgreSQL (`pgdata`) dan Redis (`redisdata`) tidak diekspos keluar dari *container* kecuali melalui jembatan *port* lokal yang dikelola oleh *Docker Daemon*.
3.  **Captive Portal ESP32:** Kata sandi Wi-Fi dan IP Server tidak di-*hardcode* ke dalam *source code* C++, melainkan disimpan di memori *flash* perangkat secara aman menggunakan pustaka `WiFiManager`.

---

## E-Wallet Autodebit Security (Transaksi)

Sistem pembayaran dirancang agar tidak ada saldo "menggantung":
1. Perhitungan durasi parkir dikonversi menjadi jam melalui logika `datetime.timezone.utc` absolut, terhindar dari *bug* manipulasi jam lokal perangkat.
2. Pengurangan saldo (*deduction*) dieksekusi secara sinkron di *Backend* dan di- *commit* ke PostgreSQL (`db.commit()`) di dalam sebuah transaksi. Jika terjadi *Error 500*, SQLAlchemy secara otomatis melakukan pembatalan (`rollback`), sehingga saldo mahasiswa tidak akan terpotong secara sia-sia.
