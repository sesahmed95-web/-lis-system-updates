# ============================================================================
#  نشر تحديث جديد — سكربت واحد يسوي كل الخطوات المتكررة تلقائياً
#  شغّله دائماً من نفس مكانه (داخل مجلد lis_system الرئيسي اللي تشتغل عليه).
# ============================================================================
#  شنو يسوي بالضبط:
#   1) يتأكد إن أداة GitHub الرسمية (gh) مسجّل دخولها — أول مرة بس تسجّل
#      دخول بمتصفحك بحسابك العادي (نفس تسجيل الدخول لأي موقع)، وخلص —
#      ما تحتاج تسوي أو تلصق أي توكن يدوياً بعدها أبداً، ولا اليوم ولا
#      بأي نشرة جاية.
#   2) يعرض رقم VERSION الحالي ويقترح الرقم التالي — تأكّد بالعين وحدة.
#   3) يسألك: هذا التحديث لكل العملاء (عام) ولا لعميل واحد بس (خاص)؟
#      - عام: ينطبق على كل نسخة مثبتة بأي مكان.
#      - خاص: تدخل رقم جهاز العميل (Hardware ID) الظاهر بلوحة المصمم
#        عنده — التحديث هذا ينوصل لهذا الجهاز بس، وبقية العملاء ما
#        يتأثرون ولا يشوفون هذا الإصدار إطلاقاً.
#   4) يسوي ملف zip صحيح (نفس تركيب "lis_system/..." المطلوب) ويستثني تلقائياً
#      lis.db, __pycache__, ملفات uploads الخاصة بأي عميل، .git، إلخ.
#   5) ينشر الإصدار مباشرة على GitHub (بدون فتح متصفح يدوياً، بدون سحب
#      وإفلات، بدون ضغط Publish) عن طريق أمر gh واحد.
# ============================================================================

$ErrorActionPreference = "Stop"
try { chcp 65001 | Out-Null } catch {}
$Root = $PSScriptRoot

# --- إعدادات المستودع (لو غيّرت المستودع بالمستقبل عدّل هذي القيمة فقط) ---
$GithubOwner = "sesahmed95-web"
$GithubRepo  = "-lis-system-updates"
$RepoSlug    = "$GithubOwner/$GithubRepo"

Write-Host "============================================================"
Write-Host "  نشر تحديث جديد — مختبر أمراض الدم"
Write-Host "============================================================"
Write-Host ""

# 1) تأكد إن gh (GitHub CLI) مثبتة، وإلا ثبّتها تلقائياً --------------------
function Test-GhInstalled { return [bool](Get-Command gh -ErrorAction SilentlyContinue) }

if (-not (Test-GhInstalled)) {
    Write-Host "أداة GitHub CLI (gh) غير مثبتة — جاري تثبيتها تلقائياً..." -ForegroundColor Yellow
    try {
        winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    } catch {
        Write-Host "❌ تعذر التثبيت التلقائي عبر winget." -ForegroundColor Red
        Write-Host "    حمّلها يدوياً مرة وحدة من هذا الرابط ثم أعد تشغيل هذا السكربت:" -ForegroundColor Red
        Write-Host "    https://cli.github.com" -ForegroundColor Red
        Read-Host "اضغط Enter للخروج"
        exit 1
    }
    # حدّث PATH بنفس الجلسة الحالية حتى يلقى أمر gh بدون إعادة فتح PowerShell
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (-not (Test-GhInstalled)) {
        Write-Host "✅ انتهى التثبيت — بس لازم تسكّر هذا الملف وتفتحه من جديد مرة وحدة ثانية حتى يتعرف عليها." -ForegroundColor Yellow
        Read-Host "اضغط Enter للخروج"
        exit 0
    }
}

# 2) تأكد من تسجيل الدخول (مرة وحدة فقط — يبقى محفوظ بعدها دائماً) --------
$authCheck = & gh auth status --hostname github.com 2>&1
$isLoggedIn = $LASTEXITCODE -eq 0
if (-not $isLoggedIn) {
    Write-Host "أول مرة تنشر من هذا الجهاز — راح يفتحلك المتصفح تسجّل دخول بحساب" -ForegroundColor Yellow
    Write-Host "GitHub العادي (نفس اليوزر والباسورد، أو حتى بدون كلمة سر إذا مسجّل دخول أصلاً بالمتصفح)." -ForegroundColor Yellow
    Write-Host "هذا يصير مرة وحدة بالعمر — بعدها السكربت يتذكرك تلقائياً كل مرة." -ForegroundColor Yellow
    Write-Host ""
    & gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ فشل تسجيل الدخول. أعد تشغيل السكربت وجرب مرة ثانية." -ForegroundColor Red
        Read-Host "اضغط Enter للخروج"
        exit 1
    }
    Write-Host "✅ تم تسجيل الدخول بنجاح — ما راح يطلبها منك بعد اليوم." -ForegroundColor Green
} else {
    Write-Host "✅ مسجّل دخول أصلاً على GitHub — ماكو شي تسويه هنا." -ForegroundColor Green
}
Write-Host ""

# 3) رقم الإصدار ------------------------------------------------------------
$versionFile = Join-Path $Root "VERSION"
$currentVersion = (Get-Content $versionFile -Raw).Trim()
$suggested = 0
if ([int]::TryParse($currentVersion, [ref]$suggested)) { $suggested = $suggested + 1 } else { $suggested = 1 }

