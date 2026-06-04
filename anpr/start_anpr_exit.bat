@echo off
for /f "tokens=1,2 delims== eol=#" %%a in (.env.exit) do set "%%a=%%b"
.venv\Scripts\python.exe anpr_main.py