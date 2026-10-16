# -*- coding: utf-8 -*-
"""
make_portal_preset.py — يسوّي ملف portal_preset.json لعميل معيّن (رابط البوابة + المفتاح + اسم المختبر).

الاستخدام: دبل كليك على make_portal_preset.bat (أو: python tools/make_portal_preset.py)
يسألك عن البيانات ويكتب portal_preset.json داخل  Documents\\LabClientPresets\\<اسم العميل>\\
(خارج مجلد المشروع عمدًا حتى ما يظهر بـ GitHub Desktop ويتحمّل بالغلط وفيه المفتاح السري).

بعدها: انسخ portal_preset.json جنب LabSystem_Setup.exe (مجلد installer_output) وأرسلهم للعميل. المثبّت ينسخ الملف لمجلد البرنامج،
والبرنامج يطبّقه عند أول تشغيل (ويحوّله لـ portal_preset.applied.json).
مهم: الملف فيه المفتاح السري — لا ترفعه على GitHub ولا ترسله لغير العميل صاحبه.
"""
import json
import os
import sys


# إعدادات تصميم التقارير/ترتيبها اللي تنتقل للعميل (نفس _PRESET_KEYS بـ database.py، بدون أي كلمة مرور/توكن).
DESIGN_KEYS = (
    "result_layout_json", "combined_panel_group_order", "results_entry_test_order",
    "logo_width", "logo_position", "letterhead_font_size", "letterhead_font_family",
    "report_underline_style", "report_row_pad", "report_col_pad",
    "test_name_font_size", "result_value_font_size", "show_result_flag",
    "flag_color_low", "flag_color_high", "conclusion_marker_colors",
    "patient_info_top_gap", "patient_info_row_gap", "patient_info_label_width", "patient_info_col_gap",
    "barcode_test_names_mode", "barcode_show_lab_name", "vb_names_mode",
    "theme_primary_color", "theme_page_bg_color",
    # الشاشة الرئيسية: صورة الخلفية (الشعار الكبير) + ضبطها
    "dashboard_bg_path", "dashboard_bg_overlay_opacity", "dashboard_bg_blur", "dashboard_bg_position",
    "dashboard_bg_size_mode", "dashboard_bg_size_percent", "dashboard_overlay_color",
    "dashboard_bg_brightness", "dashboard_hero_text_color",
    # v51: تصميم GUE/GSE/SFA + تلوين الأحمر + الملصقات + الشاشة الأولى (landing) — كله ينتقل للعميل
    "exam_abnormal_red", "report_design_exam", "report_design_coag", "auto_flag_color_enabled", "label_layout_tube", "label_layout_request", "barcode_copies", "barcode_group_mode", "known_analyzers", "whatsapp_country_code", "landing_title", "landing_title_en", "landing_bg_banner_size", "landing_bg_logo_size", "landing_bg_overlay_opacity", "landing_bg_position", "landing_bg_shape", "landing_image_opacity", "landing_image_position", "landing_image_shape", "landing_gradient_color", "landing_bg_image_path", "landing_bglogo_image_path", "landing_lab_image_path", "landing_reception_image_path", "landing_together_image_path"
)
TEST_DESIGN_COLS = ("report_group", "panel_color", "panel_page_break", "row_spacing", "done_by_note")


def ask(prompt, default=""):
    v = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    return v or default


