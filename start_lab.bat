@echo off
title Lab Server - لا تغلق هذي النافذة
cd /d "C:\Users\Mas\Documents\GitHub\-lis-system-updates"
start "" cmd /c "timeout /t 6 >nul & start http://127.0.0.1:9090"
python app.py
pause