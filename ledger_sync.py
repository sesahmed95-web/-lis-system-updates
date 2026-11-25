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
_st = {"syncing": False, "ok_t": 0.0, "err": "", "try_t": 0.0, "incoming": 0}
_H = {}   # دوال البرنامج (رقم التسجيل، الأطباء، السعر...) تُمرَّر من app.py عند التثبيت


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


_cols_ok = {"v": False}


def _ensure_cols(db):
    if _cols_ok["v"]:
        return
    try:
        db.execute("SELECT expenses_note FROM visits LIMIT 1")
    except Exception:
        try:
            db.execute("ALTER TABLE visits ADD COLUMN expenses_note TEXT")
            db.commit()
        except Exception:
            pass
    _cols_ok["v"] = True


def _num(x):
    try:
        f = float(str(x if x is not None else "").replace(",", "").strip() or 0)
    except ValueError:
        return ""
    if f == 0:
        return ""
    return str(int(f)) if f == int(f) else str(f)


def _sent_str(db, vid):
    """التحاليل المرسلة لمختبر آخر (LIS) بصيغة نص السجل: «t1, t2 — المختبر ؛ t3 — مختبر2»."""
    try:
        rows = db.execute(
            "SELECT td.name AS n, ot.forwarded_lab_name AS lab FROM orders o JOIN order_tests ot ON ot.order_id=o.id "
            "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=? AND TRIM(COALESCE(ot.forwarded_lab_name,''))<>'' "
            "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY ot.id", (vid,)).fetchall()
    except Exception:
        return ""
    by = {}
    for r in rows:
        by.setdefault(r["lab"].strip(), []).append(r["n"])
    return " ؛ ".join("%s — %s" % (", ".join(v), k) for k, v in by.items())


def _parse_sent(txt):
    """«t1, t2 — Lab ؛ t3» → [(test, lab)]"""
    out = []
    for seg in re.split(r"[؛;\n]+", txt or ""):
        seg = seg.strip()
        if not seg:
            continue
        lab = ""
        for sep in (" — ", " - ", " – "):
            if sep in seg:
                seg, lab = seg.rsplit(sep, 1)
                break
        for t in _split_tests(seg):
            out.append((t, lab.strip()))
    return out


def _apply_sent(db, vid, idx, C_sent, base_sent):
    """يضبط «مرسل لمختبر آخر» على تحاليل الزيارة حسب نص السجل. ما يرجّع إلا عدد التحاليل المتأثرة."""
    try:
        if _H.get("ensure_partner"):
            _H["ensure_partner"](db)       # ينشئ أعمدة forwarded_* إذا ما موجودة
    except Exception:
        pass
    want = {}
    for t, lab in _parse_sent(C_sent):
        tid = _match_test(idx, t)
        if tid:
            want[tid] = lab or "مختبر آخر"
    had = set()
    for t, _lab in _parse_sent(base_sent):
        tid = _match_test(idx, t)
        if tid:
            had.add(tid)
    n = 0
    for r in db.execute("SELECT ot.id, ot.test_definition_id tid, ot.status FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=?", (vid,)).fetchall():
        if (r["status"] or "") in ("Cancelled", "Canceled", "Rejected"):
            continue
        tid = r["tid"]
        try:
            if tid in want:
                lab = want[tid]
                pl = db.execute("SELECT pp.cost FROM partner_labs pl JOIN partner_lab_prices pp ON pp.lab_id=pl.id WHERE pl.name=? AND pp.test_definition_id=?", (lab, tid)).fetchone()
                db.execute("UPDATE order_tests SET forwarded_lab_name=?, forwarded_cost=? WHERE id=?", (lab, float(pl["cost"] or 0) if pl else 0, r["id"]))
                n += 1
            elif tid in had:
                db.execute("UPDATE order_tests SET forwarded_lab_name=NULL, forwarded_cost=0 WHERE id=?", (r["id"],))
                n += 1
        except Exception:
            pass
    return n


def _orig_tests(db, vid, lis_tests):
    """زيارة مستوردة من السجل: نحافظ على أسماء التحاليل كما كتبها العميل بالسجل (ما لم تتغير قائمة التحاليل بالـLIS)."""
    try:
        raw = _get(db, "ledger_orig_v%d" % vid)
        if raw:
            o = json.loads(raw)
            if len(lis_tests) == int(o.get("n", -1)):
                return o["tests"]
    except Exception:
        pass
    return ", ".join(lis_tests)


# ------------------------------------------------------------------ طبيب فاحص لكل تحليل (v99)
def _has_exam_col(db):
    try:
        return any(r[1] == "examining_doctor" for r in db.execute("PRAGMA table_info(order_tests)").fetchall())
    except Exception:
        return False


def _keys_by_tid(db):
    """{test_definition_id: [أسماء/اختصارات يعرفها السجل]} — حتى يطابق السجل تحليله مهما كتبه."""
    keys = {}
    try:
        for r in db.execute("SELECT id, name, short_name, code FROM test_definitions").fetchall():
            ks = [x for x in (r["name"], r["short_name"], r["code"]) if x]
            keys[r["id"]] = list(dict.fromkeys(ks))
        idx = {}
        for tid, ks in keys.items():
            for k in ks:
                idx.setdefault(_nt(k), tid)
        for a, target in _EXTRA_ALIAS.items():
            tid = idx.get(_nt(target))
            if tid and a not in keys[tid]:
                keys[tid].append(a)
    except Exception:
        pass
    return {t: ks[:8] for t, ks in keys.items()}


def _exam_by_tid(db, vid):
    """{tid: الطبيب الفاحص الفعلي} للتحاليل المؤهلة (is_examining_test=1) غير الملغاة."""
    out = {}
    try:
        v = db.execute("SELECT examining_doctor FROM visits WHERE id=?", (vid,)).fetchone()
        default = ((v["examining_doctor"] if v else "") or "").strip()
        sel = "COALESCE(ot.examining_doctor,'')" if _has_exam_col(db) else "''"
        for r in db.execute(
                "SELECT ot.test_definition_id AS tid, " + sel + " AS ed FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
                "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=? AND COALESCE(td.is_examining_test,0)=1 "
                "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') AND (ot.fee_waived IS NULL OR ot.fee_waived=0)", (vid,)).fetchall():
            doc = ((r["ed"] or "").strip() or default)
            if doc:
                out[r["tid"]] = doc
    except Exception:
        pass
    return out


def _td_payload(db, vid, keys):
    out = {}
    for tid, doc in _exam_by_tid(db, vid).items():
        for k in keys.get(tid, []):
            out[k] = doc
    return out


def _td_to_tids(td, idx):
    """{نص تحليل: طبيب} → {str(tid): طبيب}"""
    out = {}
    for k, doc in (td or {}).items():
        tid = _match_test(idx, k) if k else None
        if tid and doc:
            out[str(tid)] = str(doc).strip()
    return out


def _set_test_doctors(db, vid, want, default):
    """يطبّق {str(tid): طبيب} على تحاليل الزيارة المؤهلة. يساوي الافتراضي أو غير موجود = NULL (يتبع طبيب الزيارة)."""
    if not _has_exam_col(db):
        return
    default = (default or "").strip()
    for r in db.execute("SELECT ot.id, ot.test_definition_id AS tid FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
                        "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=? AND COALESCE(td.is_examining_test,0)=1", (vid,)).fetchall():
        d = (want.get(str(r["tid"])) or "").strip()
        db.execute("UPDATE order_tests SET examining_doctor=? WHERE id=?", (d if d and d != default else None, r["id"]))
    try:
        from database import recompute_examining_doctor_fee
        recompute_examining_doctor_fee(db, vid)
    except Exception:
        pass


