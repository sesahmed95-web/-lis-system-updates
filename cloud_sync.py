# -*- coding: utf-8 -*-
"""
cloud_sync.py — مزامنة نتائج الزيارات مع بوابة النتائج السحابية (cloud_portal على Render)
==========================================================================================
الفكرة: لكل زيارة رمز عشوائي طويل (portal_token) يُطبع كـQR للمريض. هذا الملف:
  1) يولّد الرمز عند الحاجة.
  2) يبني الحمولة: pending (مع الوقت المتوقع) أو ready (جدول النتائج HTML).
  3) عامل خلفي (thread) كل ~30 ثانية يقارن "بصمة" حالة كل زيارة حديثة بآخر بصمة اندفعت
     للبوابة، ويرسل فقط الجديد. لو ما فيه إنترنت يعيد المحاولة تلقائيًا (backoff) — فما
     نحتاج نربط كل أماكن حفظ النتائج بالبرنامج، ولا تضيع نتيجة بسبب انقطاع.

الاتصال خارجي فقط (من جهاز المختبر نحو البوابة) — ما نفتح أي منفذ بالمختبر.
يعتمد فقط على مكتبات بايثون القياسية (urllib) — ما يحتاج تثبيت شي إضافي.

التوصيل مع app.py: app.py يسجّل دالة collector عبر set_collector(...) تُرجع بيانات الزيارة
(حتى لا نعمل استيراد دائري ونعيد استخدام نفس منطق بناء صفوف النتائج بالتقارير).
"""
import base64
import hashlib
import os
import html as _html
import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import database

SYNC_INTERVAL_SEC = 30
RECENT_DAYS = 31          # نتابع الزيارات الحديثة فقط (البوابة تحذف بعد 30 يوم افتراضيًا)
HTTP_TIMEOUT_SEC = 70     # Render المجاني يحتاج وقت يصحى من النوم (cold start)
# إعادة دفع دورية حتى لو ما تغيّر شي: على خطة Render المجانية قاعدة SQLite مؤقتة وتنمسح عند النوم/إعادة
# النشر، فإعادة الإرسال كل بضع ساعات ترجّع السجلات المفقودة تلقائيًا (الحل الجذري: Postgres/قرص دائم).
REPUSH_HOURS = 6
MISSING_CHECK_SEC = 300   # كل 5 دقائق نسأل البوابة: أي رموز ضاعت (نوم Render)؟ ونعيد دفعها فورًا (وهذا أيضًا يبقيها صاحية أثناء دوام المختبر)
PDF_RETRY_MIN = 10        # لو فشل توليد PDF نعيد المحاولة بعد 10 دقائق (مو كل 30 ثانية)
MAX_PDF_BYTES = 6 * 1024 * 1024

_collector = None
_pdf_maker = None
_last_missing_check = 0.0
_wake = threading.Event()
_started = False
_start_lock = threading.Lock()


def set_collector(fn):
    """fn(db, visit_id) -> dict أو None:
       {"patient_name", "created_at", "tests": [{"td_id", "code", "name", "status",
                                                 "rows": [ {name,result,unit,flag,range_display,value2,unit2,...} ]}]}"""
    global _collector
    _collector = fn


def set_pdf_maker(fn):
    """fn(visit_id) -> bytes (PDF) أو None. يُسجَّل من app.py (نفس تقارير المختبر المصممة)."""
    global _pdf_maker
    _pdf_maker = fn


# ------------------------------------------------------------------ الإعدادات
def get_cfg(db):
    gs = database.get_setting
    return {
        "enabled": gs(db, "portal_enabled", "0") == "1",
        "url": (gs(db, "portal_url", "") or "").strip().rstrip("/"),
        "api_key": (gs(db, "portal_api_key", "") or "").strip(),
        "default_hours": _num(gs(db, "portal_default_hours", "2"), 2.0),
        "overrides": parse_overrides(gs(db, "portal_tat_overrides", "")),
        "ready_when": gs(db, "portal_ready_when", "completed"),   # completed | verified
        "pdf_enabled": gs(db, "portal_pdf_enabled", "1") == "1",   # إرفاق نسخة PDF للمريض
        # local  = البوابة مدمجة ببرنامج المختبر (portal_local.py) وتُعرَّض بنفق — بدون Render/GitHub
        # remote = البوابة القديمة على Render (cloud_portal) عبر مفتاح سري
        "mode": "remote" if gs(db, "portal_mode", "local") == "remote" else "local",
    }


