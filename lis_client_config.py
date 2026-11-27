# -*- coding: utf-8 -*-
"""
lis_client_config.py - «ملف تهيئة العميل»: ينقل مفتاح الربط (سجل المرضى) ومفتاح البوابة (نتائج المريض بالباركود)
ومفتاح الذكاء الاصطناعي وتصميم التقارير من جهازك إلى جهاز العميل، فلا يدخلها العميل ولا تتغير عنده.

  - التصدير: LIS ← الإعدادات ← «تهيئة العميل»  (/management/client-config)  → ملف مشفّر .lcc بكلمة سر تختارها.
  - الاستيراد: من نفس الصفحة عند العميل (يرفع الملف + كلمة السر).
  - تلقائي: ضع الملف client_config.json (غير مشفّر) بجانب app.py وقت التنصيب؛ يُطبَّق مرة واحدة عند أول تشغيل
    ثم يُحذف الملف (لأنه يحوي مفاتيح). التطبيق التلقائي يملأ الفارغ فقط ولا يستبدل شيئاً مضبوطاً.
  - الاستيراد اليدوي يملأ الفارغ فقط إلا إذا اخترت «استبدال الموجود».
التشفير: مفتاح من كلمة السر بـ PBKDF2-SHA256 (200 ألف دورة) + تيار HMAC-SHA256 + توقيع تحقق؛ أي كلمة سر خاطئة أو ملف معدَّل يُرفض.
"""
import base64, hashlib, hmac, io, json, os, re, secrets, time
from datetime import datetime

FORMAT = "lis-client-config-v1"
_HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_FILE = os.path.join(_HERE, "client_config.json")

GROUPS = [
    ("link", "مفتاح الربط بسجل المرضى", lambda k: k in ("ledger_url", "ledger_key", "ledger_enabled")),
    ("gateway", "مفتاح البوابة (نتائج المريض بالباركود)", lambda k: k.startswith("portal_") and k != "portal_remote_synced"),
    ("ai", "مفاتيح الذكاء الاصطناعي", lambda k: k.startswith("ai_")),
    ("design", "تصميم التقارير والنتائج", lambda k: (k.startswith(("report_", "result_", "results_", "patient_info_", "barcode_")) and not k.endswith("_path"))),
    ("identity", "اسم المختبر وبياناته", lambda k: k in ("app_name", "app_name_ar", "lab_name", "lab_address", "lab_phone", "lab_email", "lab_footer")),
]
SECRET_HINT = ("key", "token", "pass", "secret")


def _all_settings(db):
    return {r[0]: r[1] for r in db.execute("SELECT key, value FROM settings").fetchall()}


def collect(db, groups):
    st = _all_settings(db)
    out = {}
    for gid, _label, pred in GROUPS:
        if gid in groups:
            for k, v in st.items():
                if pred(k) and v not in (None, ""):
                    out[k] = v
    return out


# ---------------------------------------------------------------- تشفير الملف
def _derive(passphrase, salt):
    k = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 200000, 64)
    return k[:32], k[32:]


def _stream(ek, nonce, n):
    out, i = b"", 0
    while len(out) < n:
        out += hmac.new(ek, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return out[:n]


def encrypt_config(settings, passphrase, meta=None):
    if len(passphrase or "") < 4:
        raise ValueError("كلمة سر الملف 4 خانات على الأقل")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    ek, mk = _derive(passphrase, salt)
    raw = json.dumps({"settings": settings, "meta": meta or {}}, ensure_ascii=False).encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(raw, _stream(ek, nonce, len(raw))))
    mac = hmac.new(mk, salt + nonce + ct, hashlib.sha256).digest()
    b = lambda x: base64.b64encode(x).decode("ascii")
    return json.dumps({"format": FORMAT, "enc": True, "salt": b(salt), "nonce": b(nonce), "ct": b(ct), "mac": b(mac)})


