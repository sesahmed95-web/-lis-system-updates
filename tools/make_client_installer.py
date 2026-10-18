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
import argparse, base64, fnmatch, importlib.util, json, os, re, shutil, sqlite3, sys, tempfile

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
SENSITIVE = re.compile(r"(token|secret|api_?key|password|passwd|whatsapp|smtp)", re.I)
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

    # ملفات static/uploads المشار إليها بأي إعداد (شعار، خلفية الرئيسية، صور الشاشة الأولى...) تُنسخ كلها
    keep_names = set()
    try:
        _c = sqlite3.connect(os.path.join(bld, "lis.db"))
        for (_k, _v) in _c.execute("SELECT key, value FROM settings"):
            _v = (_v or "").strip().replace("\\", "/")
            if _v.startswith("uploads/") and "/" not in _v[len("uploads/"):] and not SENSITIVE.search(_k or ""):
                keep_names.add(_v[len("uploads/"):])
        _c.close()
    except Exception as _e:
        print("WARNING: could not read upload names from settings:", _e)
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
            if parts == ["static", "uploads"] and fn not in keep_names and not any(fnmatch.fnmatch(fn, p) for p in UPLOAD_KEEP):
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

    # 3b) branding preset (شعار + أطباء الترويسة بشهاداتهم + تصاميم + صور الشاشة الرئيسية) داخل الـSetup نفسه.
    #     يُطبَّق عند أول تشغيل مرة وحدة بكل جهاز حتى لو كان عند العميل lis.db قديم (الـSetup ما يبدّل قاعدة موجودة).
    try:
        pre_msg = build_branding_preset(bld)
    except Exception as e:
        pre_msg = "WARNING: branding preset not created: %r" % (e,)
    print(pre_msg)

    # 4) build + installer scripts
    open(os.path.join(bld, "build_client.bat"), "w", encoding="ascii", newline="").write(BUILD_BAT)
    iss = open(os.path.join(bld, "installer.iss"), encoding="utf-8-sig").read() if os.path.exists(os.path.join(bld, "installer.iss")) else ""
    line = 'Source: "lis.db"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall'
    if "[Files]" not in iss: sys.exit("ERROR: installer.iss has no [Files] section.")
    if 'Source: "lis.db"' not in iss: iss = iss.replace("[Files]", "[Files]\r\n; client's prepared (empty of patients) database - never overwrites an existing one\r\n" + line, 1)
    if os.path.exists(os.path.join(bld, "portal_preset.json")) and "LisPresetNotApplied" not in iss:
        pl = 'Source: "portal_preset.json"; DestDir: "{app}"; Flags: ignoreversion; Check: LisPresetNotApplied'
        iss = iss.replace("[Files]", "[Files]\r\n; branding (logo, doctors' degrees, report design): applied once per computer\r\n" + pl, 1)
        fn = ("\r\nfunction LisPresetNotApplied: Boolean;\r\nbegin\r\n"
              "  Result := not FileExists(ExpandConstant('{app}\\portal_preset.applied.json'));\r\nend;\r\n")
        iss = (iss.replace("[Code]", "[Code]" + fn, 1) if "[Code]" in iss else iss + "\r\n[Code]" + fn)
    if not has_icon: iss = re.sub(r"(?im)^SetupIconFile=.*\r?\n", "", iss)
    open(os.path.join(bld, "installer_client.iss"), "w", encoding="utf-8-sig", newline="").write(iss)

    print("\n".join(report)); print("\nOK: %d files in %s" % (n, bld))
    if skipped_up: print("NOT copied from static\\uploads (not logo/background/stamps): " + ", ".join(sorted(set(skipped_up))[:20]))
    print("Next: double-click build_client.bat inside client_build")