Write-Host "الإصدار الحالي المكتوب بملف VERSION: $currentVersion"
$newVersionInput = Read-Host "رقم الإصدار الجديد؟ (اضغط Enter بدون كتابة أي شي لاستخدام الاقتراح: $suggested)"
if ([string]::IsNullOrWhiteSpace($newVersionInput)) {
    $newVersion = $suggested
} else {
    $newVersion = $newVersionInput.Trim()
}

# 4) عام لجميع العملاء ولا خاص بعميل واحد؟ -----------------------------------
Write-Host ""
Write-Host "هذا التحديث:"
Write-Host "  1) عام — ينطبق على جميع العملاء"
Write-Host "  2) خاص — ينطبق على عميل واحد فقط (تحدد رقم جهازه)"
$scopeChoice = Read-Host "اختر 1 أو 2"

$tagSuffix = ""
$targetHwDisplay = "جميع العملاء (تحديث عام)"
if ($scopeChoice -eq "2") {
    $hwInput = Read-Host "أدخل Hardware ID مال جهاز العميل (زي ما هو ظاهر بلوحة المصمم بالضبط)"
    $hwClean = ($hwInput -replace '[^A-Za-z0-9]', '').ToUpper()
    if (-not $hwClean) {
        Write-Host "❌ رقم الجهاز فارغ أو غير صالح. تم الإلغاء." -ForegroundColor Red
        Read-Host "اضغط Enter للخروج"
        exit 1
    }
    $tagSuffix = "__" + $hwClean
    $targetHwDisplay = "هذا الجهاز فقط: $hwInput"
}
$releaseTag = "$newVersion$tagSuffix"

Write-Host ""
Write-Host "ملخّص قبل النشر:"
Write-Host "  رقم الإصدار : $newVersion"
Write-Host "  النطاق      : $targetHwDisplay"
Write-Host "  Tag على GitHub : $releaseTag"
$confirmV = Read-Host "تأكيد النشر بهذي البيانات؟ (اكتب نعم للمتابعة)"
if ($confirmV -ne "نعم") {
    Write-Host "تم الإلغاء." -ForegroundColor Red
    Read-Host "اضغط Enter للخروج"
    exit 1
}

Set-Content -Path $versionFile -Value $newVersion -NoNewline -Encoding UTF8
Write-Host "✅ تم تحديث VERSION إلى $newVersion" -ForegroundColor Green
Write-Host ""

# 5) بناء ملف الـ zip ---------------------------------------------------------
$parentDir = Split-Path $Root -Parent
$outDir = Join-Path $parentDir "publish_output"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$stageRoot = Join-Path $outDir "stage_$releaseTag"
$stageInner = Join-Path $stageRoot "lis_system"
if (Test-Path $stageRoot) { Remove-Item $stageRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stageInner | Out-Null

Write-Host "جاري تجهيز الملفات..."
$excludeDirs  = @('__pycache__', '.git', '.venv', 'venv', 'publish_output', 'node_modules')
$excludeFiles = @('lis.db', '*.pyc', '*.pyo', '*.log', '.env', 'Thumbs.db', '.DS_Store')

robocopy $Root $stageInner /E /XD $excludeDirs /XF $excludeFiles /NFL /NDL /NJH /NJS /NC /NS | Out-Null

# نظّف محتوى static/uploads (شعارات/ملفات عملاء سابقين) لكن خلي المجلد موجود
$uploadsDir = Join-Path $stageInner "static\uploads"
if (Test-Path $uploadsDir) {
    Get-ChildItem $uploadsDir -Force | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Recurse -Force
}

$zipName = "lis_system_updated_$releaseTag.zip"
$zipPath = Join-Path $outDir $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $stageInner -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $stageRoot -Recurse -Force

Write-Host "✅ تم إنشاء ملف الحزمة:" -ForegroundColor Green
Write-Host "   $zipPath"
Write-Host ""

# 6) نشر الإصدار مباشرة على GitHub عن طريق أمر gh واحد ----------------------
Write-Host "جاري نشر الإصدار على GitHub..."

$releaseNotes = if ($tagSuffix) { "تحديث خاص بجهاز $hwInput فقط — رقم $newVersion" } else { "تحديث عام رقم $newVersion" }

try {
    & gh release create $releaseTag $zipPath `
        --repo $RepoSlug `
        --title $releaseTag `
        --notes $releaseNotes
    if ($LASTEXITCODE -ne 0) { throw "gh release create رجع بخطأ" }
    Write-Host ""
    Write-Host "✅ تم النشر بنجاح — خلص، ما يحتاج أي خطوة يدوية ثانية." -ForegroundColor Green
    Write-Host "    $targetHwDisplay" -ForegroundColor Green
}
catch {
    Write-Host "❌ فشل النشر على GitHub." -ForegroundColor Red
    Write-Host "    السبب المحتمل: رقم الإصدار '$releaseTag' مستخدم سابقاً، أو مشكلة اتصال بالنت." -ForegroundColor Red
    Write-Host "    ملف الـ zip جاهز عندك بأي حال بالمسار:" -ForegroundColor Yellow
    Write-Host "    $zipPath"
    Read-Host "اضغط Enter للخروج"
    exit 1
}

Write-Host ""
Read-Host "اضغط Enter للإغلاق"
