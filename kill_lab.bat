@echo off
echo ============================================================
echo  Stopping EVERY Lab System process (python / pythonw / LabSystem / LIS)
echo  WARNING: this also closes any other Python program you have open.
echo ============================================================
taskkill /F /T /IM python.exe  >nul 2>&1
taskkill /F /T /IM pythonw.exe >nul 2>&1
taskkill /F /T /IM LabSystem.exe >nul 2>&1
taskkill /F /T /IM LIS.exe >nul 2>&1
timeout /t 3 /nobreak >nul
echo.
echo Anything still listening on port 9090 / 9091 (should be EMPTY):
netstat -ano | findstr /R ":9090 :9091"
echo.
echo If a line appeared above, its LAST number is the PID. Close it with:
echo     taskkill /F /PID that_number
echo If nothing appeared, start the program normally now.
echo.
pause
