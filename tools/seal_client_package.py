# -*- coding: utf-8 -*-
"""
seal_client_package.py — "ختم" نسخة العميل: يطلع منها ملف زيب واحد جاهز للتنصيب بنقرة وحدة (INSTALL.bat)
==========================================================================================
الفكرة: تجهّز مجلد العميل كامل بنفسك (اسم المختبر، الشعار، الدكاترة والأختام، تصاميم التقارير، النسب الطبيعية، بوابة النتائج...)
بتشغيل البرنامج منه. بعدين تشغّل هذي الأداة عليه:
  1) تاخذ نسخة من قاعدة البيانات وتمسح منها كل بيانات المرضى والزيارات والفواتير والنتائج والسجلات (تبقي الإعدادات والتحاليل والنسب والتصاميم)،
  2) تمسح بيانات ترخيص جهازك أنت (يتولّد للعميل ترخيصه/تجربته عند أول تشغيل) وأي مفاتيح/مسارات تخص جهازك،
  3) تجمّع البرنامج + قاعدة العميل النظيفة + شعاره وأختامه + requirements.txt + INSTALL.bat بزيب واحد.

التشغيل (من مجلد برنامج العميل المجهّز، وليس من مجلد مختبرك الشغّال):
    python tools\\seal_client_package.py "C:\\Clients\\Nour"
خيارات مفيدة:
    --admin-password كلمة_سر_جديدة     (ينصح به: يبدّل admin123 الافتراضية)
    --deactivate-demo-users            (يعطّل rec/tech/super/acc الافتراضيين؛ العميل ينشئ موظفيه)
    --keep-license                     (لا تمسح بيانات الترخيص — فقط إذا تعرف شنو تسوي)
    --keep-setting مفتاح               (استثناء من مسح الإعدادات الحساسة؛ يتكرر)
    --out مجلد_الخرج                   (الافتراضي: مجلد sealed بجانب المجلد المجهّز)
"""
import argparse
import getpass
import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

# ---------------------------------------------------------------- ما يُمسح من القاعدة (بيانات تشغيلية/مرضى)
WIPE_TABLES = [
    "whatsapp_sends", "visit_previous_merges", "visit_prev_prefs", "result_history", "results",
    "removed_order_tests", "report_row_notes", "saved_reports", "patient_followups", "payments", "invoices",
    "order_tests", "orders", "visits", "patients", "sample_counters", "portal_state",
    "audit_logs", "host_interface_log", "license_issue_log",
]
LICENSE_TABLES = ["license_info"]          # مربوطة بجهازك (hardware_id) — تُمسح افتراضيًا
# إعدادات تبقى لأنها تخص العميل نفسه
KEEP_SETTINGS = {"portal_api_key", "portal_url", "portal_mode", "portal_enabled", "github_read_token"}
SENSITIVE_RE = re.compile(r"(token|secret|api_?key|password|passwd|whatsapp|smtp)", re.I)
DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
DEFAULT_USERS = {"admin": "admin123", "rec": "rec123", "tech": "tech123", "super": "super123", "acc": "acc123"}
DEMO_USERS = ("rec", "tech", "super", "acc")
SEED_NAME_AR = "مختبر أمراض الدم التخصصي - د. ليث سلمان"

# ---------------------------------------------------------------- ما ينسخ من المجلد
EXCLUDE_DIRS = {"__pycache__", ".git", "sealed", "client_packages", "tools", "portal_pdf_cache", "venv", ".venv",
                ".idea", ".vscode", "node_modules"}
EXCLUDE_FILES = {"lis.db", "lis.db-journal", "lis.db-wal", "lis.db-shm", "portal_public.db", "portal_public.db-wal",
                 "portal_public.db-shm", "crash_log.txt", "error_log.txt", "server_log.txt", "server_log.old.txt",
                 "run_log.txt", "portal_preset.json", "portal_preset.applied.json", "INSTALL.bat",
                 "requirements.txt", "README_CLIENT.txt"}
EXCLUDE_SUFFIX = (".pyc", ".db-journal", ".log", ".zip")
EMPTY_DIRS = ("static/whatsapp_pdfs", "static/pdf_archive", "static/reports_pdf")   # ملفات PDF مرضى — تُترك فاضية

# اسم الاستيراد → اسم الحزمة بـpip (للي يختلفون)
PIP_NAMES = {"PIL": "pillow", "docx": "python-docx", "yaml": "pyyaml", "cv2": "opencv-python", "serial": "pyserial",
             "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "OpenSSL": "pyopenssl", "Crypto": "pycryptodome",
             "win32com": "pywin32", "win32api": "pywin32", "fitz": "pymupdf", "usb": "pyusb", "jwt": "pyjwt"}
