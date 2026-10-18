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

CHECK_EVERY = 6 * 3600
MAX_ZIP = 40 * 1024 * 1024
ALLOWED_TOP = ("templates/",)
_state = {"checking": False, "applying": False}
_lock = threading.Lock()


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


def update_url(db, get_setting):
    u = (get_setting(db, "update_url", "") or DEFAULT_UPDATE_URL or "").strip().rstrip("/")
    return u if u.startswith("https://") or u.startswith("http://127.0.0.1") or u.startswith("file://") else ""


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


def fetch_manifest(base):
    m = json.loads(_http_get(base + "/update.json", 200_000).decode("utf-8"))
    for k in ("version", "file", "sha256", "sig"):
        if not m.get(k):
            raise ValueError("update.json ناقص: " + k)
    if "/" in m["file"] or "\\" in m["file"]:
        raise ValueError("اسم ملف التحديث غير صالح")
    return m


def check_now(db, get_setting, set_setting):
    base = update_url(db, get_setting)
    now = datetime.now().isoformat(timespec="seconds")
    if not base:
        return {"ok": False, "configured": False, "message": "عنوان التحديثات غير مضبوط"}
    try:
        m = fetch_manifest(base)
        cur = current_version()
        avail = _vkey(m["version"]) > _vkey(cur)
        set_setting(db, "update_last_check", now)
        set_setting(db, "update_available_version", m["version"] if avail else "")
        set_setting(db, "update_available_notes", (m.get("notes") or "")[:500] if avail else "")
        db.commit()
        return {"ok": True, "configured": True, "available": avail, "version": m["version"], "current": cur,
                "notes": m.get("notes", "")}
    except Exception as e:  # noqa: BLE001
        set_setting(db, "update_last_check", now)
        db.commit()
        return {"ok": False, "configured": True, "message": "تعذر فحص التحديث: %s" % e}


def apply_now(db, get_setting, set_setting):
    """download -> verify -> validate -> swap.  Does NOT restart (caller schedules restart())."""
    if not frozen() and os.environ.get("LIS_UPDATER_TEST") != "1":
        return {"ok": False, "message": "التحديث الداخلي يعمل فقط في البرنامج المنصَّب (Setup)"}
    with _lock:
        if _state["applying"]:
            return {"ok": False, "message": "التحديث قيد التنفيذ"}
        _state["applying"] = True
    stage = os.path.join(updates_dir(), "staging")
    try:
        base = update_url(db, get_setting)
        if not base:
            return {"ok": False, "message": "عنوان التحديثات غير مضبوط"}
        m = fetch_manifest(base)
        if _vkey(m["version"]) <= _vkey(current_version()):
            return {"ok": False, "message": "البرنامج محدّث"}
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
        backup_db("pre_update")
        cur, prev = os.path.join(updates_dir(), "current"), os.path.join(updates_dir(), "previous")
        shutil.rmtree(prev, ignore_errors=True)
        if os.path.isdir(cur):
            os.replace(cur, prev)
        os.replace(stage, cur)
        try:
            os.remove(os.path.join(updates_dir(), "boot_attempt.json"))
        except Exception:
            pass
        set_setting(db, "update_available_version", "")
        set_setting(db, "update_last_applied", "%s @ %s" % (m["version"], datetime.now().isoformat(timespec="seconds")))
        db.commit()
        return {"ok": True, "version": m["version"], "message": "تم تنزيل التحديث. سيُعاد تشغيل البرنامج الآن."}
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(stage, ignore_errors=True)
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
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
                subprocess.Popen('cmd /c ping -n 4 127.0.0.1 >nul & start "" "%s"' % exe, shell=True, close_fds=True,
                                 creationflags=flags, cwd=os.path.dirname(exe))
        finally:
            os._exit(0)
    threading.Thread(target=_go, daemon=True).start()


# ----------------------------------------------------------------------------- web: routes, banner, loops
_BANNER_JS = r"""
<script>
(function(){
  if (window.__lisUpd) return; window.__lisUpd = 1;
  var bar = null;
  function esc(s){var d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
  function show(v, notes){
    try{ if (sessionStorage.getItem('lis_upd_later')===v) return; }catch(e){}
    if (bar) return;
    bar = document.createElement('div');
    bar.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:99999;background:#14233a;color:#fff;'+
      'padding:12px 16px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.35);font:14px/1.5 Tahoma,Arial,sans-serif;max-width:92vw;direction:rtl;display:flex;gap:10px;align-items:center;flex-wrap:wrap';
    bar.innerHTML = '<span>🆕 يتوفر تحديث للبرنامج (إصدار '+esc(v)+')'+(notes?' — '+esc(notes):'')+'</span>'+
      '<button id="lisUpdNow" style="background:#2e9e6b;color:#fff;border:0;border-radius:8px;padding:6px 14px;cursor:pointer;font:inherit">تحديث الآن</button>'+
      '<button id="lisUpdLater" style="background:transparent;color:#cfe0f5;border:1px solid #5b7aa0;border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit">لاحقاً</button>';
    document.body.appendChild(bar);
    document.getElementById('lisUpdLater').onclick=function(){try{sessionStorage.setItem('lis_upd_later',v);}catch(e){} bar.remove(); bar=null;};
    document.getElementById('lisUpdNow').onclick=function(){
      if(!confirm('سيُعاد تشغيل البرنامج خلال ثوانٍ. تأكد أنك حفظت عملك. المتابعة؟')) return;
      bar.innerHTML='<span>⏳ جاري التحديث... لا تغلق النافذة</span>';
      fetch('/api/update/apply',{method:'POST'}).then(function(r){return r.json();}).then(function(j){
        if(!j.ok){bar.innerHTML='<span>⚠️ '+esc(j.message)+'</span>';setTimeout(function(){if(bar){bar.remove();bar=null;}},8000);return;}
        var n=0,t=setInterval(function(){n++;
          fetch('/api/update/status',{cache:'no-store'}).then(function(r){return r.json();}).then(function(s){
            if(s.current===j.version){clearInterval(t);location.reload();}
          }).catch(function(){});
          if(n>60){clearInterval(t);bar.innerHTML='<span>⚠️ لم يعد البرنامج للعمل خلال دقيقة — شغّله من الأيقونة</span>';}
        },2000);
      }).catch(function(){bar.innerHTML='<span>⚠️ تعذر الاتصال بالبرنامج</span>';});
    };
  }
  function poll(){
    fetch('/api/update/status',{cache:'no-store'}).then(function(r){return r.json();}).then(function(s){
      if(s.available) show(s.available_version, s.notes);
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
        return jsonify(current=cur, available=bool(av) and _vkey(av) > _vkey(cur), available_version=av,
                       notes=get_setting(db, "update_available_notes", "") or "", frozen=frozen(),
                       configured=bool(update_url(db, get_setting)),
                       last_check=get_setting(db, "update_last_check", ""))

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
        r = apply_now(db, get_setting, set_setting)
        if r.get("ok") and frozen():
            restart()
        return jsonify(r)

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
