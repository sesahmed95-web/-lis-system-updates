@echo off
title Installing Hematology Lab Program
echo Installing, please wait...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
