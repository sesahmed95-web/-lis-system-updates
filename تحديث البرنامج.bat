@echo off
title تحديث برنامج مختبر أمراض الدم
echo جاري إيقاف النسخة القديمة (إن وجدت) وتثبيت النسخة الجديدة...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
echo.
echo تم. البرنامج الآن يفتح بآخر تحديث.
pause
