# -*- coding: utf-8 -*-
r"""
make_client_links.py - يجهّز كل شي يخص عميل واحد: مفاتيح جديدة + ملفات الربط + أوامر السحابة.

الاستعمال:
    py tools\make_client_links.py --client Nour
    py tools\make_client_links.py --client Nour --ledger-url https://lab-ledger-nour.XXXX.workers.dev
    py tools\make_client_links.py --client Nour --ledger-url https://... --portal-url https://... --portal-key KEY

الناتج بالمجلد  client_links\<Client>\ :
    ledger_link.json         -> يوضع بجانب LabSystem_Setup.exe (فقط إذا أعطيت --ledger-url)
    portal_activation.json   -> يوضع بجانب LabSystem_Setup.exe. افتراضياً بوابة النتائج = نفس سحابة السجل ونفس المفتاح
                                (يُكتب تلقائياً مع --ledger-url). تعطي --portal-url/--portal-key فقط لو تريد بوابة منفصلة (مثلاً Render).
    cloud_setup.txt          -> أوامر إنشاء سحابة هذا العميل (D1 + secrets + نشر) بالترتيب
    wrangler.toml            -> نسخة خاصة بهذا العميل (database_id لازم تلصقه بعد أمر d1 create)
    PRIVATE_keys.txt         -> المفاتيح (لا ترسله لأحد، ولا ترفعه لأي مكان)

أول تشغيل لعميل يولّد مفاتيح جديدة؛ التشغيلات التالية لنفس العميل تبقي نفس المفاتيح (إلا إذا مرّرت --lis-key).
المفاتيح حروف/أرقام فقط (hex) فتنطبق عليها شروط البرنامج والسحابة (16 حرف على الأقل).
"""
import argparse
import json
import os
import re
import secrets
import sys


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "client"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--ledger-url", default="")
    ap.add_argument("--portal-url", default="")
    ap.add_argument("--portal-key", default="")
    ap.add_argument("--lis-key", default="")
    ap.add_argument("--out", default="client_links")
    a = ap.parse_args()

    sl = slug(a.client)
    folder = os.path.join(a.out, a.client)
    os.makedirs(folder, exist_ok=True)
    lis_key = re.sub(r"[^A-Za-z0-9_.\-]", "", a.lis_key) or secrets.token_hex(16)       # 32 حرف
    auth_secret = secrets.token_hex(24)                                                    # 48 حرف
    _pk = os.path.join(folder, "PRIVATE_keys.txt")
    if os.path.exists(_pk):          # إعادة تشغيل لنفس العميل: لا نغيّر المفاتيح اللي ممكن انحطت بالسحابة
        _t = open(_pk, encoding="utf-8").read()
        _m = re.search(r"^AUTH_SECRET: (\S+)", _t, re.M)
        if _m:
            auth_secret = _m.group(1)
        _m = re.search(r"^LIS_KEY: (\S+)", _t, re.M)
        if _m and not a.lis_key:
            lis_key = _m.group(1)
    if len(lis_key) < 16:
        sys.exit("ERROR: LIS_KEY لازم 16 حرف على الأقل")
    worker = "lab-ledger-" + sl
    made = []

    if a.ledger_url:
        u = a.ledger_url.strip().rstrip("/")
        if not u.lower().startswith("https://"):
            sys.exit("ERROR: --ledger-url لازم يبدأ بـ https://")
        with open(os.path.join(folder, "ledger_link.json"), "w", encoding="utf-8") as f:
            json.dump({"url": u, "key": lis_key}, f, ensure_ascii=False, indent=1)
        made.append("ledger_link.json")
    if a.ledger_url and not (a.portal_url or a.portal_key):      # بوابة النتائج داخل نفس الـWorker وبنفس المفتاح
        a.portal_url, a.portal_key = a.ledger_url, lis_key
    if a.portal_url or a.portal_key:
        pu, pk = a.portal_url.strip().rstrip("/"), a.portal_key.strip()
        if not (pu.lower().startswith("https://") and len(pk) >= 8):
            sys.exit("ERROR: للبوابة لازم --portal-url (https) و --portal-key (8 أحرف فأكثر)")
        with open(os.path.join(folder, "portal_activation.json"), "w", encoding="utf-8") as f:
            json.dump({"url": pu, "key": pk, "client": a.client}, f, ensure_ascii=False, indent=2)
        made.append("portal_activation.json")

    with open(os.path.join(folder, "wrangler.toml"), "w", encoding="utf-8") as f:
        f.write('name = "%s"\nmain = "src/worker.js"\ncompatibility_date = "2025-01-01"\n\n'
                '[assets]\ndirectory = "./public"\nbinding = "ASSETS"\nrun_worker_first = ["/api/*", "/r/*"]\n\n'
                '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "%s"\n'
                'database_id = "PUT_NEW_DATABASE_ID_HERE"\n' % (worker, worker))
    made.append("wrangler.toml")

    steps = (
        "سحابة العميل «%(c)s»  - نفّذ داخل مجلد lab-ledger-cloud، بهذا الترتيب:\n\n"
        "1) انسخ wrangler.toml من هذا المجلد فوق wrangler.toml الموجود (احتفظ بنسختك القديمة).\n"
        "   لا تبقي database_id الخاص بقاعدتك أنت، وإلا يشترك العميل بقاعدتك!\n\n"
        "2) npx wrangler d1 create %(w)s\n"
        "   انسخ قيمة database_id من الناتج والصقها بدل PUT_NEW_DATABASE_ID_HERE بملف wrangler.toml.\n\n"
        "3) المفاتيح (الصق القيمة من PRIVATE_keys.txt عندما يسأل):\n"
        "   npx wrangler secret put AUTH_SECRET\n"
        "   npx wrangler secret put LIS_KEY\n\n"
        "4) npx wrangler deploy\n"
        "   الرابط يظهر بآخر الناتج (https://%(w)s.<حسابك>.workers.dev).\n\n"
        "5) أعد تشغيل هذه الأداة بنفس العميل وبالرابط ومع --lis-key من PRIVATE_keys.txt حتى تنكتب ledger_link.json:\n"
        "   py tools\\make_client_links.py --client %(c)s --ledger-url https://%(w)s.XXXX.workers.dev --lis-key <LIS_KEY>\n\n"
        "6) أول مرة تدخل رابط السحابة بالمتصفح تسوي حساب مدير (/api/auth/setup)، والعميل يحتاج هذا الحساب لسجل المرضى.\n"
        "7) تحقق: افتح <الرابط>/api/ping لازم يرجع ok.\n"
        "   بوابة النتائج (QR المريض) بنفس الرابط ونفس LIS_KEY، فما تحتاج Render ولا مفتاح ثاني.\n\n"
        "ثم ضع ledger_link.json (و portal_activation.json إن وجد) بجانب LabSystem_Setup.exe وارسلها للعميل.\n"
    ) % {"c": a.client, "w": worker}
    with open(os.path.join(folder, "cloud_setup.txt"), "w", encoding="utf-8") as f:
        f.write(steps)
    made.append("cloud_setup.txt")

    with open(os.path.join(folder, "PRIVATE_keys.txt"), "w", encoding="utf-8") as f:
        f.write("Client: %s\nWorker name: %s\nLIS_KEY: %s\nAUTH_SECRET: %s\n" % (a.client, worker, lis_key, auth_secret))
        f.write("Portal key: %s\n" % (a.portal_key or "(not set)"))
    made.append("PRIVATE_keys.txt")

    print("OK -> %s" % os.path.abspath(folder))
    print("  " + "\n  ".join(made))
    print("LIS_KEY: %s" % lis_key)
    if not a.ledger_url:
        print("ملاحظة: ledger_link.json ما انكتب لأن --ledger-url ما انعطى. اقرأ cloud_setup.txt (الخطوة 5).")


if __name__ == "__main__":
    main()