SKIP_IMPORTS = {"markupsafe", "jinja2", "werkzeug", "itsdangerous", "click", "blinker"}      # تأتي مع Flask


def _sha(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


# ================================================================== القاعدة
def sanitize_db(src_db, dst_db, args):
    """نسخة متسقة (backup API يشتغل حتى لو البرنامج شغّال) ثم تنظيف. يرجّع تقرير نصي."""
    rep = []
    s = sqlite3.connect(src_db)
    d = sqlite3.connect(dst_db)
    s.backup(d)
    s.close()
    d.row_factory = sqlite3.Row
    d.execute("PRAGMA foreign_keys=OFF")
    tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    wiped = []
    for t in WIPE_TABLES + ([] if args.keep_license else LICENSE_TABLES):
        if t in tables:
            n = d.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            d.execute(f'DELETE FROM "{t}"')
            if "sqlite_sequence" in tables:
                d.execute("DELETE FROM sqlite_sequence WHERE name=?", (t,))
            if n:
                wiped.append(f"{t}={n}")
    rep.append("صفوف ممسوحة: " + (", ".join(wiped) if wiped else "لا شي (القاعدة كانت نظيفة)"))

    # إعدادات حساسة أو مسارات تخص جهازك
    cleared, kept = [], []
    if "settings" in tables:
        for r in d.execute("SELECT key, value FROM settings").fetchall():
            k, v = r["key"], (r["value"] or "")
            bad = (SENSITIVE_RE.search(k) and k not in KEEP_SETTINGS and k not in (args.keep_setting or [])) or \
                  bool(DRIVE_PATH_RE.match(v.strip()))
            if bad and v.strip():
                d.execute("UPDATE settings SET value='' WHERE key=?", (k,))
                cleared.append(k)
            elif SENSITIVE_RE.search(k) and v.strip():
                kept.append(k)
    rep.append("إعدادات حساسة/مسارات جهازك تم تفريغها: " + (", ".join(cleared) or "لا شي"))
    if kept:
        rep.append("إعدادات حساسة بقيت (تخص العميل أو استثنيتها): " + ", ".join(kept))

    # المستخدمون
    users_msgs = []
    if "users" in tables:
        if args.admin_password:
            d.execute("UPDATE users SET password_hash=? WHERE username='admin'", (_sha(args.admin_password),))
            users_msgs.append("تم تغيير كلمة سر admin")
        if args.deactivate_demo_users:
            d.execute(f"UPDATE users SET is_active=0 WHERE username IN ({','.join('?' * len(DEMO_USERS))})", DEMO_USERS)
            users_msgs.append("تم تعطيل المستخدمين التجريبيين " + "/".join(DEMO_USERS))
        weak = []
        for r in d.execute("SELECT username, password_hash, is_active FROM users").fetchall():
            dp = DEFAULT_USERS.get(r["username"])
            if dp and r["password_hash"] == _sha(dp) and r["is_active"]:
                weak.append(f"{r['username']}/{dp}")
        if weak:
            users_msgs.append("⚠ ما زالت كلمات السر الافتراضية فعّالة: " + ", ".join(weak))
    rep.extend(users_msgs)

    row = d.execute("SELECT value FROM settings WHERE key='app_name_ar'").fetchone() if "settings" in tables else None
    if not row or not (row[0] or "").strip():
        rep.append("⚠ اسم المختبر بالعربي (app_name_ar) فاضي!")
    elif row[0] == SEED_NAME_AR:
        rep.append("⚠ اسم المختبر ما زال الاسم الافتراضي للبرنامج، مو اسم العميل!")

    d.commit()
    d.execute("PRAGMA journal_mode=DELETE")     # ملف واحد بدون -wal
    d.execute("VACUUM")
    # فحص نهائي
    left = {}
    for t in ("patients", "visits", "orders", "order_tests", "results", "invoices", "payments"):
        if t in tables:
            n = d.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if n:
                left[t] = n
    d.close()
    if left:
        raise SystemExit(f"❌ بقيت بيانات مرضى بعد التنظيف: {left}")
    return rep


# ================================================================== requirements
def build_requirements(ws):
    import ast
    import importlib.metadata as md
    std = set(sys.stdlib_module_names)
    local = {os.path.splitext(f)[0] for f in os.listdir(ws) if f.endswith(".py")}
    mods = set()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS and x != "static"]
        for f in files:
            if f.endswith(".py"):
                try:
                    tree = ast.parse(open(os.path.join(root, f), encoding="utf-8").read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        mods.update(a.name.split(".")[0] for a in n.names)
                    elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                        mods.add(n.module.split(".")[0])
    third = sorted(m for m in mods if m not in std and m not in local and m not in SKIP_IMPORTS)
    lines, notes = [], []
    for m in third:
        pkg = PIP_NAMES.get(m, m)
        try:
            lines.append(f"{pkg}>={md.version(pkg)}")
        except md.PackageNotFoundError:
            # ما نكتبه بـrequirements: لو كان ملف ناقص من مجلد البرنامج أو اسم غير صحيح، pip عند العميل راح يفشل.
            notes.append(f"{pkg}: مستورد بالكود لكن مو ملف بمجلد البرنامج ولا حزمة مثبّتة عندك — تأكد أن ملفه موجود بالمجلد")
    if not any(l.lower().startswith("flask") for l in lines):
        lines.insert(0, "flask")
    return "\n".join(lines) + "\n", notes


# ================================================================== ملفات العميل
def install_bat(pyver):
    nodot = pyver.replace(".", "")
    t = r'''@echo off
setlocal EnableExtensions
title LIS Installer
rem One-click installer. Copies the program to C:\LIS, installs Python packages in a private venv,
rem installs Chromium (for PDF), creates the desktop shortcut + auto-start, then opens the program.
rem Needs internet the first time only. Keeps an existing database untouched when re-run.
set "TARGET=C:\LIS"
set "SRC=%~dp0"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

if /i not "%SRC%"=="%TARGET%" (
    echo Copying the program to %TARGET% ...
    if exist "%TARGET%\lis.db" (
        robocopy "%SRC%" "%TARGET%" /E /XF lis.db /NFL /NDL /NJH /NJS /NP >nul
    ) else (
        robocopy "%SRC%" "%TARGET%" /E /NFL /NDL /NJH /NJS /NP >nul
    )
    if errorlevel 8 (
        echo Copy failed. Please send a screenshot of this window.
        pause
        exit /b 1
    )
    call "%TARGET%\INSTALL.bat"
    exit /b
)
cd /d "%TARGET%"

echo.
echo [1/5] Looking for Python ...
set "PY="
where py >nul 2>nul && py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python not found. Installing Python @PYVER@ with winget, please wait ...
    winget install -e --id Python.Python.@PYVER@ --silent --accept-package-agreements --accept-source-agreements
    if exist "%LocalAppData%\Programs\Python\Python@NODOT@\python.exe" set PY="%LocalAppData%\Programs\Python\Python@NODOT@\python.exe"
)
if not defined PY (
    echo.
    echo Could not install Python automatically.
    echo Please install Python @PYVER@ from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
    echo then run INSTALL.bat again.
    pause
    exit /b 1
)

echo.
echo [2/5] Creating the private environment ...
if not exist "venv\Scripts\python.exe" %PY% -m venv venv
if not exist "venv\Scripts\python.exe" (
    echo Failed to create the environment.
    pause
    exit /b 1
)

echo.
echo [3/5] Installing packages (needs internet) ...
"venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package installation failed. Check the internet connection and run INSTALL.bat again.
    pause
    exit /b 1
)

echo.
echo [4/5] Installing Chromium for PDF reports (about 150 MB) ...
"venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 echo WARNING: Chromium download failed. The program works, but PDF export will not until you run INSTALL.bat again.

echo.
echo [5/5] Creating shortcuts and starting the program ...
call install_autostart.bat
call open_lab.bat
exit /b 0
'''
    t = t.replace("@PYVER@", pyver).replace("@NODOT@", nodot)
    t = "\r\n".join(t.split("\n"))
    t.encode("ascii")      # لازم ASCII صرف (نفس علة الملفات القديمة)
    return t


def readme_client(lab):
    return f"""تنصيب برنامج المختبر — {lab}
================================

1) فك الضغط عن الملف (كليك يمين ← Extract All) بأي مكان، مثلًا سطح المكتب.
2) اضغط مرتين على الملف  INSTALL.bat
   - أول مرة يحتاج إنترنت (تنزيل المكتبات وجزء PDF) ويأخذ بضع دقائق. لا تغلق النافذة السوداء.
   - يتنصب البرنامج بالمجلد C:\\LIS ويصير له اختصار على سطح المكتب ويشتغل تلقائيًا مع الويندوز.
3) بعد الانتهاء يفتح البرنامج لحاله. استخدم اسم المستخدم وكلمة السر اللي سلّمها لك المورّد.

ملاحظات
- تكدر تحذف المجلد المفكوك بعد التنصيب؛ البرنامج الأصلي صار بـC:\\LIS.
- إعادة تشغيل INSTALL.bat لاحقًا آمنة: ما تمسح قاعدة بياناتك.
- إذا ما فتح البرنامج، افتح الملف C:\\LIS\\server_log.txt وصوّر آخر الأسطر للمورّد.
"""


# ================================================================== التجميع
def collect_files(ws):
    for root, dirs, files in os.walk(ws):
        rel_root = os.path.relpath(root, ws).replace("\\", "/")
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        if any(rel_root == e or rel_root.startswith(e + "/") for e in EMPTY_DIRS):
            continue
        for f in files:
            if f in EXCLUDE_FILES or f.endswith(EXCLUDE_SUFFIX) or f.startswith("client_"):
                continue
            yield os.path.join(root, f), (f if rel_root == "." else rel_root + "/" + f)


def main():
    ap = argparse.ArgumentParser(description="ختم نسخة العميل وتجميعها بزيب تنصيب واحد")
    ap.add_argument("workspace", help="مجلد برنامج العميل المجهّز (فيه app.py و lis.db)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--admin-password", default=None)
    ap.add_argument("--deactivate-demo-users", action="store_true")
    ap.add_argument("--keep-license", action="store_true")
    ap.add_argument("--keep-setting", action="append", default=[])
    ap.add_argument("--python-version", default=f"{sys.version_info.major}.{sys.version_info.minor}",
                    help="إصدار بايثون اللي يثبّته INSTALL.bat إذا ما لقى بايثون (الافتراضي: نفس إصدار جهازك)")
    ap.add_argument("--yes", action="store_true", help="بدون أسئلة")
    args = ap.parse_args()

    ws = os.path.abspath(args.workspace)
    db_path = os.path.join(ws, "lis.db")
    if not (os.path.exists(os.path.join(ws, "app.py")) and os.path.exists(db_path)):
        sys.exit("❌ المجلد لازم يحتوي app.py و lis.db (شغّل البرنامج منه مرة وجهّزه أولًا).")

    if not args.admin_password and not args.yes and sys.stdin.isatty():
        p = getpass.getpass("كلمة سر جديدة لمستخدم admin عند العميل (Enter للإبقاء على الافتراضية): ")
        args.admin_password = p or None

    out_dir = os.path.abspath(args.out or os.path.join(os.path.dirname(ws), "sealed"))
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="lis_seal_")
    try:
        clean_db = os.path.join(tmp, "lis.db")
        report = sanitize_db(db_path, clean_db, args)
        reqs, req_notes = build_requirements(ws)

        con = sqlite3.connect(clean_db)
        row = con.execute("SELECT value FROM settings WHERE key='app_name'").fetchone()
        row_ar = con.execute("SELECT value FROM settings WHERE key='app_name_ar'").fetchone()
        con.close()
        lab_en = (row[0] if row and row[0] else "") or ""
        lab_ar = (row_ar[0] if row_ar and row_ar[0] else lab_en) or "Lab"
        slug = re.sub(r"[^A-Za-z0-9]+", "_", lab_en).strip("_") or "client"
        zip_path = os.path.join(out_dir, f"{slug}_Setup.zip")

        n = 0
        uploads = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full, arc in collect_files(ws):
                zf.write(full, arc)
                n += 1
                uploads += arc.startswith("static/uploads/")
            for e in EMPTY_DIRS:
                zf.writestr(e + "/.keep", "")
            zf.write(clean_db, "lis.db")
            zf.writestr("requirements.txt", reqs)
            zf.writestr("INSTALL.bat", install_bat(args.python_version))
            zf.writestr("README_CLIENT.txt", readme_client(lab_ar))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    size = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n✅ تم ختم نسخة العميل: {lab_ar}")
    print(f"   الملف: {zip_path}  ({size:.1f} MB، {n} ملف، منها {uploads} من static/uploads = شعار/أختام/صور)")
    print("\n— تقرير القاعدة —")
    for r in report:
        print("  •", r)
    print("\n— requirements.txt —")
    print("  " + reqs.replace("\n", "\n  ").rstrip())
    for nn in req_notes:
        print("  ⚠", nn)
    print(f"\nINSTALL.bat سيثبّت Python {args.python_version} تلقائيًا (winget) إذا ما لقاه عند العميل.")
    print("راجع التحذيرات ⚠ أعلاه قبل ما ترسل الملف للعميل.")


if __name__ == "__main__":
    main()
