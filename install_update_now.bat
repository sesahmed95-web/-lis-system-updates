@echo off
setlocal enabledelayedexpansion
rem === LabSystem manual update installer (ASCII only, run from anywhere, double-click) ===
set "SRC=%~dp0"
set "APP="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p=(Get-Process LabSystem -ErrorAction SilentlyContinue | Select-Object -First 1).Path; if($p){Split-Path $p}"`) do set "APP=%%P"
if not defined APP if exist "C:\LabSystem\LabSystem.exe" set "APP=C:\LabSystem"
if not defined APP if exist "D:\LabSystem\LabSystem.exe" set "APP=D:\LabSystem"
if not defined APP (
  echo Could not find LabSystem.exe. Open the lab program first, then run this file again.
  pause & exit /b 1
)
echo Program folder: %APP%
set "LOG=%SRC%install_result.txt"
echo LabSystem install %DATE% %TIME% > "%LOG%"
echo APP=%APP% >> "%LOG%"
echo bundled VERSION: >> "%LOG%"
type "%APP%\VERSION" >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo Closing the program...
taskkill /f /im LabSystem.exe >nul 2>&1
timeout /t 3 >nul
set "CUR=%APP%\updates\current"
if exist "%CUR%" ren "%CUR%" "old_%RANDOM%" 2>>"%LOG%"
mkdir "%CUR%" 2>>"%LOG%"
for %%F in (app.py ledger_sync.py lab_updater.py auto_updater.py) do (
  if exist "%SRC%%%F" (copy /y "%SRC%%%F" "%CUR%\" >>"%LOG%" 2>&1) else (echo MISSING %%F next to this file >> "%LOG%")
)
>"%CUR%\VERSION" echo 268
echo --- files in current: >> "%LOG%"
dir /b "%CUR%" >> "%LOG%"
echo --- update_log tail: >> "%LOG%"
if exist "%APP%\updates\update_log.txt" (powershell -NoProfile -Command "Get-Content '%APP%\updates\update_log.txt' -Tail 30" >> "%LOG%")
echo Starting the program...
cd /d "%APP%"
if exist start_lab.vbs (wscript start_lab.vbs) else (start "" "%APP%\LabSystem.exe")
echo.
echo Done. Wait 20 seconds, then open: http://localhost:9090/ledger
echo If nothing changed, send me the file: %LOG%
pause
