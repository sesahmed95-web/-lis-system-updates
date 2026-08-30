@echo off
cd /d "%~dp0"

echo This will close ALL open Chrome windows and the running lab program.
echo Save any work in Chrome now.
pause

echo.
echo Closing old program process...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":9090" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p
)

echo.
echo Closing Chrome and chromedriver...
taskkill /F /IM chrome.exe
taskkill /F /IM chromedriver.exe

echo.
echo Waiting a few seconds...
timeout /t 5

echo.
echo Starting install.bat now...
call install.bat

echo.
echo Done. Press any key to close this window.
pause