DESIGN_KEYS = (
    "result_layout_json", "combined_panel_group_order", "results_entry_test_order",
    "logo_width", "logo_position", "letterhead_font_size", "letterhead_font_family",
    "report_underline_style", "report_row_pad", "report_col_pad", "test_name_font_size", "result_value_font_size",
    "show_result_flag", "flag_color_low", "flag_color_high", "conclusion_marker_colors",
    "patient_info_top_gap", "patient_info_row_gap", "patient_info_label_width", "patient_info_col_gap",
    "barcode_test_names_mode", "barcode_show_lab_name", "vb_names_mode", "theme_primary_color", "theme_page_bg_color",
    "report_header_style", "report_header_accent", "report_header_subtitle",
    "dashboard_bg_path", "dashboard_bg_overlay_opacity", "dashboard_bg_blur", "dashboard_bg_position",
    "dashboard_bg_size_mode", "dashboard_bg_size_percent", "dashboard_overlay_color",
    "dashboard_bg_brightness", "dashboard_hero_text_color",
    "exam_abnormal_red", "report_design_exam", "report_design_coag", "auto_flag_color_enabled", "label_layout_tube",
    "label_layout_request", "barcode_copies", "barcode_group_mode", "known_analyzers", "whatsapp_country_code",
    "landing_title", "landing_title_en", "landing_bg_banner_size", "landing_bg_logo_size", "landing_bg_overlay_opacity",
    "landing_bg_position", "landing_bg_shape", "landing_image_opacity", "landing_image_position", "landing_image_shape",
    "landing_gradient_color", "landing_bg_image_path", "landing_bglogo_image_path", "landing_lab_image_path",
    "landing_reception_image_path", "landing_together_image_path",
)


def build_branding_preset(bld):
    """يقرأ النسخة المنظَّفة bld/lis.db + bld/static/uploads ويكتب bld/portal_preset.json (بدون أي توكن/باسورد/مفتاح بوابة)."""
    con = sqlite3.connect(os.path.join(bld, "lis.db")); con.row_factory = sqlite3.Row
    try:
        keys = ("app_name", "app_name_ar", "lab_phone", "lab_address", "logo_path") + DESIGN_KEYS
        st = {r["key"]: r["value"] for r in con.execute(
            "SELECT key, value FROM settings WHERE key IN (%s)" % ",".join("?" * len(keys)), keys)}
        cols = [r[1] for r in con.execute("PRAGMA table_info(examining_doctors_list)")]
        want = [c for c in ("name", "title", "degree_ar", "degree_en", "sort_order", "font_size") if c in cols]
        docs = [dict(r) for r in con.execute("SELECT " + ", ".join(want) +
                " FROM examining_doctors_list WHERE show_on_letterhead=1 ORDER BY sort_order, id")] if "name" in want else []
        tcols = [r[1] for r in con.execute("PRAGMA table_info(test_definitions)")]
        tw = [c for c in ("code", "report_group", "panel_color", "panel_page_break", "row_spacing", "done_by_note") if c in tcols]
        tds = [dict(r) for r in con.execute("SELECT " + ", ".join(tw) + " FROM test_definitions")] if len(tw) > 1 else []
    finally:
        con.close()
    up = os.path.join(bld, "static")
    def _b64(rel):
        fp = os.path.join(up, rel.replace("/", os.sep))
        if os.path.isfile(fp) and os.path.getsize(fp) <= 3 * 1024 * 1024:
            with open(fp, "rb") as fh:
                return {"filename": os.path.basename(fp), "b64": base64.b64encode(fh.read()).decode("ascii")}
        return None
    settings = {k: v for k, v in st.items() if k != "logo_path" and (v or "").strip()}
    pre = {"settings": settings, "letterhead_doctors": docs, "test_designs": tds}
    logo = _b64(st.get("logo_path") or "") if (st.get("logo_path") or "").strip() else None
    if logo: pre["logo"] = logo
    files, seen = [], set()
    for k in DESIGN_KEYS:
        if k.endswith("_path") and (st.get(k) or "").strip() not in ("", "-"):
            f = _b64(st[k])
            if f and f["filename"] not in seen:
                files.append(f); seen.add(f["filename"])
    if files: pre["files"] = files
    with open(os.path.join(bld, "portal_preset.json"), "w", encoding="utf-8") as fh:
        json.dump(pre, fh, ensure_ascii=False)
    withdeg = sum(1 for d in docs if d.get("degree_ar") or d.get("degree_en"))
    return ("branding preset: logo=%s, doctors=%d (with degrees: %d), extra images=%d, design settings=%d"
            % ("YES" if logo else "NO (logo file not found!)", len(docs), withdeg, len(files), len(settings)))


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
