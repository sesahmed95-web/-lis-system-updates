# restart_server.ps1
# يطفي السيرفر الحالي (Python/Flask) ويشغله من جديد — استخدمه بعد أي تعديل
# على app.py أو database.py حتى تنطبق التعديلات فعلياً (تحديث الكود ما ينفذ
# إلا بعد إعادة تشغيل العملية، مو بالتلقائي وهو شغال).

# ============ عدّل هذا السطر فقط: مسار مجلد البرنامج عندك ============
$AppFolder = "C:\LabApp"          # غيّره لمسار مجلد البرنامج الحقيقي عندك
$LauncherVbs = "تشغيل البرنامج.vbs"   # اسم ملف التشغيل (لو تستخدمه)
$Port = 9090                       # نفس البورت الظاهر بالمتصفح (localhost:9090)
# ======================================================================

Write-Host "1) أدور على العملية اللي تستخدم البورت $Port ..." -ForegroundColor Cyan
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $procIds = $conn.OwningProcess | Sort-Object -Unique
    foreach ($processId in $procIds) {
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "   إطفاء العملية: $($proc.ProcessName) (PID $processId)" -ForegroundColor Yellow
            Stop-Process -Id $processId -Force
        }
    }
    Start-Sleep -Seconds 2
    Write-Host "   تم الإطفاء." -ForegroundColor Green
} else {
    Write-Host "   ما لقيت عملية شغالة على هذا البورت (ممكن يكون السيرفر مطفي أصلاً)." -ForegroundColor DarkYellow
}

# احتياط إضافي: أي عملية python.exe لسا فاتحة app.py تحديداً (لو ما انطفت
# بالخطوة فوق لأي سبب — مثلاً البورت تغيّر).
Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "app\.py" } |
    ForEach-Object {
        Write-Host "   إطفاء عملية Python إضافية: PID $($_.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "2) تشغيل السيرفر من جديد ..." -ForegroundColor Cyan
Set-Location $AppFolder

$vbsPath = Join-Path $AppFolder $LauncherVbs
if (Test-Path $vbsPath) {
    Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""
    Write-Host "   شغّلت البرنامج عن طريق: $LauncherVbs" -ForegroundColor Green
} else {
    Start-Process "python.exe" -ArgumentList "app.py" -WorkingDirectory $AppFolder
    Write-Host "   ما لقيت ملف $LauncherVbs — شغّلت app.py مباشرة بدله." -ForegroundColor Green
}

Write-Host "3) خلص. افتح المتصفح على http://localhost:$Port بعد ثوانٍ." -ForegroundColor Cyan
