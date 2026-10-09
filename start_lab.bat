@echo off
cd /d "%~dp0"
tasklist /fi "imagename eq LabSystem.exe" | find /i "LabSystem.exe" >nul
if errorlevel 1 start "" /min "%~dp0LabSystem.exe"
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:9090
