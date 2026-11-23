# -*- coding: utf-8 -*-
r"""
lab_updater.py - in-app updates (no re-install) + automatic safety copies of the patient database.

UPDATE FLOW
  designer:  python tools\make_update_package.py          -> update_packages\update.json + update_<ver>.zip   (signed)
             upload both files to the update address (one public folder; they hold no patient data and no secrets)
  client:    the program checks that address (every 6 h and at start) ->  a bar appears:
             "New update available [Update now] [Later]"   -> download, verify signature, validate, swap, restart.
  The update only replaces code + templates (updates\current). lis.db / uploads / backups are never touched,
  a copy of lis.db is made before every update, and a bad update is quarantined automatically (lab_overlay.py).

SAFETY COPIES
  once a day (and before every update) lis.db is copied with SQLite's online-backup API to
  C:\ProgramData\LabSystemBackup\  (outside the program folder, kept 14 days).  The installer offers to restore
  from there when the program is installed again on a computer where the data folder is gone.
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import hashlib
import base64
import threading
import urllib.request
import urllib.error
from datetime import datetime

# ---- set these two once (see tools\make_update_package.py --init-keys) ---------------------------------------------
PUBLIC_KEY_B64 = "BIvWzHkoQLs26itNenrUpBTruHmz5aOWIitoWyXvu1U="            # Ed25519 public key (base64) printed by --init-keys
DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/sesahmed95-web/lab-updates/main/updates"        # folder URL that contains update.json, e.g. https://your-name.github.io/lab-updates
# ---------------------------------------------------------------------------------------------------------------------

# v94: مصادر احتياطية للتحديث. إذا تعذّر الأول (GitHub محجوب/الحساب مقفل/المستودع خاص) يجرّب البرنامج التالي تلقائياً.
# الثاني = سحابتك على Cloudflare (مجلد public/updates بمشروع lab-ledger-cloud، يُنشر بـ نشر-التحديث.bat) — لا يحتاج GitHub إطلاقاً.
FALLBACK_UPDATE_URLS = [
    "https://lab-ledger.sesahmed95.workers.dev/updates",
]

CHECK_EVERY = 6 * 3600
MAX_ZIP = 40 * 1024 * 1024
ALLOWED_TOP = ("templates/",)
_state = {"checking": False, "applying": False}
_lock = threading.Lock()


def _ulog(msg):
    """v88: سجل بسيط لخطوات التحديث (updates\\update_log.txt) حتى نعرف وين يعلق عند العميل."""
    try:
        os.makedirs(updates_dir(), exist_ok=True)
        with open(os.path.join(updates_dir(), "update_log.txt"), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def frozen():
    return bool(getattr(sys, "frozen", False))


def exe_dir():
    return os.path.dirname(sys.executable) if frozen() else os.path.dirname(os.path.abspath(__file__))


def updates_dir():
    return os.path.join(exe_dir(), "updates")


def backup_dir():
    d = os.environ.get("LIS_BACKUP_DIR")
    if d:
        return d
    base = os.environ.get("ProgramData") or os.path.expanduser("~")
    return os.path.join(base, "LabSystemBackup")


def _vkey(v):
    out = []
    for p in str(v).strip().replace("-", ".").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def _read(path, default="0"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or default
    except Exception:
        return default


def current_version():
    """what is really running: the update (if active) else the installed version"""
    b = _read(os.path.join(exe_dir(), "VERSION"))
    if os.environ.get("LIS_OVERLAY_ACTIVE") == "1":
        o = os.environ.get("LIS_OVERLAY_VERSION") or _read(os.path.join(updates_dir(), "current", "VERSION"))
        if _vkey(o) > _vkey(b):
            return o
    return b


def pending_dir():
    return os.path.join(updates_dir(), "pending")


def _pending_supported():
    """هل lab_overlay المضمَّن بالـexe يعرف يرقّي updates\\pending إلى current عند التشغيل؟ (Setup جديد فقط)"""
    try:
        import lab_overlay
        return bool(getattr(lab_overlay, "PENDING_SUPPORT", False))
    except Exception:
        return False


def staged_version():
    """أحدث إصدار منزَّل ومجهَّز على القرص ولم يشتغل بعد (يشتغل عند الفتح القادم). '' إن لم يوجد.
    المصدر هو القرص نفسه (pending أو current) وليس إعدادات القاعدة، فلا يتناقض مع الواقع أبداً."""
    run = current_version()
    best = ""
    for d in (pending_dir(), os.path.join(updates_dir(), "current")):
        if os.path.isfile(os.path.join(d, "app.py")):
            v = _read(os.path.join(d, "VERSION"))
            if _vkey(v) > _vkey(run) and (not best or _vkey(v) > _vkey(best)):
                best = v
    return best


def effective_version():
    """أحدث إصدار موجود عند العميل (الشغّال أو المجهَّز). كل مقارنة «هل يوجد تحديث؟» تتم عليه."""
    return staged_version() or current_version()


def update_url(db, get_setting):
    u = (get_setting(db, "update_url", "") or DEFAULT_UPDATE_URL or "").strip().rstrip("/")
    return u if u.startswith("https://") or u.startswith("http://127.0.0.1") or u.startswith("file://") else ""


def update_urls(db, get_setting):
    """كل عناوين التحديث بالترتيب: المضبوط يدوياً ثم الافتراضي ثم الاحتياطية (بدون تكرار)."""
    out = []
    for u in [get_setting(db, "update_url", ""), DEFAULT_UPDATE_URL] + list(FALLBACK_UPDATE_URLS):
        u = (u or "").strip().rstrip("/")
        if (u.startswith("https://") or u.startswith("http://127.0.0.1") or u.startswith("file://")) and u not in out:
            out.append(u)
    return out


def fetch_best(bases):
    """يجرّب كل المصادر ويرجّع (base, manifest) لأحدث إصدار متاح، مع قائمة أخطاء المصادر المعطّلة."""
    best, errs = None, []
    for b in bases:
        try:
            m = fetch_manifest(b)
            if best is None or _vkey(m["version"]) > _vkey(best[1]["version"]):
                best = (b, m)
        except Exception as e:  # noqa: BLE001
            errs.append("%s -> %s" % (b, e))
    if best is None:
        raise ValueError("كل مصادر التحديث تعذّرت: " + " | ".join(errs)[:400])
    for e in errs:
        _ulog("source failed: " + e)
    return best[0], best[1], errs


# ----------------------------------------------------------------------------- crypto / package checks
def verify_signature(version, sha256_hex, sig_b64, pub_b64=None):
    pub_b64 = pub_b64 or PUBLIC_KEY_B64
    if not pub_b64:
        return False, "لم يُضبط المفتاح العام للتحديثات بالبرنامج"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception:
        return False, "مكتبة cryptography غير موجودة بهذا البرنامج"
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(
            base64.b64decode(sig_b64), ("%s|%s" % (version, sha256_hex)).encode("utf-8"))
        return True, ""
    except InvalidSignature:
        return False, "توقيع التحديث غير صحيح - لن يُطبَّق"
    except Exception as e:  # noqa: BLE001
        return False, "تعذر فحص التوقيع: %s" % e


def _safe_extract(zip_path, dest):
    import zipfile
    total = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            if "/" not in name and name.endswith(".html"):
                name = "templates/" + name          # v94: قالب بجذر الـzip (مثل new_visit.html) كان يُرفض فيفشل التحديث كله
            if name.startswith("/") or ".." in name.split("/") or ":" in name:
                raise ValueError("مسار غير مسموح داخل التحديث: " + name)
            ok = name == "VERSION" or ("/" not in name and name.endswith(".py")) or \
                any(name.startswith(p) for p in ALLOWED_TOP)
            if not ok:
                raise ValueError("ملف غير مسموح داخل التحديث: " + name)
            total += info.file_size
            if total > 120 * 1024 * 1024:
                raise ValueError("حجم التحديث كبير بشكل غير طبيعي")
            target = os.path.join(dest, *name.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _validate_tree(root):
    """syntax-check every .py and every template before the update is allowed to go live"""
    if not os.path.isfile(os.path.join(root, "app.py")):
        raise ValueError("التحديث لا يحتوي app.py")
    for fn in os.listdir(root):
        if fn.endswith(".py"):
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8") as f:
                compile(f.read(), fp, "exec")
    try:
        import jinja2
        env = jinja2.Environment()
        for dp, _dn, fns in os.walk(os.path.join(root, "templates")):
            for fn in fns:
                if fn.endswith(".html"):
                    with open(os.path.join(dp, fn), "r", encoding="utf-8") as f:
                        env.parse(f.read())
    except ImportError:
        pass


# ----------------------------------------------------------------------------- database safety copies
def backup_db(tag="daily"):
    """consistent copy of lis.db (online backup API) -> backup_dir(). returns path or ''"""
    try:
        from database import DB_PATH
        if not os.path.exists(DB_PATH):
            return ""
        d = backup_dir()
        os.makedirs(d, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S") if tag != "daily" else datetime.now().strftime("%Y%m%d")
        name = "lis_%s%s.db" % (("pre_update_" if tag == "pre_update" else ""), stamp)
        dst = os.path.join(d, name)
        src = sqlite3.connect(DB_PATH, timeout=30)
        try:
            out = sqlite3.connect(dst)
            try:
                src.backup(out)
                patients = visits = None
                try:
                    patients = out.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                    visits = out.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
                except Exception:
                    pass
            finally:
                out.close()
        finally:
            src.close()
        if tag == "daily":
            shutil.copy2(dst, os.path.join(d, "lis_latest.db"))
            with open(os.path.join(d, "lis_latest.json"), "w", encoding="utf-8") as f:
                json.dump({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "patients": patients, "visits": visits}, f)
        # keep the last 14 daily copies and the last 5 pre-update copies
        for prefix, keep in (("lis_2", 14), ("lis_pre_update_", 5)):
            files = sorted(f for f in os.listdir(d) if f.startswith(prefix) and f.endswith(".db") and f != "lis_latest.db")
            for old in files[:-keep]:
                try:
                    os.remove(os.path.join(d, old))
                except Exception:
                    pass
        return dst
    except Exception as e:  # noqa: BLE001
        try:
            print("backup_db failed:", e)
        except Exception:
            pass
        return ""


# ----------------------------------------------------------------------------- check / apply
def _http_get(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "LabSystem-Updater"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("الملف أكبر من الحد المسموح")
    return data


def _my_hw_id():
    """معرّف جهاز هذا العميل (نفس Hardware ID بالترخيص) — يُستخدم لاستلام تحديثات موجّهة له فقط."""
    try:
        import re as _re
        from license_manager import get_hardware_id
        return _re.sub(r"[^A-Za-z0-9_-]", "", str(get_hardware_id() or "")).upper()
    except Exception:
        return ""


def _fetch_one(base, name):
    m = json.loads(_http_get(base + "/" + name, 200_000).decode("utf-8"))
    for k in ("version", "file", "sha256", "sig"):
        if not m.get(k):
            raise ValueError(name + " ناقص: " + k)
    if "/" in m["file"] or "\\" in m["file"]:
        raise ValueError("اسم ملف التحديث غير صالح")
    return m


def fetch_manifest(base):
    """التحديث العام update.json + (إن وُجد) تحديث موجّه لهذا الجهاز فقط update_for_<HWID>.json.
    نرجّع الأحدث منهما. تحديث موجّه لجهاز ثاني ما يشوفه هذا الجهاز أبداً (اسم الملف مرتبط بالـHWID)."""
    m = _fetch_one(base, "update.json")
    hw = _my_hw_id()
    if hw:
        try:
            t = _fetch_one(base, "update_for_%s.json" % hw)
            if _vkey(t["version"]) > _vkey(m["version"]):
                m = t
        except Exception:
            pass
    return m


# ----------------------------------------------------------------------------- ربط العميل تلقائياً (بدون لصق ملفات)
# المصمم يولّد links_<HWID>.json (موقّع بمفتاح التحديثات + مشفّر بمعرّف جهاز العميل) من /designer/client-link ويضعه بنفس مكان update.json
# (GitHub و/أو public/updates بالسحابة). جهاز العميل يجلبه مع فحص التحديث، يتحقق من التوقيع، يفكّه، ويضبط رابط ومفاتيح
# السجل السحابي وبوابة النتائج بنفسه. لا يطبّق نفس الملف مرتين، ولا يقدر جهاز ثاني يفكّه (المفتاح مشتق من HWID).
_links_applier = None


def set_links_applier(fn):
    global _links_applier
    _links_applier = fn


def _links_key(hw, created):
    return hashlib.sha256(("lislink|%s|%s" % (hw.strip().upper(), created)).encode("utf-8")).digest()


def _links_stream(key, n):
    out = bytearray()
    ctr = 0
    while len(out) < n:
        out += hashlib.sha256(key + ctr.to_bytes(4, "big")).digest()
        ctr += 1
    return bytes(out[:n])


def seal_links(hw, created, data):
    import hmac
    key = _links_key(hw, created)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(raw, _links_stream(key, len(raw))))
    tag = hmac.new(key, ct, hashlib.sha256).digest()[:16]
    return base64.b64encode(tag + ct).decode("ascii")


def open_links(hw, created, sealed):
    import hmac
    key = _links_key(hw, created)
    blob = base64.b64decode(sealed)
    tag, ct = blob[:16], blob[16:]
    if not hmac.compare_digest(tag, hmac.new(key, ct, hashlib.sha256).digest()[:16]):
        raise ValueError("ملف الربط لا يخص هذا الجهاز")
    return json.loads(bytes(a ^ b for a, b in zip(ct, _links_stream(key, len(ct)))).decode("utf-8"))


def links_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def check_links(db, get_setting, set_setting):
    """يرجّع رسالة لو طُبّق ملف ربط جديد، وإلا None. لا يرفع استثناء."""
    try:
        hw = _my_hw_id()
        if not hw or _links_applier is None:
            return None
        for base in update_urls(db, get_setting):
            try:
                env = json.loads(_http_get(base + "/links_%s.json" % hw, 400_000).decode("utf-8"))
            except Exception:
                continue
            created, sig, payload = env.get("created", ""), env.get("sig", ""), env.get("payload")
            if not (created and sig and isinstance(payload, dict) and payload.get("links")):
                continue
            if created == get_setting(db, "last_applied_links", ""):
                return None
            ok, why = verify_signature(created, links_digest(payload), sig)
            if not ok:
                set_setting(db, "links_last_status", "⚠️ %s — %s" % (datetime.now().isoformat(timespec="seconds"), why))
                db.commit()
                return None
            data = open_links(hw, created, payload["links"])
            msg = _links_applier(db, data) or "تم"
            set_setting(db, "last_applied_links", created)
            set_setting(db, "links_last_status", "✅ %s — %s" % (datetime.now().isoformat(timespec="seconds"), msg))
            db.commit()
            _ulog("links applied: " + msg)
            return msg
    except Exception as e:  # noqa: BLE001
        try:
            set_setting(db, "links_last_status", "⚠️ تعذر تطبيق ملف الربط: %s" % str(e)[:200])
            db.commit()
        except Exception:
            pass
    return None


def check_now(db, get_setting, set_setting):
    check_links(db, get_setting, set_setting)
    bases = update_urls(db, get_setting)
    now = datetime.now().isoformat(timespec="seconds")
    if not bases:
        return {"ok": False, "configured": False, "message": "عنوان التحديثات غير مضبوط"}
    try:
        base, m, _errs = fetch_best(bases)
        cur = current_version()
        stg = staged_version()
        avail = _vkey(m["version"]) > _vkey(stg or cur)      # ما نعرض تحديثاً سبق تجهيزه
        set_setting(db, "update_last_check", now)
        set_setting(db, "update_available_version", m["version"] if avail else "")
        set_setting(db, "update_available_notes", (m.get("notes") or "")[:500] if avail else "")
        db.commit()
        return {"ok": True, "configured": True, "available": avail, "version": m["version"], "current": cur,
                "staged": stg, "notes": m.get("notes", "")}
    except Exception as e:  # noqa: BLE001
        set_setting(db, "update_last_check", now)
        set_setting(db, "update_last_error", str(e)[:500])
        db.commit()
        _ulog("check FAILED: %s" % e)
        return {"ok": False, "configured": True, "message": "تعذر فحص التحديث: %s" % e}


def apply_now(db, get_setting, set_setting):
    """download -> verify -> validate -> STAGE.  لا يعيد تشغيل البرنامج أبداً.
    التحديث يُجهَّز على القرص ويشتغل تلقائياً عند الفتح القادم (حالة «مجهَّز»)، فلا شريط يتكرر ولا حلقة.
    إذا نُشر إصدار أحدث قبل إعادة التشغيل يستبدل المجهَّز القديم، فيستلم العميل دائماً الأحدث فقط."""
    if not frozen() and os.environ.get("LIS_UPDATER_TEST") != "1":
        return {"ok": False, "message": "التحديث الداخلي يعمل فقط في البرنامج المنصَّب (Setup)"}
    with _lock:
        if _state["applying"]:
            return {"ok": False, "message": "التحديث قيد التنفيذ"}
        _state["applying"] = True
    stage = os.path.join(updates_dir(), "staging")
    try:
        bases = update_urls(db, get_setting)
        if not bases:
            return {"ok": False, "message": "عنوان التحديثات غير مضبوط"}
        base, m, _errs = fetch_best(bases)
        _ulog("apply: start, base=%s, current=%s" % (base, current_version()))
        _ulog("apply: manifest version=%s" % m.get("version"))
        if _vkey(m["version"]) <= _vkey(effective_version()):
            return {"ok": False, "message": "البرنامج محدّث" if not staged_version() else "التحديث مجهَّز مسبقاً ويعمل عند الفتح القادم",
                    "staged": staged_version()}
        data = _http_get(base + "/" + m["file"], MAX_ZIP)
        digest = hashlib.sha256(data).hexdigest()
        if digest != m["sha256"]:
            return {"ok": False, "message": "الملف المنزَّل تالف (بصمة غير مطابقة)"}
        ok, why = verify_signature(m["version"], digest, m["sig"])
        if not ok:
            return {"ok": False, "message": why}
        os.makedirs(updates_dir(), exist_ok=True)
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        zp = os.path.join(updates_dir(), "download.zip")
        with open(zp, "wb") as f:
            f.write(data)
        try:
            _safe_extract(zp, stage)
            with open(os.path.join(stage, "VERSION"), "w", encoding="utf-8") as f:
                f.write(m["version"])
            _validate_tree(stage)
        finally:
            try:
                os.remove(zp)
            except Exception:
                pass
        _ulog("apply: downloaded+verified, staging")
        backup_db("pre_update")
        if _pending_supported():
            # lab_overlay (الجديد) يرقّي pending -> current قبل تشغيل البرنامج، فالنسخة الشغّالة الآن لا تُمسّ إطلاقاً
            shutil.rmtree(pending_dir(), ignore_errors=True)
            os.replace(stage, pending_dir())
            mode = "pending"
        else:
            # exe قديم (lab_overlay بدون pending): نكتب مباشرة بـcurrent، وسيُحمَّل عند أول تشغيل قادم
            cur, prev = os.path.join(updates_dir(), "current"), os.path.join(updates_dir(), "previous")
            shutil.rmtree(prev, ignore_errors=True)
            if os.path.isdir(cur):
                os.replace(cur, prev)
            os.replace(stage, cur)
            try:
                os.remove(os.path.join(updates_dir(), "boot_attempt.json"))
            except Exception:
                pass
            mode = "current"
        set_setting(db, "update_available_version", "")
        set_setting(db, "update_available_notes", "")
        set_setting(db, "update_staged_version", m["version"])
        set_setting(db, "update_last_applied", "%s @ %s" % (m["version"], datetime.now().isoformat(timespec="seconds")))
        db.commit()
        _ulog("apply: OK -> %s staged (%s), runs at next launch" % (m["version"], mode))
        return {"ok": True, "version": m["version"], "staged": True, "mode": mode,
                "message": "تم تجهيز التحديث (إصدار %s). سيعمل تلقائياً عند فتح البرنامج المرة القادمة." % m["version"]}
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(stage, ignore_errors=True)
        _ulog("apply: FAILED %r" % (e,))
        return {"ok": False, "message": "فشل التحديث: %s" % e}
    finally:
        with _lock:
            _state["applying"] = False


def restart(delay=1.5):
    """relaunch the program after this process has released port 9090 (the open browser window just reconnects)."""
    def _go():
        time.sleep(delay)
        try:
            if frozen():
                import subprocess
                exe = sys.executable
                env = dict(os.environ)
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"      # العملية الجديدة تشتغل كتشغيل مستقل لا ابن للعملية القديمة
                for k in [k for k in env if k.startswith("_PYI_") or k == "_MEIPASS2"]:
                    env.pop(k, None)
                # أهم إصلاح: العملية الجديدة كانت ترث LIS_OVERLAY_ACTIVE=1 من القديمة، فيتخطى lab_overlay.boot() التحديث
                # ويشغّل الكود المضمَّن بالـexe (النسخة القديمة) ويبقى رقم الإصدار قديمًا => الشريط يعلق على «جاري التحديث».
                for k in ("LIS_OVERLAY_ACTIVE", "LIS_OVERLAY_DIR", "LIS_OVERLAY_VERSION"):
                    env.pop(k, None)
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
                _ulog("restart: relaunching %s" % exe)
                subprocess.Popen('cmd /c ping -n 4 127.0.0.1 >nul & start "" "%s"' % exe, shell=True, close_fds=True,
                                 creationflags=flags, cwd=os.path.dirname(exe), env=env)
        except Exception as e:  # noqa: BLE001
            _ulog("restart: FAILED %r" % (e,))
        finally:
            os._exit(0)
    threading.Thread(target=_go, daemon=True).start()


# ----------------------------------------------------------------------------- web: routes, banner, loops
_BANNER_JS = r"""
<script>
(function(){
  if (window.__lisUpd) return; window.__lisUpd = 1;
  var bar = null, hideT = null;
  function esc(s){var d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
  function mk(html){
    if(!bar){
      bar = document.createElement('div');
      bar.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:99999;background:#14233a;color:#fff;'+
        'padding:12px 16px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.35);font:14px/1.5 Tahoma,Arial,sans-serif;max-width:92vw;direction:rtl;display:flex;gap:10px;align-items:center;flex-wrap:wrap';
      document.body.appendChild(bar);
    }
    bar.innerHTML = html;
  }
  function hide(){ if(hideT){clearTimeout(hideT);hideT=null;} if(bar){bar.remove();bar=null;} }
  function lget(k){ try{return localStorage.getItem(k)||'';}catch(e){return '';} }
  function lset(k,v){ try{localStorage.setItem(k,v);}catch(e){} }
  var BTN = 'border:0;border-radius:8px;padding:6px 14px;cursor:pointer;font:inherit;';
  function waitBack(ver){
    var n=0,down=false,t=setInterval(function(){n++;
      fetch('/api/update/status',{cache:'no-store'}).then(function(r){return r.json();}).then(function(s){
        if(down || (ver && s.current===ver)){clearInterval(t);location.reload();}
      }).catch(function(){down=true;});
      if(n===45){mk('<span>⏳ ياخذ وقت أطول من المعتاد... انتظر قليلًا</span>');}
      if(n>90){clearInterval(t);mk('<span>⚠️ لم يعد البرنامج للعمل — أغلق هذه النافذة وشغّل البرنامج من أيقونته.</span>');}
    },2000);
  }
  // حالة «مجهَّز»: التحديث نُزِّل وتحقّقنا منه، ويشتغل عند الفتح القادم. تظهر مرة وحدة لكل إصدار وتختفي لوحدها.
  function showStaged(v){
    lset('lis_upd_staged_seen', v);
    mk('<span>✅ تم تجهيز التحديث (إصدار '+esc(v)+'). سيعمل تلقائياً عند فتح البرنامج المرة القادمة.</span>'+
      '<button id="lisUpdRestart" style="'+BTN+'background:#2e9e6b;color:#fff">إعادة التشغيل الآن</button>'+
      '<button id="lisUpdOk" style="'+BTN+'background:transparent;color:#cfe0f5;border:1px solid #5b7aa0">حسناً</button>');
    document.getElementById('lisUpdOk').onclick=hide;
    document.getElementById('lisUpdRestart').onclick=function(){
      if(!confirm('سيُعاد تشغيل البرنامج خلال ثوانٍ. تأكد أنك حفظت عملك. المتابعة؟')) return;
      mk('<span>⏳ جاري إعادة التشغيل... لا تغلق النافذة</span>');
      fetch('/api/update/restart',{method:'POST'}).then(function(){waitBack(v);}).catch(function(){waitBack(v);});
    };
    hideT=setTimeout(hide,15000);
  }
  function showAvail(v, notes){
    // «لاحقاً» تُحفظ 24 ساعة بالمتصفح (localStorage + كوكي احتياطي) بدل sessionStorage الي يضيع بنافذة البرنامج
    try{ var z=lget('lis_upd_later'); if(z){ var a=z.split('|'); if(a[0]===v && (Date.now()-Number(a[1]||0))<86400000) return; } }catch(e){}
    if (document.cookie.indexOf('lis_upd_later='+encodeURIComponent(v))!==-1) return;
    if (window.__lisUpdFrozen===false) return;   // تشغيل من المصدر (مو exe): التحديث ما يتفعّل هنا فلا داعي للإشعار
    if (bar) return;
    mk('<span>🆕 يتوفر تحديث للبرنامج (إصدار '+esc(v)+')'+(notes?' — '+esc(notes):'')+'</span>'+
      '<button id="lisUpdNow" style="'+BTN+'background:#2e9e6b;color:#fff">تحديث الآن</button>'+
      '<button id="lisUpdLater" style="'+BTN+'background:transparent;color:#cfe0f5;border:1px solid #5b7aa0">لاحقاً</button>');
    document.getElementById('lisUpdLater').onclick=function(){lset('lis_upd_later',v+'|'+Date.now());try{document.cookie='lis_upd_later='+encodeURIComponent(v)+';max-age=86400;path=/';}catch(e){} hide();};
    document.getElementById('lisUpdNow').onclick=function(){
      mk('<span>⏳ جاري تنزيل التحديث وتجهيزه... (لن يُعاد تشغيل البرنامج الآن)</span>');
      fetch('/api/update/apply',{method:'POST'}).then(function(r){return r.json();}).then(function(j){
        if(!j.ok){mk('<span>⚠️ '+esc(j.message)+'</span>');hideT=setTimeout(hide,8000);return;}
        showStaged(j.version);
      }).catch(function(){mk('<span>⚠️ تعذر الاتصال بالبرنامج</span>');hideT=setTimeout(hide,8000);});
    };
  }
  function poll(){
    fetch('/api/update/status',{cache:'no-store'}).then(function(r){return r.json();}).then(function(s){
      window.__lisUpdFrozen = !!s.frozen;
      if(s.available) showAvail(s.available_version, s.notes);
      else if(s.staged && s.staged_version && lget('lis_upd_staged_seen')!==s.staged_version && !bar) showStaged(s.staged_version);
    }).catch(function(){});
  }
  setTimeout(poll,1500); setInterval(poll,15*60*1000);
})();
</script>
"""


def register(app, get_db, get_setting, set_setting, login_required):
    from flask import jsonify, request

    @app.route("/api/update/status")
    def api_update_status():
        db = get_db()
        av = (get_setting(db, "update_available_version", "") or "")
        cur = current_version()
        stg = staged_version()
        return jsonify(current=cur, available=bool(av) and _vkey(av) > _vkey(stg or cur), available_version=av,
                       staged=bool(stg), staged_version=stg,
                       notes=get_setting(db, "update_available_notes", "") or "", frozen=frozen(),
                       configured=bool(update_urls(db, get_setting)),
                       last_check=get_setting(db, "update_last_check", ""))

    @app.route("/api/update/diagnose")
    @login_required
    def api_update_diagnose():
        """v94: يبيّن بالضبط ليش ما يوصل التحديث: كل مصدر (GitHub/Cloudflare) شنو يرجّع + آخر سطور السجل."""
        db = get_db()
        res = []
        for b in update_urls(db, get_setting):
            try:
                m = fetch_manifest(b)
                res.append({"url": b, "ok": True, "version": m["version"], "notes": (m.get("notes") or "")[:120]})
            except Exception as e:  # noqa: BLE001
                res.append({"url": b, "ok": False, "error": str(e)[:300]})
        tail = ""
        try:
            with open(os.path.join(updates_dir(), "update_log.txt"), "r", encoding="utf-8") as f:
                tail = "".join(f.readlines()[-25:])
        except Exception:
            pass
        return jsonify(current=current_version(), staged=staged_version(), frozen=frozen(), hw_id=_my_hw_id(),
                       auto_check=get_setting(db, "update_auto_check", "1"), last_check=get_setting(db, "update_last_check", ""),
                       last_error=get_setting(db, "update_last_error", ""), links_status=get_setting(db, "links_last_status", ""), sources=res, log_tail=tail)

    @app.route("/api/update/check", methods=["POST"])
    @login_required
    def api_update_check():
        db = get_db()
        r = check_now(db, get_setting, set_setting)
        return jsonify(r)

    @app.route("/api/update/apply", methods=["POST"])
    @login_required
    def api_update_apply():
        db = get_db()
        r = apply_now(db, get_setting, set_setting)      # يجهّز فقط. لا إعادة تشغيل هنا (هذا كان سبب حلقة «يتوفر تحديث»)
        return jsonify(r)

    @app.route("/api/update/restart", methods=["POST"])
    @login_required
    def api_update_restart():
        """إعادة تشغيل يدوية اختيارية (زر «إعادة التشغيل الآن») لتفعيل تحديث مجهَّز فوراً."""
        if not frozen():
            return jsonify(ok=False, message="إعادة التشغيل متاحة فقط بالبرنامج المنصَّب")
        restart()
        return jsonify(ok=True)

    @app.after_request
    def _inject_update_banner(resp):
        try:
            if resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough:
                return resp
            data = resp.get_data()
            if b"lis-sidebar-hidden" not in data or b"__lisUpd" in data or b"</body>" not in data:
                return resp
            resp.set_data(data.replace(b"</body>", _BANNER_JS.encode("utf-8") + b"</body>", 1))
        except Exception:
            pass
        return resp

    def _loop():
        time.sleep(60)
        last_backup_day = ""
        while True:
            db = None
            try:
                db = get_db()
                if frozen() and (get_setting(db, "update_auto_check", "1") != "0"):
                    check_now(db, get_setting, set_setting)
                today = datetime.now().strftime("%Y%m%d")
                if today != last_backup_day:
                    if backup_db("daily"):
                        last_backup_day = today
            except Exception:
                pass
            finally:
                try:
                    if db is not None:
                        db.close()
                except Exception:
                    pass
            time.sleep(CHECK_EVERY if last_backup_day else 600)

    def _healthy():
        time.sleep(40)
        try:
            import lab_overlay
            lab_overlay.mark_healthy()
        except Exception:
            pass

    if os.environ.get("LIS_UPDATER_NO_THREADS") != "1":
        threading.Thread(target=_loop, daemon=True).start()
        threading.Thread(target=_healthy, daemon=True).start()
