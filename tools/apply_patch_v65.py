# -*- coding: utf-8 -*-
r"""
apply_patch_v65.py  -  patch آمن لـ app.py (ما يستبدل ملفك).

  باركود الأنابيب يتجمّع حسب "نوع الأنبوب" مو حسب القسم:
     كل التحاليل اللي تحتاج Serum (كيمياء + هرمونات + فيتامينات + دلائل ورمية + فايروسات...) = باركود واحد
     كل اللي تحتاج EDTA (CBC, BF, Retic, ESR, HbA1c, Hb.electro, Hb.H, Sickling, Coombs...) = باركود واحد
     كل التخثر (PT, PTT, D-dimer, Fibrinogen...) = باركود واحد (Citrate)
     البول والبراز والسائل المنوي وغيرها = كل واحد بحاويته.
  + صفحة جديدة للمسؤول: /management/tube-types  لترتيب نوع الأنبوب لكل تحليل (تقترح تلقائيًا وتحفظ بضغطة).

شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v65.py
ينشئ نسخة احتياطية app.py.bak_v65. لو أي مكان بـ app.py مختلف عن المتوقع يوقف ولا يغيّر شيئًا.
"""
import os, py_compile, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")

A1_OLD = 'group_mode = (request.args.get("group") or get_setting(db, "barcode_group_mode", "department") or "department").strip()'
A1_NEW = '''group_mode = (request.args.get("group") or get_setting(db, "barcode_group_mode", "") or "tube").strip()
    if group_mode == "department" and not request.args.get("group"):
        group_mode = "tube"   # v65: الافتراضي صار التجميع حسب نوع الأنبوب (?group=department يرجّع القديم)'''

A2_OLD = 'key = (dept or stype) if group_mode != "sample_type" else stype'
A2_NEW = '''if group_mode == "tube":
            key = _tube_type_of(r["sample_type"], r["department"], r["test_name"])
        else:
            key = (dept or stype) if group_mode != "sample_type" else stype'''

A3_OLD = '"sample_type": stype if group_mode == "sample_type" else "",'
A3_NEW = '"sample_type": stype if group_mode in ("sample_type", "tube") else "",'

MAIN_ANCHOR = 'if __name__ == "__main__":'

