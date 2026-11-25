@echo off
cd /d "%~dp0"
echo Running apply_sync_testdocs.py in: %cd%
if not exist app.py (
  echo ERROR: app.py not found in this folder. Put this file next to app.py
  pause
  exit /b 1
)
py apply_sync_testdocs.py
echo.
pause
