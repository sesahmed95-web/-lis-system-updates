@echo off
taskkill /f /im LabSystem.exe >nul 2>&1
echo Lab System stopped.
timeout /t 2 >nul
