# -*- coding: utf-8 -*-
r"""
make_client_installer.py  -  build a ONE-CLICK installer (LabSystem_Setup.exe) for a client
that carries ALL your customisations (lab name, logo, doctors/stamps, report designs,
normal ranges, custom units ...) with an EMPTY patient database.

Run it on the prepared client folder (a COPY of your program folder, not your working lab):
    python tools\make_client_installer.py "C:\Clients\Nour" --admin-password NEWPASS --deactivate-demo-users --yes

What it does (your folders are never modified):
  1) cleans a copy of lis.db  (uses seal_client_package.sanitize_db: patients/visits/results/invoices wiped,
     your device license wiped, secrets wiped, designer account replaced by a random one)
  2) copies the code to <out>\client_build\ , replacing the designer login written in database.py
  3) copies static\ but keeps ONLY logo / dashboard background / stamps from static\uploads
     (patient files, WhatsApp PDFs and your WhatsApp login (whatsapp_profile) are NOT copied)
  4) writes build_client.bat + installer_client.iss  (the .iss also installs the clean lis.db, only if the
     client has none yet - re-installing/updating never overwrites his data)
Then:  double-click  <out>\client_build\build_client.bat   ->  <out>\client_build\installer_output\LabSystem_Setup.exe
"""
import argparse, fnmatch, importlib.util, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("seal", os.path.join(HERE, "seal_client_package.py"))
seal = importlib.util.module_from_spec(spec); spec.loader.exec_module(seal)
for _f in ("scrub_designer_seed", "sanitize_db", "EXCLUDE_FILES"):
    if not hasattr(seal, _f):
        sys.exit("ERROR: tools\\seal_client_package.py is an OLD version (missing %s). Replace it with the seal_client_package.py from the zip." % _f)

SKIP_DIRS = {".git", "__pycache__", "build", "dist", "installer_output", "portal_pdf_cache", "whatsapp_profile", "tools",
             "sealed", "client_packages", "client_build", "venv", ".venv", ".idea", ".vscode", "node_modules"}
SKIP_FILES = set(seal.EXCLUDE_FILES) | {"local_config.py", ".gitignore", ".gitattributes", "build_client.bat", "installer_client.iss"}
SKIP_PATTERNS = ["*.bak*", "*.pyc", "*.log", "*.zip", "lis.db*", "*.db-wal", "*.db-shm", "- Copy.gitignore", "designer_login_PRIVATE.txt"]
STATIC_SKIP_DIRS = {"whatsapp_pdfs", "pdf_archive", "reports_pdf"}
UPLOAD_KEEP = ("logo*", "dashboard-bg*")          # files directly inside static/uploads
UPLOAD_KEEP_DIRS = {"stamps"}                      # folders inside static/uploads


