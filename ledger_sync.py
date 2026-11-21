# -*- coding: utf-8 -*-
"""ledger_sync.py — ربط برنامج المختبر (LIS) بـ «سجل المرضى السحابي» (Cloudflare).

يدفع الزيارات (اسم المريض، التحاليل، المبلغ المدفوع، الطبيب/المختبر المرسل) إلى السحابة كل دقيقتين تلقائياً،
فتظهر بالموبايل والحاسبة. بيانات المرضى والحسابات فقط (لا نتائج ولا صور).
- الإعدادات: صفحة /ledger  (الرابط + مفتاح الربط LIS_KEY).
- لا يغيّر أي شيء بقاعدة المختبر (قراءة فقط) عدا مفاتيح إعداداته بجدول settings.
- الفشل (بدون إنترنت/خطأ) لا يوقف البرنامج: يعيد المحاولة بالدورة التالية.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LIS-Ledger/1.0"
INTERVAL = 120
_lock = threading.Lock()
_started = {"v": False}
_st = {"syncing": False, "ok_t": 0.0, "err": "", "try_t": 0.0}


# ------------------------------------------------------------------ settings helpers
def _db():
    from database import get_db
    return get_db()


def _get(db, k, d=""):
    r = db.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r["value"] if r and r["value"] is not None else d


def _set(db, k, v):
    if db.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone():
        db.execute("UPDATE settings SET value=? WHERE key=?", (v, k))
    else:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))


def cfg(db):
    try:
        back = max(1, min(60, int(_get(db, "ledger_days_back", "3") or 3)))
    except ValueError:
        back = 3
    return {
        "url": (_get(db, "ledger_url") or "").strip().rstrip("/"),
        "key": re.sub(r"[^A-Za-z0-9_.\-]", "", _get(db, "ledger_key") or ""),
        "enabled": _get(db, "ledger_enabled", "0") == "1",
        "back": back,
    }


def _redact(t):
    t = str(t or "")
    return re.sub(r"[A-Za-z0-9_\-]{24,}", "***", t)[:240]


# ------------------------------------------------------------------ data collection
_AGE_UNIT = {"years": "سنة", "year": "سنة", "y": "سنة", "months": "شهر", "month": "شهر", "m": "شهر",
             "days": "يوم", "day": "يوم", "d": "يوم", "سنة": "سنة", "شهر": "شهر", "يوم": "يوم"}


def _gender(g):
    g = (g or "").strip().lower()
    if g in ("m", "male", "ذكر"):
        return "ذكر"
    if g in ("f", "female", "أنثى", "انثى"):
        return "أنثى"
    return ""


def collect_day(db, day):
    """صفوف يوم واحد بصيغة السجل السحابي."""
    vs = db.execute(
        "SELECT v.id, v.registration_number, v.sample_no, v.created_at, v.status, v.referral_center_id, v.doctor_id, "
        "p.full_name, p.gender, p.age, p.age_unit, "
        "(SELECT name FROM referral_centers rc WHERE rc.id=v.referral_center_id) AS center, "
        "(SELECT full_name FROM doctors d WHERE d.id=v.doctor_id) AS doctor, "
        "(SELECT COALESCE(SUM(i.paid_amount),0) FROM invoices i WHERE i.visit_id=v.id) AS paid, "
        "(SELECT COALESCE(SUM(i.total_amount-COALESCE(i.discount_amount,0)),0) FROM invoices i WHERE i.visit_id=v.id) AS net "
        "FROM visits v JOIN patients p ON p.id=v.patient_id "
        "WHERE substr(v.created_at,1,10)=? AND COALESCE(v.status,'') NOT IN ('Cancelled','Canceled') "
        "ORDER BY v.id", (day,)).fetchall()
    rows = []
    for v in vs:
        tests = [r["name"] for r in db.execute(
            "SELECT td.name FROM orders o JOIN order_tests ot ON ot.order_id=o.id "
            "JOIN test_definitions td ON td.id=ot.test_definition_id "
            "WHERE o.visit_id=? AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') "
            "AND COALESCE(ot.hidden_from_log,0)=0 ORDER BY ot.id", (v["id"],)).fetchall() if r["name"]]
        center = (v["center"] or "").strip()
        is_lab = bool(center) and center.lower() not in ("walk-in", "walkin")
        ref = center if is_lab else (v["doctor"] or "").strip()
        # مختبر محيل (يحاسَب بالآجل): نرسل صافي الفاتورة ليظهر بحساب المختبر؛ غيره: المدفوع فعلاً
        paid = float((v["net"] if is_lab else v["paid"]) or 0)
        net_total = float(v["net"] or 0)
        rows.append({
            "lisId": "v%d" % v["id"],
            "lisReg": str(v["registration_number"] or ""),
            "sampleNo": str(v["sample_no"] or ""),
            "name": (v["full_name"] or "").strip(),
            "gender": _gender(v["gender"]),
            "age": "" if v["age"] is None else str(v["age"]),
            "ageUnit": _AGE_UNIT.get(str(v["age_unit"] or "").strip().lower(), "سنة"),
            "refDoctor": ref,
            "priceType": "lab" if is_lab else "patient",
            "paid": int(paid) if paid == int(paid) else paid,
            "total": int(net_total) if net_total == int(net_total) else net_total,
            "tests": ", ".join(tests),
        })
    return rows


# ------------------------------------------------------------------ transport
def _request(url, key, body, timeout=30):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdr = {"x-lis-key": key, "User-Agent": _UA, "Accept": "application/json"}
    if data is not None:
        hdr["Content-Type"] = "application/json"
    method = "POST" if data is not None else "GET"
    err = ""
    try:
        req = urllib.request.Request(url, data=data, headers=hdr, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            j = {}
        return e.code, j
    except Exception as e:  # SSL/DNS/timeout → جرّب curl
        err = "%s: %s" % (type(e).__name__, _redact(e))
    exe = shutil.which("curl") or shutil.which("curl.exe")
    if exe:
        tf = None
        try:
            cmd = [exe, "-sS", "-m", str(timeout), "-X", method, "-w", "\n__HTTP__%{http_code}", "-A", _UA]
            for k, v in hdr.items():
                cmd += ["-H", "%s: %s" % (k, v)]
            if data is not None:
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
                tf.write(data)
                tf.close()
                cmd += ["--data-binary", "@" + tf.name]
            cmd.append(url)
            p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            out = p.stdout.decode("utf-8", "replace")
            if "\n__HTTP__" in out:
                body_s, code = out.rsplit("\n__HTTP__", 1)
                if int(code or 0):
                    try:
                        return int(code), json.loads(body_s)
                    except Exception:
                        return int(code), {}
            err += " | curl: " + _redact(p.stderr.decode("utf-8", "replace"))
        except Exception as e:
            err += " | curl: " + _redact(e)
        finally:
            if tf:
                try:
                    os.unlink(tf.name)
                except Exception:
                    pass
    raise ConnectionError(err or "no connection")


def _explain(code, j):
    m = (j or {}).get("message") or (j or {}).get("error") or ""
    if code == 401:
        return "مفتاح الربط غير صحيح (يجب أن يطابق LIS_KEY بالسحابة)."
    if code == 500 and (j or {}).get("code") == "no_lis_key":
        return "السحابة ما عندها LIS_KEY — نفّذ: npx wrangler secret put LIS_KEY"
    if code == 404:
        return "الرابط غير صحيح أو نسخة السحابة قديمة (ما فيها جسر المختبر). أعد نشر السحابة."
    return "رفضت السحابة الطلب (HTTP %s) %s" % (code, _redact(m))


def test_connection(db):
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return False, "أدخل رابط السحابة (https://…) ومفتاح الربط أولاً."
    try:
        code, j = _request(c["url"] + "/api/lis/ping", c["key"], None, 20)
    except Exception as e:
        return False, "تعذّر الاتصال بالسحابة: " + _redact(e)
    if code == 200 and j.get("ok"):
        return True, "الاتصال بالسحابة شغّال ✓"
    return False, _explain(code, j)


# ------------------------------------------------------------------ sync
def sync(db, days=None, force=False):
    _st["syncing"], _st["try_t"] = True, time.time()
    try:
        r = _sync(db, days, force)
    finally:
        _st["syncing"] = False
    if r[0]:
        _st["ok_t"], _st["err"] = time.time(), ""
    else:
        _st["err"] = r[1]
    return r


def _sync(db, days=None, force=False):
    """يدفع آخر N يوم (الافتراضي من الإعداد). يرجع (ok, رسالة, عدد المحدَّث)."""
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return False, "الربط غير مضبوط.", 0
    n = max(1, min(90, int(days or c["back"])))
    today = date.today()
    payload, marks = {}, {}
    for i in range(n):
        d = (today - timedelta(days=i)).isoformat()
        rows = collect_day(db, d)
        ids = sorted(r["lisId"] for r in rows)
        prev_ids = []
        try:
            prev_ids = json.loads(_get(db, "ledger_ids_" + d, "[]") or "[]")
        except Exception:
            pass
        removed = [x for x in prev_ids if x not in ids]
        h = hashlib.sha1(json.dumps([rows, removed], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if not force and h == _get(db, "ledger_hash_" + d, ""):
            continue
        payload[d] = {"rows": rows, "removed": removed}
        marks[d] = (h, ids)
    if not payload:
        return True, "لا تغييرات جديدة.", 0
    keys = list(payload)
    up = rm = 0
    for i in range(0, len(keys), 10):  # دفعات (حد الخادم 40 يوم بالطلب)
        part = {k: payload[k] for k in keys[i:i + 10]}
        try:
            code, j = _request(c["url"] + "/api/lis/push", c["key"], {"days": part}, 45)
        except Exception as e:
            return False, "تعذّر الاتصال بالسحابة: " + _redact(e), up
        if code != 200 or not j.get("ok"):
            return False, _explain(code, j), up
        up += int(j.get("upserted", 0))
        rm += int(j.get("removed", 0))
        for d in part:
            _set(db, "ledger_hash_" + d, marks[d][0])
            _set(db, "ledger_ids_" + d, json.dumps(marks[d][1]))
    _set(db, "ledger_last_ok", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    _set(db, "ledger_last_err", "")
    db.commit()
    return True, "تم: %s تحديث، %s حذف (%s يوم)." % (up, rm, len(payload)), up


# ------------------------------------------------------------------ دفعات أُدخلت من السجل السحابي (تحتاج اعتماد موظف)
def pending_payments(db):
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return False, "الربط غير مضبوط.", []
    try:
        code, j = _request(c["url"] + "/api/lis/pull?days=7", c["key"], None, 25)
    except Exception as e:
        return False, "تعذّر الاتصال بالسحابة: " + _redact(e), []
    if code != 200 or not j.get("ok"):
        return False, _explain(code, j), []
    items = []
    for it in j.get("items", []):
        m = re.fullmatch(r"v(\d+)", str(it.get("lisId", "")))
        if not m or float(it.get("diff") or 0) <= 0:
            continue
        inv = db.execute("SELECT id, total_amount, discount_amount, paid_amount, is_locked FROM invoices WHERE visit_id=? ORDER BY id DESC LIMIT 1", (int(m.group(1)),)).fetchone()
        if not inv:
            continue
        it["visit_id"] = int(m.group(1))
        it["invoice_paid"] = float(inv["paid_amount"] or 0)
        it["locked"] = bool(inv["is_locked"])
        items.append(it)
    return True, "", items


def approve_payment(db, lis_id, user_id=None):
    """يعتمد دفعة السجل السحابي: يسجّلها كدفعة نقدية بفاتورة الزيارة. المبلغ يُحسب من السحابة (لا يُؤخذ من المتصفح)."""
    ok, msg, items = pending_payments(db)
    if not ok:
        return False, msg
    it = next((x for x in items if x["lisId"] == lis_id), None)
    if not it:
        return False, "لا توجد دفعة معلّقة لهذي الزيارة (ربما اعتُمدت)."
    if it["locked"]:
        return False, "الفاتورة مقفلة — افتحها أولاً من صفحة الفواتير."
    inv = db.execute("SELECT * FROM invoices WHERE visit_id=? ORDER BY id DESC LIMIT 1", (it["visit_id"],)).fetchone()
    amount = float(it["diff"])
    new_paid = float(inv["paid_amount"] or 0) + amount
    status = "Paid" if new_paid >= float(inv["total_amount"] or 0) else "Partial"
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("INSERT INTO payments (invoice_id, amount, method, user_id, paid_at) VALUES (?, ?, 'Cash', ?, ?)", (inv["id"], amount, user_id, now))
    db.execute("UPDATE invoices SET paid_amount=?, status=? WHERE id=?", (new_paid, status, inv["id"]))
    db.commit()
    sync(db, 7, force=True)  # يثبّت المبلغ الجديد بالسحابة فتختفي من المعلّقة
    return True, "تم تسجيل دفعة %s على فاتورة %s." % (int(amount) if amount == int(amount) else amount, it.get("name", ""))


def _loop():
    time.sleep(20)
    while True:
        try:
            db = _db()
            try:
                if cfg(db)["enabled"]:
                    with _lock:
                        ok, msg, _n = sync(db)
                    if not ok:
                        _set(db, "ledger_last_err", "%s  %s" % (datetime.now().strftime("%H:%M"), msg))
                        db.commit()
            finally:
                db.close()
        except Exception:
            pass
        time.sleep(INTERVAL)


def start():
    if _started["v"]:
        return
    _started["v"] = True
    threading.Thread(target=_loop, name="ledger-sync", daemon=True).start()


_BADGE = ('<script id="lis-ledger-badge">(function(){try{if(window.top!==window.self||document.getElementById("lis-lg"))return;'
          'var d=document.createElement("a");d.id="lis-lg";d.href="/ledger";d.title="مزامنة السجل السحابي";'
          'd.style.cssText="position:fixed;bottom:10px;left:8px;z-index:99990;display:none;align-items:center;gap:6px;background:#fff;border:1px solid #cbd5e1;border-radius:20px;padding:3px 10px;font:12px Tahoma,sans-serif;color:#334155;text-decoration:none;box-shadow:0 1px 6px #0002";'
          'var c={g:"#16a34a",y:"#eab308",r:"#dc2626"};'
          'function u(){fetch("/ledger/status",{cache:"no-store"}).then(function(r){return r.json()}).then(function(j){'
          'if(j.hide){d.style.display="none";return}d.style.display="flex";'
          'd.innerHTML="<span style=\\"width:10px;height:10px;border-radius:50%;background:"+(j.enabled?c[j.color]:"#94a3b8")+"\\"></span>"+j.label;d.title=j.detail||""}).catch(function(){})}'
          'document.addEventListener("DOMContentLoaded",function(){document.body.appendChild(d);u();setInterval(u,15000)});'
          'if(document.body){document.body.appendChild(d);u();setInterval(u,15000)}}catch(e){}})();</script>')


def status():
    now = time.time()
    if _st["syncing"]:
        return "y", "جاري المزامنة…", ""
    if _st["err"]:
        return "r", "السحابة: غير متصل", _st["err"]
    if _st["ok_t"] and now - _st["ok_t"] < INTERVAL * 3:
        return "g", "السحابة: متزامن ✓", time.strftime("آخر مزامنة %H:%M:%S", time.localtime(_st["ok_t"]))
    return "y", "بانتظار المزامنة…", ""


# ------------------------------------------------------------------ web page + routes
_PAGE = r'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ربط السجل السحابي</title><style>
body{margin:0;font-family:Tahoma,"Segoe UI",sans-serif;background:#f4f8f7;color:#16302b;padding:18px}
.c{max-width:640px;margin:auto;background:#fff;border:1px solid #d6e4e1;border-radius:14px;padding:20px}
h2{margin:0 0 6px}label{display:block;margin:14px 0 4px;font-weight:700}
input[type=text],input[type=password]{width:100%;padding:10px;border:1px solid #b9cfcb;border-radius:9px;font-size:15px;direction:ltr;box-sizing:border-box}
button{padding:10px 16px;border:0;border-radius:9px;background:#0f766e;color:#fff;font-size:15px;cursor:pointer;margin:6px 4px 0 0}
button.g{background:#64748b}.m{margin-top:14px;padding:10px;border-radius:9px;background:#eef6f5;white-space:pre-wrap;min-height:20px}
.s{font-size:13px;color:#475569;margin-top:10px;line-height:1.8}a{color:#0f766e}</style></head><body><div class="c">
<h2>☁ ربط «سجل المرضى السحابي»</h2>
<div class="s">يدفع الزيارات والمبالغ للسحابة كل دقيقتين لتظهر على الموبايل. بيانات المرضى والحسابات فقط.</div>
<label>رابط السحابة</label><input type="text" id="u" placeholder="https://lab-ledger.xxxx.workers.dev" value="__URL__">
<label>مفتاح الربط (LIS_KEY) <span style="font-weight:400;color:#64748b">__HAS__</span></label><input type="password" id="k" placeholder="اتركه فارغاً للإبقاء على المحفوظ" autocomplete="off">
<label><input type="checkbox" id="e" __EN__> تفعيل المزامنة التلقائية</label>
<div><button id="sv">حفظ</button><button id="ts" class="g">اختبار الاتصال</button><button id="sy" class="g">مزامنة الآن</button><button id="bf" class="g">رفع آخر 30 يوم</button></div>
<div class="m" id="r">__STAT__</div>
<h3 style="margin:18px 0 6px">دفعات أُدخلت من السجل (بانتظار اعتمادك)</h3><div id="pp" class="s">جاري التحميل…</div>
<div class="s">فتح السجل: <a href="__URL__" target="_blank">__URL__</a></div></div>
<script>
var $=function(i){return document.getElementById(i)};
function post(p,b){return fetch(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})}).then(function(r){return r.json()})}
function body(){return {url:$("u").value,key:$("k").value,enabled:$("e").checked}}
function run(p,b,w){$("r").textContent=w;post(p,b).then(function(j){$("r").textContent=j.message||j.error||"تم"}).catch(function(e){$("r").textContent="فشل: "+e})}
$("sv").onclick=function(){run("/ledger/save",body(),"جاري الحفظ…")};
$("ts").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/test",{},"جاري الاختبار…")})};
$("sy").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/sync",{days:3},"جاري المزامنة…")})};
$("bf").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/sync",{days:30,force:true},"جاري رفع 30 يوم…")})};
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function lp(){post("/ledger/pending",{}).then(function(j){if(!j.ok){$("pp").textContent=j.message||"تعذّر التحميل";return}
if(!j.items.length){$("pp").textContent="لا توجد دفعات معلّقة ✓";return}
$("pp").innerHTML=j.items.map(function(i){return '<div style="padding:8px;border:1px solid #d6e4e1;border-radius:9px;margin:6px 0">'+esc(i.name)+' — <b>'+i.diff+'</b> د.ع ('+esc(i.date)+') <button data-id="'+esc(i.lisId)+'">اعتماد</button></div>'}).join("");
Array.prototype.forEach.call($("pp").querySelectorAll("button"),function(b){b.onclick=function(){b.disabled=true;post("/ledger/approve",{lisId:b.getAttribute("data-id")}).then(function(j){$("r").textContent=j.message;lp()})}})}).catch(function(){$("pp").textContent="تعذّر التحميل"})}
lp();
</script></body></html>'''


def install(app):
    from flask import Blueprint, request, jsonify, session, Response
    import html as _h

    bp = Blueprint("ledger_sync", __name__)

    def allowed():
        return bool(session.get("designer_id") or ("interface" in session))

    @bp.route("/ledger")
    def page():
        if not allowed():
            return Response("<meta charset=utf-8><body dir=rtl style='font-family:Tahoma;padding:20px'>سجّل الدخول من الشاشة الرئيسية أولاً.</body>", 401, mimetype="text/html")
        db = _db()
        try:
            c = cfg(db)
            ok, err = _get(db, "ledger_last_ok", ""), _get(db, "ledger_last_err", "")
            stat = ("آخر مزامنة ناجحة: " + ok if ok else "لم تتم مزامنة بعد.") + (("\nآخر خطأ: " + err) if err else "")
            html = (_PAGE.replace("__URL__", _h.escape(c["url"], True)).replace("__HAS__", "(محفوظ ✓)" if c["key"] else "")
                    .replace("__EN__", "checked" if c["enabled"] else "").replace("__STAT__", _h.escape(stat)))
        finally:
            db.close()
        return Response(html, mimetype="text/html")

    @bp.route("/ledger/save", methods=["POST"])
    def save():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        d = request.get_json(silent=True) or {}
        db = _db()
        try:
            u = (d.get("url") or "").strip().rstrip("/")
            if u and not u.lower().startswith("https://"):
                return jsonify(ok=False, message="الرابط لازم يبدأ بـ https://"), 400
            _set(db, "ledger_url", u)
            k = re.sub(r"[^A-Za-z0-9_.\-]", "", d.get("key") or "")   # يحذف BOM/مسافات/اقتباس/أي حرف غير مفتاح
            if k:
                _set(db, "ledger_key", k[:200])
            _set(db, "ledger_enabled", "1" if d.get("enabled") else "0")
            db.commit()
            return jsonify(ok=True, message="تم الحفظ ✓")
        finally:
            db.close()

    @bp.route("/ledger/test", methods=["POST"])
    def test():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        db = _db()
        try:
            ok, msg = test_connection(db)
            return jsonify(ok=ok, message=msg)
        finally:
            db.close()

    @bp.route("/ledger/sync", methods=["POST"])
    def do_sync():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        d = request.get_json(silent=True) or {}
        db = _db()
        try:
            with _lock:
                ok, msg, n = sync(db, d.get("days"), bool(d.get("force")))
            if not ok:
                _set(db, "ledger_last_err", "%s  %s" % (datetime.now().strftime("%H:%M"), msg))
                db.commit()
            return jsonify(ok=ok, message=msg)
        finally:
            db.close()

    @bp.route("/ledger/pending", methods=["POST"])
    def pend():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        db = _db()
        try:
            ok, msg, items = pending_payments(db)
            return jsonify(ok=ok, message=msg, items=items)
        finally:
            db.close()

    @bp.route("/ledger/approve", methods=["POST"])
    def approve():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        d = request.get_json(silent=True) or {}
        db = _db()
        try:
            with _lock:
                ok, msg = approve_payment(db, str(d.get("lisId") or ""), session.get("user_id"))
            return jsonify(ok=ok, message=msg)
        finally:
            db.close()

    @bp.route("/ledger/status")
    def st():
        if not allowed():
            return jsonify(enabled=False, hide=True)
        db = _db()
        try:
            en = cfg(db)["enabled"]
        finally:
            db.close()
        col, label, detail = status()
        if not en:
            label, detail = "☁ ربط السجل", "اضغط لإعداد الربط مع السجل السحابي"
        return jsonify(enabled=en, color=col, label=label, detail=detail)

    @app.after_request
    def _inject(resp):
        try:
            if (resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                    and request.method == "GET" and not request.path.startswith(("/ledger", "/ai/assistant", "/api/"))):
                b = resp.get_data(as_text=True)
                if "</body>" in b and "lis-ledger-badge" not in b:
                    resp.set_data(b.replace("</body>", _BADGE + "</body>", 1))
        except Exception:
            pass
        return resp

    app.register_blueprint(bp)
    start()
