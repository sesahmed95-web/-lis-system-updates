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
        st = {r["key"]: r["value"] for r in con.execute(
            "SELECT key, value FROM settings WHERE key IN ('app_name','app_name_ar','lab_phone','lab_address','logo_path')")}
        cols = [r[1] for r in con.execute("PRAGMA table_info(examining_doctors_list)")]
        want = [c for c in ("name", "title", "degree_ar", "degree_en", "sort_order", "font_size") if c in cols]
        docs = [dict(r) for r in con.execute(
            "SELECT " + ", ".join(want) + " FROM examining_doctors_list WHERE show_on_letterhead=1 ORDER BY sort_order, id")]
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
    return st, docs, logo


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
            print(f"   -> found: {len(bdocs)} letterhead doctor(s), logo: {'yes' if blogo else 'NO (file not found)'}")
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

    settings = {
        "app_name_ar": name_ar, "app_name": name_en or name_ar,
        "lab_phone": phone, "lab_address": address,
        "portal_enabled": "1", "portal_mode": "remote", "portal_url": url,
        "portal_api_key": key, "portal_pdf_enabled": "1", "portal_default_hours": hours,
    }
    settings = {k: v for k, v in settings.items() if v != ""}
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name_en or url.split("//")[-1].split(".")[0]).strip("_") or "client"
    out_dir = os.path.join(os.path.expanduser("~"), "Documents", "LabClientPresets", slug)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "portal_preset.json")
    payload = {"settings": settings}
    if bdocs:
        payload["letterhead_doctors"] = bdocs
    if blogo:
        payload["logo"] = blogo
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
