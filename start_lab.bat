@echo off
chcp 65001 >nul
title Lab Server - لا تغلق هذي النافذة
cd /d "C:\Users\Mas\Documents\GitHub\-lis-system-updates"

rem --- لو السيرفر شغّال أصلاً (المنفذ 9090) لا نشغّله مرة ثانية، فقط نفتح النافذة ---
netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if %errorlevel%==0 goto openwin

start "" /min cmd /c "python app.py & pause"

rem --- ننتظر لين يصير السيرفر جاهز (أقصى 60 ثانية) ---
set /a tries=0
:wait
set /a tries+=1
if %tries% gtr 60 goto openwin
timeout /t 1 >nul
netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if not %errorlevel%==0 goto wait

:openwin
set "URL=http://127.0.0.1:9090"
set "PROF=%LOCALAPPDATA%\LabAppWindow"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

rem --- نافذة مستقلة بدون شريط المتصفح (وضع التطبيق) ---
if exist "%EDGE%" ( start "" "%EDGE%" --app=%URL% --user-data-dir="%PROF%" --start-maximized & exit /b )
if exist "%CHROME%" ( start "" "%CHROME%" --app=%URL% --user-data-dir="%PROF%" --start-maximized & exit /b )
start "" %URL%
exit /b
