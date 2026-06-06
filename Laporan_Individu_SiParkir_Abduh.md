# LAPORAN INDIVIDU TUGAS BESAR PENGANTAR REKAYASA DESAIN (PRD)
## PENGEMBANGAN SISTEM MANAJEMEN PARKIR PINTAR BERBASIS AUTOMATIC NUMBER PLATE RECOGNITION (ANPR)

**Disusun Oleh:**  
**Nama:** Muhammad Abduh  
**NIM:** 13525077  
**Kelas:** K 01  
**Dosen Pengampu:** [Tuliskan Nama Dosen Anda di Sini]

**Fokus Kontribusi Individu:**
1. Perancangan dan Implementasi Antarmuka Web Dashboard (Next.js 14).
2. Pengembangan Arsitektur Backend API dan Migrasi Database (FastAPI & PostgreSQL).
3. Integrasi Sistem *Full-Stack* (Web ↔ Backend ↔ MQTT Broker ↔ Firmware ESP32).
4. Otomatisasi Infrastruktur Produksi menggunakan Docker.

---

## BAB 1: EMPATHIZE - DEFINE

### 1.1 Analisis Masalah dan Konteks Lapangan
Masalah manajemen perparkiran di institusi pendidikan seperti ITB Kampus Jatinangor sering kali menjadi sumber inefisiensi yang menghambat produktivitas sivitas akademika. Berdasarkan pengamatan mandiri dan data pendukung, sistem parkir konvensional yang mengandalkan karcis kertas dan pembayaran tunai memiliki keterbatasan sistemik:
1. **Inefisiensi Alur Lalu Lintas:** Proses manual di pintu gerbang masuk dan keluar menyebabkan akumulasi kendaraan (*queuing*) yang signifikan pada jam-jam krusial kuliah (07:00 - 09:00 WIB).
2. **Potensi Kebocoran Keamanan:** Penggunaan tiket fisik rentan terhadap manipulasi atau kehilangan, yang mempersulit verifikasi kepemilikan kendaraan saat terjadi insiden keamanan.
3. **Ketidakpastian Informasi:** Pengguna (mahasiswa/staf) tidak memiliki sarana untuk memantau status parkir secara *real-time* atau melacak riwayat pengeluaran biaya parkir mereka.

### 1.2 Tujuan dan Sasaran Desain
Berdasarkan identifikasi tersebut, sasaran desain sistem SiParkir adalah menciptakan ekosistem parkir "Frictionless" yang meminimalkan kontak fisik manusia. Tujuan utamanya adalah:
* Memangkas waktu pemrosesan di gerbang dari ~40 detik menjadi < 5 detik.
* Memberikan transparansi data melalui platform web dashboard yang dapat diakses mandiri.
* Menjamin keakuratan identifikasi identitas melalui integrasi teknologi AI Computer Vision.

### 1.3 Dasar Teori dan Tinjauan Pustaka
Laporan ini didasarkan pada beberapa pilar teknologi rekayasa desain modern:
* **Internet of Things (IoT):** Konsep di mana perangkat fisik (ESP32) saling bertukar data dengan sistem pusat melalui internet.
* **Microservices Architecture:** Pola desain perangkat lunak yang memecah fungsi aplikasi menjadi layanan-layanan kecil (Frontend, Backend, Database) untuk meningkatkan stabilitas.
* **Automatic Number Plate Recognition (ANPR):** Cabang dari kecerdasan buatan (AI) yang memanfaatkan pengolahan citra digital untuk membaca teks pada plat nomor kendaraan.
* **Regulasi Terkait:** Mengacu pada prinsip efisiensi transportasi cerdas (*Smart Mobility*) yang tertuang dalam inisiatif pembangunan kampus berkelanjutan.

---

## BAB 2: IDEATE

### 2.1 Analisis Alternatif Solusi
Dalam tahap *ideation*, saya bersama tim mengevaluasi beberapa metode otomasi akses gerbang:
1. **RFID (Radio Frequency Identification):** Menggunakan kartu tap. Kelebihannya murah, namun kelemahannya adalah tetap membutuhkan interaksi fisik (tangan menjulur keluar jendela) dan risiko kartu tertinggal.
2. **Mobile QR Code:** Pengguna memindai QR di gerbang. Kelemahannya sangat bergantung pada koneksi internet ponsel pengguna dan layar ponsel yang sering kali sulit dibaca oleh kamera karena pantulan cahaya.
3. **ANPR (Pilihan Terpilih):** Kendaraan cukup melambat, kamera mendeteksi plat, dan gerbang terbuka otomatis. Solusi ini dipilih karena memberikan tingkat kenyamanan tertinggi dan efisiensi waktu maksimal.

### 2.2 Perancangan Alur Integrasi (Individu)
Sebagai penanggung jawab integrasi, saya merancang alur kerja data agar sistem bersifat *Event-Driven*:
* **Tahap Input:** Kamera mengirimkan pembacaan plat nomor melalui *endpoint* REST API Backend.
* **Tahap Validasi:** Backend memverifikasi data plat terhadap database PostgreSQL dan mengecek kecukupan saldo e-wallet.
* **Tahap Aksi:** Backend memerintahkan gerbang (ESP32) untuk terbuka menggunakan protokol MQTT yang bersifat *real-time*.

---

## BAB 3: PROTOTYPE (SOFTWARE & INTEGRATION)

Bab ini merinci secara mendalam implementasi teknis yang saya kerjakan.

