# -*- coding: utf-8 -*-
r"""
client_builder.py  -  Designer-panel tool: fill the client's details, press ONE button, get LabSystem_Setup.exe.

Page:  /designer/client-builder   (designer login only; works only from the source/developer copy, never from an installed EXE)

What the button does (steps run in the background, the page shows the live log):
  1. saves the lab details in this folder's database (name AR/EN, phone, address, portal URL + key)
  2. optional: creates the client's results portal on Cloudflare (runs  node scripts/new-client.mjs <name>  in your portal project
     folder, then reads the URL + secret key from clients\<name>\INFO.txt and stores them here)
  3. runs tools\make_client_installer.py   (cleans a copy of lis.db: patients/visits wiped, random designer login, ...)
  4. runs build_client.bat  (PyInstaller -> LabSystem.exe, then Inno Setup -> installer_output\LabSystem_Setup.exe)
Your folder is never changed except the lab details you typed (they are saved in its database - that is the point:
this folder IS the client's copy).
"""
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$")
WEAK = {"admin", "admin123", "123123", "12345678", "123456789", "password", "11111111", "00000000"}
BUILD_CMD = None          # tests only: override the build command
_LOCK = threading.Lock()
_JOB = {"state": "idle", "step": "", "log": [], "result": "", "error": "", "started": 0.0, "finished": 0.0}
_SECRETS = []             # strings that must never appear in the log


# ----------------------------------------------------------------------------- helpers
def is_frozen():
    return bool(getattr(sys, "frozen", False))


def out_dir():
    return os.path.join(os.path.dirname(HERE), "client_installer_" + os.path.basename(HERE))


def setup_path():
    return os.path.join(out_dir(), "client_build", "installer_output", "LabSystem_Setup.exe")


def find_inno():
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if not base:
            continue
        for ver in ("Inno Setup 6", "Inno Setup 7"):
            p = os.path.join(base, ver, "ISCC.exe")
            if os.path.exists(p):
                return p
    return ""


def prereqs(portal_dir=""):
    """[(label, ok, hint)] - what the build needs on THIS computer."""
    import shutil
    items = []
    items.append(("تشغيل من نسخة المطوّر (ليس EXE منصّب)", not is_frozen(), "افتح البرنامج بـ python app.py من مجلد العميل"))
    for rel in ("tools/make_client_installer.py", "tools/seal_client_package.py", "installer.iss", "build.bat", "start_lab.vbs", "stop_lab.bat"):
        items.append(("ملف " + rel, os.path.exists(os.path.join(HERE, rel.replace("/", os.sep))), "الملف ناقص بمجلد البرنامج"))
    inno = find_inno()
    items.append(("Inno Setup 6 (يطلع ملف التنصيب)", bool(inno), "نزّله من jrsoftware.org ونصّبه، وإلا يبقى الـ EXE بدون Setup"))
    if portal_dir:
        items.append(("Node.js (لإنشاء البوابة)", bool(shutil.which("node")), "نصّب Node.js"))
        items.append(("مجلد مشروع البوابة", os.path.exists(os.path.join(portal_dir, "scripts", "new-client.mjs")),
                      "اختر المجلد اللي فيه scripts\\new-client.mjs"))
    return items


def _log(msg):
    msg = str(msg).rstrip()
    for s in _SECRETS:
        if s and s in msg:
            msg = msg.replace(s, "••••••")
    with _LOCK:
        _JOB["log"].append(msg)
        if len(_JOB["log"]) > 600:
            del _JOB["log"][:100]


def _step(name):
    with _LOCK:
        _JOB["step"] = name
    _log("")
    _log("=== " + name + " ===")


