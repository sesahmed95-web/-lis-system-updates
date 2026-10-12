@echo off
cd /d "%~dp0"
set OUT=lab_diag.txt
echo === Lab diagnostics %date% %time% === > %OUT%
echo. >> %OUT%
echo --- Processes: python / pythonw / LabSystem / LIS --- >> %OUT%
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|LabSystem|LIS)(\.exe)?$' } | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List" >> %OUT% 2>&1
echo. >> %OUT%
echo --- Who listens on 9090 / 9091 (last number = PID) --- >> %OUT%
netstat -ano | findstr /R ":9090 :9091" >> %OUT% 2>&1
echo. >> %OUT%
echo --- Database files --- >> %OUT%
dir lis.db* >> %OUT% 2>&1
echo. >> %OUT%
echo --- error_log.txt (last 80 lines) --- >> %OUT%
powershell -NoProfile -Command "if (Test-Path error_log.txt) { Get-Content error_log.txt -Tail 80 } else { 'no error_log.txt here' }" >> %OUT% 2>&1
echo. >> %OUT%
echo --- crash_log.txt (last 40 lines) --- >> %OUT%
powershell -NoProfile -Command "if (Test-Path crash_log.txt) { Get-Content crash_log.txt -Tail 40 } else { 'no crash_log.txt here' }" >> %OUT% 2>&1
echo.
echo Done. The file lab_diag.txt was created in this folder. Send it.
start notepad %OUT%
pause
