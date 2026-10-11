@echo off
py -3 "%~dp0make_portal_preset.py"
if errorlevel 1 python "%~dp0make_portal_preset.py"
echo.
pause
