# -*- coding: utf-8 -*-
"""فحص قبل نشر التحديث: يبحث عن أي قالب (template) يشير له app.py أو قالب آخر لكنه غير موجود بمجلد templates.
التشغيل (من مجلد المشروع):   py check_templates.py
إذا ظهر "ناقص" ← أضف الملف لمجلد templates قبل «نشر تحديث»، وإلا تظهر صفحات خطأ عند العميل (TemplateNotFound)."""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
tdir = os.path.join(here, "templates")
if not os.path.isdir(tdir):
    print("لا يوجد مجلد templates بجانب هذا الملف."); sys.exit(2)
have = set()
for dp, _d, fns in os.walk(tdir):
    for fn in fns:
        have.add(os.path.relpath(os.path.join(dp, fn), tdir).replace("\\", "/"))
refs = {}                     # القالب المطلوب -> من أين
def add(name, src):
    name = name.strip().lstrip("/")
    if name and "{" not in name and "%" not in name and name.endswith((".html", ".txt", ".xml", ".css", ".js")):
        refs.setdefault(name, set()).add(src)
for fn in sorted(os.listdir(here)):
    if fn.endswith(".py"):
        try:
            t = open(os.path.join(here, fn), encoding="utf-8").read()
        except Exception:
            continue
        for m in re.finditer(r"render_template\(\s*[\"']([^\"']+)[\"']", t):
            add(m.group(1), fn)
        for m in re.finditer(r"[\"']((?:[\w\-]+/)*[\w\-]+\.html)[\"']", t):
            add(m.group(1), fn)
for dp, _d, fns in os.walk(tdir):
    for fn in fns:
        if fn.endswith(".html"):
            rel = os.path.relpath(os.path.join(dp, fn), tdir).replace("\\", "/")
            t = open(os.path.join(dp, fn), encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r"\{%-?\s*(?:include|extends|import|from)\s+[\"']([^\"']+)[\"']", t):
                add(m.group(1), "templates/" + rel)
missing = sorted(n for n in refs if n not in have)
print("قوالب موجودة:", len(have), "| قوالب مُشار إليها:", len(refs))
if not missing:
    print("✔ لا يوجد قالب ناقص."); sys.exit(0)
print("✖ قوالب ناقصة (%d):" % len(missing))
for n in missing:
    print("  -", n, "  ← مذكور في:", ", ".join(sorted(refs[n]))[:150])
sys.exit(1)
