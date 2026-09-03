# Al-Karama LIS - launcher (PowerShell version, no VBScript / WSH needed)
# ملاحظة مهمة (إصلاح لاحق): كان فيه "$ErrorActionPreference = SilentlyContinue"
# هنا يشمل السكربت كامل — هذا كان يخفي أي خطأ حقيقي بتشغيل بايثون/السيرفر
# بصمت، فيفتح المتصفح على الرابط حتى لو السيرفر فشل يشتغل أصلاً، وتطلع
# "تعذر الوصول لهذا الموقع" بدون أي تفسير. صار الآن مقصور بس على أوامر
# الترميز التجميلية (chcp/OutputEncoding) اللي فعلاً ما يهم فشلها.
try { chcp 65001 | Out-Null } catch {}
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}
$AppDir = $PSScriptRoot
Set-Location $AppDir
$PidFile = Join-Path $AppDir "server.pid"
$LogFile = Join-Path $AppDir "server_start_error.log"
$AppUrl  = "http://localhost:9090"
$host.UI.RawUI.WindowTitle = "برنامج مختبر أمراض الدم"

function Show-Msg($text) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($text, "Al-Karama LIS") | Out-Null
}

function Fail($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    Show-Msg $text
    exit
}

Write-Host "جاري تشغيل برنامج مختبر أمراض الدم (إصدار 15)..."
Write-Host ""

# 1) Is the server already running from a previous launch?
$serverRunning = $false
if (Test-Path $PidFile) {
    $savedPid = (Get-Content $PidFile -TotalCount 1).Trim()
    if ($savedPid) {
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "python|^py$") { $serverRunning = $true }
    }
}

if ($serverRunning) {
    Write-Host "البرنامج شغال من قبل، بس بفتح النافذة..."
} else {
    Write-Host "جاري التحقق من وجود Python..."
    # نبحث عن بايثون بمسارات معروفة صريحة أولاً (نفس النسخة المؤكد إنها
    # تشتغل صح لما تُشغَّل يدويًا من PowerShell) قبل الاعتماد على PATH —
    # لأن لما تُشغَّل هذي النافذة من أيقونة سطح المكتب (لا شل تفاعلي)،
    # قد يلتقط Get-Command نسخة بايثون مختلفة أو "وهمية" يحطها ويندوز
    # افتراضيًا بمجلد WindowsApps (تفتح متجر مايكروسوفت بس وما تشغّل أي
    # شي فعليًا) بدل التنصيب الحقيقي — وهذا كان سبب الفشل الصامت.
    $pyCmd = $null
    $knownPythonPaths = @(
        "C:\Python314\python.exe",
        "$env:LocalAppData\Programs\Python\Python314\python.exe",
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe"
    )
    foreach ($p in $knownPythonPaths) {
        if (Test-Path $p) { $pyCmd = $p; break }
    }
    if (-not $pyCmd) {
        # احتياطي: نفحص PATH، بس نتجاهل أي نسخة تطلع من مجلد WindowsApps
        # (نفس نسخة ويندوز الوهمية اللي تسبب المشكلة).
        $candidates = @(Get-Command py -ErrorAction SilentlyContinue, Get-Command python -ErrorAction SilentlyContinue) |
            Where-Object { $_ -and $_.Source -notmatch "WindowsApps" }
        if ($candidates) { $pyCmd = $candidates[0].Source }
    }
    if (-not $pyCmd) {
        $msg = "تعذر العثور على Python الحقيقي على هذا الجهاز (تم تجاهل أي نسخة وهمية من WindowsApps)." + "`n`n" + 'ثبت Python من https://www.python.org/downloads/ وفعل خيار "Add python.exe to PATH" اثناء التثبيت، ثم اعد تشغيل الجهاز وجرب مرة اخرى.'
        Fail $msg
    }
    Write-Host "Python موجود ($pyCmd). جاري التحقق من المكتبات المطلوبة..."

    # نتحقق في كل تشغيلة (فحص سريع جدًا) بدل الاعتماد على ملف علامة واحد
    # يخلي التحقق يتخطى نفسه للأبد؛ هذا يضمن إن أي مكتبة جديدة تنضاف
    # بتحديث لاحق (مثل qrcode و python-barcode لطباعة الباركود) تتنزل
    # تلقائيًا حتى عند الأجهزة اللي عندها تنصيب قديم.
    & $pyCmd -c "import flask, PIL, docx, qrcode, barcode" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "جاري تنزيل المكتبات المطلوبة (يحتاج انترنت أول مرة أو بعد أي تحديث)..."
        & $pyCmd -m pip install -r (Join-Path $AppDir "requirements.txt") --quiet --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) {
            Fail "تعذر تثبيت المكتبات المطلوبة (يحتاج اتصال بالانترنت اول مرة فقط). تاكد من اتصال الجهاز بالانترنت وجرب تشغيل البرنامج مرة اخرى."
        }
        Write-Host "تم تنزيل المكتبات بنجاح."
    } else {
        Write-Host "المكتبات موجودة، تخطينا هذي الخطوة."
    }

    Write-Host "جاري تشغيل السيرفر..."
    if (Test-Path $LogFile) { Remove-Item $LogFile -ErrorAction SilentlyContinue }
    try {
        # نسجّل أي خطأ فعلي يطبعه بايثون وقت الإقلاع (مثلاً مكتبة ناقصة،
        # خطأ صياغة بملف .py، تعارض منفذ...) بملف نصي، بدل ما يضيع لأن
        # النافذة مخفية (-WindowStyle Hidden) — لو صار فشل صامت زي المرات
        # الماضية، هذا الملف يوضح السبب الحقيقي بالضبط.
        $proc = Start-Process -FilePath $pyCmd -ArgumentList @("app.py") -WorkingDirectory $AppDir `
            -WindowStyle Hidden -PassThru -RedirectStandardError $LogFile
        Start-Sleep -Milliseconds 800
        if ($proc.HasExited) {
            $errText = ""
            if (Test-Path $LogFile) { $errText = Get-Content $LogFile -Raw }
            Fail ("تعذر تشغيل السيرفر — توقف فورًا بعد الإقلاع.`n`n" + $errText)
        }
        Set-Content -Path $PidFile -Value $proc.Id
    } catch {
        Fail ("تعذر تشغيل السيرفر: " + $_.Exception.Message)
    }
}

Write-Host "جاري الانتظار حتى يجهز السيرفر..."
$ready = $false
for ($i = 0; $i -lt 100; $i++) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", 9090)
        if ($client.Connected) { $ready = $true; $client.Close(); break }
    } catch {}
    Start-Sleep -Milliseconds 150
}

if (-not $ready) {
    Write-Host "السيرفر ماطلع جاهز خلال الفحص، بس رح نجرب نفتح المتصفح على أي حال..." -ForegroundColor Yellow
}

Write-Host "جاري فتح البرنامج..."

$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)
$edgePaths = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)
$browser = ($chromePaths + $edgePaths) | Where-Object { Test-Path $_ } | Select-Object -First 1
try {
    if ($browser) {
        Start-Process -FilePath $browser -ArgumentList "--app=$AppUrl", "--window-size=1280,860"
    } else {
        Start-Process $AppUrl
    }
} catch {
    try { Start-Process "cmd.exe" -ArgumentList "/c start $AppUrl" -WindowStyle Hidden } catch {}
}

if (-not $ready) {
    Write-Host ""
    Write-Host "إذا ما فتح المتصفح البرنامج، اكتب هذا الرابط يدويًا بالمتصفح:"
    Write-Host $AppUrl -ForegroundColor Cyan
}