def decrypt_config(text, passphrase):
    d = json.loads(text)
    if d.get("format") != FORMAT:
        raise ValueError("الملف ليس ملف تهيئة عميل صالحاً")
    if not d.get("enc"):
        return d.get("settings") or {}
    salt, nonce, ct, mac = (base64.b64decode(d[k]) for k in ("salt", "nonce", "ct", "mac"))
    ek, mk = _derive(passphrase or "", salt)
    if not hmac.compare_digest(mac, hmac.new(mk, salt + nonce + ct, hashlib.sha256).digest()):
        raise ValueError("كلمة السر خاطئة أو الملف تالف")
    raw = bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct))))
    return json.loads(raw.decode("utf-8")).get("settings") or {}


# ---------------------------------------------------------------- التطبيق
def apply_settings(db, set_setting, incoming, overwrite=False):
    cur = _all_settings(db)
    done = skipped = 0
    for k, v in (incoming or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9_]{1,80}", str(k)) or not any(p(k) for _g, _l, p in GROUPS):
            skipped += 1
            continue
        if not overwrite and cur.get(k) not in (None, ""):
            skipped += 1
            continue
        set_setting(db, k, v)
        done += 1
    db.commit()
    return done, skipped


def auto_apply(get_db, set_setting, log=print):
    """تهيئة تلقائية لمرة واحدة: client_config.json بجانب app.py (يملأ الفارغ فقط ثم يُحذف)."""
    if not os.path.exists(AUTO_FILE):
        return
    try:
        d = json.load(io.open(AUTO_FILE, encoding="utf-8"))
        if d.get("format") != FORMAT or d.get("enc"):
            log("client_config.json: صيغة غير صالحة للتطبيق التلقائي (يجب غير مشفّر)")
            return
        db = get_db()
        n, s = apply_settings(db, set_setting, d.get("settings") or {}, overwrite=False)
        try:
            size = os.path.getsize(AUTO_FILE)
            with open(AUTO_FILE, "r+b") as f:       # نمسح محتواه قبل الحذف لأنه يحوي مفاتيح
                f.write(b"\0" * size)
        except Exception:
            pass
        os.remove(AUTO_FILE)
        log("client_config: طُبّق %d إعداد وتُرك %d (موجود مسبقاً) وحُذف الملف" % (n, s))
    except Exception as e:
        log("client_config: فشل التطبيق التلقائي: %s" % e)