def _num(v, default):
    try:
        return max(0.0, float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def parse_overrides(text):
    """سطر بكل تحليل: CODE=ساعات  (مثلاً FBS=1 أو HBA1C=24)"""
    out = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            k = k.strip().upper()
            if k:
                out[k] = _num(v, None) if _num(v, None) is not None else None
    return {k: v for k, v in out.items() if v is not None}


def is_configured(cfg):
    if cfg.get("mode") == "local":
        return bool(cfg["enabled"] and cfg["url"])
    return bool(cfg["enabled"] and cfg["url"] and cfg["api_key"])


def portal_link(cfg, token):
    return f"{cfg['url']}/r/{token}" if cfg.get("url") and token else ""


# ------------------------------------------------------------------ الرمز
def ensure_token(db, visit_id):
    row = db.execute("SELECT portal_token FROM visits WHERE id=?", (visit_id,)).fetchone()
    if not row:
        return None
    if row["portal_token"]:
        return row["portal_token"]
    token = secrets.token_urlsafe(32)   # 32 بايت عشوائي — يستحيل تخمينه
    db.execute("UPDATE visits SET portal_token=? WHERE id=?", (token, visit_id))
    db.commit()
    return token


# ------------------------------------------------------------------ بناء الحمولة
def _eta_text(cfg, data):
    """الوقت المتوقع = أطول وقت بين التحاليل غير الجاهزة (أو كلها لو ما اكتمل شي)، منسوبًا لوقت التسجيل."""
    # وقت يحدده الاستقبال يدويًا بصفحة زيارة جديدة (اختياري) — يغلب التقدير التلقائي
    _exp = (data.get("expected_ready_at") or "").strip()
    if _exp:
        try:
            _dt = datetime.fromisoformat(_exp)
            return "الوقت المتوقع: " + _dt.strftime("%Y-%m-%d") + " الساعة " + _dt.strftime("%H:%M")
        except (TypeError, ValueError):
            pass
    pending = [t for t in data["tests"] if not _is_ready(cfg, t["status"])] or data["tests"]
    hours = 0.0
    for t in pending:
        h = cfg["overrides"].get((t.get("code") or "").upper(), cfg["default_hours"])
        hours = max(hours, h)
    if hours <= 0:
        return ""
    try:
        start = datetime.fromisoformat(data["created_at"])
        eta_at = start + timedelta(hours=hours)
        hhmm = eta_at.strftime("%H:%M")
    except (TypeError, ValueError):
        hhmm = ""
    if hours == int(hours):
        h_txt = {1: "ساعة", 2: "ساعتين"}.get(int(hours), f"{int(hours)} ساعات")
    else:
        h_txt = f"{hours:g} ساعة"
    return f"الوقت المتوقع: حوالي {h_txt}" + (f" (قرابة الساعة {hhmm})" if hhmm else "")


def _is_ready(cfg, status):
    if cfg["ready_when"] == "verified":
        return status == "Verified"
    return status in ("Completed", "Verified")


def _esc(v):
    return _html.escape("" if v is None else str(v))


def _results_html(cfg, data):
    parts = []
    for t in data["tests"]:
        if not _is_ready(cfg, t["status"]) or not t["rows"]:
            continue
        body = []
        for r in t["rows"]:
            if r.get("result") in (None, ""):
                continue
            flag = r.get("flag")
            flag_html = ""
            if flag and flag != "Normal":
                flag_html = f' <b style="color:#B91C1C;">{_esc(flag)}</b>'
            tiers = r.get("range_tiers") or []
            if len(tiers) > 1 or (tiers and tiers[0].get("label")):
                # نسب متعددة (مثل HbA1c / Vit D): كل حالة بسطر مستقل بتسميتها
                rng_html = "".join(
                    "<div dir='ltr' style='text-align:start;'>"
                    + (f"<b>{_esc(x.get('label'))}:</b> " if x.get("label") else "") + _esc(x.get("value", "")) + "</div>"
                    for x in tiers)
            else:
                rng = r.get("range_display") or (tiers[0].get("value") if tiers else "") or ""
                rng_html = f"<span dir='ltr'>{_esc(rng)}</span>"
            unit = _esc(r.get("unit") or "")
            if r.get("value2") not in (None, "") and r.get("unit2"):
                unit += f' <span style="color:#64748B;">/ {_esc(r["value2"])} {_esc(r["unit2"])}</span>'
            body.append(
                f"<tr><td style='text-align:start;font-weight:600;'>{_esc(r.get('name'))}</td>"
                f"<td><b dir='ltr'>{_esc(r.get('result'))}</b>{flag_html}</td><td dir='ltr'>{unit}</td><td>{rng_html}</td></tr>")
        if body:
            parts.append(
                f"<h3 style='margin:18px 0 6px;font-size:15px;color:#205072;'>{_esc(t['name'])}</h3>"
                "<table><tr><th>التحليل</th><th>النتيجة</th><th>الوحدة</th><th>المدى الطبيعي</th></tr>"
                + "".join(body) + "</table>")
    waiting = [t["name"] for t in data["tests"] if not _is_ready(cfg, t["status"])]
    if waiting:
        parts.append("<p style='margin-top:16px;color:#92400E;background:#FEF9E7;border-radius:8px;padding:8px 10px;'>"
                     "⏳ قيد التحضير: " + _esc("، ".join(waiting)) + "</p>")
    return "".join(parts)


def build_payload(db, visit_id, cfg, token=None):
    if _collector is None:
        return None
    data = _collector(db, visit_id)
    if not data or not data["tests"]:
        return None
    token = token or ensure_token(db, visit_id)
    all_ready = all(_is_ready(cfg, t["status"]) for t in data["tests"])
    # الاسم الظاهر للمريض: كامل كما هو بالبرنامج (راجع README لتقليله إن حبيت)
    payload = {"token": token, "patient_name": data["patient_name"] or "—",
               "status": "ready" if all_ready else "pending",
               # اسم المختبر الظاهر بصفحة المريض = اسم المختبر بإعدادات هذا البرنامج (يختلف لكل عميل)
               "lab_name": (database.get_setting(db, "app_name_ar", "") or database.get_setting(db, "app_name", "")
                            or "")[:120]}
    if all_ready:
        payload["results_html"] = _results_html(cfg, data)
    else:
        payload["eta_text"] = _eta_text(cfg, data)
    return payload


def _fingerprint(payload):
    # lab_name خارج البصمة: تغيير الاسم لا يستوجب إعادة توليد كل ملفات PDF؛ يصل مع أول دفع طبيعي.
    raw = json.dumps({k: v for k, v in payload.items() if k != "lab_name"}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ HTTP
def _post(cfg, path, payload):
    req = urllib.request.Request(
        cfg["url"] + path, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": cfg["api_key"],
                 "User-Agent": "LIS-CloudSync/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        return resp.status


# ------------------------------------------------------------------ كاش PDF
# توليد PDF بـChromium ياخذ عدة ثواني. نخزّن النسخة على القرص (portal_pdf_cache) مفتاحها بصمة محتوى النتيجة،
# فإعادة الدفع بعد نوم Render ترسل الملف المخزّن مباشرة بدل إعادة توليد عشرات الملفات.
_last_prune = 0.0


def _pdf_cache_dir():
    path = os.path.join(database._BASE_DIR, "portal_pdf_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _get_pdf(visit_id, fp):
    d = _pdf_cache_dir()
    name = f"{visit_id}_{fp[:24]}.pdf"
    path = os.path.join(d, name)
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            if data[:4] == b"%PDF":
                return data
        except OSError:
            pass
    pdf = _pdf_maker(visit_id)
    if pdf and pdf[:4] == b"%PDF" and len(pdf) <= MAX_PDF_BYTES:
        try:
            for f in os.listdir(d):                       # نسخ قديمة لنفس الزيارة (نتيجة تغيّرت)
                if f.startswith(f"{visit_id}_") and f != name:
                    os.remove(os.path.join(d, f))
            with open(path, "wb") as fh:
                fh.write(pdf)
        except OSError:
            pass
    return pdf


def _prune_pdf_cache():
    """مرة بالساعة: يحذف ملفات الكاش الأقدم من (RECENT_DAYS + 5) يوم."""
    global _last_prune
    if time.time() - _last_prune < 3600:
        return
    _last_prune = time.time()
    try:
        d = _pdf_cache_dir()
        limit = time.time() - (RECENT_DAYS + 5) * 86400
        for f in os.listdir(d):
            fp_ = os.path.join(d, f)
            if os.path.getmtime(fp_) < limit:
                os.remove(fp_)
    except OSError:
        pass


def _post_json(cfg, path, payload):
    req = urllib.request.Request(
        cfg["url"] + path, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": cfg["api_key"],
                 "User-Agent": "LIS-CloudSync/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def test_connection(cfg):
    """(ok, رسالة). local: نفتح الرابط العام من جهاز المختبر نفسه ونتأكد إنه يوصل لبوابة البرنامج.
    remote: نرسل سجل تجريبي ثم نحذفه."""
    if cfg.get("mode") == "local":
        if not cfg["url"]:
            return False, "أدخل الرابط العام (من Tailscale Funnel أو Cloudflare Tunnel) أولاً."
        if not cfg["url"].startswith("https://"):
            return False, "الرابط لازم يبدأ بـ https:// (الموبايل ما يفتح روابط بدون تشفير بشكل موثوق)."
        try:
            req = urllib.request.Request(cfg["url"] + "/healthz", headers={"User-Agent": "LIS-CloudSync/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read(200).decode("utf-8", "ignore")
            if "lis-portal-ok" in body:
                return True, "✅ الرابط العام يوصل لبوابة البرنامج بنجاح."
            return False, "❌ الرابط يفتح لكن مو لبوابة برنامجك (تأكد أن النفق يشير للمنفذ 9091)."
        except urllib.error.HTTPError as e:
            return False, f"❌ الرابط رجّع HTTP {e.code} — النفق شغّال؟ يشير للمنفذ 9091؟"
        except Exception as e:  # noqa: BLE001
            return False, f"❌ تعذر الوصول للرابط العام: {type(e).__name__} — شغّل النفق أولاً."
    if not cfg["url"] or not cfg["api_key"]:
        return False, "أدخل رابط البوابة والمفتاح السري أولاً."
    tok = "connection-test-" + secrets.token_hex(8)
    try:
        _post(cfg, "/api/push", {"token": tok, "patient_name": "Connection Test", "status": "pending"})
        _post(cfg, "/api/delete", {"token": tok})
        return True, "✅ الاتصال ناجح والمفتاح صحيح."
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "❌ المفتاح السري غير مطابق لـ API_SECRET_KEY بـ Render."
        if e.code == 500:
            return False, "❌ السيرفر يقول API_SECRET_KEY غير مضبوط بمتغيرات Render."
        return False, f"❌ البوابة رجّعت خطأ HTTP {e.code}."
    except Exception as e:  # noqa: BLE001 — أي فشل شبكة نعرضه بنص مفهوم
        return False, f"❌ تعذر الوصول للبوابة (إنترنت/رابط خطأ؟): {type(e).__name__}"


def _deliver(cfg, payload, pdf_bytes):
    """يسلّم الحمولة: محليًا (نفس العملية) أو عبر HTTP لبوابة Render."""
    if cfg.get("mode") == "local":
        import portal_local
        portal_local.store(payload["token"], payload["patient_name"], payload["status"],
                           payload.get("eta_text"), payload.get("results_html"), pdf_bytes, payload.get("lab_name") or None)
        return
    send = dict(payload)
    if pdf_bytes:
        send["pdf_b64"] = base64.b64encode(pdf_bytes).decode("ascii")
    _post(cfg, "/api/push", send)


# ------------------------------------------------------------------ المزامنة
def sync_visit(db, visit_id, cfg=None, force=False):
    """يرسل زيارة وحدة إذا تغيّرت حالتها. يرجع (ok, msg). لا يرمي استثناءات."""
    cfg = cfg or get_cfg(db)
    if not is_configured(cfg):
        return False, "المزامنة غير مفعّلة/غير مكتملة الإعداد"
    payload = build_payload(db, visit_id, cfg)
    if payload is None:
        return False, "لا توجد بيانات للزيارة"
    fp = _fingerprint(payload)
    want_pdf = bool(payload["status"] == "ready" and cfg.get("pdf_enabled") and _pdf_maker is not None)
    st = db.execute("SELECT * FROM portal_state WHERE visit_id=?", (visit_id,)).fetchone()
    now = datetime.now()
    if st and not force:
        if st["last_hash"] in (fp, fp + ":pdf"):
            had_pdf = st["last_hash"].endswith(":pdf")
            try:
                age = now - datetime.fromisoformat(st["last_pushed_at"])
            except (TypeError, ValueError):
                age = timedelta(hours=REPUSH_HOURS + 1)
            pdf_retry = want_pdf and not had_pdf and age >= timedelta(minutes=PDF_RETRY_MIN)
            # النتيجة الجاهزة اللي وصل ملف PDF الخاص بها لا تحتاج إعادة دفع دورية (كانت تعيد توليد كل
            # الـPDFات كل 6 ساعات). لو ضاعت من البوابة، /api/missing يكتشفها ويعيد دفعها من الكاش.
            settled = payload["status"] == "ready" and (had_pdf or not want_pdf)
            if not pdf_retry and (settled or age < timedelta(hours=REPUSH_HOURS)):
                return True, "محدّث"
        if st["next_try_at"] and st["next_try_at"] > now.isoformat(timespec="seconds"):
            return False, "بانتظار إعادة المحاولة"
    pdf_bytes = None
    stored_hash = fp
    pdf_err = None
    if want_pdf:
        try:
            pdf = _get_pdf(visit_id, fp)
            if pdf and pdf[:4] == b"%PDF" and len(pdf) <= MAX_PDF_BYTES:
                pdf_bytes = pdf
                stored_hash = fp + ":pdf"
            else:
                pdf_err = "PDF: لم يُولَّد ملف صالح (هل playwright مثبّت؟ playwright install chromium)"
        except Exception as e:  # noqa: BLE001 — فشل الـPDF ما يمنع نشر النتيجة نفسها
            pdf_err = ("PDF: " + f"{type(e).__name__}: {e}")[:300]
    try:
        _deliver(cfg, payload, pdf_bytes)
    except Exception as e:  # noqa: BLE001
        attempts = (st["attempts"] if st else 0) + 1
        delay = min(900, 20 * (2 ** min(attempts, 6)))      # 40ث، 80ث ... حتى 15 دقيقة
        nxt = (now + timedelta(seconds=delay)).isoformat(timespec="seconds")
        msg = f"{type(e).__name__}: {e}"[:300]
        db.execute(
            "INSERT INTO portal_state (visit_id, last_error, attempts, next_try_at) VALUES (?,?,?,?) "
            "ON CONFLICT(visit_id) DO UPDATE SET last_error=excluded.last_error, "
            "attempts=excluded.attempts, next_try_at=excluded.next_try_at",
            (visit_id, msg, attempts, nxt))
        db.commit()
        return False, msg
    db.execute(
        "INSERT INTO portal_state (visit_id, last_status, last_hash, last_pushed_at, last_error, attempts, next_try_at) "
        "VALUES (?,?,?,?,?,0,NULL) ON CONFLICT(visit_id) DO UPDATE SET last_status=excluded.last_status, "
        "last_hash=excluded.last_hash, last_pushed_at=excluded.last_pushed_at, last_error=excluded.last_error, attempts=0, next_try_at=NULL",
        (visit_id, payload["status"], stored_hash, now.isoformat(timespec="seconds"), pdf_err))
    db.commit()
    return True, payload["status"]


def _find_missing_visit_ids(db, cfg):
    """يسأل البوابة أي رموز (دفعناها سابقًا) صارت غير موجودة عندها — يصير لما Render ينام أو يعيد النشر."""
    global _last_missing_check
    if time.time() - _last_missing_check < MISSING_CHECK_SEC:
        return set()
    _last_missing_check = time.time()
    rows = db.execute(
        "SELECT v.id, v.portal_token FROM visits v JOIN portal_state ps ON ps.visit_id = v.id "
        "WHERE v.portal_token IS NOT NULL AND v.portal_token<>'' AND ps.last_pushed_at IS NOT NULL "
        "AND v.created_at>=?",
        ((datetime.now() - timedelta(days=RECENT_DAYS)).isoformat(timespec="seconds"),)).fetchall()
    if not rows:
        return set()
    by_token = {r["portal_token"]: r["id"] for r in rows}
    try:
        res = _post_json(cfg, "/api/missing", {"tokens": list(by_token)[:2000]})
    except Exception:  # noqa: BLE001 — البوابة قد تكون نايمة/بدون إنترنت؛ نجرب بالدورة القادمة
        return set()
    return {by_token[t] for t in (res.get("missing") or []) if t in by_token}


def sync_all_recent(db=None):
    own = db is None
    db = db or database.get_db()
    try:
        cfg = get_cfg(db)
        if not is_configured(cfg):
            return 0
        since = (datetime.now() - timedelta(days=RECENT_DAYS)).isoformat(timespec="seconds")
        ids = [r["id"] for r in db.execute(
            "SELECT id FROM visits WHERE portal_token IS NOT NULL AND portal_token<>'' AND created_at>=?", (since,))]
        _prune_pdf_cache()
        lost = _find_missing_visit_ids(db, cfg) if cfg.get("mode") != "local" else set()
        n = 0
        for vid in ids:
            ok, _ = sync_visit(db, vid, cfg, force=(vid in lost))
            n += 1 if ok else 0
        return n
    finally:
        if own:
            db.close()


def revoke(db, visit_id):
    """إلغاء الرمز: حذف من البوابة (لو أمكن) + مسح الرمز محليًا (الـQR المطبوع يصير بلا فائدة)."""
    cfg = get_cfg(db)
    row = db.execute("SELECT portal_token FROM visits WHERE id=?", (visit_id,)).fetchone()
    if not row or not row["portal_token"]:
        return False, "لا يوجد رمز"
    msg = ""
    if cfg.get("mode") == "local":
        import portal_local
        portal_local.delete(row["portal_token"])
    elif is_configured(cfg):
        try:
            _post(cfg, "/api/delete", {"token": row["portal_token"]})
        except Exception as e:  # noqa: BLE001
            msg = f"(تعذر الحذف من البوابة الآن: {type(e).__name__})"
    db.execute("UPDATE visits SET portal_token=NULL WHERE id=?", (visit_id,))
    db.execute("DELETE FROM portal_state WHERE visit_id=?", (visit_id,))
    db.commit()
    return True, msg


# ------------------------------------------------------------------ العامل الخلفي
def trigger():
    """يوقظ العامل فورًا (مثلاً بعد تسجيل زيارة) بدل انتظار الدورة التالية."""
    _wake.set()


def _loop():
    while True:
        _wake.wait(SYNC_INTERVAL_SEC)
        _wake.clear()
        try:
            sync_all_recent()
        except Exception:  # noqa: BLE001 — العامل ما يوقف أبدًا
            pass


def start_worker():
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        try:
            import portal_local
            portal_local.start_server()      # البوابة العامة المدمجة (127.0.0.1:9091) — آمنة: قراءة فقط
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=_loop, name="portal-sync", daemon=True).start()


# ------------------------------------------------------------------ تشخيص "ليش الـQR ما يطلّع النتائج؟"
def diagnose(db, visit_id):
    """يفحص سلسلة الـQR كاملة ويرجّع قائمة (مستوى, نص): ok / warn / bad. للقراءة فقط (ما يغيّر شي)."""
    import urllib.parse
    out = []
    cfg = get_cfg(db)
    if not cfg["enabled"]:
        out.append(("bad", "المزامنة غير مفعّلة: الإعدادات ← 📱 بوابة النتائج ← فعّل."))
    url = cfg["url"]
    if not url:
        out.append(("bad", "رابط البوابة العام فاضي: الصق رابط النفق (https://...) بالإعدادات ← بوابة النتائج."))
    else:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        private = (host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168.") or host.startswith("10.")
                   or (host.startswith("172.") and host.split(".")[1:2] and host.split(".")[1].isdigit() and 16 <= int(host.split(".")[1]) <= 31)
                   or host.endswith(".local"))
        if private:
            out.append(("bad", f"الرابط ({host}) محلي/شبكة داخلية — موبايل المريض ما يقدر يوصله. لازم رابط عام https من Tailscale Funnel أو Cloudflare Tunnel."))
        elif not url.startswith("https://"):
            out.append(("warn", "الرابط ما يبدأ بـ https:// — بعض الموبايلات ما تفتحه. استخدم رابط https."))
        else:
            out.append(("ok", f"الرابط العام: {url}"))
    if cfg.get("mode") == "local":
        try:
            with urllib.request.urlopen("http://127.0.0.1:9091/healthz", timeout=4) as r:
                ok = b"lis-portal-ok" in r.read(200)
            out.append(("ok", "بوابة البرنامج المحلية (9091) شغّالة.") if ok else ("bad", "المنفذ 9091 يرد لكن مو بوابة البرنامج."))
        except Exception as e:  # noqa: BLE001
            out.append(("bad", f"بوابة البرنامج المحلية (9091) ما تشتغل ({type(e).__name__}) — أعد تشغيل البرنامج."))
        if url and url.startswith("https://"):
            ok, msg = test_connection(cfg)
            out.append(("ok" if ok else "bad", "الرابط العام من هذا الجهاز: " + msg.replace("✅ ", "").replace("❌ ", "")))
    row = db.execute("SELECT portal_token FROM visits WHERE id=?", (visit_id,)).fetchone()
    tok = row["portal_token"] if row else None
    if not tok:
        out.append(("bad", "هذي الزيارة ما لها رمز QR بعد (سجّلت قبل تفعيل المزامنة؟). افتح ورقة الـQR مرة ثانية لتوليده."))
    st = db.execute("SELECT * FROM portal_state WHERE visit_id=?", (visit_id,)).fetchone()
    if tok and not st:
        out.append(("warn", "الزيارة لم تُدفع للبوابة بعد (انتظر نصف دقيقة أو اضغط 🔄 مزامنة)."))
    if st and st["last_error"]:
        out.append(("bad", "آخر خطأ مزامنة: " + str(st["last_error"])))
    if st and st["last_status"]:
        if st["last_status"] == "ready":
            out.append(("ok", "حالة الزيارة بالبوابة: جاهزة — النتائج تظهر للمريض."))
        else:
            out.append(("warn", "حالة الزيارة بالبوابة: «قيد التحضير» — النتائج لا تظهر إلا بعد اكتمال كل تحاليل الزيارة."))
    sts = db.execute(
        "SELECT td.name, ot.status FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
        "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=?", (visit_id,)).fetchall()
    pend = [r["name"] for r in sts if not _is_ready(cfg, r["status"])]
    if pend:
        need = "Verified (معتمدة)" if cfg["ready_when"] == "verified" else "Completed (مكتملة)"
        out.append(("warn", f"تحاليل غير {need} بعد: " + "، ".join(pend[:8]) + " — لذلك تبقى الصفحة «قيد التحضير»."))
    elif sts:
        out.append(("ok", "كل تحاليل الزيارة مكتملة."))
    return out
