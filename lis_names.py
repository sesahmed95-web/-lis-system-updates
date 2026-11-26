# -*- coding: utf-8 -*-
"""
lis_names.py (v112) — استيراد أسماء المرضى من ملف العميل (Excel .xlsx / CSV) بعد المسح، أو البدء فارغاً.
  - الصفحة:  /admin/import-names   (خطوتان: معاينة ← تأكيد بالرقم السري). العمود الأول (أو عمود «الاسم») = الاسم؛ اختيارياً: الجنس، العمر، الهاتف.
  - بعد مسح السجلات (lis_wipe) يظهر شريط بكل الصفحات: «استيراد أسماء من ملف» أو «ابدأ فارغاً» (الإعداد names_choice_pending).
  - يستورد الأسماء فقط (جدول patients) — بدون زيارات/نتائج. يتخطى المكرر (الاسم + الهاتف) الموجود أصلاً.
"""
import html as _h
import io
import re
import secrets
import time
from datetime import datetime

_CTX = {}
_PENDING = {}            # token -> (expires, people)
_AR_DIGITS = {ord(a): b for a, b in zip("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")}
_HDR = {
    "name": ("name", "full_name", "fullname", "patient", "patient name", "اسم", "الاسم", "اسم المريض", "المريض"),
    "gender": ("gender", "sex", "الجنس", "جنس"),
    "age": ("age", "العمر", "عمر"),
    "phone": ("phone", "mobile", "tel", "الهاتف", "رقم الهاتف", "الموبايل", "موبايل", "رقم الموبايل", "الجوال"),
}