# ---------------------------------------------------------------- الصفحة
_E = lambda x: (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
_CSS = ("body{font-family:Tahoma,Arial;background:#f1f5f9;margin:0;padding:18px;direction:rtl}.c{max-width:720px;margin:auto;background:#fff;border-radius:14px;"
        "padding:18px;box-shadow:0 4px 18px rgba(0,0,0,.08)}h2{margin-top:0}.b{background:#205072;color:#fff;border:0;border-radius:9px;padding:9px 16px;font:700 14px Tahoma;"
        "cursor:pointer}label{display:block;margin:6px 0}input[type=text],input[type=password],input[type=file]{padding:8px;border:1px solid #94a3b8;border-radius:8px;width:100%;"
        "box-sizing:border-box}.m{padding:10px;border-radius:9px;margin:10px 0}.ok{background:#dcfce7}.er{background:#fee2e2}.sec{border:1px solid #cbd5e1;border-radius:11px;padding:12px;margin:12px 0}"
        "small{color:#64748b}")


def install(app, ctx):
    from flask import Response, request, session, redirect
    get_db, get_setting, set_setting = ctx["get_db"], ctx["get_setting"], ctx["set_setting"]
    login_required = ctx["login_required"]

    def is_admin():
        return bool(session.get("designer_id")) or session.get("role") == "admin"

    def page(msg="", ok=True):
        db = get_db()
        st = _all_settings(db)
        rows = []
        for gid, label, pred in GROUPS:
            n = sum(1 for k, v in st.items() if pred(k) and v not in (None, ""))
            rows.append("<label><input type='checkbox' name='g' value='%s' %s> %s <small>(%d إعداد محفوظ عندك)</small></label>" % (gid, "checked" if gid != "identity" else "", _E(label), n))
        m = "<div class='m %s'>%s</div>" % ("ok" if ok else "er", _E(msg)) if msg else ""
        html = ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>تهيئة العميل</title><style>%s</style><div class='c'>"
                "<a href='/'>↩ الرئيسية</a><h2>🧩 تهيئة العميل</h2>%s"
                "<div class='sec'><b>تصدير (من جهازك)</b><p><small>يُنتج ملفاً مشفراً فيه مفتاح الربط ومفتاح البوابة والذكاء الاصطناعي وتصميم التقارير. أرسله للعميل واستورده عنده مرة واحدة.</small></p>"
                "<form method='post' action='/management/client-config/export'>%s<label>كلمة سر للملف (تُعطيها للعميل بشكل منفصل)<input type='password' name='pw' required minlength='4'></label>"
                "<button class='b'>⬇ تصدير الملف</button></form></div>"
                "<div class='sec'><b>استيراد (عند العميل)</b><form method='post' action='/management/client-config/import' enctype='multipart/form-data'>"
                "<label>الملف (.lcc)<input type='file' name='f' required></label><label>كلمة السر<input type='password' name='pw' required></label>"
                "<label><input type='checkbox' name='ow' value='1'> استبدال الإعدادات الموجودة (وإلا يملأ الفارغ فقط)</label><button class='b'>⬆ استيراد</button></form></div>"
                "<p><small>طريقة التطبيق التلقائي: ضع ملفاً غير مشفّر باسم client_config.json بجانب app.py وقت التنصيب؛ يُطبَّق مرة واحدة ثم يُحذف.</small></p></div>") % (_CSS, m, "".join(rows))
        return Response(html, mimetype="text/html")

    @app.route("/management/client-config")
    @login_required
    def cc_page():
        if not is_admin():
            return Response("للمدير فقط", 403)
        return page()

    @app.route("/management/client-config/export", methods=["POST"])
    @login_required
    def cc_export():
        if not is_admin():
            return Response("للمدير فقط", 403)
        groups = set(request.form.getlist("g"))
        try:
            data = collect(get_db(), groups)
            name = get_setting(get_db(), "app_name_ar", "") or get_setting(get_db(), "app_name", "") or "lab"
            blob = encrypt_config(data, request.form.get("pw") or "", {"created": datetime.now().isoformat(timespec="seconds"), "groups": sorted(groups), "lab": name})
        except Exception as e:
            return page("تعذّر التصدير: %s" % e, False)
        try:
            ctx.get("log_action") and ctx["log_action"]("Export", "client_config", 0, "تصدير تهيئة عميل (%d إعداد)" % len(data))
        except Exception:
            pass
        fn = "client_config_%s.lcc" % time.strftime("%Y%m%d")
        return Response(blob, mimetype="application/octet-stream", headers={"Content-Disposition": "attachment; filename=" + fn})

    @app.route("/management/client-config/import", methods=["POST"])
    @login_required
    def cc_import():
        if not is_admin():
            return Response("للمدير فقط", 403)
        try:
            f = request.files.get("f")
            data = decrypt_config(f.read().decode("utf-8"), request.form.get("pw") or "")
            n, s = apply_settings(get_db(), set_setting, data, overwrite=request.form.get("ow") == "1")
        except Exception as e:
            return page("تعذّر الاستيراد: %s" % e, False)
        try:
            ctx.get("log_action") and ctx["log_action"]("Import", "client_config", 0, "استيراد تهيئة عميل (%d طُبّق، %d تُرك)" % (n, s))
        except Exception:
            pass
        return page("تم: طُبّق %d إعداد وتُرك %d (موجود مسبقاً). أعد تشغيل البرنامج ليأخذ كل شيء." % (n, s), True)

    auto_apply(get_db_for_startup(ctx), set_setting)


def get_db_for_startup(ctx):
    """اتصال خاص لمرحلة الإقلاع (خارج طلب Flask)."""
    def _get():
        try:
            import ledger_sync as ls
            return ls._db()
        except Exception:
            return ctx["get_db"]()
    return _get
