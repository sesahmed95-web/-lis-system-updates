# -*- coding: utf-8 -*-
"""
extract_print_function.py
==========================
سكريبت تشخيصي فقط (ما يعدّل app.py) — يستخرج دالة طباعة التقرير بالضبط
حتى نعرف وين نضيف استثناء GUE/GSE/SFA يتجاوز "مصمم التقارير" ويطبع
مباشرة من قوالبنا الجاهزة.

طريقة التشغيل: بنفس مجلد app.py:
    python extract_print_function.py > print_function_dump.txt

بعدها افتح print_function_dump.txt وانسخ محتواه كامل وارسله.
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

content = "".join(lines)
out = []

# ندور عن أي دالة اسمها فيه "print_report" (بأي حروف كبيرة/صغيرة)
candidates = re.findall(r"^def\s+(\w*print_report\w*)\s*\(", content, re.MULTILINE)
out.append(f"=== دوال لكيتها بأسمائها فيها 'print_report': {candidates} ===\n")

for func_name in candidates:
    out.append(f"\n{'='*80}\n### {func_name} ###\n{'='*80}\n")
    pattern = rf"^def {re.escape(func_name)}\s*\(.*?\n(?:.*\n)*?(?=^def |\Z)"
    m = re.search(pattern, content, re.MULTILINE)
    out.append(m.group(0) if m else "(تعذر استخراج المحتوى الكامل تلقائيًا)")

out.append(f"\n{'='*80}\n### get_report_template (منطق اختيار القالب) ###\n{'='*80}\n")
m2 = re.search(r"^def get_report_template\s*\(.*?\n(?:.*\n)*?(?=^def |\Z)", content, re.MULTILINE)
out.append(m2.group(0) if m2 else "ما لكيت دالة بهذا الاسم بالضبط بـ app.py — ممكن تكون بـ database.py.")

with open("print_function_dump.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("تم — افتح print_function_dump.txt (يدعم UTF-8، افتحه بـ Notepad عادي أو VS Code)")
