# Deployment Guide — Docker & Skrip Otomatisasi (Windows)

Sistem ANPR Parkir kini telah berevolusi menggunakan arsitektur **Docker Compose**, **PostgreSQL**, dan **MQTT**. Dokumen ini memberikan panduan ringkas dan modern untuk melakukan *deployment* atau menjalankan *prototype* di mesin lokal.

---

## 🛠 Prerequisites (Kebutuhan Sistem)

| Tool | Platform | Keterangan |
|------|----------|------------|
| **Docker Desktop** | Windows/Mac | Pastikan WSL2 Engine aktif di pengaturannya. |
| **Python 3.10+** | Windows | Wajib diinstal di *host* (Windows) untuk skrip kamera ANPR. |
| **Arduino IDE 2.x**| Windows/Mac | Untuk melakukan *flash* kode ke board ESP32 pertama kali. |
| **Kabel Jumper** | Fisik | Untuk merakit Servo SG90 ke ESP32 (GND, 5V, Pin 18). |

> **Catatan:** Skrip kamera (ANPR) berjalan di luar Docker (di Windows PowerShell/CMD langsung) agar *library* OpenCV (`cv2`) dapat mendeteksi webcam atau IP Camera secara *real-time* tanpa terhambat jaringan virtualisasi.

---

## 🚀 Langkah 1: Kunci Keamanan & Konfigurasi

Semua kredensial disederhanakan. Anda hanya perlu **2 kunci rahasia utama**.

1. Buka Terminal / CMD di laptop Anda.
2. Buat dua buah kunci acak menggunakan perintah Python berikut:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. Salin (*copy*) dua hasil yang berbeda tersebut.
4. Buka dan isi file **`backend/.env`**:
   ```ini
   # Ganti dengan kunci hex pertama
   JWT_SECRET_KEY="104e13636b13b1f5f9ed... (contoh)"
   
   # Ganti dengan kunci hex kedua
   ANPR_KEY="f192b4512b40cf... (contoh)"
   ```
5. Buka dan isi file **`anpr/.env`**:
   ```ini
   # Ganti dengan kunci hex kedua (Wajib SAMA dengan backend)
   ANPR_KEY="f192b4512b40cf... (contoh)"
   ```

---

## ⚙️ Langkah 2: Skrip 1-Klik (`start_otomatis.bat`)

Untuk menjalankan seluruh arsitektur secara instan tanpa mengetik perintah Docker manual:

1. Klik ganda (2x) file **`start_otomatis.bat`** di *File Explorer* Anda.
2. Akan muncul menu pilihan interaktif di *Command Prompt*:
   ```text
   Pilih Mode Kamera ANPR:
   [1] Gerbang Masuk (Entry - G1)
   [2] Gerbang Keluar (Exit - EXIT1)
   Masukkan pilihan (1/2):
   ```
3. Ketik `1` lalu tekan Enter untuk mode Masuk.
4. Skrip akan secara otomatis:
   - Melacak **IP WiFi/Hotspot** laptop Anda.
   - Mengubah `API_ENDPOINT` di file `anpr/.env` menggunakan IP tersebut.
   - Menjalankan **Docker Compose** di *background*.
   - Membuka virtual environment `.venv` dan menyalakan kamera.

> **Tips Presentasi Multi-Kamera:** Jika ingin mendemokan gerbang masuk dan keluar bersamaan, buat salinan folder `anpr` menjadi `anpr_keluar`. Pada `anpr_keluar/.env`, atur `CAMERA_INDEX` ke IP Webcam HP Anda dan `GATE_DIRECTION=exit`. Jalankan secara bersamaan!

---

## 🔌 Langkah 3: Setup Perangkat IoT (ESP32)

Karena kini kita menggunakan protokol **MQTT** dan fitur **Captive Portal (WiFiManager)**, Anda tidak perlu lagi melakukan *hardcode* nama Wi-Fi dan IP di kodingan C++!

1. Buka file `firmware/esp32_gate/esp32_mqtt_gate.ino` di Arduino IDE.
2. Pastikan Anda telah menginstal pustaka (*library*):
   - `PubSubClient` (oleh Nick O'Leary)
   - `ArduinoJson` (oleh Benoit Blanchon)
   - `ESP32Servo`
   - `WiFiManager` (oleh tzapu)
3. Sambungkan ESP32 dan klik **Upload**.
4. Cabut ESP32 dan colokkan ke **Batok Charger HP** atau **Powerbank**. *(Jangan gunakan USB laptop agar motor servo tidak kekurangan arus/brownout).*
5. Buka Wi-Fi HP Anda, lalu cari hotspot bernama **Gerbang_ITB_Setup**.
6. Sambungkan dan layar pengaturan akan muncul (Captive Portal).
7. Pilih Wi-Fi kampus / Hotspot Anda. Di kotak *MQTT Server IP*, ketikkan **IP Laptop Docker Anda** (IP yang dilacak oleh skrip `.bat` tadi).
8. Klik Save. Selesai!

---

## 📈 Langkah 4: Pengujian Keseluruhan (End-to-End)

1. Buka browser dan akses **`http://localhost:3000`** (Dashboard Mahasiswa).
2. Daftarkan plat nomor baru (contoh: `D 1234 ITB`), jenis kendaraan, dan modelnya.
3. Hubungkan E-Wallet dan isikan saldo (contoh: Rp100.000).
4. Hadapkan plat nomor tersebut ke depan **Kamera ANPR**.
5. Kamera mendeteksi dan mengirim ke Backend.
6. Motor Servo berputar 90 derajat (terbuka).
7. Di layar Web, plat `D 1234 ITB` otomatis muncul di tab **Status Parkir (Sedang Parkir)** berkat fitur React Query *Auto-Polling*.
8. Uji cobakan kamera sebagai Gerbang Keluar (`exit`), saldo e-wallet akan terpotong secara instan di tab **Riwayat & Biaya**.

---

## 🛠️ Docker Cheat Sheet (Pencarian Masalah)

Jika Anda perlu melihat apa yang terjadi di belakang layar, gunakan terminal dan ketik perintah berikut:

- **Melihat Status Layanan:** `docker compose ps`
- **Melihat Pemakaian RAM/CPU:** `docker stats`
- **Melihat Log Server API:** `docker compose logs backend -f`
- **Merestart Cepat Backend:** `docker compose restart backend`
- **Menghapus Semua Data Database (Reset):** `docker compose down -v`
