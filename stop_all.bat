@echo off
echo Stopping all services...
taskkill /IM python.exe /F /T 2>nul
taskkill /IM node.exe /F /T 2>nul
echo Done.
pause