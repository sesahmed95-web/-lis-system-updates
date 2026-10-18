@echo off
echo Closing any old Lab System server that is still running on port 9090 ...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9090" ^| findstr "LISTENING"') do (
  echo Found process PID %%a - closing it
  taskkill /F /PID %%a
  set FOUND=1
)
if "%FOUND%"=="0" echo No old server found on port 9090.
echo.
echo Done. Now start the program again as usual.
pause
