# -*- coding: utf-8 -*-
r"""
update_publisher.py - صفحة المصمم "نشر تحديث للعملاء"  (/designer/publish-update)

تجمع خطوات الإعداد الأربع + نشر كل تحديث بأزرار بدل سطر الأوامر:
  إعداد مرة واحدة:  1) تثبيت cryptography   2) إنشاء مفتاح التوقيع (+ لصق PUBLIC_KEY_B64 بـ lab_updater.py تلقائيًا)
                    3) ضبط رابط التحديثات DEFAULT_UPDATE_URL من مستودع GitHub العام   4) رابط لصفحة بناء Setup العميل
  كل تحديث:        زر واحد = (رفع VERSION) + بناء الزيب + التوقيع + رفع update.json والزيب لمستودع GitHub العام.
                    ("بناء فقط" يبني الملفين بمجلد update_packages لترفعهما يدويًا).
تشتغل فقط من نسخة المطوّر (python app.py) وبدخول المصمم. توكن الكتابة هو نفسه المحفوظ بلوحة المصمم (github_write_token)
ولا يُكتب بأي ملف ولا يظهر بالسجل. المفتاح الخاص يبقى بمجلد المستخدم خارج المشروع ولا يُرفع لأي مكان.
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(os.path.expanduser("~"), ".lab_update_signing_key.pem")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$")
DIR_RE = re.compile(r"^[A-Za-z0-9._/-]{0,60}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,60}$")
_LOCK = threading.Lock()
_JOB = {"state": "idle", "title": "", "log": [], "error": "", "result": ""}
_SECRETS = []
RUN = None        # tests only: override subprocess runner


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def _log(msg):
    for s in _SECRETS:
        if s:
            msg = msg.replace(s, "***")
    with _LOCK:
        _JOB["log"].append(msg)
        del _JOB["log"][:-300]


def _run(cmd, timeout=900):
    """يشغّل أمر ويكتب خرجه بالسجل. يرجع (ok, output)."""
    if RUN:
        return RUN(cmd)
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        for ln in out.strip().splitlines()[-25:]:
            _log("   " + ln)
        return p.returncode == 0, out
    except Exception as e:  # noqa: BLE001
        _log("   خطأ: %s" % e)
        return False, str(e)


# ----------------------------------------------------------------------------- lab_updater.py patching
def _updater_path():
    return os.path.join(HERE, "lab_updater.py")


def read_updater_values():
    try:
        t = open(_updater_path(), encoding="utf-8").read()
    except Exception:
        return "", ""
    pk = re.search(r'^PUBLIC_KEY_B64\s*=\s*"([^"]*)"', t, re.M)
    url = re.search(r'^DEFAULT_UPDATE_URL\s*=\s*"([^"]*)"', t, re.M)
    return (pk.group(1) if pk else ""), (url.group(1) if url else "")


def patch_updater(name, value):
    """يغيّر سطر PUBLIC_KEY_B64 أو DEFAULT_UPDATE_URL بملف lab_updater.py."""
    path = _updater_path()
    t = open(path, encoding="utf-8").read()
    pat = re.compile(r'^(%s\s*=\s*)"[^"]*"' % re.escape(name), re.M)
    if not pat.search(t):
        raise RuntimeError("السطر %s غير موجود بـ lab_updater.py" % name)
    t = pat.sub(lambda m: '%s"%s"' % (m.group(1), value), t, count=1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def public_key_from_private():
    """يستخرج المفتاح العام (base64) من المفتاح الخاص المحفوظ."""
    from cryptography.hazmat.primitives import serialization
    with open(KEY_PATH, "rb") as f:
        k = serialization.load_pem_private_key(f.read(), password=None)
    return base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()


def raw_url(repo, branch, folder):
    return "https://raw.githubusercontent.com/%s/%s%s" % (repo, branch, ("/" + folder.strip("/")) if folder.strip("/") else "")


# ----------------------------------------------------------------------------- GitHub contents API
def _gh(token, method, path, body=None):
    req = urllib.request.Request("https://api.github.com" + path, method=method,
                                 data=(json.dumps(body).encode("utf-8") if body is not None else None))
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "lab-update-publisher")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except Exception:
            return e.code, None


GH = _gh   # tests replace this


def gh_upload(token, repo, branch, folder, filename, data, message):
    path = "/repos/%s/contents/%s" % (repo, (folder.strip("/") + "/" if folder.strip("/") else "") + filename)
    sha = None
    st, js = GH(token, "GET", path + "?ref=" + branch)
    if st == 200 and isinstance(js, dict):
        sha = js.get("sha")
    elif st not in (404,):
        raise RuntimeError("GitHub رفض الاتصال (%s): %s" % (st, (js or {}).get("message", "") if isinstance(js, dict) else ""))
    body = {"message": message, "content": base64.b64encode(data).decode("ascii"), "branch": branch}
    if sha:
        body["sha"] = sha
    st, js = GH(token, "PUT", path, body)
    if st not in (200, 201):
        msg = (js or {}).get("message", "") if isinstance(js, dict) else ""
        hint = " — تأكد أن التوكن يملك صلاحية Contents: Read and write لهذا المستودع." if st in (401, 403, 404) else ""
        raise RuntimeError("فشل رفع %s (%s) %s%s" % (filename, st, msg, hint))


def gh_prune(token, repo, branch, folder, keep):
    """يحذف زيبات قديمة (update_*.zip) من المستودع ويُبقي الأحدث (keep)."""
    try:
        base = "/repos/%s/contents/%s" % (repo, folder.strip("/"))
        st, js = GH(token, "GET", base + "?ref=" + branch)
        if st != 200 or not isinstance(js, list):
            return
        zips = []
        for it in js:
            m = re.match(r"^update_(\d+)\.zip$", it.get("name", ""))
            if m:
                zips.append((int(m.group(1)), it))
        zips.sort(key=lambda x: x[0], reverse=True)
        for _, it in zips[keep:]:
            GH(token, "DELETE", base + "/" + it["name"], {"message": "remove old update", "sha": it["sha"], "branch": branch})
            _log("   حُذف القديم: " + it["name"])
    except Exception:
        pass


# ----------------------------------------------------------------------------- jobs
def _start(title, fn):
    with _LOCK:
        if _JOB["state"] == "running":
            return False, "في عملية شغّالة الآن — انتظر تنتهي."
        _JOB.update(state="running", title=title, log=[], error="", result="")

    def work():
        try:
            res = fn()
            with _LOCK:
                _JOB["state"] = "done"
                _JOB["result"] = res or ""
        except Exception as e:  # noqa: BLE001
            _log("✖ " + str(e))
            with _LOCK:
                _JOB["state"] = "error"
                _JOB["error"] = str(e)

    threading.Thread(target=work, daemon=True).start()
    return True, "بدأت"


def job_install_crypto():
    _log("تثبيت مكتبة cryptography ...")
    ok, _ = _run([sys.executable, "-m", "pip", "install", "cryptography"])
    if not ok:
        raise RuntimeError("فشل التثبيت — تأكد من اتصال الإنترنت.")
    _log("✔ تم. (إذا أول مرة، أعد فتح هذي الصفحة)")
    return "تم تثبيت cryptography"


def job_init_keys():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        raise RuntimeError("ثبّت cryptography أولاً (الخطوة 1).")
    if not os.path.exists(KEY_PATH):
        _log("إنشاء مفتاح التوقيع الخاص ...")
        ok, out = _run([sys.executable, os.path.join("tools", "make_update_package.py"), "--init-keys"])
        if not ok or not os.path.exists(KEY_PATH):
            raise RuntimeError("تعذّر إنشاء المفتاح.")
        _log("✔ المفتاح الخاص محفوظ بـ: " + KEY_PATH + "  — خذ منه نسخة احتياطية وما ترسله لأحد!")
    else:
        _log("مفتاح التوقيع موجود أصلاً (ما انكتب فوقه): " + KEY_PATH)
    pub = public_key_from_private()
    patch_updater("PUBLIC_KEY_B64", pub)
    _log("✔ ألصقت PUBLIC_KEY_B64 بملف lab_updater.py تلقائيًا.")
    return "تم"


def _bump_version():
    vp = os.path.join(HERE, "VERSION")
    cur = open(vp, encoding="utf-8").read().strip() if os.path.exists(vp) else ""
    if cur.isdigit():
        new = str(int(cur) + 1)
    elif not cur:
        new = "1"
        _log("⚠ ما لقيت ملف VERSION، أنشأته برقم 1.")
    else:
        raise RuntimeError("ملف VERSION فيه قيمة غير رقمية (%s) — اجعله رقمًا ثم أعد." % cur)
    with open(vp, "w", encoding="utf-8") as f:
        f.write(new)
    _log("رقم النسخة: %s ← %s" % (cur or "-", new))
    return new


def job_build(notes, bump, upload, cfg, token):
    pk, url = read_updater_values()
    if not pk:
        raise RuntimeError("PUBLIC_KEY_B64 فاضي بـ lab_updater.py — نفّذ الخطوة 2 أولاً.")
    if not os.path.exists(KEY_PATH):
        raise RuntimeError("مفتاح التوقيع الخاص غير موجود — نفّذ الخطوة 2 أولاً.")
    if upload:
        if not token:
            raise RuntimeError("توكن الكتابة غير محفوظ (لوحة المصمم ← توكن GitHub للكتابة).")
        if not REPO_RE.match(cfg["repo"]) or not BRANCH_RE.match(cfg["branch"]) or not DIR_RE.match(cfg["folder"]):
            raise RuntimeError("إعدادات المستودع غير صحيحة (المستودع بصيغة account/repo).")
        if url and url.rstrip("/") != raw_url(cfg["repo"], cfg["branch"], cfg["folder"]).rstrip("/"):
            _log("⚠ DEFAULT_UPDATE_URL بـ lab_updater.py مختلف عن مكان الرفع الحالي — العملاء يقرؤون من: " + url)
    ver = _bump_version() if bump else (open(os.path.join(HERE, "VERSION"), encoding="utf-8").read().strip()
                                         if os.path.exists(os.path.join(HERE, "VERSION")) else "")
    _log("بناء الحزمة وتوقيعها ...")
    cmd = [sys.executable, os.path.join("tools", "make_update_package.py"), "--notes", notes or ""]
    ok, out = _run(cmd)
    if not ok:
        raise RuntimeError("فشل بناء التحديث (انظر السطور أعلاه).")
    outdir = os.path.join(HERE, "update_packages")
    man = json.load(open(os.path.join(outdir, "update.json"), encoding="utf-8"))
    zname = man["file"]
    _log("✔ الحزمة جاهزة: %s (نسخة %s)" % (zname, man["version"]))
    if not upload:
        return "بُنيت الحزمة بمجلد update_packages — ارفع update.json و %s يدويًا." % zname
    msg = "update %s" % man["version"]
    _log("رفع الزيب لـ GitHub ...")
    gh_upload(token, cfg["repo"], cfg["branch"], cfg["folder"], zname, open(os.path.join(outdir, zname), "rb").read(), msg)
    _log("رفع update.json (آخر خطوة حتى ما يشوف العميل تحديث ناقص) ...")
    gh_upload(token, cfg["repo"], cfg["branch"], cfg["folder"], "update.json", open(os.path.join(outdir, "update.json"), "rb").read(), msg)
    gh_prune(token, cfg["repo"], cfg["branch"], cfg["folder"], keep=2)
    _log("✔ نُشر التحديث %s. العملاء يشوفونه خلال ساعات أو عند فتح البرنامج (GitHub قد يأخّر الكاش ~5 دقائق)." % man["version"])
    return "نُشر التحديث %s" % man["version"]


# ----------------------------------------------------------------------------- page
def register(app, designer_required, get_db, get_setting, set_setting):
    from flask import jsonify, render_template_string, request

    def _cfg():
        db = get_db()
        try:
            return {"repo": get_setting(db, "pub_repo", ""), "branch": get_setting(db, "pub_branch", "main") or "main",
                    "folder": get_setting(db, "pub_dir", "updates"),
                    "has_token": bool(get_setting(db, "github_write_token", ""))}
        finally:
            db.close()

    def _checks(c):
        try:
            import cryptography  # noqa: F401
            has_crypto = True
        except ImportError:
            has_crypto = False
        pk, url = read_updater_values()
        vp = os.path.join(HERE, "VERSION")
        return {"crypto": has_crypto, "key": os.path.exists(KEY_PATH), "pk": bool(pk), "url": url,
                "url_expected": raw_url(c["repo"], c["branch"], c["folder"]) if REPO_RE.match(c["repo"] or "") else "",
                "version": open(vp, encoding="utf-8").read().strip() if os.path.exists(vp) else "",
                "key_path": KEY_PATH}

    @app.route("/designer/publish-update")
    @designer_required
    def designer_publish_update():
        c = _cfg()
        return render_template_string(PAGE, c=c, k=_checks(c), frozen=is_frozen())

    @app.route("/designer/publish-update/save", methods=["POST"])
    @designer_required
    def designer_publish_update_save():
        p = request.get_json(silent=True) or {}
        repo, branch, folder = (p.get("repo") or "").strip(), (p.get("branch") or "main").strip(), (p.get("folder") or "").strip().strip("/")
        if not REPO_RE.match(repo):
            return jsonify(ok=False, message="المستودع لازم بصيغة  account/repo")
        if not BRANCH_RE.match(branch) or not DIR_RE.match(folder):
            return jsonify(ok=False, message="الفرع أو المجلد فيه رموز غير مسموحة")
        db = get_db()
        try:
            set_setting(db, "pub_repo", repo)
            set_setting(db, "pub_branch", branch)
            set_setting(db, "pub_dir", folder)
            db.commit()
        finally:
            db.close()
        url = raw_url(repo, branch, folder)
        try:
            patch_updater("DEFAULT_UPDATE_URL", url)
        except Exception as e:  # noqa: BLE001
            return jsonify(ok=False, message=str(e))
        return jsonify(ok=True, message="تم الحفظ، وضبطت DEFAULT_UPDATE_URL بـ lab_updater.py: " + url)

    def _guard():
        if is_frozen():
            return jsonify(ok=False, message="تشتغل فقط من نسخة المطوّر (python app.py)، مو من برنامج منصّب.")
        return None

    @app.route("/designer/publish-update/run", methods=["POST"])
    @designer_required
    def designer_publish_update_run():
        g = _guard()
        if g:
            return g
        p = request.get_json(silent=True) or {}
        action = p.get("action")
        c = _cfg()
        db = get_db()
        try:
            token = get_setting(db, "github_write_token", "")
        finally:
            db.close()
        _SECRETS[:] = [token]
        if action == "crypto":
            ok, msg = _start("تثبيت cryptography", job_install_crypto)
        elif action == "keys":
            ok, msg = _start("إنشاء مفتاح التوقيع", job_init_keys)
        elif action in ("publish", "build"):
            notes = (p.get("notes") or "").strip()[:300]
            bump = bool(p.get("bump", True))
            ok, msg = _start("بناء ونشر التحديث" if action == "publish" else "بناء التحديث",
                             lambda: job_build(notes, bump, action == "publish", c, token))
        else:
            return jsonify(ok=False, message="أمر غير معروف")
        return jsonify(ok=ok, message=msg)

    @app.route("/designer/publish-update/status")
    @designer_required
    def designer_publish_update_status():
        with _LOCK:
            return jsonify(dict(_JOB, log=list(_JOB["log"])))


PAGE = r"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>نشر تحديث للعملاء</title>
<style>
body{font-family:Tahoma,Arial,sans-serif;background:#F1F5F9;margin:0;padding:20px;color:#0F172A}
.w{max-width:880px;margin:0 auto}.c{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:16px 18px;margin-bottom:14px}
h1{font-size:20px;margin:0 0 4px}h3{margin:0 0 8px;font-size:16px}.m{color:#64748B;font-size:13px}
.ok{color:#15803D}.bad{color:#B91C1C}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
input[type=text]{padding:7px 10px;border:1px solid #CBD5E1;border-radius:7px;font:14px Tahoma}
button,a.b{background:#205072;color:#fff;border:0;border-radius:8px;padding:8px 16px;font:700 14px Tahoma;cursor:pointer;text-decoration:none;display:inline-block}
button.s,a.s{background:#fff;color:#205072;border:1px solid #205072}button:disabled{opacity:.5;cursor:not-allowed}
#log{background:#0F172A;color:#E2E8F0;border-radius:8px;padding:10px;font:12.5px/1.6 Consolas,monospace;white-space:pre-wrap;min-height:60px;max-height:320px;overflow:auto;display:none}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;background:#F1F5F9}
</style></head><body><div class="w">
<h1>📦 نشر تحديث للعملاء</h1>
<div class="m">يبني تحديثًا موقّعًا (كود + قوالب فقط، بدون قاعدة بيانات ولا توكنات) ويرفعه لمستودع GitHub العام. العميل يشوف «يتوفر تحديث» بنفسه.</div>
{% if frozen %}<div class="c bad">هذي الصفحة تشتغل فقط من نسخة المطوّر (python app.py).</div>{% endif %}

<div class="c"><h3>الإعداد مرة واحدة</h3>
 <div class="row"><b>1) مكتبة cryptography:</b> {% if k.crypto %}<span class="ok">✔ مثبّتة</span>{% else %}<span class="bad">✖ غير مثبّتة</span> <button onclick="run('crypto')">تثبيت</button>{% endif %}</div>
 <div class="row"><b>2) مفتاح التوقيع:</b>
   {% if k.key and k.pk %}<span class="ok">✔ موجود، والمفتاح العام ملصوق بـ lab_updater.py</span>
   {% else %}<span class="bad">✖ غير جاهز</span> <button onclick="run('keys')" {{ '' if k.crypto else 'disabled' }}>إنشاء المفتاح ولصق المفتاح العام</button>{% endif %}</div>
 {% if k.key %}<div class="m">المفتاح الخاص: <span dir="ltr">{{ k.key_path }}</span> — خذ منه نسخة احتياطية الآن (لو ضاع ما تقدر تصدّر تحديثات لعملاء Setup الحاليين). لا ترسله لأحد.</div>{% endif %}
 <div class="row"><b>3) مستودع GitHub العام للتحديثات:</b></div>
 <div class="row"><input type="text" id="repo" placeholder="account/repo" value="{{ c.repo }}" style="width:220px" dir="ltr">
   <input type="text" id="branch" value="{{ c.branch }}" style="width:90px" dir="ltr" title="الفرع">
   <input type="text" id="folder" value="{{ c.folder }}" style="width:120px" dir="ltr" title="المجلد">
   <button class="s" onclick="saveCfg()">حفظ وضبط الرابط</button></div>
 <div class="m">الرابط الحالي بـ lab_updater.py: <span dir="ltr">{{ k.url or '(فاضي)' }}</span>
   {% if k.url and k.url_expected and k.url.rstrip('/') == k.url_expected.rstrip('/') %}<span class="ok">✔ مطابق</span>{% elif k.url_expected %}<span class="bad">⚠ يختلف عن: {{ k.url_expected }}</span>{% endif %}</div>
 <div class="m">المستودع لازم يكون <b>عامًا (Public)</b> وما يحتوي أسرارًا. توكن الكتابة: {% if c.has_token %}<span class="ok">✔ محفوظ بلوحة المصمم</span>{% else %}<span class="bad">✖ غير محفوظ — احفظه من لوحة المصمم (توكن GitHub للكتابة)، بصلاحية Contents: Read and write لهذا المستودع فقط.</span>{% endif %}</div>
 <div class="row"><b>4) Setup العميل:</b> <a class="b s" href="/designer/client-builder">🏗 تجهيز ملف تنصيب العميل</a>
   <span class="m">ابنيه مرة بعد الخطوات أعلاه؛ هو يحمل المفتاح العام ويقبل التحديثات بعدها.</span></div>
</div>

<div class="c"><h3>نشر تحديث الآن</h3>
 <div class="m">رقم النسخة الحالي (VERSION): <b>{{ k.version or '—' }}</b></div>
 <div class="row"><input type="text" id="notes" placeholder="وصف قصير للتحديث (يظهر للعميل)" style="width:100%;max-width:560px"></div>
 <div class="row"><label><input type="checkbox" id="bump" checked> ارفع رقم النسخة تلقائيًا (+1)</label></div>
 <div class="row"><button id="pubBtn" onclick="publish('publish')">🚀 ابنِ ووقّع وانشر</button>
   <button class="s" onclick="publish('build')">بناء فقط (أرفعه يدويًا)</button></div>
 <div class="m">التحديث ما يضيف مكتبات بايثون ولا ملفات static (صور/خطوط) — هذي تحتاج Setup جديد.</div>
</div>
<div id="log"></div>
</div>
<script>
function post(u,b){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json();});}
function saveCfg(){post('/designer/publish-update/save',{repo:v('repo'),branch:v('branch'),folder:v('folder')}).then(function(d){alert(d.message);if(d.ok)location.reload();});}
function v(i){return document.getElementById(i).value;}
function run(a){post('/designer/publish-update/run',{action:a}).then(function(d){if(!d.ok){alert(d.message);return;}poll(true);});}
function publish(a){if(a==='publish'&&!confirm('نشر التحديث لكل العملاء؟'))return;post('/designer/publish-update/run',{action:a,notes:v('notes'),bump:document.getElementById('bump').checked}).then(function(d){if(!d.ok){alert(d.message);return;}poll(true);});}
var t=null;
function poll(first){var el=document.getElementById('log');el.style.display='block';clearInterval(t);
 function tick(){fetch('/designer/publish-update/status').then(function(r){return r.json();}).then(function(s){
   el.textContent=(s.title?('▶ '+s.title+'\n'):'')+s.log.join('\n')+(s.state==='done'?'\n\n✔ '+s.result:'')+(s.state==='error'?'\n\n✖ '+s.error:'');el.scrollTop=el.scrollHeight;
   if(s.state!=='running'){clearInterval(t);if(s.state==='done'&&/cryptography|تم$/.test(s.result))setTimeout(function(){location.reload();},1200);}});}
 tick();t=setInterval(tick,1200);}
</script></body></html>"""