def read_branding(db_path, project_dir):
    """يقرأ من lis.db (قراءة فقط): أسماء المختبر + أطباء ترويسة التقارير بشهاداتهم + ملف الشعار."""
    import base64
    import sqlite3
    con = sqlite3.connect("file:" + db_path.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        _keys = ("app_name", "app_name_ar", "lab_phone", "lab_address", "logo_path") + DESIGN_KEYS
        st = {r["key"]: r["value"] for r in con.execute(
            "SELECT key, value FROM settings WHERE key IN (" + ",".join("?" * len(_keys)) + ")", _keys)}
        tcols = [r[1] for r in con.execute("PRAGMA table_info(test_definitions)")]
        twant = [c for c in ("code",) + TEST_DESIGN_COLS if c in tcols]
        test_designs = [dict(r) for r in con.execute("SELECT " + ", ".join(twant) + " FROM test_definitions")] \
            if "code" in twant and len(twant) > 1 else []
        cols = [r[1] for r in con.execute("PRAGMA table_info(examining_doctors_list)")]
        want = [c for c in ("name", "title", "degree_ar", "degree_en", "sort_order", "font_size") if c in cols]
        docs = [dict(r) for r in con.execute(
            "SELECT " + ", ".join(want) + " FROM examining_doctors_list WHERE show_on_letterhead=1 ORDER BY sort_order, id")]
        try:
            lay = [dict(r) for r in con.execute(
                "SELECT td.code AS code, o.layout_json AS layout_json FROM report_layout_overrides o "
                "JOIN test_definitions td ON td.id=o.scope_id WHERE o.scope='test'")]
        except Exception:
            lay = []
        try:
            rcols = [r[1] for r in con.execute("PRAGMA table_info(report_templates)")]
            rsel = [c for c in ("heading", "rows_json", "heading_align", "rows_align") if c in rcols]
            rts = [dict(r) for r in con.execute(
                "SELECT td.code AS code, " + ", ".join("t." + c for c in rsel) + " FROM report_templates t "
                "JOIN test_definitions td ON td.id=t.test_definition_id")] if rsel else []
        except Exception:
            rts = []
    finally:
        con.close()
    logo = None
    lp = (st.get("logo_path") or "").strip()
    if lp:
        for base in (os.path.join(project_dir, "static"), os.path.join(os.path.dirname(db_path), "static")):
            fp = os.path.join(base, lp.replace("/", os.sep))
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    logo = {"filename": os.path.basename(fp), "b64": base64.b64encode(fh.read()).decode("ascii")}
                break
    st["__test_designs__"] = test_designs
    st["__layouts__"] = lay
    st["__templates__"] = rts
    # ملفات إضافية (صورة خلفية الشاشة الرئيسية)
    files = []
    bp = (st.get("dashboard_bg_path") or "").strip()
    if bp and bp != "-":
        for base in (os.path.join(project_dir, "static"), os.path.join(os.path.dirname(db_path), "static")):
            fp = os.path.join(base, bp.replace("/", os.sep))
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    files.append({"filename": os.path.basename(fp), "b64": base64.b64encode(fh.read()).decode("ascii")})
                break
    # صور إضافية: كل إعداد ينتهي بـ _path (الشاشة الأولى/الرئيسية) غير الشعار
    seen = {f["filename"] for f in files}
    for k in DESIGN_KEYS:
        if not k.endswith("_path") or k == "dashboard_bg_path":
            continue
        pv = (st.get(k) or "").strip()
        if not pv or pv == "-":
            continue
        for base in (os.path.join(project_dir, "static"), os.path.join(os.path.dirname(db_path), "static")):
            fp = os.path.join(base, pv.replace("/", os.sep))
            if os.path.isfile(fp) and os.path.basename(fp) not in seen:
                with open(fp, "rb") as fh:
                    files.append({"filename": os.path.basename(fp), "b64": base64.b64encode(fh.read()).decode("ascii")})
                seen.add(os.path.basename(fp))
                break
    st["__files__"] = files
    return st, docs, logo


def read_catalog(db_path):
    """يقرأ من lis.db (قراءة فقط) كتالوج التحاليل: أسعار + باراميترات + مدايات مرجعية + اقتراحات + باقات + إضافة سريعة + أجور الفاحص."""
    import sqlite3
    con = sqlite3.connect("file:" + db_path.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    try:
        code_of = {}
        tests = []
        sec_name = {}
        sections = []
        if "sections" in names:
            for r in con.execute("SELECT * FROM sections"):
                sec_name[r["id"]] = r["name"]
            for r in con.execute("SELECT * FROM sections ORDER BY sort_order, id"):
                sections.append({"name": r["name"], "parent_name": sec_name.get(r["parent_id"]),
                                 "dept_name": r["dept_name"], "sort_order": r["sort_order"]})
        for r in con.execute("SELECT * FROM test_definitions"):
            d = dict(r)
            code_of[d["id"]] = d["code"]
            d.pop("id", None)
            d["section_name"] = sec_name.get(d.pop("section_id", None))
            tests.append(d)
        params = []
        pid_map = {}
        for r in con.execute("SELECT * FROM test_parameters ORDER BY test_definition_id, id"):
            d = dict(r)
            pid_map[d["id"]] = d
            d["test_code"] = code_of.get(d.pop("test_definition_id"))
            d["ranges"] = []
            d["suggestions"] = []
            params.append(d)
        for r in con.execute("SELECT * FROM reference_ranges"):
            d = dict(r)
            p = pid_map.get(d.pop("test_parameter_id"))
            d.pop("id", None)
            if p is not None:
                p["ranges"].append(d)
        if "suggestions" in names:
            for r in con.execute("SELECT test_parameter_id, content FROM suggestions"):
                p = pid_map.get(r["test_parameter_id"])
                if p is not None:
                    p["suggestions"].append(r["content"])
        for d in params:
            d.pop("id", None)
        pkgs = []
        if "packages" in names:
            for r in con.execute("SELECT * FROM packages"):
                d = dict(r)
                d["tests"] = [code_of.get(x["test_definition_id"]) for x in con.execute(
                    "SELECT test_definition_id FROM package_tests WHERE package_id=?", (d.pop("id"),))]
                d["tests"] = [c for c in d["tests"] if c]
                pkgs.append(d)
        quick = []
        if "quick_add_items" in names:
            quick = [{"code": code_of.get(r["test_definition_id"]), "display_order": r["display_order"], "is_active": r["is_active"]}
                     for r in con.execute("SELECT * FROM quick_add_items ORDER BY display_order") if code_of.get(r["test_definition_id"])]
        rates = []
        if "examining_doctor_rates" in names:
            rates = [{"doctor_name": r["doctor_name"], "code": code_of.get(r["test_definition_id"]), "rate": r["rate"]}
                     for r in con.execute("SELECT * FROM examining_doctor_rates") if code_of.get(r["test_definition_id"])]
        return {"sections": sections, "tests": tests, "parameters": params, "packages": pkgs, "quick_add": quick, "examining_rates": rates}
    finally:
        con.close()


def read_users(db_path):
    import sqlite3
    con = sqlite3.connect("file:" + db_path.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT username, full_name, role, is_active FROM users WHERE username NOT LIKE '\\_\\_interface\\_%' ESCAPE '\\' ORDER BY id")]
    finally:
        con.close()


def main():
    print("=== Portal preset maker ===  (you can type Arabic names; press Enter to skip optional questions)\n", flush=True)
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_db = os.path.join(project_dir, "lis.db")
    src = ask("0) Copy lab names + report doctors (with certificates) + logo from a lis.db?\n"
              "   Enter = this project's lis.db | type a full path | n = skip",
              default_db if os.path.isfile(default_db) else "n")
    bst, bdocs, blogo = {}, [], None
    if src.lower() not in ("n", "no", ""):
        try:
            bst, bdocs, blogo = read_branding(src, project_dir)
            print(f"   -> found: {len(bdocs)} letterhead doctor(s), logo: {'yes' if blogo else 'NO (file not found)'}, "
                  f"report design settings: {sum(1 for k in DESIGN_KEYS if bst.get(k) not in (None, ''))}, "
                  f"test designs: {len(bst.get('__test_designs__', []))}")
        except Exception as e:      # قاعدة مقفلة/مسار خطأ: نكمل بدون
            print("   (could not read that database:", type(e).__name__, e, ") - close the program and try again, or continue without it")
    name_ar = ask("1) Lab name in ARABIC (optional)", bst.get("app_name_ar", "") or "")
    name_en = ask("2) Lab name in ENGLISH (optional)", bst.get("app_name", "") or "")
    phone = ask("3) Lab phone (optional)", bst.get("lab_phone", "") or "")
    address = ask("4) Lab address (optional)", bst.get("lab_address", "") or "")
    url = ask("5) Portal URL (https://....workers.dev)").rstrip("/")
    if not url.startswith("https://"):
        sys.exit("ERROR: the portal URL must start with https://")
    key = ask("6) Secret key (paste from INFO.txt)").replace(" ", "")
    if len(key) < 16:
        sys.exit("ERROR: the key is empty or too short - paste the full key from INFO.txt")
    hours = ask("7) Default expected time in hours", "1.5")
    catalog, users = None, None
    if src.lower() not in ("n", "no", ""):
        if ask("8) Copy test PRICES + reference ranges + parameters + packages + quick-add? (client can still edit) [Y/n]", "Y").lower() not in ("n", "no"):
            try:
                catalog = read_catalog(src)
                print(f"   -> {len(catalog['tests'])} tests, {len(catalog['parameters'])} parameters, "
                      f"{sum(len(p['ranges']) for p in catalog['parameters'])} ranges, {len(catalog['packages'])} packages")
            except Exception as e:
                print("   (could not read catalog:", type(e).__name__, e, ")")
        tmp = ask("9) Copy user accounts? Type ONE temporary password for all of them (client changes later) | Enter = skip", "")
        if tmp:
            try:
                sys.path.insert(0, project_dir)
                from database import hash_password
                ulist = read_users(src)
                h = hash_password(tmp)
                users = [dict(u, password_hash=h) for u in ulist]
                print(f"   -> {len(users)} user account(s): " + ", ".join(u['username'] for u in users))
            except Exception as e:
                print("   (could not read users:", type(e).__name__, e, ")")

    settings = {
        "app_name_ar": name_ar, "app_name": name_en or name_ar,
        "lab_phone": phone, "lab_address": address,
        "portal_enabled": "1", "portal_mode": "remote", "portal_url": url,
        "portal_api_key": key, "portal_pdf_enabled": "1", "portal_default_hours": hours,
    }
    for k in DESIGN_KEYS:                      # تصميم التقارير + الترتيب من lis.db (إن اخترت نسخها)
        if bst.get(k) not in (None, ""):
            settings[k] = bst[k]
    settings = {k: v for k, v in settings.items() if v != ""}
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name_en or url.split("//")[-1].split(".")[0]).strip("_") or "client"
    out_dir = os.path.join(os.path.expanduser("~"), "Documents", "LabClientPresets", slug)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "portal_preset.json")
    payload = {"settings": settings}
    if bst.get("__test_designs__"):
        payload["test_designs"] = bst["__test_designs__"]
    if bst.get("__layouts__"):
        payload["layout_overrides"] = bst["__layouts__"]
    if bst.get("__templates__"):
        payload["report_templates"] = bst["__templates__"]
    if catalog:
        payload["catalog"] = catalog
    if users:
        payload["users"] = users
    if bdocs:
        payload["letterhead_doctors"] = bdocs
    if blogo:
        payload["logo"] = blogo
    if bst.get("__files__"):
        payload["files"] = bst["__files__"]
    with open(out, "w", encoding="utf-8") as fh:        # بدون BOM (json.load ما يقبل BOM)
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nDONE. File created:\n{out}")
    print("Copy it next to LabSystem_Setup.exe and send both to the client. (Do NOT upload to GitHub: it contains the secret key)")
    try:
        os.startfile(out_dir)           # يفتح المجلد (ويندوز)
    except Exception:
        pass


if __name__ == "__main__":
    main()
