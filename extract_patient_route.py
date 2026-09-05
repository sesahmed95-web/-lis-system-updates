# -*- coding: utf-8 -*-
"""
extract_patient_route.py
=========================
تشخيصي فقط (ما يعدّل app.py) — يدور عن كل الدوال اللي فيها INSERT/UPDATE
على جدول patients، حتى نعرف وين نربط محرك التحويل الصوتي (عربي -> إنكليزي)
لاسم المريض تلقائيًا.

طريقة التشغيل: بنفس مجلد app.py:
    python extract_patient_route.py
بعدها افتح patient_route_dump.txt وانسخ محتواه وارسله.
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

out = []

# كل الدوال اللي بجسمها INSERT INTO patients أو UPDATE patients
func_pattern = re.compile(r"^def\s+(\w+)\s*\(.*?\n(?:.*\n)*?(?=^def |\Z)", re.MULTILINE)
matches = []
for m in func_pattern.finditer(content):
    body = m.group(0)
    if re.search(r"(INSERT INTO patients|UPDATE patients)", body):
        matches.append(m.group(1))

out.append(f"=== دوال فيها INSERT/UPDATE على جدول patients: {matches} ===\n")

for func_name in matches:
    out.append(f"\n{'='*80}\n### {func_name} ###\n{'='*80}\n")
    pattern = rf"^def {re.escape(func_name)}\s*\(.*?\n(?:.*\n)*?(?=^def |\Z)"
    m2 = re.search(pattern, content, re.MULTILINE)
    out.append(m2.group(0) if m2 else "(تعذر الاستخراج)")

with open("patient_route_dump.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("تم — افتح patient_route_dump.txt")
