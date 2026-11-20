# -*- coding: utf-8 -*-
r"""
lab_overlay.py - bootstrap for in-app updates of the installed (PyInstaller) program.

How it works
------------
The installed LabSystem.exe contains the code that was current when Setup was built.
A small signed update package (code + templates only; see tools/make_update_package.py and lab_updater.py)
is unpacked to   <install folder>\updates\current\   and THIS bootstrap, called at the very top of app.py,
runs the newer app.py from there instead of the bundled one.

* lis.db, static\uploads, backups ... are never touched (they are not part of an update).
* If the new code fails to start, the update is quarantined and the bundled version starts instead.
* If the new code crashes twice within 40 s of starting, it is quarantined too (crash-loop protection).
* Update folders:  updates\current (active)  updates\previous (one step rollback)  updates\bad_<ver> (quarantined)
* This file is deliberately tiny and is never replaced by an update.
"""
import os
import sys
import time
import json
import shutil
import importlib.util

HEALTHY_AFTER = 40       # seconds alive = this start is considered good
PENDING_SUPPORT = True   # lab_updater يفحص هذا العلم: التحديث يُنزَّل إلى updates\\pending ويُرقَّى إلى current هنا عند التشغيل


def _log(msg):
    try:
        base = os.path.dirname(sys.executable)
        with open(os.path.join(base, "error_log.txt"), "a", encoding="utf-8") as f:
            f.write("[overlay %s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _vkey(v):
    out = []
    for p in str(v).strip().replace("-", ".").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def exe_dir():
    return os.path.dirname(sys.executable)


def updates_dir():
    return os.path.join(exe_dir(), "updates")


def read_version(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or "0"
    except Exception:
        return "0"


def bundled_version():
    return read_version(os.path.join(exe_dir(), "VERSION"))


def overlay_version():
    return read_version(os.path.join(updates_dir(), "current", "VERSION"))


def quarantine(reason):
    """move updates\\current out of the way (keeps it as bad_<ver> for inspection)."""
    cur = os.path.join(updates_dir(), "current")
    if os.path.isdir(cur):
        dst = os.path.join(updates_dir(), "bad_%s_%d" % (overlay_version(), int(time.time())))
        try:
            os.replace(cur, dst)
        except Exception:
            shutil.rmtree(cur, ignore_errors=True)
    try:
        os.remove(os.path.join(updates_dir(), "boot_attempt.json"))
    except Exception:
        pass
    prev = os.path.join(updates_dir(), "previous")
    if os.path.isdir(prev):                       # fall back to the last update that worked
        try:
            os.replace(prev, cur)
        except Exception:
            pass
    _log("update quarantined: " + reason)


def promote_pending():
    """يُستدعى قبل تحميل أي كود: إذا وُجد تحديث مجهَّز (updates\\pending) وأحدث من الحالي يصير هو current.
    بهذا النسخة الشغّالة لا تتغير ملفاتها وهي تعمل، والتحديث يبدأ فعلياً عند أول فتح بعد التجهيز (بدون أي restart من البرنامج)."""
    pend = os.path.join(updates_dir(), "pending")
    if not os.path.isdir(pend):
        return
    cur = os.path.join(updates_dir(), "current")
    prev = os.path.join(updates_dir(), "previous")
    try:
        pv = read_version(os.path.join(pend, "VERSION"))
        have = max(_vkey(bundled_version()), _vkey(overlay_version()) if os.path.isdir(cur) else (0,))
        if not os.path.isfile(os.path.join(pend, "app.py")) or _vkey(pv) <= have:
            shutil.rmtree(pend, ignore_errors=True)          # قديم أو ناقص: نتجاهله
            return
        shutil.rmtree(prev, ignore_errors=True)
        moved = False
        if os.path.isdir(cur):
            os.replace(cur, prev)
            moved = True
        try:
            os.replace(pend, cur)
        except Exception:
            if moved:                                          # رجّع القديم حتى لا نخسر نسخة شغّالة
                try:
                    os.replace(prev, cur)
                except Exception:
                    pass
            raise
        try:
            os.remove(os.path.join(updates_dir(), "boot_attempt.json"))
        except Exception:
            pass
        _log("pending update %s promoted to current" % pv)
    except Exception as e:      # noqa: BLE001
        _log("promote_pending failed: %s" % e)


def mark_healthy():
    try:
        os.remove(os.path.join(updates_dir(), "boot_attempt.json"))
    except Exception:
        pass


def _restart_bundled():
    """start a fresh process (it will find no overlay) and end this one."""
    import subprocess
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([sys.executable], close_fds=True, creationflags=flags)
    finally:
        os._exit(0)


def boot(real_file, g):
    """called from app.py:  import lab_overlay; lab_overlay.boot(__file__, globals())
    Returns normally when the bundled code should run; otherwise never returns."""
    # الحارس صار بمتغيرات البايثون (g) وليس بمتغير بيئة موروث: العملية الجديدة بعد التحديث كانت ترث
    # LIS_OVERLAY_ACTIVE=1 من القديمة فتتخطى التحديث وتبقى النسخة القديمة (حلقة "يتوفر تحديث" المتكررة).
    if not getattr(sys, "frozen", False) or g.get("_LIS_OVERLAY_ON"):
        return
    promote_pending()
    cur = os.path.join(updates_dir(), "current")
    app_py = os.path.join(cur, "app.py")
    if not os.path.isfile(app_py):
        return
    ov, bv = overlay_version(), bundled_version()
    if _vkey(ov) <= _vkey(bv):
        return        # the installed Setup is newer than the downloaded update: ignore it

    # crash-loop protection
    marker = os.path.join(updates_dir(), "boot_attempt.json")
    attempts = 0
    try:
        with open(marker, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == ov:
            attempts = int(d.get("attempts", 0))
    except Exception:
        pass
    if attempts >= 2:
        quarantine("crashed %d times right after start" % attempts)
        return
    try:
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"version": ov, "attempts": attempts + 1, "t": time.time()}, f)
    except Exception:
        pass

    try:
        # 1) newer versions of the other modules (database.py, translations.py ...) replace the bundled ones
        for fn in sorted(os.listdir(cur)):
            if not fn.endswith(".py") or fn in ("app.py", "lab_overlay.py"):
                continue
            name = fn[:-3]
            spec = importlib.util.spec_from_file_location(name, os.path.join(cur, fn))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        # 2) run the new app.py as the main program (same globals, same __file__ -> data folders unchanged)
        g["_LIS_OVERLAY_ON"] = True
        os.environ["LIS_OVERLAY_ACTIVE"] = "1"
        os.environ["LIS_OVERLAY_DIR"] = cur
        os.environ["LIS_OVERLAY_VERSION"] = ov
        with open(app_py, "r", encoding="utf-8") as f:
            src = f.read()
        g["__file__"] = real_file
        exec(compile(src, app_py, "exec"), g)
    except SystemExit:
        raise
    except BaseException as e:      # noqa: BLE001  - the new code failed before/while starting
        import traceback
        _log("update %s failed to start: %s\n%s" % (ov, e, traceback.format_exc()))
        quarantine("failed to start: %s" % e)
        _restart_bundled()
    raise SystemExit(0)