BLOCK = r'''# --- v65: باركود الأنابيب حسب نوع الأنبوب + صفحة ترتيب أنواع الأنابيب للتحاليل ---
import re as _re_v65
TUBE_TYPES = ["Blood-EDTA", "Serum", "Citrate", "Urine", "Stool", "Semen", "Bone Marrow", "Fluid", "Swab", "Other"]
_TUBE_TYPE_TITLES = {"Blood-EDTA": "EDTA (غطاء بنفسجي)", "Serum": "Serum / Gel (غطاء أصفر/أحمر)", "Citrate": "Citrate (غطاء أزرق — تخثر)",
                     "Urine": "بول", "Stool": "براز", "Semen": "سائل منوي", "Bone Marrow": "نقي عظم", "Fluid": "سائل (Fluid/CSF)",
                     "Swab": "مسحة / زرع", "Other": "غير ذلك (ملصق مستقل)"}


def _tube_type_of(sample_type, department, name):
    """يرجّع نوع الأنبوب القانوني للتحليل (أحد TUBE_TYPES) أو "" إذا ما نعرف (يبقى بملصقه الفردي).
    الأولوية: sample_type المكتوب بالتحليل (يتحمّل اختلاف الكتابة) ثم تخمين من القسم والاسم."""
    st = (sample_type or "").strip().lower()
    dept = (department or "").strip().lower()
    nm = (name or "").strip().lower()
    if st:
        if any(k in st for k in ("edta", "lavender", "purple", "whole blood")):
            return "Blood-EDTA"
        if any(k in st for k in ("citrate", "blue top")):
            return "Citrate"
        if any(k in st for k in ("serum", "gel", "sst", "plain", "clot activator")):
            return "Serum"
        if "urine" in st:
            return "Urine"
        if any(k in st for k in ("stool", "feces", "faeces")):
            return "Stool"
        if "semen" in st:
            return "Semen"
        if "marrow" in st:
            return "Bone Marrow"
        if any(k in st for k in ("fluid", "csf", "pleural", "ascit", "synovial")):
            return "Fluid"
        if "swab" in st or "culture" in st:
            return "Swab"
        if st in ("other", "others"):
            return ""
    # تخمين (sample_type فاضي أو عام مثل "Blood")
    if "coag" in dept or _re_v65.search(r"\b(pt|ptt|aptt|inr)\b|d[\s.\-]?dimer|fibrinogen", nm):
        return "Citrate"
    if _re_v65.search(r"bma|bone marrow|biopsy|\bbmp\b", nm):
        return "Bone Marrow"
    if "fluid" in nm:
        return "Fluid"
    if _re_v65.search(r"\bcbc\b|blood film|\bbf\b|retic|\besr\b|hb[\s.\-]*(electro|h\b|f\b|prep)|sickl|coombs|a1c|hba1c|blood group|\babo\b|g6pd|osmotic|\bham", nm):
        return "Blood-EDTA"
    if "hemat" in dept:
        return "Blood-EDTA"
    if any(k in dept for k in ("chem", "hormone", "vitamin", "tumor", "viral", "serolog", "immun", "lipid", "diabet", "marker")):
        return "Serum"
    if "urine" in nm or re.search(r"\bgue\b", nm):
        return "Urine"
    if "stool" in nm or re.search(r"\bgse\b", nm):
        return "Stool"
    if "semen" in nm or re.search(r"\bsfa\b", nm):
        return "Semen"
    return ""


@app.route("/management/tube-types", methods=["GET", "POST"])
@roles_required("admin")
def tube_types_page():
    """ترتيب نوع الأنبوب لكل تحليل: يقترح تلقائيًا (حسب الاسم/القسم/النوع الحالي) وتعدّل وتحفظ. الباركود يتجمّع بعدها حسب هذا النوع."""
    db = get_db()
    tests = db.execute("SELECT id, code, name, department, COALESCE(sample_type, '') AS sample_type FROM test_definitions "
                       "ORDER BY department, name").fetchall()
    msg = ""
    if request.method == "POST":
        n = 0
        for t in tests:
            v = (request.form.get("tt_%d" % t["id"]) or "").strip()
            if v in TUBE_TYPES and v != (t["sample_type"] or ""):
                db.execute("UPDATE test_definitions SET sample_type=? WHERE id=?", ("" if v == "Other" else v, t["id"]))
                n += 1
        db.commit()
        log_action("TubeTypes", "test_definitions", 0, "updated %d" % n)
        msg = "تم الحفظ — تحديث %d تحليل." % n
        tests = db.execute("SELECT id, code, name, department, COALESCE(sample_type, '') AS sample_type FROM test_definitions "
                           "ORDER BY department, name").fetchall()
    rows = []
    for t in tests:
        cur = _tube_type_of(t["sample_type"], t["department"], t["name"])
        rows.append({"id": t["id"], "code": t["code"], "name": t["name"], "dept": t["department"] or "", "current": t["sample_type"],
                     "val": cur or "Other"})
    page = """<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>أنواع الأنابيب</title>
<style>body{font-family:Tahoma,Arial,sans-serif;background:#F1F5F9;margin:0;padding:18px;color:#0F172A}.w{max-width:980px;margin:0 auto}
.c{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:14px 18px;margin-bottom:12px}table{width:100%;border-collapse:collapse}
th{background:#205072;color:#fff;padding:7px 8px;text-align:right;font-size:13px}td{padding:5px 8px;border-bottom:1px solid #E5E7EB;font-size:14px}
select{padding:4px 6px;border-radius:6px;border:1px solid #CBD5E1}button{background:#205072;color:#fff;border:0;border-radius:8px;padding:9px 20px;font:700 14px Tahoma;cursor:pointer}
.m{color:#64748B;font-size:13px}.ok{color:#15803D;font-weight:700}tr.ch td{background:#FFFBEB}</style></head><body><div class="w">
<h2 style="margin:0 0 4px">🧪 أنواع الأنابيب للتحاليل</h2>
<div class="c"><div class="m">اختر نوع الأنبوب لكل تحليل. باركود الأنابيب يتجمّع حسب هذا النوع <b>بغض النظر عن القسم</b>: كل التحاليل اللي تحتاج Serum = باركود واحد، كل EDTA = باركود واحد،
كل Citrate (تخثر) = باركود واحد. القيمة المعروضة هي <b>اقتراح تلقائي</b> (أو القيمة الحالية)؛ عدّل ما يلزم ثم احفظ. "غير ذلك" = ملصق مستقل للتحليل.</div>
{% if msg %}<div class="ok" style="margin-top:8px">{{ msg }}</div>{% endif %}</div>
<form method="post"><div class="c"><table><tr><th>التحليل</th><th>الكود</th><th>القسم</th><th>النوع الحالي</th><th>نوع الأنبوب</th></tr>
{% for r in rows %}<tr class="{{ 'ch' if r.current != (r.val if r.val != 'Other' else '') else '' }}"><td>{{ r.name }}</td><td dir="ltr">{{ r.code }}</td><td>{{ r.dept }}</td><td dir="ltr" class="m">{{ r.current or '—' }}</td>
<td><select name="tt_{{ r.id }}">{% for k in tube_types %}<option value="{{ k }}" {{ 'selected' if k == r.val }}>{{ titles[k] }}</option>{% endfor %}</select></td></tr>{% endfor %}
</table><div style="margin-top:12px"><button type="submit">💾 حفظ كل الأنواع</button> <a href="/designer" style="margin-inline-start:12px" class="m">رجوع</a></div></div></form></div></body></html>"""
    from flask import render_template_string as _rts_v65
    return _rts_v65(page, rows=rows, tube_types=TUBE_TYPES, titles=_TUBE_TYPE_TITLES, msg=msg)


'''


def main():
    if not os.path.exists(P):
        sys.exit("ERROR: app.py not found at " + P)
    s = open(P, encoding="utf-8").read()
    if "_tube_type_of" in s:
        sys.exit("Already patched - nothing to do.")
    for name, anchor in (("A1", A1_OLD), ("A2", A2_OLD), ("A3", A3_OLD), ("MAIN", MAIN_ANCHOR)):
        c = s.count(anchor)
        if c != 1:
            sys.exit("STOPPED: anchor %s found %d times (expected 1). app.py differs from what this patch expects - nothing changed." % (name, c))
    new = s.replace(A1_OLD, A1_NEW).replace(A2_OLD, A2_NEW).replace(A3_OLD, A3_NEW).replace(MAIN_ANCHOR, BLOCK + MAIN_ANCHOR)
    for need in ("def roles_required", "def log_action"):
        if need not in s:
            sys.exit("STOPPED: app.py has no '%s' - nothing changed." % need)
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: patched file has a syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v65")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: app.py patched (backup: app.py.bak_v65). Restart the program, then open /management/tube-types")


if __name__ == "__main__":
    main()
