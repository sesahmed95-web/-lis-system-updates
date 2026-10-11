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


def main():
    print("=== Portal preset maker ===  (you can type Arabic names; press Enter to skip optional questions)\n", flush=True)
    name_ar = ask("1) Lab name in ARABIC (optional, Enter to skip)")
    name_en = ask("2) Lab name in ENGLISH (optional)")
    phone = ask("3) Lab phone (optional)")
    address = ask("4) Lab address (optional)")
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
    with open(out, "w", encoding="utf-8") as fh:        # بدون BOM (json.load ما يقبل BOM)
        json.dump({"settings": settings}, fh, ensure_ascii=False, indent=2)
    print(f"\nDONE. File created:\n{out}")
    print("Copy it next to LabSystem_Setup.exe and send both to the client. (Do NOT upload to GitHub: it contains the secret key)")
    try:
        os.startfile(out_dir)           # يفتح المجلد (ويندوز)
    except Exception:
        pass


if __name__ == "__main__":
    main()