def collect_day(db, day):
    """صفوف يوم واحد بصيغة السجل السحابي."""
    _ensure_cols(db)
    vs = db.execute(
        "SELECT v.id, v.registration_number, v.sample_no, v.created_at, v.status, v.referral_center_id, v.doctor_id, "
        "v.examining_doctor, v.expenses, v.expenses_note, "
        "p.full_name, p.gender, p.age, p.age_unit, "
        "(SELECT name FROM referral_centers rc WHERE rc.id=v.referral_center_id) AS center, "
        "(SELECT full_name FROM doctors d WHERE d.id=v.doctor_id) AS doctor, "
        "(SELECT COALESCE(SUM(i.paid_amount),0) FROM invoices i WHERE i.visit_id=v.id) AS paid, "
        "(SELECT COALESCE(SUM(i.total_amount-COALESCE(i.discount_amount,0)),0) FROM invoices i WHERE i.visit_id=v.id) AS net "
        "FROM visits v JOIN patients p ON p.id=v.patient_id "
        "WHERE substr(v.created_at,1,10)=? AND COALESCE(v.status,'') NOT IN ('Cancelled','Canceled') "
        "ORDER BY v.id", (day,)).fetchall()
    rows = []
    _kb = _keys_by_tid(db)
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
            "tests": _orig_tests(db, v["id"], tests),
            "labDoctor": (v["examining_doctor"] or "").strip(),
            "expenses": _num(v["expenses"]),
            "expNote": (v["expenses_note"] or "").strip(),
            "sentTests": _sent_str(db, v["id"]),
            "testDoctors": _td_payload(db, v["id"], _kb),
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