def skip_file(n):
    return n in SKIP_FILES or any(fnmatch.fnmatch(n, p) for p in SKIP_PATTERNS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace"); ap.add_argument("--out", default=None)
    ap.add_argument("--admin-password"); ap.add_argument("--deactivate-demo-users", action="store_true")
    ap.add_argument("--keep-license", action="store_true"); ap.add_argument("--keep-designer", action="store_true")
    ap.add_argument("--keep-setting", action="append", default=[]); ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    if not (os.path.exists(os.path.join(ws, "app.py")) and os.path.exists(os.path.join(ws, "lis.db"))):
        sys.exit("ERROR: the folder must contain app.py and lis.db (the prepared client folder).")
    out = os.path.abspath(a.out or os.path.join(os.path.dirname(ws), "client_installer_" + os.path.basename(ws)))
    bld = os.path.join(out, "client_build")
    if os.path.exists(bld): shutil.rmtree(bld)
    os.makedirs(bld)

    # 1) database
    report = seal.sanitize_db(os.path.join(ws, "lis.db"), os.path.join(bld, "lis.db"), a)

    # 2+3) code and static
    n = 0; skipped_up = []
    for dp, dns, fns in os.walk(ws):
        rel = os.path.relpath(dp, ws); parts = [] if rel == "." else rel.replace("\\", "/").split("/")
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not (parts[:1] == ["static"] and d in STATIC_SKIP_DIRS)]
        in_up = parts[:2] == ["static", "uploads"]
        if parts == ["static", "uploads"]:
            dns[:] = [d for d in dns if d in UPLOAD_KEEP_DIRS]
        for fn in fns:
            if rel == "." and fn == "lis.db": continue
            if skip_file(fn): continue
            if parts == ["static", "uploads"] and not any(fnmatch.fnmatch(fn, p) for p in UPLOAD_KEEP):
                skipped_up.append(fn); continue
            dst = os.path.join(bld, rel if rel != "." else "", fn); os.makedirs(os.path.dirname(dst), exist_ok=True)
            full = os.path.join(dp, fn)
            if fn.endswith(".py") and not a.keep_designer and rel == ".":
                try: txt = open(full, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError): txt = None
                if txt and "INSERT INTO designer_account" in txt:
                    new, found = seal.scrub_designer_seed(txt)
                    if not found: sys.exit("ERROR: designer insert in %s not recognised - stopped, nothing built." % fn)
                    open(dst, "w", encoding="utf-8", newline="").write(new); n += 1; continue
            shutil.copy2(full, dst); n += 1
    # the build + installer expect icon\lab-icon.ico at the root; many projects keep it in static\icon
    ico = os.path.join(bld, "icon", "lab-icon.ico"); has_icon = os.path.exists(ico)
    if not has_icon:
        cands = [os.path.join(bld, "static", "icon", "lab-icon.ico")]
        for dp, dns, fns in os.walk(os.path.join(bld, "static")):
            cands += [os.path.join(dp, f) for f in fns if f.lower().endswith(".ico")]
        src_ico = next((c for c in cands if os.path.exists(c)), None)
        if src_ico:
            os.makedirs(os.path.dirname(ico), exist_ok=True); shutil.copy2(src_ico, ico); has_icon = True
            print("icon: copied %s -> icon\\lab-icon.ico" % os.path.relpath(src_ico, bld))
        else:
            print("WARNING: no .ico file found - the program is built without a custom icon.")
    for must in ("start_lab.vbs", "stop_lab.bat", "installer.iss", "build.bat"):
        if not os.path.exists(os.path.join(bld, must)): print("WARNING: %s is missing from the folder - the installer needs it." % must)

    # 4) build + installer scripts
    open(os.path.join(bld, "build_client.bat"), "w", encoding="ascii", newline="").write(BUILD_BAT)
    iss = open(os.path.join(bld, "installer.iss"), encoding="utf-8-sig").read() if os.path.exists(os.path.join(bld, "installer.iss")) else ""
    line = 'Source: "lis.db"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall'
    if "[Files]" not in iss: sys.exit("ERROR: installer.iss has no [Files] section.")
    if 'Source: "lis.db"' not in iss: iss = iss.replace("[Files]", "[Files]\r\n; client's prepared (empty of patients) database - never overwrites an existing one\r\n" + line, 1)
    if not has_icon: iss = re.sub(r"(?im)^SetupIconFile=.*\r?\n", "", iss)
    open(os.path.join(bld, "installer_client.iss"), "w", encoding="utf-8-sig", newline="").write(iss)

    print("\n".join(report)); print("\nOK: %d files in %s" % (n, bld))
    if skipped_up: print("NOT copied from static\\uploads (not logo/background/stamps): " + ", ".join(sorted(set(skipped_up))[:20]))
    print("Next: double-click build_client.bat inside client_build")


BUILD_BAT = r"""@echo off
setlocal
cd /d "%~dp0"
echo ==== 1/3 Tools ====
python -m pip install --upgrade pyinstaller
python -m pip install cryptography
if exist requirements.txt python -m pip install -r requirements.txt
echo ==== 2/3 Building LabSystem.exe ====
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
set ADD=--add-data "templates;templates" --add-data "static;static"
if exist icon set ADD=%ADD% --add-data "icon;icon"
if exist fonts set ADD=%ADD% --add-data "fonts;fonts"
set ICONARG=
if exist "icon\lab-icon.ico" set ICONARG=--icon "icon\lab-icon.ico"
python -m PyInstaller --noconfirm --clean --onedir --noconsole --name LabSystem %ICONARG% %ADD% app.py
if errorlevel 1 ( echo BUILD FAILED & if not defined LAB_NOPAUSE pause & exit /b 1 )
if exist VERSION copy /y VERSION dist\LabSystem\VERSION >nul
echo ==== 3/3 Installer ====
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" ( "%ISCC%" installer_client.iss ) else ( echo Inno Setup not found: open installer_client.iss in Inno Setup and press Ctrl+F9 )
echo Done. Setup file: installer_output\LabSystem_Setup.exe
if not defined LAB_NOPAUSE pause
"""
if __name__ == "__main__":
    main()
