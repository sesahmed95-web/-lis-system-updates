# تحديث برنامج مختبر أمراض الدم — يوقف أي نسخة قديمة شغالة بالخلفية أولاً
# (حتى لو نسيت توقفها يدويًا)، بعدين يثبت هذا الإصدار الجديد فوق نفس مكان
# التثبيت الدائم (%LOCALAPPDATA%\HematologistLIS)، وأخيرًا يشغّله مباشرة.
#
# -Source : مصدر ملفات الإصدار الجديد. افتراضياً نفس مجلد هذا السكربت
#           (حالة التحديث اليدوي: تحطون ملفات جديدة جنب update.ps1
#           وتضغطون عليه). عند التحديث التلقائي (auto_updater.py) يُمرَّر
#           مسار مجلد مؤقت تم تنزيله وفكّه من GitHub.
# -Silent : يخفي رسالة "تم التحديث بنجاح" المنبثقة (تُستخدم مع التحديث
#           التلقائي بالخلفية حتى لا يفاجَأ المستخدم بنافذة).
param(
    [string]$Source = $PSScriptRoot,
    [switch]$Silent
)
$ErrorActionPreference = "SilentlyContinue"
try { chcp 65001 | Out-Null } catch {}
$Dest   = Join-Path $env:LOCALAPPDATA "HematologistLIS"
$PidFile = Join-Path $Dest "server.pid"

function Show-Msg($text) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($text, "تحديث Al-Karama LIS") | Out-Null
}

Write-Host "جاري إيقاف أي نسخة قديمة شغالة بالخلفية..."

# 1) أوقف العملية المسجلة بملف server.pid إذا كانت لسا شغالة
if (Test-Path $PidFile) {
    $savedPid = (Get-Content $PidFile -TotalCount 1).Trim()
    if ($savedPid) {
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "python") {
            Stop-Process -Id $savedPid -Force
            Write-Host "تم إيقاف السيرفر القديم (PID $savedPid)."
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 2) احتياطًا: أوقف أي عملية لسا محجزة على نفس المنفذ 9090 حتى لو ملف
#    الـ pid كان ضايع أو قديم (مثلاً بعد ريستارت غير طبيعي للجهاز)
try {
    Get-NetTCPConnection -LocalPort 9090 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
} catch {}

Start-Sleep -Milliseconds 700

Write-Host "جاري تثبيت الإصدار الجديد فوق: $Dest ..."
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Path (Join-Path $Source '*') -Destination $Dest -Recurse -Force `
    -Exclude @('install.ps1', 'install.bat', 'update.ps1', 'تحديث البرنامج.bat', 'server.pid', 'lis.db')

# أعد إنشاء أيقونة سطح المكتب لو كانت مفقودة لأي سبب
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) "برنامج مختبر أمراض الدم.lnk"
if (-not (Test-Path $shortcutPath)) {
    $WshShell = New-Object -ComObject WScript.Shell
    $shortcut = $WshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $runPath = Join-Path $Dest 'run.ps1'
    $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runPath + '"'
    $shortcut.WindowStyle = 7
    $shortcut.WorkingDirectory = $Dest
    $iconPath = Join-Path $Dest 'static\icon\lab-icon.ico'
    if (Test-Path $iconPath) { $shortcut.IconLocation = $iconPath }
    $shortcut.Save()
}

Write-Host "تم التحديث بنجاح. جاري تشغيل البرنامج..."
Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Dest 'run.ps1')
)

# نظّف المجلد المؤقت لو كان مصدر التحديث تنزيل تلقائي من الإنترنت (تحت
# %TEMP%) — ما نلمس أي مصدر ثاني (مثل مجلد يدوي جنب هذا السكربت).
try {
    $tempRoot = [System.IO.Path]::GetTempPath()
    if ($Source -and $Source.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Start-Sleep -Seconds 3
        Remove-Item -Path $Source -Recurse -Force -ErrorAction SilentlyContinue
    }
} catch {}

if (-not $Silent) {
    Show-Msg "تم تحديث البرنامج بنجاح وتشغيله بآخر إصدار."
}