def _push_rates(db, c):
    """أجور الأطباء الفاحصين (لكل طبيب ولكل تحليل) إلى السحابة ليحسب السجل نفس الأجور. فشلها لا يوقف المزامنة."""
    try:
        keys = _keys_by_tid(db)
        rates = {}
        for r in db.execute("SELECT doctor_name, test_definition_id AS tid, rate FROM examining_doctor_rates WHERE rate>0").fetchall():
            d = rates.setdefault(r["doctor_name"], {})
            for k in keys.get(r["tid"], []):
                d[k] = float(r["rate"])
        h = hashlib.sha1(json.dumps(rates, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if h == _get(db, "ledger_rates_hash", ""):
            return
        code, j = _request(c["url"] + "/api/lis/accounts", c["key"], {"docRates": rates}, 30)
        if code == 200 and j.get("ok"):
            _set(db, "ledger_rates_hash", h)
            db.commit()
    except Exception:
        pass


def _sync(db, days=None, force=False):
    """يدفع آخر N يوم (الافتراضي من الإعداد). يرجع (ok, رسالة, عدد المحدَّث)."""
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return False, "الربط غير مضبوط.", 0
    n = max(1, min(400, int(days or c["back"])))
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
        _push_rates(db, c)
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
    _push_rates(db, c)
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


# ------------------------------------------------------------------ مرضى أُدخلوا بالسجل → واردون للـLIS
_EXTRA_ALIAS = {
    "bf": "peripheral blood film", "blood film": "peripheral blood film", "retic": "reticulocyte count",
    "blood group & rh": "abo/rh", "blood group": "abo/rh", "coombs direct": "direct coombs test",
    "coombs indirect": "indirect coombs test", "pt": "coagulation tests", "inr": "coagulation tests",
    "ptt": "activated partial thromboplastin time", "hb electrophoresis": "hemoglobin electrophoresis",
    "esr": "erythrocyte sedimentation rate", "blood sugar (f)": "fasting blood glucose", "blood sugar (r)": "random blood glucose",
    "hba1c": "glycated hemoglobin", "vit.d": "vitamin d (25-hydroxy)", "gue": "general urine examination (gue)", "gse": "general stool examination (gse)",
}


def _nt(x):
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", (x or "").lower())


def _split_tests(txt):
    return [t.strip() for t in re.split(r"[,،;\n+]+", txt or "") if t.strip()]


def _test_index(db):
    idx = {}
    for r in db.execute("SELECT id, name, short_name, code FROM test_definitions WHERE COALESCE(is_active,1)=1").fetchall():
        for k in (r["name"], r["short_name"], r["code"]):
            if k and _nt(k) not in idx:
                idx[_nt(k)] = r["id"]
    try:
        import lab_catalog
        for e in lab_catalog.CATALOG:
            keys = [e["name"], e["short"]] + list(e["aliases"])
            tid = next((idx[_nt(k)] for k in keys if _nt(k) in idx), None)
            if tid:
                for k in keys:
                    idx.setdefault(_nt(k), tid)
    except Exception:
        pass
    for a, target in _EXTRA_ALIAS.items():
        tid = idx.get(_nt(target))
        if tid:
            idx.setdefault(_nt(a), tid)
    return idx


def _match_test(idx, name):
    cands = [name, re.sub(r"\([^)]*\)", "", name)]
    cands += re.findall(r"\(([^)]+)\)", name)
    for c in cands:
        k = _nt(c)
        if k and k in idx:
            return idx[k]
    for c in cands:      # مطابقة بداية الاسم إذا كانت وحيدة (مثل Widal Test ← Widal Test (Salmonella...))
        k = _nt(c)
        if len(k) >= 5:
            hits = {v for kk, v in idx.items() if kk.startswith(k)}
            if len(hits) == 1:
                return hits.pop()
    return None


def incoming(db, days=14):
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return False, "الربط غير مضبوط.", []
    try:
        code, j = _request(c["url"] + "/api/lis/incoming?days=%d" % max(1, min(400, int(days))), c["key"], None, 25)
    except Exception as e:
        return False, "تعذّر الاتصال بالسحابة: " + _redact(e), []
    if code != 200 or not j.get("ok"):
        return False, _explain(code, j), []
    idx = _test_index(db)
    items = []
    for it in j.get("items", []):
        ok, bad = [], []
        for t in _split_tests(it.get("tests")):
            tid = _match_test(idx, t)
            (ok if tid else bad).append(t)
        it["matched"], it["unmatched"] = ok, bad
        if _get(db, "ledger_imp_%s|%s" % (it.get("date"), it.get("rowId"))):
            continue        # مستورد سابقاً (ننتظر تثبيته بالسحابة)
        items.append(it)
    if days <= 30:
        _st["incoming"] = len(items)
    return True, "", items


def _claim(c, it, lis_id, reg):
    try:
        code, j = _request(c["url"] + "/api/lis/claim", c["key"], {"date": it["date"], "rowId": it["rowId"], "lisId": lis_id, "lisReg": reg}, 25)
        return code == 200 and bool(j.get("ok"))
    except Exception:
        return False


def import_item(db, date_s, row_id, user_id=None, branch_id=None, _items=None, _sync_after=True, _days=14):
    """يستورد مريضاً مضافاً بالسجل: مريض + زيارة + تحاليل + فاتورة/دفعة، ثم يربطه بالسحابة (لا يتكرر)."""
    c = cfg(db)
    key = "ledger_imp_%s|%s" % (date_s, row_id)
    prev = _get(db, key)
    if prev:
        reg = ""
        m = re.fullmatch(r"v(\d+)", prev)
        if m:
            r = db.execute("SELECT registration_number FROM visits WHERE id=?", (int(m.group(1)),)).fetchone()
            reg = str(r["registration_number"]) if r else ""
        _claim(c, {"date": date_s, "rowId": row_id}, prev, reg)
        return True, "مستورد سابقاً."
    if _items is None:
        ok, msg, items = incoming(db, _days)
        if not ok:
            return False, msg
    else:
        items = _items
    it = next((x for x in items if x["date"] == date_s and x["rowId"] == row_id), None)
    if not it:
        return False, "هذا المريض لم يعد بالقائمة (ربما اُستورد أو حُذف من السجل)."
    H = _H
    if not H:
        return False, "وظائف الاستيراد غير جاهزة."
    idx = _test_index(db)
    tids = []
    for t in _split_tests(it["tests"]):
        tid = _match_test(idx, t)
        if tid and tid not in tids:
            tids.append(tid)
    now_dt = datetime.now()
    created = now_dt.isoformat(timespec="seconds") if date_s == now_dt.strftime("%Y-%m-%d") else date_s + "T" + now_dt.strftime("%H:%M:%S")
    is_lab = it.get("priceType") == "lab"
    ref = (it.get("refDoctor") or "").strip()
    doctor_id = None if is_lab else H["doctor"](db, ref)
    center_id = H["center"](db, ref) if is_lab else None
    gender = {"ذكر": "Male", "أنثى": "Female"}.get(it.get("gender") or "", "")
    unit = {"سنة": "Years", "شهر": "Months", "يوم": "Days"}.get(it.get("ageUnit") or "", "Years")
    try:
        age = float(it["age"]) if str(it.get("age") or "").strip() else None
        age = int(age) if age is not None and age == int(age) else age
    except ValueError:
        age = None
    name = (it.get("name") or "").strip()
    pcur = db.execute("INSERT INTO patients (full_name, gender, age, age_unit, branch_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (name, gender, age, unit, branch_id, created))
    reg = H["next_reg"](db)
    note = "مستورد من سجل المرضى السحابي"
    if it["unmatched"]:
        note += " — تحاليل لم تُطابَق (أضفها يدوياً): " + "، ".join(it["unmatched"])
    vcur = db.execute(
        "INSERT INTO visits (registration_number, patient_id, doctor_id, referral_center_id, visit_type, fasting, notes, status, branch_id, created_by, created_at) "
        "VALUES (?, ?, ?, ?, 'walk-in', 'Undefined', ?, 'Open', ?, ?, ?)",
        (reg, pcur.lastrowid, doctor_id, center_id, note, branch_id, user_id, created))
    vid = vcur.lastrowid
    _ensure_cols(db)
    try:
        db.execute("UPDATE visits SET examining_doctor=?, attending_doctor=?, expenses=?, expenses_note=? WHERE id=?",
                   ((it.get("labDoctor") or "").strip(), (it.get("labDoctor") or "").strip(), float(_num(it.get("expenses")) or 0), (it.get("expNote") or "").strip(), vid))
    except Exception:
        pass
    try:
        db.execute("UPDATE visits SET sample_no=? WHERE id=?", (H["sample_no"](db, None), vid))
    except Exception:
        pass
    oid = db.execute("INSERT INTO orders (visit_id, status, created_at) VALUES (?, 'Open', ?)", (vid, created)).lastrowid
    total = 0.0
    for tid in tids:
        price = H["price"](db, tid, doctor_id, center_id)
        db.execute("INSERT INTO order_tests (order_id, test_definition_id, status, barcode, price, doctor_id, collected_at, created_at, price_missing) "
                   "VALUES (?, ?, 'Collected', ?, ?, ?, ?, ?, ?)",
                   (oid, tid, "%s%03d" % (reg, tid), price if price is not None else 0, doctor_id, created, created, 1 if price is None else 0))
        total += price or 0
    if (it.get("sentTests") or "").strip():
        _apply_sent(db, vid, idx, it.get("sentTests"), "")
    if isinstance(it.get("testDoctors"), dict) and it["testDoctors"]:
        try:
            _set_test_doctors(db, vid, _td_to_tids(it["testDoctors"], idx), (it.get("labDoctor") or "").strip())
        except Exception:
            pass
    paid = 0.0 if is_lab else max(0.0, float(it.get("paid") or 0))
    inv_total = total if is_lab else max(total, paid)    # أسعار الكتالوج 0 افتراضياً: لا نخلي المدفوع أكبر من الفاتورة
    disc = max(0.0, total - inv_total)
    extra = max(0.0, inv_total - total)
    status_ = "Paid" if (inv_total > 0 and paid >= inv_total) else ("Partial" if paid > 0 else ("Paid" if inv_total <= 0 else "Unpaid"))
    icur = db.execute("INSERT INTO invoices (visit_id, total_amount, discount_amount, extra_charges, paid_amount, status, created_by, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (vid, inv_total, disc, extra, paid, status_, user_id, created))
    if paid > 0:
        db.execute("INSERT INTO payments (invoice_id, amount, method, user_id, paid_at) VALUES (?, ?, 'Cash', ?, ?)",
                   (icur.lastrowid, paid, user_id, created))
    _set(db, key, "v%d" % vid)
    _set(db, "ledger_orig_v%d" % vid, json.dumps({"tests": it["tests"], "n": len(tids)}, ensure_ascii=False))
    db.commit()
    _claim(c, it, "v%d" % vid, str(reg))
    if _sync_after:
        try:
            sync(db, 14, force=True)
        except Exception:
            pass
    msg = "تم استيراد %s (وصل %s)" % (name, reg)
    if it["unmatched"]:
        msg += " — لم تُطابَق: " + "، ".join(it["unmatched"])
    return True, msg


def skip_item(db, date_s, row_id):
    c = cfg(db)
    try:
        code, j = _request(c["url"] + "/api/lis/claim", c["key"], {"date": date_s, "rowId": row_id, "skip": True}, 25)
        return code == 200 and bool(j.get("ok"))
    except Exception:
        return False


_seen = {}   # توقيع كل مريض وارد: لا نستورده إلا إذا ثبت بدون تغيير بين مسحتين (حتى لا نستورد صفاً العميل لسا يكتب تحاليله)


def _auto_import(db):
    """يستورد تلقائياً المرضى المضافين بالسجل بعد ما يثبت صفّهم دورة كاملة (حوالي دقيقتين)."""
    if _get(db, "ledger_auto_import", "1") != "1":
        incoming(db)
        return 0
    ok, msg, items = incoming(db)
    if not ok:
        return 0
    live = set()
    n = 0
    for it in items:
        key = "%s|%s" % (it["date"], it["rowId"])
        live.add(key)
        sig = (it.get("name"), it.get("tests"), it.get("paid"), it.get("refDoctor"), it.get("age"), it.get("gender"), it.get("priceType"))
        if _seen.get(key) == sig and n < 20:
            try:
                r_ok, r_msg = import_item(db, it["date"], it["rowId"], None, None)
                if r_ok:
                    n += 1
                    _seen.pop(key, None)
                    continue
                _st["imp_err"] = r_msg
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
                _st["imp_err"] = _redact(e)
        else:
            _seen[key] = sig
    for k in [k for k in _seen if k not in live]:
        _seen.pop(k, None)
    _st["incoming"] = max(0, len(items) - n)
    return n


# ------------------------------------------------------------------ تعديلات السجل على مريض موجود بالـLIS (اتجاه السجل ← LIS)
_CANCELABLE = ("Accepted", "Collected", "Pending", "Received", "Ordered")


def _state(r, idx=None):
    ts, seen = [], set()
    for t in _split_tests(r.get("tests")):
        if _nt(t) not in seen:
            seen.add(_nt(t))
            ts.append(t)
    age = str(r.get("age") if r.get("age") is not None else "").strip()
    if re.fullmatch(r"\d+\.0+", age):
        age = age.split(".")[0]
    st = {"name": (r.get("name") or "").strip(), "gender": r.get("gender") or "", "age": age, "ageUnit": r.get("ageUnit") or "",
            "ref": (r.get("refDoctor") or "").strip(), "lab": (r.get("priceType") == "lab"), "tests": ts,
            "labDoctor": (r.get("labDoctor") or "").strip(), "expenses": _num(r.get("expenses")), "expNote": (r.get("expNote") or "").strip(),
            "sentRaw": (r.get("sentTests") or "").strip(),
            "sent": " | ".join(sorted("%s>%s" % (_nt(t), _nt(l)) for t, l in _parse_sent(r.get("sentTests"))))}
    if idx is not None and isinstance(r.get("testDoctors"), dict):
        st["tdocs"] = _td_to_tids(r.get("testDoctors"), idx)      # غير موجود بالسحابة (صف قديم) = لا نقارن
    return st


def _same(a, b):
    skip = ("tests", "sentRaw")
    common = [k for k in a if k in b and k not in skip]
    ka = {k: a[k] for k in common}
    kb = {k: b[k] for k in common}
    return ka == kb and {_nt(t) for t in a["tests"]} == {_nt(t) for t in b["tests"]}


def _apply_cloud(db, vid, C, base, L):
    """يطبّق تعديل السجل (C) على زيارة LIS: بيانات المريض + الدكتور/المختبر + إضافة/إلغاء تحاليل + تحديث الفاتورة."""
    H = _H
    v = db.execute("SELECT patient_id, registration_number, notes FROM visits WHERE id=?", (vid,)).fetchone()
    if not v:
        return
    notes = []
    sets, vals = [], []
    if C["name"] != L["name"] and C["name"]:
        sets.append("full_name=?"); vals.append(C["name"])
    if C["gender"] != L["gender"]:
        sets.append("gender=?"); vals.append({"ذكر": "Male", "أنثى": "Female"}.get(C["gender"], ""))
    if (C["age"], C["ageUnit"]) != (L["age"], L["ageUnit"]):
        try:
            a = float(C["age"]) if C["age"] else None
            a = int(a) if a is not None and a == int(a) else a
        except ValueError:
            a = None
        sets += ["age=?", "age_unit=?"]
        vals += [a, {"سنة": "Years", "شهر": "Months", "يوم": "Days"}.get(C["ageUnit"], "Years")]
    if sets:
        db.execute("UPDATE patients SET %s WHERE id=?" % ", ".join(sets), (*vals, v["patient_id"]))
    if (C["ref"], C["lab"]) != (L["ref"], L["lab"]):
        if C["lab"]:
            db.execute("UPDATE visits SET doctor_id=NULL, referral_center_id=? WHERE id=?", (H["center"](db, C["ref"]), vid))
        else:
            db.execute("UPDATE visits SET doctor_id=?, referral_center_id=NULL WHERE id=?", (H["doctor"](db, C["ref"]), vid))
    if C.get("sent", "") != L.get("sent", ""):
        _apply_sent(db, vid, _test_index(db), C.get("sentRaw", ""), base.get("sentRaw", L.get("sentRaw", "")))
    if (C["labDoctor"], C["expenses"], C["expNote"]) != (L["labDoctor"], L["expenses"], L["expNote"]):
        _ensure_cols(db)
        db.execute("UPDATE visits SET examining_doctor=?, attending_doctor=?, expenses=?, expenses_note=? WHERE id=?",
                   (C["labDoctor"], C["labDoctor"], float(C["expenses"] or 0), C["expNote"], vid))
    if "tdocs" in C and "tdocs" in L and C["tdocs"] != L["tdocs"]:
        _set_test_doctors(db, vid, C["tdocs"], C["labDoctor"])
    elif (C["labDoctor"] != L["labDoctor"]) and "tdocs" in L:
        _set_test_doctors(db, vid, {k: x for k, x in (L.get("tdocs") or {}).items() if x != L["labDoctor"]}, C["labDoctor"])
    # --- التحاليل
    idx = _test_index(db)
    cset = {_nt(t) for t in C["tests"]}
    bset = {_nt(t) for t in base["tests"]}
    c_tids = {x for x in (_match_test(idx, t) for t in C["tests"]) if x}
    oid = db.execute("SELECT id FROM orders WHERE visit_id=? ORDER BY id LIMIT 1", (vid,)).fetchone()
    if not oid:
        oid = db.execute("INSERT INTO orders (visit_id, status, created_at) VALUES (?, 'Open', ?)", (vid, datetime.now().isoformat(timespec="seconds")))
        oid_v = oid.lastrowid
    else:
        oid_v = oid["id"]
    have = {}
    for r in db.execute("SELECT ot.id, ot.test_definition_id tid, ot.status, ot.price FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
                        "WHERE o.visit_id=? AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected')", (vid,)).fetchall():
        have[r["tid"]] = r
    doc_id = db.execute("SELECT doctor_id, referral_center_id FROM visits WHERE id=?", (vid,)).fetchone()
    now = datetime.now().isoformat(timespec="seconds")
    added = removed = 0.0
    for t in [t for t in C["tests"] if _nt(t) not in bset]:
        tid = _match_test(idx, t)
        if not tid:
            notes.append("تحليل لم يُطابَق: " + t)
            continue
        if tid in have:
            continue
        price = H["price"](db, tid, doc_id["doctor_id"], doc_id["referral_center_id"])
        db.execute("INSERT INTO order_tests (order_id, test_definition_id, status, barcode, price, doctor_id, collected_at, created_at, price_missing) "
                   "VALUES (?, ?, 'Collected', ?, ?, ?, ?, ?, ?)",
                   (oid_v, tid, "%s%03d" % (v["registration_number"], tid), price if price is not None else 0, doc_id["doctor_id"], now, now, 1 if price is None else 0))
        added += price or 0
        have[tid] = {"status": "Collected"}
    for t in [t for t in base["tests"] if _nt(t) not in cset]:
        tid = _match_test(idx, t)
        if not tid or tid in c_tids or tid not in have:
            continue
        r = have[tid]
        if (r["status"] or "") in _CANCELABLE:
            db.execute("UPDATE order_tests SET status='Cancelled' WHERE id=?", (r["id"],))
            removed += float(r["price"] or 0)
            have.pop(tid, None)
        else:
            notes.append("لم يُحذف %s لأن نتيجته أُدخلت" % t)
    if added or removed:
        inv = db.execute("SELECT id, total_amount, paid_amount, is_locked FROM invoices WHERE visit_id=? ORDER BY id DESC LIMIT 1", (vid,)).fetchone()
        if inv and not inv["is_locked"]:
            tot = max(0.0, float(inv["total_amount"] or 0) + added - removed)
            paid = float(inv["paid_amount"] or 0)
            st = "Paid" if (tot <= 0 or paid >= tot) else ("Partial" if paid > 0 else "Unpaid")
            db.execute("UPDATE invoices SET total_amount=?, status=? WHERE id=?", (tot, st, inv["id"]))
        elif inv:
            notes.append("الفاتورة مقفلة: لم يتغير مبلغها")
    if C.get("sent", "") != L.get("sent", ""):
        _apply_sent(db, vid, idx, C.get("sentRaw", ""), base.get("sentRaw", L.get("sentRaw", "")))
    if notes:
        db.execute("UPDATE visits SET notes=COALESCE(notes,'') || ? WHERE id=?", ("\n[من السجل] " + "؛ ".join(notes), vid))
    n_active = db.execute("SELECT COUNT(*) FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=? AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected')", (vid,)).fetchone()[0]
    _set(db, "ledger_orig_v%d" % vid, json.dumps({"tests": ", ".join(C["tests"]), "n": n_active}, ensure_ascii=False))
    db.commit()


_ix_cache = {}


def apply_cloud_edits(db):
    """يقارن كل صف مربوط بالسحابة مع الزيارة: إذا عدّل العميل بالسجل ولم يتغير شيء بالـLIS → يطبَّق على الـLIS.
    إذا تعدّل الاثنان معاً يغلب الـLIS (ويُرفع للسجل). يرجع عدد الزيارات المعدّلة."""
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return 0
    try:
        code, j = _request(c["url"] + "/api/lis/linked?days=%d" % max(7, c["back"]), c["key"], None, 30)
    except Exception:
        return 0
    if code != 200 or not j.get("ok"):
        return 0
    _ix_cache.clear()
    days_cache, n = {}, 0
    for it in j.get("items", []):
        m = re.fullmatch(r"v(\d+)", str(it.get("lisId", "")))
        if not m:
            continue
        vid = int(m.group(1))
        vr = db.execute("SELECT substr(created_at,1,10) d FROM visits WHERE id=?", (vid,)).fetchone()
        if not vr:
            continue
        if vr["d"] not in days_cache:
            days_cache[vr["d"]] = {r["lisId"]: r for r in collect_day(db, vr["d"])}
        Lrow = days_cache[vr["d"]].get(it["lisId"])
        if not Lrow:
            continue
        _ix = _ix_cache.setdefault("i", _test_index(db))
        Cs, Ls = _state(it, _ix), _state(Lrow, _ix)
        bkey = "ledger_base_" + it["lisId"]
        raw = _get(db, bkey)
        try:
            base = json.loads(raw) if raw else Ls
        except Exception:
            base = Ls
        if _same(Cs, base):
            if not raw or not _same(Ls, base):
                _set(db, bkey, json.dumps(Ls, ensure_ascii=False))
            continue
        if _same(Ls, base):
            try:
                _apply_cloud(db, vid, Cs, base, Ls)
                _set(db, bkey, json.dumps(Cs, ensure_ascii=False))
                n += 1
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
                _st["imp_err"] = "تعديل من السجل: " + _redact(e)
        else:
            _set(db, bkey, json.dumps(Ls, ensure_ascii=False))
    db.commit()
    if n:
        try:
            sync(db, max(7, c["back"]), force=True)
        except Exception:
            pass
    return n


_cl_cache = {}


def cloud_logs(db, f, t):
    """صفوف سجل المرضى (السحابة) بين تاريخين للإحصائيات: [{date, rows}] . تخزين مؤقت 25 ثانية. فشلها يرجع [] ."""
    st = cloud_logs.state
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        st["path"], st["err"] = "", "الربط غير مضبوط"
        return []
    ck = (f, t)
    hit = _cl_cache.get(ck)
    if hit and time.time() - hit[0] < 25:
        return hit[1]
    logs = None
    try:
        code, j = _request(c["url"] + "/api/lis/logs?from=%s&to=%s" % (f, t), c["key"], None, 25)
        if code == 200 and j.get("ok"):
            logs, st["path"], st["err"] = j.get("logs") or [], "logs", ""
        elif code == 404 or (code == 400 and (j or {}).get("code") not in ("too_long",)):
            raise LookupError("نسخة السحابة قديمة")
        else:
            st["err"] = _explain(code, j)
    except Exception as e:
        st["err"] = _redact(e)
    if logs is None:       # سحابة قديمة بدون /api/lis/logs: نقرأ غير المستوردين من /incoming (بدون مبالغ كلية)
        try:
            days = max(1, min(400, (date.today() - date.fromisoformat(f)).days + 2))
            code, j = _request(c["url"] + "/api/lis/incoming?days=%d" % days, c["key"], None, 25)
            if code == 200 and j.get("ok"):
                by = {}
                for it in j.get("items", []):
                    if f <= str(it.get("date")) <= t:
                        by.setdefault(it["date"], []).append(it)
                logs, st["path"], st["err"] = [{"date": d, "rows": r} for d, r in sorted(by.items())], "incoming", ""
        except Exception as e:
            st["err"] = _redact(e)
    logs = logs or []
    _cl_cache[ck] = (time.time(), logs)
    return logs


cloud_logs.state = {"path": "", "err": ""}


def cloud_accounts(db):
    """تسويات الأطباء وأسماؤهم من السجل (قراءة فقط): {'adj': [...], 'doctors': [...]}"""
    hit = _cl_cache.get("acct")
    if hit and time.time() - hit[0] < 25:
        return hit[1]
    c = cfg(db)
    out = {"adj": [], "docAdj": [], "genExp": [], "doctors": []}
    if c["url"].startswith("https://") and c["key"]:
        try:
            code, j = _request(c["url"] + "/api/lis/accounts", c["key"], None, 20)
            if code == 200 and j.get("ok"):
                out = {"adj": j.get("adj") or [], "docAdj": j.get("docAdj") or j.get("adj") or [], "genExp": j.get("genExp") or [], "doctors": j.get("doctors") or []}
        except Exception:
            pass
    _cl_cache["acct"] = (time.time(), out)
    return out


def fetch_accounts(db):
    """واجهة الإحصائيات: {'docAdj': تسويات الأطباء, 'genExp': صرفيات عامة} من السجل السحابي."""
    return cloud_accounts(db)


def import_all_old(db, days, user_id=None, branch_id=None):
    """زر «استيراد بيانات السجل القديمة»: يستورد كل ما أُدخل بالسجل خلال N يوم ولم يصل للـLIS."""
    ok, msg, items = incoming(db, days)
    if not ok:
        return False, msg
    n, bad = 0, []
    for it in items:
        try:
            r_ok, r_msg = import_item(db, it["date"], it["rowId"], user_id, branch_id, _items=items, _sync_after=False)
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            r_ok, r_msg = False, _redact(e)
        if r_ok:
            n += 1
        else:
            bad.append(r_msg)
    try:
        sync(db, min(400, int(days)), force=True)
    except Exception:
        pass
    return True, "تم استيراد %d من %d مريض." % (n, len(items)) + (" فشل: " + " | ".join(bad[:3]) if bad else "")


def apply_cloud_deletes(db):
    """v101: مريض حُذف من سجل المرضى (بالرقم السري) ← تُحذف زيارته من الـLIS بكل تفاصيلها (طلبات/نتائج/فواتير).
    أول تشغيل يضبط المؤشر على «الآن» فقط (لا يحذف شيئاً من الماضي). يرجع عدد الزيارات المحذوفة."""
    c = cfg(db)
    if not c["url"].startswith("https://") or not c["key"] or not _H.get("delete_visit"):
        return 0
    raw = _get(db, "ledger_del_since", "")
    try:
        code, j = _request(c["url"] + "/api/lis/deleted?since=%d" % int(raw or 0), c["key"], None, 20)
    except Exception:
        return 0
    if code != 200 or not j.get("ok"):
        return 0
    if raw == "":
        _set(db, "ledger_del_since", str(int(j.get("now") or 0)))
        db.commit()
        return 0
    n, last = 0, int(raw)
    for it in j.get("items", []):
        last = max(last, int(it.get("at") or 0))
        m = re.fullmatch(r"v(\d+)", str(it.get("lisId", "")))
        if not m:
            continue
        v = db.execute("SELECT * FROM visits WHERE id=?", (int(m.group(1)),)).fetchone()
        if v:
            try:
                _H["delete_visit"](db, v)
                n += 1
            except Exception as e:
                _st["imp_err"] = "حذف من السجل: " + _redact(e)
                return n          # لا نحرّك المؤشر: يُعاد المحاولة بالدورة القادمة
    _set(db, "ledger_del_since", str(last))
    db.commit()
    return n



# ------------------------------------------------------------------ v102: نسخة محلية لنتائج المرضى + ضمان وجودها بالسحابة
# - كل PDF يُولَّد لبوابة النتائج يُحفظ بالحاسبة (مجلد portal_archive بجانب قاعدة البيانات) مع بصمة المحتوى.
# - لو انتهت مدة النتيجة بالسحابة (180 يوم) أو انمسحت: يُعاد رفعها من النسخة المحلية مباشرة بدون إعادة توليد.
# - فحص دوري: أي نتيجة غير مرفوعة أو حالتها بالسحابة أقدم من الحالية (تسجيل/اكتمال) تُرفع تلقائياً.
# - طلبات «إعادة رفع» من سجل المرضى (لنتيجة غير موجودة بالسحابة) تُنفَّذ خلال دقيقتين إذا كان الـLIS شغّالاً.
import sqlite3 as _sq

_PG_LOCK = threading.Lock()
_pg = {"deep_t": 0.0, "last": "", "last_t": 0.0}


def arch_dir():
    from database import DB_PATH
    d = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "portal_archive")
    os.makedirs(d, exist_ok=True)
    return d


def _st_db():
    c = _sq.connect(os.path.join(arch_dir(), "state.db"), timeout=15)
    c.execute("CREATE TABLE IF NOT EXISTS st (vid INTEGER PRIMARY KEY, pdf_h TEXT DEFAULT '', push_h TEXT DEFAULT '', "
              "push_at TEXT DEFAULT '', revoked INTEGER DEFAULT 0)")
    return c


def portal_state_hash(data):
    """بصمة محتوى النتيجة (دون حقل الوقت المتوقع): تتغير فقط عند تغيّر نتيجة/مدى/حالة تحليل."""
    if not data:
        return ""
    core = {k: data.get(k) for k in ("patient_name", "created_at", "tests", "group_order")}
    return hashlib.sha1(json.dumps(core, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def archive_get(vid, h):
    """يرجع bytes للـPDF المحفوظ إذا كان لنفس محتوى النتيجة الحالي، وإلا None."""
    try:
        p = os.path.join(arch_dir(), "v%d.pdf" % int(vid))
        if not h or not os.path.isfile(p):
            return None
        c = _st_db()
        try:
            r = c.execute("SELECT pdf_h FROM st WHERE vid=?", (int(vid),)).fetchone()
        finally:
            c.close()
        if r and r[0] == h:
            with open(p, "rb") as f:
                b = f.read()
            return b if b[:4] == b"%PDF" else None
    except Exception:
        pass
    return None


def archive_save(vid, pdf, h):
    """يحفظ نسخة PDF محلية (كتابة آمنة: ملف مؤقت ثم استبدال). لا يرمي أخطاء."""
    try:
        if not pdf or pdf[:4] != b"%PDF":
            return False
        p = os.path.join(arch_dir(), "v%d.pdf" % int(vid))
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(pdf)
        os.replace(tmp, p)
        c = _st_db()
        try:
            c.execute("INSERT INTO st (vid, pdf_h) VALUES (?, ?) ON CONFLICT(vid) DO UPDATE SET pdf_h=excluded.pdf_h", (int(vid), h))
            c.commit()
        finally:
            c.close()
        return True
    except Exception:
        return False


def _st_set(vid, **kw):
    try:
        c = _st_db()
        try:
            c.execute("INSERT OR IGNORE INTO st (vid) VALUES (?)", (int(vid),))
            for k, v in kw.items():
                if k in ("push_h", "push_at", "revoked", "pdf_h"):
                    c.execute("UPDATE st SET %s=? WHERE vid=?" % k, (v, int(vid)))
            c.commit()
        finally:
            c.close()
    except Exception:
        pass


def _st_get(vid):
    try:
        c = _st_db()
        try:
            r = c.execute("SELECT push_h, revoked FROM st WHERE vid=?", (int(vid),)).fetchone()
        finally:
            c.close()
        return (r[0] or "", int(r[1] or 0)) if r else ("", 0)
    except Exception:
        return "", 0


def portal_mark_revoked(vid, on=True):
    """عند إلغاء رابط مريض (revoke) لا يعيد الفحص الدوري رفعه، ويُحذف PDF المحلي. عند إصدار QR جديد يُرفع الإلغاء."""
    _st_set(vid, revoked=1 if on else 0)
    if on:
        try:
            os.remove(os.path.join(arch_dir(), "v%d.pdf" % int(vid)))
        except OSError:
            pass


def archive_stats():
    try:
        d = arch_dir()
        n = tot = 0
        for f in os.listdir(d):
            if f.endswith(".pdf"):
                n += 1
                tot += os.path.getsize(os.path.join(d, f))
        return n, tot
    except Exception:
        return 0, 0


def _expected_code(data):
    """الحالة المتوقعة بالسحابة: r جاهزة كاملة، p جزئية، w قيد التحضير."""
    ts = [t for t in (data or {}).get("tests", []) if t.get("status") not in ("Cancelled", "Canceled", "Rejected")]
    if not ts:
        return "w"
    done = [t for t in ts if t.get("status") in ("Completed", "Verified")]
    return "r" if len(done) == len(ts) else ("p" if done else "w")


def _push_visit(db, vid):
    import cloud_sync
    cloud_sync.ensure_token(db, vid)
    ok, msg = cloud_sync.sync_visit(db, vid, force=True)
    if ok:
        try:
            coll = _H.get("portal_collect")
            _st_set(vid, push_h=portal_state_hash(coll(db, vid)) if coll else "", push_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
    return ok, msg


def portal_guard(db, force=False):
    """يضمن أن كل نتيجة (آخر portal_guard_days يوم، الافتراضي 150) موجودة بالسحابة وبحالتها الصحيحة. يرجع نص ملخّص."""
    c = cfg(db)
    if not (c["enabled"] and c["url"].startswith("https://") and c["key"]):
        return "ربط السجل غير مفعّل."
    if _get(db, "portal_guard", "1") != "1" and not force:
        return "الفحص التلقائي معطّل."
    try:
        import cloud_sync
        if not cloud_sync.get_cfg(db).get("enabled"):
            return "بوابة النتائج (QR) غير مفعّلة بالـLIS."
    except Exception as e:
        return "تعذّر تحميل cloud_sync: %s" % e
    if not _PG_LOCK.acquire(blocking=False):
        return "الفحص يعمل حالياً."
    n = {"resend": 0, "missing": 0, "changed": 0, "fail": 0}
    first_err = ""
    try:
        cap_resend = 40 if force else 10
        cap_missing = 40 if force else 4        # نتائج ناقصة قديمة: دفعات صغيرة حتى لا يُثقل الحاسبة
        cap_changed = 60 if force else 12
        # 1) طلبات «إعادة رفع» القادمة من سجل المرضى
        try:
            code, j = _request(c["url"] + "/api/lis/resend", c["key"], None, 20)
            ids = [x for x in (j.get("ids") or []) if re.fullmatch(r"v\d+", str(x))] if code == 200 else []
        except Exception:
            ids = []
        done = []
        for x in ids[:cap_resend]:
            vid = int(x[1:])
            if not db.execute("SELECT 1 FROM visits WHERE id=?", (vid,)).fetchone():
                done.append(x)                  # الزيارة غير موجودة بالـLIS: أغلق الطلب
                continue
            portal_mark_revoked(vid, False)     # طلب صريح من المستخدم = رفع الإلغاء
            ok, msg = _push_visit(db, vid)
            if ok:
                done.append(x)
                n["resend"] += 1
            else:
                n["fail"] += 1
                first_err = first_err or str(msg)
        if done:
            try:
                _request(c["url"] + "/api/lis/resend-done", c["key"], {"ids": done}, 20)
            except Exception:
                pass
        # 2) الفحص العميق (كل 5 دقائق أو يدوياً)
        now = time.time()
        if force or now - _pg["deep_t"] >= 300:
            _pg["deep_t"] = now
            try:
                win = max(7, min(365, int(_get(db, "portal_guard_days", "150") or 150)))
            except ValueError:
                win = 150
            cutoff = (date.today() - timedelta(days=win)).isoformat()
            recent_cut = (date.today() - timedelta(days=c["back"])).isoformat()
            rows = db.execute(
                "SELECT v.id AS id, v.portal_token AS tok, substr(v.created_at,1,10) AS d FROM visits v "
                "WHERE substr(v.created_at,1,10)>=? AND EXISTS (SELECT 1 FROM orders o JOIN order_tests ot ON ot.order_id=o.id "
                "WHERE o.visit_id=v.id) ORDER BY v.id DESC LIMIT 6000", (cutoff,)).fetchall()
            toks = [r["tok"] for r in rows if r["tok"]]
            have, missing_set, got, cloud_full = {}, set(), False, False
            for i in range(0, len(toks), 1500):
                try:
                    code, j = _request(c["url"] + "/api/lis/portal-missing", c["key"], {"tokens": toks[i:i + 1500]}, 40)
                except Exception:
                    break
                if code != 200 or not j.get("ok"):
                    break
                got = True
                have.update(j.get("have") or {})
                cloud_full = cloud_full or bool(j.get("full"))
                missing_set.update(j.get("missing") or [])
            if got or not toks:
                coll = _H.get("portal_collect")
                to_miss, to_chg = [], []
                for r in rows:                              # الأحدث أولاً
                    vid = r["id"]
                    _h, rev = _st_get(vid)
                    if rev:
                        continue
                    tok = r["tok"]
                    is_recent = r["d"] >= recent_cut
                    if not tok:
                        if is_recent:                       # تسجيل حديث بلا رمز: يُنشأ الرمز ويُرفع (لا نلمس القديم)
                            to_miss.append(vid)
                        continue
                    if tok in missing_set:
                        if is_recent or not cloud_full:    # السحابة ممتلئة: القديم يُرفع فقط عند طلب صريح من سجل المرضى
                            to_miss.append(vid)
                        continue
                    if not is_recent or not coll:
                        continue
                    try:
                        data = coll(db, vid)
                        h = portal_state_hash(data)
                    except Exception:
                        continue
                    if have.get(tok) != _expected_code(data) or (_h and _h != h):
                        to_chg.append(vid)
                    elif not _h:
                        _st_set(vid, push_h=h)              # مطابقة للسحابة: سجّل البصمة فقط
                for vid in to_chg[:cap_changed]:
                    ok, msg = _push_visit(db, vid)
                    n["changed" if ok else "fail"] += 1
                    if not ok:
                        first_err = first_err or str(msg)
                for vid in to_miss[:cap_missing]:
                    ok, msg = _push_visit(db, vid)
                    n["missing" if ok else "fail"] += 1
                    if not ok:
                        first_err = first_err or str(msg)
                left = max(0, len(to_miss) - cap_missing) + max(0, len(to_chg) - cap_changed)
                if left:
                    _pg["deep_t"] = 0.0                     # تبقّى عمل: كمّل بالدورة التالية
        msg = "رُفع: %d بطلب من السجل، %d ناقصة، %d محدَّثة" % (n["resend"], n["missing"], n["changed"])
        if n["fail"]:
            msg += "، فشل %d (%s)" % (n["fail"], first_err[:120])
        if any(n.values()) or force:
            _pg["last"], _pg["last_t"] = msg, time.time()
        return msg
    finally:
        _PG_LOCK.release()


def _loop():
    time.sleep(20)
    while True:
        try:
            db = _db()
            try:
                if cfg(db)["enabled"]:
                    try:
                        with _lock:
                            apply_cloud_deletes(db)      # قبل الدفع: حتى لا يُعاد رفع مريض محذوف
                    except Exception:
                        pass
                    with _lock:
                        ok, msg, _n = sync(db)
                    if not ok:
                        _set(db, "ledger_last_err", "%s  %s" % (datetime.now().strftime("%H:%M"), msg))
                        db.commit()
                    else:
                        try:
                            with _lock:
                                _auto_import(db)
                                apply_cloud_edits(db)
                                if _get(db, "ledger_backfill_v1", "") != "1":
                                    ok_b, _m, _n = sync(db, 365)       # مرة وحدة: ارفع كل سجل السنة الماضية للسحابة
                                    if ok_b:
                                        _set(db, "ledger_backfill_v1", "1")
                                        db.commit()
                        except Exception:
                            pass
                        try:
                            portal_guard(db)               # v102: ضمان رفع النتائج للسحابة (خارج قفل المزامنة)
                        except Exception:
                            pass
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
        lbl = "السحابة: متزامن ✓" + (" • %d واردة من السجل" % _st["incoming"] if _st.get("incoming") else "")
        return ("y" if _st.get("incoming") else "g"), lbl, time.strftime("آخر مزامنة %H:%M:%S", time.localtime(_st["ok_t"]))
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
<div><button id="sv">حفظ</button><button id="ts" class="g">اختبار الاتصال</button><button id="sy" class="g">مزامنة الآن</button><button id="bf" class="g">رفع آخر 30 يوم</button><button id="bo" class="g">رفع كل بيانات LIS (سنة)</button><button id="io" class="g">استيراد بيانات السجل القديمة (سنة)</button></div>
<div style="margin-top:10px"><button id="pg" class="g">رفع النتائج الناقصة للسحابة الآن</button><button id="ps" class="g">حالة النتائج</button></div>
<div class="m" id="r">__STAT__</div>
<h3 style="margin:18px 0 6px">مرضى أُدخلوا بالسجل (واردون للـLIS) <button id="ia" class="g" style="padding:4px 10px;font-size:13px">استيراد الكل</button></h3><div id="ii" class="s">جاري التحميل…</div>
<h3 style="margin:18px 0 6px">دفعات أُدخلت من السجل (بانتظار اعتمادك)</h3><div id="pp" class="s">جاري التحميل…</div>
<div class="s">فتح السجل: <a href="__URL__" target="_blank">__URL__</a></div></div>
<script>
var $=function(i){return document.getElementById(i)};
function post(p,b){return fetch(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})}).then(function(r){return r.json()})}
function body(){return {url:$("u").value,key:$("k").value,enabled:$("e").checked}}
function run(p,b,w){$("r").textContent=w;post(p,b).then(function(j){$("r").textContent=j.message||j.error||"تم"}).catch(function(e){$("r").textContent="فشل: "+e})}
$("sv").onclick=function(){run("/ledger/save",body(),"جاري الحفظ…")};
$("pg").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/portal-guard",{},"جاري البدء…")})};
$("ps").onclick=function(){run("/ledger/portal-status",{},"جاري القراءة…")};
$("ts").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/test",{},"جاري الاختبار…")})};
$("sy").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/sync",{days:3},"جاري المزامنة…")})};
$("bf").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/sync",{days:30,force:true},"جاري رفع 30 يوم…")})};
$("bo").onclick=function(){post("/ledger/save",body()).then(function(){run("/ledger/sync",{days:365,force:true},"جاري رفع بيانات سنة كاملة… قد ياخذ دقائق")})};
$("io").onclick=function(){if(!confirm("سيُستورد للـLIS كل ما أُدخل بالسجل خلال آخر سنة ولم يصل للـLIS. متأكد؟"))return;post("/ledger/save",body()).then(function(){run("/ledger/import",{old:true,days:365},"جاري الاستيراد… قد ياخذ دقائق")})};
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function lp(){post("/ledger/pending",{}).then(function(j){if(!j.ok){$("pp").textContent=j.message||"تعذّر التحميل";return}
if(!j.items.length){$("pp").textContent="لا توجد دفعات معلّقة ✓";return}
$("pp").innerHTML=j.items.map(function(i){return '<div style="padding:8px;border:1px solid #d6e4e1;border-radius:9px;margin:6px 0">'+esc(i.name)+' — <b>'+i.diff+'</b> د.ع ('+esc(i.date)+') <button data-id="'+esc(i.lisId)+'">اعتماد</button></div>'}).join("");
Array.prototype.forEach.call($("pp").querySelectorAll("button"),function(b){b.onclick=function(){b.disabled=true;post("/ledger/approve",{lisId:b.getAttribute("data-id")}).then(function(j){$("r").textContent=j.message;lp()})}})}).catch(function(){$("pp").textContent="تعذّر التحميل"})}
function li(){post("/ledger/incoming",{}).then(function(j){if(!j.ok){$("ii").textContent=j.message||"تعذّر التحميل";return}
if(!j.items.length){$("ii").textContent="لا يوجد مرضى جدد بالسجل ✓";return}
$("ii").innerHTML=j.items.map(function(i){var bad=i.unmatched.length?'<div style="color:#b91c1c">لم تُطابَق: '+esc(i.unmatched.join("، "))+'</div>':"";
return '<div style="padding:8px;border:1px solid #d6e4e1;border-radius:9px;margin:6px 0"><b>'+esc(i.name)+'</b> — '+esc(i.date)+(i.priceType==="lab"?" (مختبر: "+esc(i.refDoctor)+")":(i.refDoctor?" (د. "+esc(i.refDoctor)+")":""))+'<div>'+esc(i.tests)+'</div>'+bad+'<div>واصل: <b>'+i.paid+'</b> <button data-d="'+esc(i.date)+'" data-r="'+esc(i.rowId)+'">استيراد</button> <button class="g" data-s="1" data-d="'+esc(i.date)+'" data-r="'+esc(i.rowId)+'">تجاهل</button></div></div>'}).join("");
Array.prototype.forEach.call($("ii").querySelectorAll("button"),function(b){b.onclick=function(){b.disabled=true;post(b.getAttribute("data-s")?"/ledger/skip":"/ledger/import",{date:b.getAttribute("data-d"),rowId:b.getAttribute("data-r")}).then(function(j){$("r").textContent=j.message;li()})}})}).catch(function(){$("ii").textContent="تعذّر التحميل"})}
$("ia").onclick=function(){$("ia").disabled=true;$("r").textContent="جاري الاستيراد…";post("/ledger/import",{all:true}).then(function(j){$("r").textContent=j.message;$("ia").disabled=false;li()})};
li();lp();
</script></body></html>'''


def install(app, helpers=None):
    if helpers:
        _H.update(helpers)
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

    @bp.route("/ledger/portal-guard", methods=["POST"])
    def portal_guard_now():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401

        def _run():
            d2 = _db()
            try:
                portal_guard(d2, force=True)
            except Exception as e:
                _pg["last"], _pg["last_t"] = "خطأ: %s" % e, time.time()
            finally:
                d2.close()
        threading.Thread(target=_run, name="portal-guard-now", daemon=True).start()
        return jsonify(ok=True, message="بدأ فحص النتائج ورفع الناقص بالخلفية. اضغط «حالة النتائج» بعد دقيقة.")

    @bp.route("/ledger/portal-status", methods=["POST"])
    def portal_status():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        cnt, size = archive_stats()
        last = _pg["last"] + (time.strftime(" (%H:%M:%S)", time.localtime(_pg["last_t"])) if _pg["last_t"] else "")
        return jsonify(ok=True, message="نسخ PDF محلية: %d ملف (%.1f ميغابايت)\nآخر فحص: %s" % (cnt, size / 1048576.0, last or "—"))

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

    @bp.route("/ledger/incoming", methods=["POST"])
    def inc():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        db = _db()
        try:
            ok, msg, items = incoming(db)
            return jsonify(ok=ok, message=msg, items=items)
        finally:
            db.close()

    @bp.route("/ledger/import", methods=["POST"])
    def imp():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        d = request.get_json(silent=True) or {}
        db = _db()
        try:
            with _lock:
                if d.get("old"):
                    ok, msg = import_all_old(db, int(d.get("days") or 365), session.get("user_id"), session.get("branch_id"))
                    return jsonify(ok=ok, message=msg)
                if d.get("all"):
                    ok, msg, items = incoming(db)
                    if not ok:
                        return jsonify(ok=False, message=msg)
                    n, notes = 0, []
                    for it in items:
                        r_ok, r_msg = import_item(db, it["date"], it["rowId"], session.get("user_id"), session.get("branch_id"))
                        n += 1 if r_ok else 0
                        if not r_ok:
                            notes.append(r_msg)
                    return jsonify(ok=True, message="تم استيراد %d مريض." % n + (" " + " | ".join(notes) if notes else ""))
                ok, msg = import_item(db, str(d.get("date") or ""), str(d.get("rowId") or ""), session.get("user_id"), session.get("branch_id"))
            return jsonify(ok=ok, message=msg)
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            return jsonify(ok=False, message="فشل الاستيراد: " + _redact(e))
        finally:
            db.close()

    @bp.route("/ledger/skip", methods=["POST"])
    def skp():
        if not allowed():
            return jsonify(ok=False, message="سجّل الدخول أولاً."), 401
        d = request.get_json(silent=True) or {}
        db = _db()
        try:
            ok = skip_item(db, str(d.get("date") or ""), str(d.get("rowId") or ""))
            return jsonify(ok=ok, message="تم التجاهل." if ok else "تعذّر التجاهل.")
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
