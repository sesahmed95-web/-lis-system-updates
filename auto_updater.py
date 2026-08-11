"""
نظام التحديث التلقائي عبر الإنترنت (Auto-Update over the Internet)
====================================================================
هذا النظام منفصل تماماً عن نظام الترخيص (license_manager.py). وظيفته
الوحيدة: يخلي برنامج العميل يتحقق دورياً (أو عند الطلب من لوحة المصمم)
هل صدر إصدار أحدث من البرنامج، وإذا نعم ينزّله ويثبّته تلقائياً فوق نفس
مكان التثبيت (%LOCALAPPDATA%\\HematologistLIS) بدون ما يحتاج العميل يسوي
أي شيء يدوياً.

آلية العمل باختصار
-------------------
1. أنت (المصمم) تسوي مستودع GitHub **خاص (Private)** واحد لمشروع البرنامج.
   خاص عشان الكود ما يصير ظاهر للعموم.
2. كل مرة تسوي تحديث: تحدّث ملف VERSION برقم إصدار أكبر من السابق، وتسوي
   git push عادي لفرع main. **هذا كل شي** — ما تحتاج تسوي "Release" ولا
   ترفع ملف zip يدوياً؛ البرنامج يقرأ مباشرة آخر نسخة من فرع main.
3. برنامج كل عميل (بعد ما "يرتبط بالإنترنت" من لوحة المصمم الخاصة بجهازه)
   يتحقق دورياً من محتوى ملف VERSION على فرع main بمستودعك، يقارنه
   بالرقم المثبّت عنده محلياً، وإذا لقى رقم أحدث ينزّل نسخة كاملة من فرع
   main (zipball) ويشغّل update.ps1 تلقائياً بالخلفية (نفس السكربت
   المستخدم للتحديث اليدوي، فقط بمصدر= الملف المنزّل بدل مجلد جنب البرنامج).

⚠️ مهم جداً قبل تسليم البرنامج لأي عميل — عبّي القيم تحت:
   - GITHUB_OWNER: اسم حسابك/منظمتك على GitHub.
   - GITHUB_REPO: اسم المستودع (الخاص) اللي فيه الإصدارات.
   - GITHUB_BRANCH: اسم الفرع اللي تدفع (push) عليه تحديثاتك — افتراضياً main.
   - GITHUB_TOKEN: "Fine-grained personal access token" مربوط بهذا
     المستودع فقط وبصلاحية قراءة فقط (Contents: Read-only). هذا التوكن
     ينحزم داخل نسخة كل عميل حتى يقدر يقرأ الملفات من مستودعك
     الخاص، فخليه محدود الصلاحية قد الإمكان (قراءة فقط، على هذا
     المستودع تحديداً)، وما تستخدم توكن شخصي كامل الصلاحيات أبداً.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import base64
import urllib.request
import urllib.error
import zipfile
from datetime import datetime

# ============================ إعدادات المصمم (عبّيها قبل التسليم) =========
GITHUB_OWNER = "sesahmed95-web"     # 🔒 غيّرها
GITHUB_REPO = "-lis-system-updates"    # 🔒 غيّرها
GITHUB_BRANCH = "main"                 # 🔒 اسم الفرع اللي تدفع عليه تحديثاتك
GITHUB_TOKEN = "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"  # 🔒 غيّرها
# مسار ملف VERSION داخل المستودع (لو حاطه بمجلد فرعي غيّر هذا المسار،
# مثلاً "lis_system/VERSION"). اتركه "VERSION" لو بجذر المستودع مباشرة.
VERSION_FILE_PATH_IN_REPO = "VERSION"
# كل قد ايش ساعة يتحقق البرنامج تلقائياً من وجود تحديث جديد (فقط إذا
# كان هذا الجهاز "مربوط بالإنترنت" من لوحة المصمم).
CHECK_INTERVAL_HOURS = 6
# ===========================================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(APP_DIR, "VERSION")
API_BASE = "https://api.github.com"


def is_configured():
    """يرجع False لو المصمم نسى يعبّي القيم أعلاه — يمنع أي محاولة اتصال
    عبثية بقيم placeholder."""
    return (
        GITHUB_OWNER and "YOUR-" not in GITHUB_OWNER
        and GITHUB_REPO and "YOUR-" not in GITHUB_REPO
        and GITHUB_TOKEN and "YOUR-" not in GITHUB_TOKEN
    )


def get_local_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "0"
    except Exception:
        return "0"


def _version_key(v):
    """يحوّل نص الإصدار إلى رقم للمقارنة (v16 -> 16، 2026.08.06 -> يقارن
    كنص لو ما قدر يحوّله رقم)."""
    digits = re.sub(r"[^0-9]", "", v or "")
    return int(digits) if digits else -1


def is_newer(remote_version, local_version):
    rk, lk = _version_key(remote_version), _version_key(local_version)
    if rk != -1 and lk != -1:
        return rk > lk
    return (remote_version or "") != (local_version or "") and bool(remote_version)


def _api_request(path, accept="application/vnd.github+json"):
    req = urllib.request.Request(f"{API_BASE}{path}")
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "LIS-Auto-Updater")
    return urllib.request.urlopen(req, timeout=20)


def fetch_remote_version():
    """يقرأ محتوى ملف VERSION مباشرة من فرع GITHUB_BRANCH بالمستودع —
    بدون أي حاجة لعمل GitHub Release. أي git push عادي لهذا الفرع
    (بملف VERSION محدّث) كافي حتى تلتقطه كل نسخ العملاء تلقائياً."""
    if not is_configured():
        raise RuntimeError("لم يتم إعداد بيانات GitHub بعد (auto_updater.py) — راجع المصمم")
    path = f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{VERSION_FILE_PATH_IN_REPO}?ref={GITHUB_BRANCH}"
    with _api_request(path) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content.strip()


def _download_branch_zip(dest_path):
    """ينزّل نسخة كاملة من فرع GITHUB_BRANCH (zipball) — نفس أسلوب تنزيل
    ملف من مستودع خاص عبر GitHub API: أول طلب بتوكن يرجع تحويل (302)
    لرابط مؤقت موقّع، وهذا الرابط الثاني ما لازم نرسل معه توكن GitHub
    إطلاقاً (يرفضه)، فنطفي المتابعة التلقائية للتحويل ونسوي الطلب الثاني
    يدوياً بدون هيدر Authorization."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    zipball_url = f"{API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/zipball/{GITHUB_BRANCH}"
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(zipball_url)
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("User-Agent", "LIS-Auto-Updater")
    try:
        resp = opener.open(req, timeout=30)
        with open(dest_path, "wb") as f:
            f.write(resp.read())
        return
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        redirect_url = e.headers.get("Location")
    if not redirect_url:
        raise RuntimeError("تعذر الحصول على رابط تنزيل نسخة التحديث")
    req2 = urllib.request.Request(redirect_url)
    req2.add_header("User-Agent", "LIS-Auto-Updater")
    with urllib.request.urlopen(req2, timeout=120) as resp2, open(dest_path, "wb") as f:
        f.write(resp2.read())


def _extract_zip(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
    # لو الملف المضغوط فيه مجلد واحد فرعي (lis_system/...) رجّع مساره،
    # وإلا رجّع نفس مجلد الفك مباشرة.
    entries = [e for e in os.listdir(extract_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        return os.path.join(extract_dir, entries[0])
    return extract_dir


def apply_update(silent=True):
    """ينزّل نسخة فرع GITHUB_BRANCH، يفكّها، ويشغّل update.ps1 (نفس سكربت
    التحديث اليدوي الموجود أصلاً) بمصدر = الملف المنزّل. update.ps1 هو
    اللي يوقف السيرفر الحالي وينسخ الملفات الجديدة ويعيد التشغيل — فما
    نحتاج نعيد كتابة هذا المنطق من الصفر."""
    if sys.platform != "win32":
        raise RuntimeError("التحديث التلقائي مدعوم فقط على Windows حالياً")

    tmp_dir = tempfile.mkdtemp(prefix="lis_update_")
    zip_path = os.path.join(tmp_dir, "update.zip")
    _download_branch_zip(zip_path)
    source_dir = _extract_zip(zip_path, os.path.join(tmp_dir, "extracted"))

    update_script = os.path.join(APP_DIR, "update.ps1")
    if not os.path.exists(update_script):
        raise RuntimeError("update.ps1 غير موجود بمجلد البرنامج")

    args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", update_script, "-Source", source_dir,
    ]
    if silent:
        args.append("-Silent")

    creationflags = 0x08000000  # CREATE_NO_WINDOW
    subprocess.Popen(args, creationflags=creationflags, cwd=APP_DIR)


def check_and_apply(db, force_apply=True):
    """يتحقق من وجود إصدار أحدث (مباشرة من ملف VERSION على فرع
    GITHUB_BRANCH — بدون أي حاجة لـ GitHub Release). لو موجود ينزّله
    ويطبّقه (البرنامج راح يعيد تشغيل نفسه تلقائياً خلال ثوان). يرجع dict
    فيه النتيجة ويسجّلها بجدول settings حتى تنعرض بلوحة المصمم."""
    from database import set_setting
    now = datetime.now().isoformat(timespec="seconds")
    try:
        local_version = get_local_version()
        remote_version = fetch_remote_version()
        if is_newer(remote_version, local_version):
            status = f"🆕 تم العثور على إصدار جديد ({remote_version}) — جاري التحديث الآن..."
            set_setting(db, "auto_update_last_check", now)
            set_setting(db, "auto_update_last_status", status)
            db.commit()
            if force_apply:
                apply_update(silent=True)
            return {"ok": True, "updated": True, "remote_version": remote_version,
                    "local_version": local_version, "message": status}
        else:
            status = f"✅ البرنامج على آخر إصدار ({local_version})"
            set_setting(db, "auto_update_last_check", now)
            set_setting(db, "auto_update_last_status", status)
            db.commit()
            return {"ok": True, "updated": False, "remote_version": remote_version,
                    "local_version": local_version, "message": status}
    except Exception as e:
        status = f"⚠️ تعذر التحقق من التحديث: {e}"
        set_setting(db, "auto_update_last_check", now)
        set_setting(db, "auto_update_last_status", status)
        db.commit()
        return {"ok": False, "updated": False, "message": status}


def background_loop(get_db_func):
    """خيط خلفية دائم — ينام ثم يتحقق كل CHECK_INTERVAL_HOURS، وفقط إذا
    كان هذا الجهاز "مربوط بالإنترنت" (auto_update_enabled=1) من لوحة
    المصمم. يشتغل نفس شكل خيط واتساب الموجود أصلاً بالبرنامج."""
    from database import get_setting
    # فحص أول بعد 30 ثانية من الإقلاع (مو فوري حتى ما يبطّئ الإقلاع)
    time.sleep(30)
    while True:
        try:
            db = get_db_func()
            enabled = get_setting(db, "auto_update_enabled", "0") == "1"
            if enabled and is_configured():
                check_and_apply(db, force_apply=True)
                check_revocation(db)
            db.close()
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL_HOURS * 3600)


# ==================================================== إلغاء ترخيص عن بُعد ==
# آلية مستقلة عن التفعيل نفسه (license_manager.py) لكنها تستخدم نفس مستودع
# GitHub الخاص المُعدّ أعلاه. تخزّن قائمة أجهزة العملاء الملغاة كملف JSON
# واحد داخل المستودع (REVOCATION_FILE_PATH)، وكل جهاز عميل "مربوط
# بالإنترنت" يفحصها بنفس دورة فحص التحديثات (وبنفس توكن القراءة أعلاه —
# لا حاجة لصلاحية كتابة لقراءتها).
#
# النشر (كتابة الملف على GitHub) يحتاج توكن مختلف بصلاحية كتابة، ولا
# يُخزَّن هذا التوكن أبداً داخل هذا الملف ولا يُشحَن مع نسخة أي عميل —
# المصمم يدخله بنفسه من لوحة المصمم (يُحفَظ محلياً بجهازه فقط، بجدول
# settings)، فيبقى توكن القراءة المضمَّن أعلاه (GITHUB_TOKEN) بصلاحية
# قراءة فقط دائماً كما أوصينا بالتعليق بأعلى الملف — حتى لو استخرجه أي
# عميل من نسخته ما يقدر يعدّل شي بمستودعك.
REVOCATION_FILE_PATH = "revoked_licenses.json"


def _contents_url(path):
    return f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"


def fetch_revocation_list():
    """يرجع dict {hardware_id: {reason, revoked_at}}. يرجع {} بهدوء لو
    الملف غير موجود بعد بالمستودع (يعني ماكو أي إلغاء لحد الآن) — هذا
    ليس خطأ. يرفع Exception فقط لو صار خطأ اتصال/صلاحيات حقيقي."""
    if not is_configured():
        raise RuntimeError("لم يتم إعداد بيانات GitHub بعد (auto_updater.py) — راجع المصمم")
    try:
        with _api_request(_contents_url(REVOCATION_FILE_PATH)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    content_b64 = data.get("content", "")
    raw = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
    parsed = json.loads(raw) if raw.strip() else {}
    return parsed if isinstance(parsed, dict) else {}


def push_revocation(write_token, hardware_id, reason, revoke=True):
    """ينشر/يسحب إلغاء ترخيص جهاز عميل على مستودع GitHub. write_token
    يُمرَّر من المتصل (لوحة المصمم) — يُقرأ من settings لحظياً، لا يُخزَّن
    بهذا الملف. revoke=False تعني رفع الإلغاء (استعادة الجهاز) بدل
    فرضه، بحذف معرّف الجهاز من القائمة بدل إضافته."""
    if not is_configured():
        raise RuntimeError("لم يتم إعداد بيانات GitHub بعد (auto_updater.py) — راجع المصمم")
    if not write_token:
        raise RuntimeError("أدخل توكن GitHub بصلاحية كتابة أولاً (قسم الإعدادات أسفل هذا القسم)")

    hardware_id = hardware_id.strip().upper()
    sha = None
    current = {}
    try:
        with _api_request(_contents_url(REVOCATION_FILE_PATH)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sha = data.get("sha")
        raw = base64.b64decode(data.get("content", "").replace("\n", "")).decode("utf-8")
        current = json.loads(raw) if raw.strip() else {}
        if not isinstance(current, dict):
            current = {}
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        # الملف غير موجود بعد — أول عملية إلغاء تنشئه

    if revoke:
        current[hardware_id] = {
            "reason": reason or "",
            "revoked_at": datetime.now().isoformat(timespec="seconds"),
        }
        commit_msg = f"Revoke license: {hardware_id}"
    else:
        current.pop(hardware_id, None)
        commit_msg = f"Restore license: {hardware_id}"

    new_content_b64 = base64.b64encode(json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    body = {"message": commit_msg, "content": new_content_b64}
    if sha:
        body["sha"] = sha

    req = urllib.request.Request(
        f"{API_BASE}{_contents_url(REVOCATION_FILE_PATH)}",
        data=json.dumps(body).encode("utf-8"), method="PUT",
    )
    req.add_header("Authorization", f"Bearer {write_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "LIS-Auto-Updater")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20):
        pass


def check_revocation(db):
    """يُستدعى بنفس دورة فحص التحديثات (تلقائياً كل CHECK_INTERVAL_HOURS
    أو يدوياً بزر 'تحقق من تحديث الآن'). يقارن معرّف جهاز هذا التنصيب
    بقائمة الإلغاء البعيدة، ولو موجود يقفل الترخيص محلياً فوراً (نفس أثر
    انتهاء الصلاحية، لكن بسبب مختلف يظهر للمستخدم)."""
    import license_manager
    try:
        revoked_map = fetch_revocation_list()
    except Exception:
        return  # فشل الاتصال بالإلغاء البعيد لا يوقف بقية الفحص أبداً
    hw = license_manager.get_hardware_id()
    entry = revoked_map.get(hw)
    if entry:
        license_manager.mark_revoked(db, entry.get("reason", ""))
