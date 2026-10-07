# -*- coding: utf-8 -*-
"""
make_client_package.py — تجهيز نسخة البرنامج لعميل جديد (تشغّله أنت، مو العميل)
==============================================================================
يطلع زيب جاهز: اسم المختبر + رابط ومفتاح بوابة النتائج مضبوطين مسبقًا، وبدون أي بيانات من مختبرك
(لا قاعدة بيانات، لا مرضى، لا شعار/أختام، لا ملفات PDF قديمة).

التشغيل (من مجلد البرنامج):
    python tools/make_client_package.py
أو بدون أسئلة:
    python tools/make_client_package.py --name "مختبر النور" --url https://nour-lab.onrender.com

الخرج (بمجلد client_packages/):
    client_<اسم>.zip          ← هذا اللي ترسله للعميل
    client_<اسم>_RENDER.txt   ← للاحتفاظ بيه عندك فقط: القيم اللي تحطها بـRender (فيه المفتاح السري)
"""
import argparse
import json
import os
import re
import secrets
import sys
import zipfile
from datetime import datetime

SRC_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ملفات/مجلدات ما تروح للعميل أبدًا
EXCLUDE_DIRS = {"__pycache__", ".git", "client_packages", "tools", "portal_pdf_cache", ".idea", ".vscode"}
EXCLUDE_FILES = {
    "lis.db", "lis.db-journal", "lis.db-wal", "lis.db-shm", "portal_public.db",
    "crash_log.txt", "error_log.txt", "portal_preset.json", "portal_preset.applied.json",
}
EXCLUDE_SUFFIX = (".pyc", ".db-journal", ".log")
# محتويات هذي المجلدات بيانات مختبرك أنت (شعار، أختام، PDFات مرضى): نترك المجلد فاضي
EMPTY_DIRS = ("static/uploads", "static/whatsapp_pdfs", "static/pdf_archive", "static/reports_pdf")


def _ask(prompt, default=""):
    v = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    return v or default


def _slug(name_en, name_ar):
    base = re.sub(r"[^A-Za-z0-9]+", "_", name_en or "").strip("_")
    return base or "lab_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def build(src, name_ar, name_en, phone, address, url, key, retention, out_dir):
    slug = _slug(name_en, name_ar)
    preset = {"settings": {
        "app_name_ar": name_ar, "app_name": name_en or name_ar,
        "lab_phone": phone, "lab_address": address,
        "portal_enabled": "1", "portal_mode": "remote", "portal_url": url.rstrip("/"),
        "portal_api_key": key, "portal_pdf_enabled": "1",
    }}
    preset["settings"] = {k: v for k, v in preset["settings"].items() if v != ""}
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"client_{slug}.zip")
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src):
            rel_root = os.path.relpath(root, src).replace("\\", "/")
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            in_empty = any(rel_root == e or rel_root.startswith(e + "/") for e in EMPTY_DIRS)
            if in_empty:
                continue                                       # محتوى هذا المجلد يخص مختبرك: يُترك فاضي
            for f in files:
                if f in EXCLUDE_FILES or f.endswith(EXCLUDE_SUFFIX):
                    continue
                if f.startswith("client_") and f.endswith(".zip"):
                    continue
                zf.write(os.path.join(root, f), (f if rel_root == "." else rel_root + "/" + f))
                n += 1
        for e in EMPTY_DIRS:                                  # تأكد المجلدات موجودة حتى لو ما كانت بالمصدر
            zf.writestr(e + "/.keep", "")
        zf.writestr("portal_preset.json", json.dumps(preset, ensure_ascii=False, indent=2))
    info_path = os.path.join(out_dir, f"client_{slug}_RENDER.txt")
    with open(info_path, "w", encoding="utf-8") as fh:
        fh.write(f"""بيانات العميل: {name_ar}  ({datetime.now():%Y-%m-%d %H:%M})
==================================================
⚠ للاحتفاظ بها عندك فقط — لا ترسل هذا الملف للعميل.

الرابط العام للبوابة : {url}
المفتاح السري         : {key}

القيم اللي تضعها بخدمة Render الخاصة بالعميل (Environment Variables):
  API_SECRET_KEY    = {key}
  LAB_NAME          = {name_ar}
  TZ_OFFSET_HOURS   = 3
  (اختياري) RETENTION_DAYS = 30

ملف الزيب المرسل للعميل: {os.path.basename(zip_path)}
 - يحتوي portal_preset.json: عند أول تشغيل يضبط اسم المختبر وبوابة النتائج تلقائيًا ثم يُعاد تسميته.
 - بدون قاعدة بيانات: البرنامج ينشئ قاعدة جديدة فارغة عند أول تشغيل.
""")
    return zip_path, info_path, n


def main():
    ap = argparse.ArgumentParser(description="تجهيز نسخة البرنامج لعميل جديد")
    ap.add_argument("--src", default=SRC_DEFAULT, help="مجلد البرنامج (الافتراضي: المجلد الأب لـtools)")
    ap.add_argument("--name"); ap.add_argument("--name-en", default=None)
    ap.add_argument("--phone", default=None); ap.add_argument("--address", default=None)
    ap.add_argument("--url"); ap.add_argument("--key", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    interactive = not (a.name and a.url)
    name_ar = a.name or _ask("اسم المختبر بالعربي (يظهر لمرضاه بصفحة النتائج)")
    name_en = a.name_en if a.name_en is not None else (_ask("اسم المختبر بالإنجليزي (اختياري)") if interactive else "")
    phone = a.phone if a.phone is not None else (_ask("رقم هاتف المختبر (اختياري)") if interactive else "")
    address = a.address if a.address is not None else (_ask("عنوان المختبر (اختياري)") if interactive else "")
    url = (a.url or _ask("رابط بوابة Render لهذا العميل (https://xxxx.onrender.com)")).strip()
    if not name_ar:
        sys.exit("❌ اسم المختبر مطلوب.")
    if not url.startswith("https://"):
        sys.exit("❌ الرابط لازم يبدأ بـ https://")
    key = a.key or secrets.token_urlsafe(32)
    out_dir = a.out or os.path.join(a.src, "client_packages")
    zip_path, info_path, n = build(a.src, name_ar, name_en, phone, address, url, key, None, out_dir)
    print(f"\n✅ تم: {n} ملف")
    print(f"   للعميل : {zip_path}")
    print(f"   لك أنت : {info_path}   ← فيه المفتاح السري لتضعه بـRender")
    print(f"\nالمفتاح السري (ضعه بـRender كـ API_SECRET_KEY):\n{key}\n")


if __name__ == "__main__":
    main()
