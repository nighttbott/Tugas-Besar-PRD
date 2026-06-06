@echo off
setlocal EnableDelayedExpansion

echo =======================================================
echo     ANPR PARKING SYSTEM - AUTO START (WINDOWS)
echo =======================================================
echo.

:: 1. Dapatkan IPv4 lokal (Wi-Fi / Ethernet) dan hindari IP WSL/VirtualBox
echo [1] Melacak IP Address Laptop...
set "MY_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4 Address" /C:"IPv4 Address"') do (
    set "IP_TEMP=%%a"
    set "IP_TEMP=!IP_TEMP: =!"
    
    :: Hanya ambil IP yang BUKAN 172.* (WSL) dan 169.* (APIPA)
    echo !IP_TEMP! | findstr /R "^172\." >nul
    if errorlevel 1 (
        echo !IP_TEMP! | findstr /R "^169\." >nul
        if errorlevel 1 (
            set "MY_IP=!IP_TEMP!"
        )
    )
)

if "%MY_IP%"=="" (
    echo [ERROR] Gagal menemukan IP Address lokal. Pastikan Anda terhubung ke Wi-Fi/Hotspot!
    pause
    exit /b
)
echo     IP Address ditemukan: %MY_IP%
echo.

:: 2. Update file anpr/.env secara dinamis
echo [2] Memperbarui konfigurasi ANPR Kamera...
set "ENV_FILE=anpr\.env"
if not exist "%ENV_FILE%" (
    echo [ERROR] File %ENV_FILE% tidak ditemukan!
    pause
    exit /b
)

:: Buat file temporary
set "TEMP_ENV=anpr\.env.tmp"
if exist "%TEMP_ENV%" del "%TEMP_ENV%"

:: Baca file lama, ganti baris API_ENDPOINT, lalu tulis ke file baru
for /f "tokens=* delims=" %%A in ('type "%ENV_FILE%"') do (
    set "LINE=%%A"
    echo !LINE! | findstr /B "API_ENDPOINT=" >nul
    if not errorlevel 1 (
        echo API_ENDPOINT=http://%MY_IP%:8000/api/v1/gate/trigger>> "%TEMP_ENV%"
    ) else (
        echo !LINE!>> "%TEMP_ENV%"
    )
)

:: Timpa file asli
move /Y "%TEMP_ENV%" "%ENV_FILE%" >nul
echo     Sukses mengubah API_ENDPOINT menjadi http://%MY_IP%:8000
echo.

:: 3. Jalankan Docker
echo [3] Menghidupkan Server Docker...
call docker compose up -d
echo     Docker Services berjalan di background.
echo.

:: 4. Jalankan Skrip Python ANPR
echo [4] Memulai Kamera ANPR...
cd anpr
if not exist ".venv\Scripts\activate" (
    echo [ERROR] Virtual Environment .venv tidak ditemukan di folder anpr!
    pause
    exit /b
)

echo     Mengaktifkan Virtual Environment...
call .venv\Scripts\activate.bat

echo     Menjalankan anpr_main.py...
python anpr_main.py

pause