def _run(cmd, cwd, env=None, timeout=3000):
    """runs a command (no shell), streams its output to the log, returns exit code."""
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["LAB_NOPAUSE"] = "1"
    if env:
        e.update(env)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen(cmd, cwd=cwd, env=e, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", creationflags=flags)
    killer = threading.Timer(timeout, p.kill)
    killer.start()
    try:
        for line in p.stdout:
            _log(line)
        p.wait()
    finally:
        killer.cancel()
    return p.returncode


def parse_info(text):
    """reads (url, key) from clients/<name>/INFO.txt written by new-client.mjs"""
    url = re.search(r"https://[A-Za-z0-9.\-]+\.workers\.dev", text)
    key = re.search(r"(?:المفتاح السري)\s*[:：]\s*([0-9a-fA-F]{16,})", text)
    return (url.group(0) if url else ""), (key.group(1) if key else "")


def _validate(p, has_key_saved):
    if not (p.get("name_ar", "").strip() or p.get("name_en", "").strip()):
        return "اكتب اسم المختبر (عربي أو إنكليزي)"
    pw = p.get("admin_password", "")
    if len(pw) < 8 or pw.lower() in WEAK:
        return "كلمة سر admin ضعيفة: 8 أحرف أو أكثر، وليست admin أو 12345678 أو ما يشبهها"
    if p.get("portal_auto"):
        if not SLUG_RE.match(p.get("portal_slug", "")):
            return "اسم البوابة: حروف إنكليزية صغيرة وأرقام وشرطة (3 إلى 30 حرف)"
        pd = p.get("portal_dir", "")
        if not os.path.exists(os.path.join(pd, "scripts", "new-client.mjs")):
            return "مجلد مشروع البوابة غلط: لازم فيه scripts\\new-client.mjs"
    else:
        url = p.get("portal_url", "").strip()
        if url and not url.startswith("https://"):
            return "رابط البوابة لازم يبدأ بـ https://"
        if url and not (p.get("portal_key", "").strip() or has_key_saved):
            return "رابط البوابة موجود بس المفتاح فاضي"
    return ""


def _apply(hooks, p):
    db = hooks["get_db"]()
    try:
        s = hooks["set_setting"]
        s(db, "app_name_ar", p.get("name_ar", "").strip())
        s(db, "app_name", p.get("name_en", "").strip() or p.get("name_ar", "").strip())
        s(db, "lab_phone", p.get("phone", "").strip())
        s(db, "lab_address", p.get("address", "").strip())
        url = p.get("portal_url", "").strip().rstrip("/")
        key = p.get("portal_key", "").strip().replace(" ", "")
        if url:
            s(db, "portal_url", url)
            s(db, "portal_mode", "remote")
        if key:
            s(db, "portal_api_key", key)
        if url:
            s(db, "portal_enabled", "1")
        if p.get("portal_dir"):
            s(db, "builder_portal_dir", p["portal_dir"])
        db.commit()
    finally:
        db.close()


def _pipeline(p, hooks):
    ok = False
    try:
        _step("1/4  حفظ بيانات المختبر")
        if p.get("portal_key"):
            _SECRETS.append(p["portal_key"].strip())
        _apply(hooks, p)
        _log("تم حفظ الاسم والهاتف والعنوان وإعدادات البوابة بقاعدة هذا المجلد")

        if p.get("portal_auto"):
            _step("2/4  إنشاء بوابة العميل على Cloudflare")
            slug = p["portal_slug"]
            rc = _run(["node", os.path.join("scripts", "new-client.mjs"), slug], cwd=p["portal_dir"], timeout=900)
            info = os.path.join(p["portal_dir"], "clients", slug, "INFO.txt")
            if rc != 0 or not os.path.exists(info):
                raise RuntimeError("فشل إنشاء البوابة. غالبًا لازم تسجّل دخول مرة وحدة: افتح cmd واكتب  npx wrangler login")
            url, key = parse_info(open(info, encoding="utf-8").read())
            if not (url and key):
                raise RuntimeError("البوابة انعملت بس ما قدرت أقرأ الرابط/المفتاح من " + info)
            _SECRETS.append(key)
            _apply(hooks, dict(p, portal_url=url, portal_key=key))
            _log("البوابة جاهزة: " + url + "   (المفتاح انحفظ بالبرنامج، ونسخة منه بـ " + info + ")")
        else:
            _log("(تخطّي إنشاء البوابة: استخدمنا الرابط/المفتاح المكتوبين)")

        _step("3/4  تنظيف نسخة قاعدة البيانات وتجهيز ملفات البناء")
        cmd = [sys.executable, os.path.join("tools", "make_client_installer.py"), HERE, "--out", out_dir(),
               "--admin-password", p["admin_password"], "--yes"]
        if p.get("deactivate_demo", True):
            cmd.append("--deactivate-demo-users")
        _SECRETS.append(p["admin_password"])
        if _run(cmd, cwd=HERE, timeout=900) != 0:
            raise RuntimeError("فشل تجهيز الملفات (اقرأ السجل أعلاه)")

        _step("4/4  بناء البرنامج وملف التنصيب (عدة دقائق، لا تسكّر الصفحة)")
        bld = os.path.join(out_dir(), "client_build")
        build = BUILD_CMD or ["cmd.exe", "/c", "build_client.bat"]
        if _run(build, cwd=bld, timeout=3000) != 0:
            raise RuntimeError("فشل البناء (اقرأ آخر سطور السجل)")
        if os.path.exists(setup_path()):
            with _LOCK:
                _JOB["result"] = setup_path()
            _log("✔ جاهز: " + setup_path())
            ok = True
        else:
            raise RuntimeError("انبنى LabSystem.exe بس ما انعمل ملف التنصيب (Inno Setup مو منصّب؟). افتح client_build\\installer_client.iss بـ Inno Setup واضغط Ctrl+F9")
    except Exception as e:  # noqa: BLE001
        with _LOCK:
            _JOB["error"] = str(e)
        _log("✖ " + str(e))
    finally:
        _SECRETS.clear()
        with _LOCK:
            _JOB["state"] = "done" if ok else "error"
            _JOB["finished"] = time.time()


def start(p, hooks):
    """returns (ok, message)"""
    if is_frozen():
        return False, "البناء متاح فقط من نسخة المطوّر، مو من برنامج منصّب"
    db = hooks["get_db"]()
    try:
        saved = bool(hooks["get_setting"](db, "portal_api_key", ""))
    finally:
        db.close()
    err = _validate(p, saved)
    if err:
        return False, err
    with _LOCK:
        if _JOB["state"] == "running":
            return False, "فيه عملية بناء شغّالة هسه"
        _JOB.update(state="running", step="", log=[], result="", error="", started=time.time(), finished=0.0)
    threading.Thread(target=_pipeline, args=(p, hooks), daemon=True).start()
    return True, "بدأ البناء"


def status():
    with _LOCK:
        d = dict(_JOB)
        d["log"] = "\n".join(_JOB["log"][-250:])
    d["has_setup"] = bool(d["result"]) and os.path.exists(d["result"])
    return d


# ----------------------------------------------------------------------------- web page + routes
PAGE = r"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تجهيز ملف تنصيب العميل</title>
<style>
:root{--bg:#f4f7fb;--card:#fff;--tx:#14233a;--mut:#5b6b82;--bd:#d5deea;--pri:#1f5f99;--ok:#1b7f4b;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#10161f;--card:#18212d;--tx:#e8eef6;--mut:#9fb0c6;--bd:#2c3a4d;--pri:#5aa6e6;--ok:#4cc38a;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 "Segoe UI",Tahoma,Arial,sans-serif}
.w{max-width:860px;margin:0 auto;padding:18px}h1{font-size:21px;margin:6px 0 4px}p.s{margin:0 0 14px;color:var(--mut)}
.c{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px;margin:0 0 12px}.c h2{font-size:16px;margin:0 0 10px}
.g{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:640px){.g{grid-template-columns:1fr}}
label{display:block;font-size:13px;color:var(--mut);margin:0 0 3px}input[type=text],input[type=password]{width:100%;padding:8px 10px;border:1px solid var(--bd);border-radius:8px;background:var(--bg);color:var(--tx);font:inherit}
input.l{direction:ltr;text-align:left}.f{grid-column:1/-1}.row{display:flex;align-items:center;gap:8px;margin:6px 0}
button,a.b{display:inline-block;border:0;border-radius:9px;padding:10px 18px;font:inherit;cursor:pointer;background:var(--pri);color:#fff;text-decoration:none}
button.sec{background:transparent;color:var(--pri);border:1px solid var(--pri)}button:disabled{opacity:.5;cursor:not-allowed}
.ok{color:var(--ok)}.bad{color:var(--bad)}.m{color:var(--mut);font-size:13px}ul.p{list-style:none;padding:0;margin:0}ul.p li{padding:2px 0}
pre{background:#0c1117;color:#d6e2f0;border-radius:10px;padding:10px;max-height:340px;overflow:auto;direction:ltr;text-align:left;font:12px/1.5 Consolas,monospace;white-space:pre-wrap;margin:8px 0 0}
#msg{margin:8px 0;min-height:22px}
</style></head><body><div class="w">
<h1>تجهيز ملف تنصيب العميل (LabSystem_Setup.exe)</h1>
<p class="s">املأ بيانات المختبر، واضغط زر واحد: يحوّل هذا المجلد إلى ملف تنصيب جاهز، بنفس التعديلات والتصاميم، وبقاعدة بدون مرضى.</p>
{% if frozen %}<div class="c bad">هذي الصفحة تشتغل فقط من نسخة المطوّر (python app.py)، مو من برنامج منصّب.</div>{% endif %}

<div class="c"><h2>1) بيانات المختبر</h2><div class="g">
<div><label>اسم المختبر بالعربي</label><input type="text" id="name_ar" value="{{ v.name_ar }}"></div>
<div><label>اسم المختبر بالإنكليزي</label><input type="text" class="l" id="name_en" value="{{ v.name_en }}"></div>
<div><label>الهاتف</label><input type="text" class="l" id="phone" value="{{ v.phone }}"></div>
<div><label>العنوان</label><input type="text" id="address" value="{{ v.address }}"></div></div>
<p class="m">الشعار والدكاترة والأختام والتصاميم والنسب تعدّلها من شاشاتها العادية بهالبرنامج قبل ما تضغط البناء.</p></div>

<div class="c"><h2>2) بوابة النتائج (QR)</h2>
<div class="row"><input type="checkbox" id="portal_auto"><label for="portal_auto" style="margin:0;color:inherit">أنشئ بوابة جديدة لهذا العميل تلقائيًا (Cloudflare)</label></div>
<div class="g" id="auto_box" style="display:none">
<div><label>اسم البوابة (إنكليزي صغير وشرطة)</label><input type="text" class="l" id="portal_slug" value="{{ v.slug }}"></div>
<div><label>مجلد مشروع البوابة</label><input type="text" class="l" id="portal_dir" value="{{ v.portal_dir }}" placeholder="C:\...\portal"></div>
<div class="f m">لازم Node.js منصّب، وتكون سجّلت دخول Cloudflare مرة وحدة (npx wrangler login). المفتاح يتولّد وينحفظ تلقائيًا.</div></div>
<div class="g" id="manual_box">
<div><label>رابط البوابة (https://...workers.dev)</label><input type="text" class="l" id="portal_url" value="{{ v.portal_url }}"></div>
<div><label>المفتاح السري {% if v.key_set %}<span class="ok">(محفوظ — اتركه فاضي للإبقاء عليه)</span>{% endif %}</label><input type="password" class="l" id="portal_key" autocomplete="off"></div></div></div>

<div class="c"><h2>3) خيارات الملف</h2><div class="g">
<div><label>كلمة سر admin للعميل (8 أحرف فأكثر)</label><input type="password" class="l" id="admin_password" autocomplete="new-password"></div>
<div class="row" style="align-self:end"><input type="checkbox" id="deactivate_demo" checked><label for="deactivate_demo" style="margin:0;color:inherit">عطّل المستخدمين التجريبيين (rec / tech / super / acc)</label></div></div></div>

<div class="c"><h2>فحص المتطلبات</h2><ul class="p">{% for l,ok,h in checks %}<li class="{{ 'ok' if ok else 'bad' }}">{{ '✔' if ok else '✖' }} {{ l }}{% if not ok %} <span class="m">— {{ h }}</span>{% endif %}</li>{% endfor %}</ul></div>

<div class="c"><button id="go" {% if frozen %}disabled{% endif %}>احفظ وابنِ ملف التنصيب</button>
<button class="sec" id="save">حفظ البيانات فقط</button><div id="msg"></div>
<div id="res" style="display:none"><a class="b" href="{{ url_download }}">تحميل LabSystem_Setup.exe</a> <button class="sec" id="open">فتح المجلد</button></div>
<pre id="log" style="display:none"></pre></div></div>
<script>
const $=i=>document.getElementById(i), J={'Content-Type':'application/json'};
function vals(){return {name_ar:$('name_ar').value,name_en:$('name_en').value,phone:$('phone').value,address:$('address').value,
portal_auto:$('portal_auto').checked,portal_slug:$('portal_slug').value.trim(),portal_dir:$('portal_dir').value.trim(),
portal_url:$('portal_url').value.trim(),portal_key:$('portal_key').value.trim(),admin_password:$('admin_password').value,deactivate_demo:$('deactivate_demo').checked}}
function say(t,c){const m=$('msg');m.textContent=t;m.className=c||''}
$('portal_auto').onchange=()=>{const a=$('portal_auto').checked;$('auto_box').style.display=a?'grid':'none';$('manual_box').style.display=a?'none':'grid'};
$('save').onclick=async()=>{const r=await fetch('{{ url_save }}',{method:'POST',headers:J,body:JSON.stringify(vals())});const d=await r.json();say(d.message,d.ok?'ok':'bad')};
$('go').onclick=async()=>{say('');const r=await fetch('{{ url_start }}',{method:'POST',headers:J,body:JSON.stringify(vals())});const d=await r.json();
 if(!d.ok){say(d.message,'bad');return}$('go').disabled=true;$('res').style.display='none';$('log').style.display='block';poll()};
$('open').onclick=()=>fetch('{{ url_open }}',{method:'POST'});
async function poll(){const r=await fetch('{{ url_status }}');const d=await r.json();const l=$('log');l.textContent=d.log;l.scrollTop=l.scrollHeight;
 if(d.state==='running'){say('⏳ '+d.step);setTimeout(poll,2000);return}
 $('go').disabled=false;if(d.state==='done'){say('✔ جاهز: '+d.result,'ok');$('res').style.display='block'}else if(d.state==='error'){say('✖ '+d.error,'bad')}}
poll();
</script></body></html>"""


def register(app, designer_required, get_db, get_setting, set_setting):
    from flask import jsonify, render_template_string, request, send_file

    hooks = {"get_db": get_db, "get_setting": get_setting, "set_setting": set_setting}

    def _vals():
        db = get_db()
        try:
            g = lambda k, d="": get_setting(db, k, d)  # noqa: E731
            return {"name_ar": g("app_name_ar"), "name_en": g("app_name"), "phone": g("lab_phone"), "address": g("lab_address"),
                    "portal_url": g("portal_url"), "key_set": bool(g("portal_api_key")), "portal_dir": g("builder_portal_dir"),
                    "slug": re.sub(r"[^a-z0-9]+", "-", os.path.basename(HERE).lower()).strip("-")[:30]}
        finally:
            db.close()

    @app.route("/designer/client-builder")
    @designer_required
    def designer_client_builder():
        v = _vals()
        return render_template_string(
            PAGE, v=v, frozen=is_frozen(), checks=prereqs(v["portal_dir"]),
            url_save="/designer/client-builder/save", url_start="/designer/client-builder/start",
            url_status="/designer/client-builder/status", url_download="/designer/client-builder/download",
            url_open="/designer/client-builder/open-folder")

    @app.route("/designer/client-builder/save", methods=["POST"])
    @designer_required
    def designer_client_builder_save():
        p = request.get_json(silent=True) or {}
        url = (p.get("portal_url") or "").strip()
        if url and not url.startswith("https://"):
            return jsonify(ok=False, message="رابط البوابة لازم يبدأ بـ https://")
        _apply(hooks, p)
        return jsonify(ok=True, message="تم حفظ البيانات بقاعدة هذا المجلد")

    @app.route("/designer/client-builder/start", methods=["POST"])
    @designer_required
    def designer_client_builder_start():
        ok, msg = start(request.get_json(silent=True) or {}, hooks)
        return jsonify(ok=ok, message=msg)

    @app.route("/designer/client-builder/status")
    @designer_required
    def designer_client_builder_status():
        return jsonify(status())

    @app.route("/designer/client-builder/download")
    @designer_required
    def designer_client_builder_download():
        p = _JOB.get("result") or ""
        if not (p and os.path.exists(p) and os.path.abspath(p) == os.path.abspath(setup_path())):
            return "لا يوجد ملف جاهز", 404
        return send_file(p, as_attachment=True, download_name="LabSystem_Setup.exe")

    @app.route("/designer/client-builder/open-folder", methods=["POST"])
    @designer_required
    def designer_client_builder_open():
        d = os.path.dirname(setup_path())
        if request.remote_addr in ("127.0.0.1", "::1") and os.path.isdir(d) and hasattr(os, "startfile"):
            os.startfile(d)  # noqa: S606
            return jsonify(ok=True)
        return jsonify(ok=False)