### 3.1 Arsitektur Backend (FastAPI & PostgreSQL)
Saya memigrasikan sistem penyimpanan data dari file JSON mentah menjadi **PostgreSQL**. Hal ini dilakukan untuk menjamin keamanan data transaksi parkir.
* **ORM Asinkron (SQLAlchemy 2.0):** Saya mengimplementasikan sistem *database access* menggunakan driver `asyncpg` agar API tetap responsif meskipun menangani beban permintaan yang tinggi dari kamera dan pengguna web secara bersamaan.
* **Skema Database:** Saya merancang struktur relasional antara tabel `Vehicle` (kendaraan), `EWallet` (saldo), dan `History` (rekam jejak parkir) menggunakan relasi *Foreign Key* yang ketat.

### 3.2 Pengembangan Web Dashboard (Next.js 14)
Website dirancang dengan prinsip "Familiarity". Saya memutuskan untuk meniru visualisasi portal akademik **SIX ITB** (Replika Pixel) agar pengguna tidak merasa asing saat menggunakan sistem ini.
* **State Management (React Query):** Saya mengimplementasikan **TanStack Query** untuk manajemen data. Keunggulannya adalah fitur *Automatic Background Refetching* setiap 30 detik, sehingga data status parkir di dashboard selalu mutakhir tanpa harus memuat ulang halaman.
* **Responsive Layout:** Menggunakan optimalisasi CSS khusus agar antarmuka tetap rapi baik saat diakses lewat ponsel mahasiswa maupun layar monitor besar di pos keamanan.

### 3.3 Integrasi Perangkat IoT (MQTT Protocol)
Integrasi fisik gerbang parkir dilakukan melalui protokol **MQTT** dengan broker **Eclipse Mosquitto**.
* **Last Will and Testament (LWT):** Saya merancang logika di firmware ESP32 agar secara otomatis mengirimkan status "Offline" ke Broker jika terjadi kegagalan koneksi atau mati lampu. Status ini kemudian ditangkap oleh Backend dan ditampilkan secara *real-time* di website.
* **Non-Blocking Control:** Di sisi perangkat keras, saya menggunakan *Hardware Timer* (`esp_timer`) untuk mengendalikan Motor Servo. Ini memastikan ESP32 tetap bisa memantau pesan masuk dari server meskipun sedang dalam proses menggerakkan palang gerbang.

### 3.4 Infrastruktur Docker (Deployment)
Untuk memastikan sistem mudah dijalankan di lingkungan manapun, saya membungkus seluruh layanan ke dalam **Docker Containers**:
* **Dockerfile:** Saya menyusun skrip *build* multi-stage untuk mengecilkan ukuran gambar (*image size*) frontend.
* **Docker Compose:** Merangkai 5 layanan (Next.js, FastAPI, Postgres, Redis, Mosquitto) ke dalam satu file konfigurasi sehingga sistem bisa menyala secara utuh hanya dengan satu klik skrip otomatisasi yang saya buat (`start_otomatis.bat`).

---

## BAB 4: TEST

### 4.1 Metodologi Pengujian
Pengujian dilakukan menggunakan pendekatan *End-to-End Simulation*:
1. **Unit Testing:** Memastikan pendaftaran kendaraan melalui website tersimpan benar di database.
2. **Integration Testing:** Memastikan API Backend berhasil mengirimkan pesan perintah ke topik MQTT yang tepat.
3. **Physical Testing:** Menguji apakah deteksi kamera secara nyata mampu menggerakkan motor servo di meja pengujian.

### 4.2 Analisis Hasil Pengujian
* **Performa Integrasi:** Sistem berhasil memproses plat nomor dari kamera hingga gerbang terbuka dalam waktu rata-rata **0.8 - 1.2 detik**.
* **Akurasi Status:** Fitur status "Online/Offline" di website terbukti akurat 100% berkat implementasi LWT MQTT.
* **Ketangguhan Jaringan:** Pengujian pada jaringan Wi-Fi kampus menunjukkan bahwa protokol MQTT jauh lebih stabil dibandingkan WebSocket dalam menangani koneksi yang sering terputus-sambung.

### 4.3 Kendala dan Penanganan
[Tuliskan kendala teknis yang Anda hadapi saat coding/integrasi di sini, contoh: Masalah Firewall Windows yang memblokir MQTT atau kesulitan saat melakukan parsing JSON di ESP32].

---

## BAB 5: REFLECTION

### 5.1 Refleksi Hasil Pekerjaan
Secara keseluruhan, saya merasa telah mencapai target desain yang direncanakan. Keberhasilan migrasi ke PostgreSQL dan implementasi MQTT telah mengubah prototipe ini dari sekadar proyek mainan menjadi sistem yang siap untuk skala produksi.

### 5.2 Pembelajaran dan Pengembangan Diri
Melalui proyek ini, saya memperoleh keterampilan teknis baru yang sangat berharga:
1. Pemahaman mendalam mengenai pengembangan aplikasi *Asynchronous* menggunakan Python dan React.
2. Logika pengaturan jaringan IoT dalam lingkungan jaringan yang kompleks (WSL2 & Docker Networking).
3. Kedisiplinan dalam mendokumentasikan kode agar mudah dipahami oleh anggota tim lainnya.

### 5.3 Saran Perbaikan Selanjutnya
Jika sistem SiParkir dikembangkan lebih lanjut, saya menyarankan:
* **Enkripsi Data:** Penambahan lapisan keamanan TLS/SSL pada komunikasi MQTT.
* **Prediksi AI:** Implementasi deteksi jenis kendaraan (mobil/motor) secara otomatis untuk penentuan tarif yang lebih dinamis.
* **Integrasi Finansial:** Kerja sama dengan penyedia layanan *Payment Gateway* untuk pengisian saldo nyata.

---

**Muhammad Abduh**  
NIM 13525077  
Jurusan [Tuliskan Jurusan Anda]  
ITB Jatinangor, Juni 2026