def read_people(data, filename):
    """يقرأ xlsx أو csv ويرجع [{name,gender,age,phone}]. يرفع ValueError برسالة مفهومة."""
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except Exception:
            raise ValueError("قراءة Excel تحتاج مكتبة openpyxl — احفظ الملف بصيغة CSV وأعد المحاولة.")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception:
            raise ValueError("تعذّر فتح ملف Excel (تالف أو ليس xlsx).")
        rows = [[("" if c is None else str(c).strip()) for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
    elif fn.endswith((".csv", ".txt")):
        import csv
        text = None
        for enc in ("utf-8-sig", "cp1256", "utf-8"):
            try:
                text = data.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            raise ValueError("تعذّر قراءة ترميز الملف — احفظه UTF-8.")
        sample = text[:2000]
        delim = ";" if sample.count(";") > sample.count(",") else ("\t" if sample.count("\t") > sample.count(",") else ",")
        rows = [[c.strip() for c in r] for r in csv.reader(text.splitlines(), delimiter=delim)]
    else:
        raise ValueError("صيغة الملف غير مدعومة — استخدم .xlsx أو .csv")
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        raise ValueError("الملف فارغ.")

    def idx(hdr, key):
        for i, h in enumerate(hdr):
            if h.strip().lower() in _HDR[key]:
                return i
        return None
    hdr = rows[0]
    ni = idx(hdr, "name")
    if ni is None:
        ni, gi, ai, pi, body = 0, None, None, None, rows            # بلا عناوين: العمود الأول = الاسم
    else:
        gi, ai, pi, body = idx(hdr, "gender"), idx(hdr, "age"), idx(hdr, "phone"), rows[1:]

    def g(v):
        v = (v or "").strip().lower()
        if v in ("m", "male", "ذكر", "ذ"):
            return "Male"
        if v in ("f", "female", "أنثى", "انثى", "أ"):
            return "Female"
        return ""
    out, seen = [], set()
    for r in body:
        nm = re.sub(r"\s+", " ", r[ni]).strip() if ni < len(r) else ""
        if not nm:
            continue
        ph = r[pi].strip() if pi is not None and pi < len(r) else ""
        key = (nm.lower(), ph)
        if key in seen:
            continue
        seen.add(key)
        age = None
        if ai is not None and ai < len(r):
            m = re.search(r"\d+", r[ai].translate(_AR_DIGITS))
            age = int(m.group()) if m else None
        out.append({"name": nm[:200], "gender": g(r[gi]) if gi is not None and gi < len(r) else "", "age": age, "phone": ph[:40]})
    if not out:
        raise ValueError("لم أجد أسماء بالملف. تأكد أن العمود الأول (أو عمود «الاسم») فيه أسماء المرضى.")
    return out


def import_people(db, people):
    """يدخل الأسماء الجديدة فقط (يتخطى الموجود بنفس الاسم+الهاتف). يرجع (أضيف, تُخطّي)."""
    have = {((r[0] or "").strip().lower(), (r[1] or "").strip()) for r in db.execute("SELECT full_name, COALESCE(phone,'') FROM patients")}
    now = datetime.now().isoformat(timespec="seconds")
    added = skipped = 0
    for x in people:
        if (x["name"].lower(), x["phone"]) in have:
            skipped += 1
            continue
        db.execute("INSERT INTO patients (full_name, gender, age, age_unit, phone, created_at) VALUES (?,?,?,?,?,?)",
                   (x["name"], x["gender"] or None, x["age"], "Years", x["phone"] or None, now))
        have.add((x["name"].lower(), x["phone"]))
        added += 1
    db.commit()
    return added, skipped


_CSS = ("body{font-family:Tahoma,Arial,sans-serif;background:#F1F5F9;margin:0;padding:22px 14px 60px}.box{max-width:760px;margin:0 auto;background:#fff;border-radius:14px;padding:20px}"
        "h2{margin:0 0 8px;color:#205072}label{display:block;margin:12px 0 4px;font-weight:700}input[type=password],input[type=file]{width:100%;padding:9px;border:1px solid #CBD5E1;border-radius:9px;box-sizing:border-box;font:14px Tahoma}"
        "button{border:0;border-radius:9px;padding:10px 20px;font:700 14px Tahoma;cursor:pointer;color:#fff;background:#205072;margin-top:14px}.s{background:#64748B;margin-inline-start:8px}"
        ".m{color:#64748B;font-size:13px;line-height:1.9}.ok{background:#DCFCE7;color:#166534;padding:10px;border-radius:9px;margin-bottom:10px}.er{background:#FEE2E2;color:#991B1B;padding:10px;border-radius:9px;margin-bottom:10px}"
        "table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}td,th{padding:6px;border-bottom:1px solid #E2E8F0;text-align:right}")


def _page(body, msg="", ok=True):
    m = ('<div class="%s">%s</div>' % ("ok" if ok else "er", _h.escape(msg))) if msg else ""
    return ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>استيراد أسماء المرضى</title><style>%s</style></head>'
            '<body><div class="box"><a href="/">&#8617; رجوع للبرنامج</a>%s%s</div></body></html>' % (_CSS, m, body))


_FORM = ('<h2>استيراد أسماء المرضى من ملف</h2><p class="m">ملف Excel (.xlsx) أو CSV. العمود الأول (أو عمود باسم «الاسم / Name») = اسم المريض. أعمدة اختيارية: الجنس، العمر، الهاتف. '
         'تُستورد الأسماء فقط (بدون زيارات أو نتائج) ويُتخطّى المكرر.</p>'
         '<form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="preview"><label>الملف</label><input type="file" name="file" accept=".xlsx,.xlsm,.csv,.txt" required>'
         '<button type="submit">معاينة</button></form>'
         '<form method="post" style="margin-top:18px" onsubmit="return confirm(\'البدء بقائمة فارغة؟\')"><input type="hidden" name="action" value="skip"><button class="s" type="submit">ابدأ فارغاً (بدون استيراد)</button></form>')


def _banner_js():
    return ('<script id="lis-names-banner-js">(function(){if(window.top!==window.self)return;var b=document.createElement("div");b.setAttribute("dir","rtl");'
            'b.style.cssText="position:fixed;top:0;inset-inline:0;z-index:2147482000;background:#FEF3C7;color:#78350F;padding:8px 14px;font:13px Tahoma,Arial;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.15)";'
            'b.innerHTML="تم مسح سجلات المرضى. اختر: <a href=\\"/admin/import-names\\" style=\\"font-weight:800;color:#92400E\\">استيراد أسماء من ملف Excel/CSV</a> &nbsp;|&nbsp; <a href=\\"#\\" id=\\"lnSkip\\" style=\\"font-weight:800;color:#92400E\\">ابدأ فارغاً</a>";'
            'document.body.appendChild(b);document.getElementById("lnSkip").onclick=function(e){e.preventDefault();var f=new FormData();f.append("action","skip");fetch("/admin/import-names",{method:"POST",body:f,credentials:"same-origin"}).then(function(){b.remove()})}})();</script>')


def install(app, ctx):
    from flask import request, session, Response
    _CTX.update(ctx or {})
    login_required = _CTX["login_required"]

    @app.route("/admin/import-names", methods=["GET", "POST"])
    @login_required
    def lis_import_names():
        db = _CTX["get_db"]()
        if request.method == "GET":
            return Response(_page(_FORM), mimetype="text/html")
        act = request.form.get("action")
        if act == "skip":
            _CTX["set_setting"](db, "names_choice_pending", "0")
            db.commit()
            _CTX["log_action"]("ImportNames", "patients", 0, "start-empty")
            return Response(_page("<p class='m'>تم: يبدأ البرنامج فارغاً.</p>", "تم اختيار البدء فارغاً.", True), mimetype="text/html")
        if act == "preview":
            f = request.files.get("file")
            try:
                if not f or not f.filename:
                    raise ValueError("اختر ملفاً.")
                people = read_people(f.read(), f.filename)
            except ValueError as e:
                return Response(_page(_FORM, str(e), False), mimetype="text/html")
            tok = secrets.token_urlsafe(16)
            now = time.time()
            for k in [k for k, v in _PENDING.items() if v[0] < now]:
                _PENDING.pop(k, None)
            _PENDING[tok] = (now + 900, people)
            rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td dir='ltr'>%s</td></tr>" % (
                _h.escape(x["name"]), x["gender"] or "", x["age"] if x["age"] is not None else "", _h.escape(x["phone"])) for x in people[:15])
            body = ("<h2>معاينة: %d اسم</h2><p class='m'>أول 15 سطراً. تأكد أن الأعمدة مفهومة ثم أكّد بالرقم السري.</p>"
                    "<table><tr><th>الاسم</th><th>الجنس</th><th>العمر</th><th>الهاتف</th></tr>%s</table>"
                    "<form method='post'><input type='hidden' name='action' value='import'><input type='hidden' name='token' value='%s'>"
                    "<label>الرقم السري للحذف/التعديل</label><input type='password' name='pin' autocomplete='off' required>"
                    "<button type='submit'>استيراد %d اسم</button><a class='m' style='margin-inline-start:12px' href='/admin/import-names'>إلغاء</a></form>") % (
                len(people), rows, tok, len(people))
            return Response(_page(body), mimetype="text/html")
        if act == "import":
            ok, err = _CTX["check_pin"](db, request.form.get("pin"), "import-names")
            if not ok:
                return Response(_page(_FORM, err, False), mimetype="text/html")
            ent = _PENDING.pop(request.form.get("token", ""), None)
            if not ent or ent[0] < time.time():
                return Response(_page(_FORM, "انتهت صلاحية المعاينة — ارفع الملف مرة ثانية.", False), mimetype="text/html")
            added, skipped = import_people(db, ent[1])
            _CTX["set_setting"](db, "names_choice_pending", "0")
            db.commit()
            _CTX["log_action"]("ImportNames", "patients", 0, "added=%d skipped=%d" % (added, skipped))
            return Response(_page("<p class='m'><a href='/front-desk/patients'>فتح قائمة المرضى</a></p>",
                                  "تم استيراد %d اسماً (وتخطّي %d مكرراً)." % (added, skipped), True), mimetype="text/html")
        return Response(_page(_FORM), mimetype="text/html")

    @app.after_request
    def _names_banner(resp):
        try:
            if resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough:
                return resp
            if request.path.startswith(("/admin/import-names", "/plus/", "/ai/")) or "/print" in request.path:
                return resp
            if not (session.get("designer_id") or "interface" in session):
                return resp
            db = _CTX["get_db"]()
            if _CTX["get_setting"](db, "names_choice_pending", "0") != "1":
                return resp
            data = resp.get_data()
            if b"lis-names-banner-js" in data or b"</body>" not in data:
                return resp
            head, _, tail = data.rpartition(b"</body>")
            resp.set_data(head + _banner_js().encode("utf-8") + b"</body>" + tail)
        except Exception:
            pass
        return resp
