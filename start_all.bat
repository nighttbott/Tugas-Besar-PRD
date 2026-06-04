@echo off
echo Starting Parking System...

:: Backend
start "Backend" cmd /k "cd backend && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

:: Frontend
start "Frontend" cmd /k "cd frontend && npm run dev"

:: ANPR Entry (Laptop Webcam)
start "ANPR Entry" cmd /k "cd anpr && set CAMERA_INDEX=0 && .venv\Scripts\python.exe anpr_main.py"

:: ANPR Exit (HP IP Camera)
start "ANPR Exit" cmd /k "cd anpr && set GATE_DIRECTION=exit && set CAMERA_INDEX=2 && .venv\Scripts\python.exe anpr_main.py"

echo All services started!