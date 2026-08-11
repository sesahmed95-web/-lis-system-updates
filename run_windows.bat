@echo off
title Al-Karama LIS Server

rem Newer Python installs (the "Python Install Manager" from python.org)
rem mainly register the "py" launcher command, while older/classic
rem installs mainly register "python" directly. Try both so this works
rem regardless of which installer was used.
where py >nul 2>nul
if %errorlevel%==0 (
    set PYCMD=py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set PYCMD=python
    ) else (
        echo.
        echo [خطأ] لم يتم العثور على Python على هذا الجهاز.
        echo تأكد من تثبيت Python من https://www.python.org/downloads/
        echo وتفعيل خيار "Add python.exe to PATH" أثناء التثبيت، ثم أعد تشغيل الجهاز.
        echo.
        pause
        exit /b 1
    )
)

rem Only install requirements the first time (or if a package is missing).
rem This is what used to make every single launch reach out over the
rem network even when nothing needed installing — now it's skipped
rem whenever Flask/Pillow/python-docx already import successfully.
%PYCMD% -c "import flask, PIL, docx" >nul 2>nul
if %errorlevel% NEQ 0 (
    echo Installing requirements ^(first run only^)...
    %PYCMD% -m pip install -r requirements.txt --quiet
) else (
    echo Requirements already installed, skipping.
)

echo.
echo Starting Al-Karama LIS...
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" cmd /c "timeout /t 2 >nul && start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=http://localhost:9090 --window-size=1280,860"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    start "" cmd /c "timeout /t 2 >nul && start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --app=http://localhost:9090 --window-size=1280,860"
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    start "" cmd /c "timeout /t 2 >nul && start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app=http://localhost:9090 --window-size=1280,860"
) else (
    start "" cmd /c "timeout /t 2 >nul && start http://localhost:9090"
)
%PYCMD% app.py
pause
