@echo off
chcp 65001 >nul
echo ============================================
echo   Al-Karama LIS — اصلاح شامل + اعادة تشغيل
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] اقفال اي نسخة Python شغالة حالياً (حتى لو عالقة)...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM pythonw.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
echo     تم.
echo.

echo [2/4] تحديث بيانات الدكاترة (اسماء + شهادات + حجم خط)...
python fix_doctors.py
if errorlevel 1 (
    echo.
    echo     !! صار خطأ اثناء تحديث البيانات. اقرأ الرسالة فوق وابعثها الي.
    pause
    exit /b 1
)
echo.

echo [3/4] تشغيل السيرفر من جديد...
if exist "run.ps1" (
    powershell -ExecutionPolicy Bypass -File "run.ps1"
) else if exist "run_windows.bat" (
    call "run_windows.bat"
) else (
    start "" python app.py
)
timeout /t 4 /nobreak >nul
echo     تم.
echo.

echo [4/4] فتح المتصفح على localhost:9090 ...
start "" "http://localhost:9090"
echo.

echo ============================================
echo   خلص. لو الاسماء والشهادات لسا قديمة بعد ما
echo   تفتح الصفحة، اعمل Ctrl+F5 (تحديث اجباري)
echo   بالمتصفح، وإذا لسا نفس المشكلة ابعثلي لقطة
echo   شاشة لهذي النافذة السوداء كاملة.
echo ============================================
pause
