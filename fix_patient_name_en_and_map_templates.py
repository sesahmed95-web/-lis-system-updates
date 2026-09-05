# -*- coding: utf-8 -*-
"""
fix_patient_name_en_and_map_templates.py
==========================================
يصلح تلقائيًا مشكلتين بـ app.py (بنسخة احتياطية أول، وبدون لمس أي شي
غير الأسطر المحددة بالضبط):

  1) بگ خطير: patient_name_en يستخدم متغير "patient" غير موجود — يسبب
     NameError بكل عملية طباعة بالبرنامج (حتى CBC). يصلحه بجلب الاسم
     الإنكليزي مباشرة من جدول patients عبر ot["patient_id"].

  2) يضيف GUE/GSE/SFA لـ REPORT_TEMPLATE_MAP تشاور مباشرة لقوالبنا
     الجاهزة (urine_exam.html/stool_exam.html/seminal_fluid.html) —
     يتخطى نظام "مصمم التقارير" الناقص بالكامل لهذي الثلاثة بس.

طريقة التشغيل: بنفس مجلد app.py:
    python fix_patient_name_en_and_map_templates.py
"""
import shutil
import time

APP_FILE = "app.py"

with open(APP_FILE, "r", encoding="utf-8") as f:
    content = f.read()

lines_before = content.count("\n")
changes = []
problems = []

# ---- إصلاح 1: بگ patient_name_en ----
BUGGY_LINE = '        patient_name_en=(patient["full_name_en"] if patient and "full_name_en" in patient.keys() else ""),'
FIXED_LINE = "        patient_name_en=patient_name_en_value,"
PRECOMPUTE_ANCHOR = 'repeat_header_on_print = department_shows_previous_values(ot["test_department"])'
PRECOMPUTE_ADDITION = (
    "\n\n    _pt_en_row = db.execute(\n"
    '        "SELECT full_name_en FROM patients WHERE id=?", (ot["patient_id"],)\n'
    "    ).fetchone()\n"
    '    patient_name_en_value = (_pt_en_row["full_name_en"] or "") if _pt_en_row else ""'
)

if content.count(BUGGY_LINE) == 1:
    content = content.replace(BUGGY_LINE, FIXED_LINE, 1)
    changes.append("✅ صُلح سطر patient_name_en (الخطأ الخطير)")
else:
    problems.append(f"⚠️ ما لكيت سطر patient_name_en المتوقع بالضبط مرة وحدة (عدد المطابقات: {content.count(BUGGY_LINE)}) — تأكد يدويًا.")

if content.count(PRECOMPUTE_ANCHOR) == 1:
    content = content.replace(PRECOMPUTE_ANCHOR, PRECOMPUTE_ANCHOR + PRECOMPUTE_ADDITION, 1)
    changes.append("✅ أُضيف حساب patient_name_en_value من جدول patients مباشرة")
else:
    problems.append(f"⚠️ ما لكيت سطر repeat_header_on_print المتوقع مرة وحدة (عدد المطابقات: {content.count(PRECOMPUTE_ANCHOR)}).")

# ---- إصلاح 2: ربط GUE/GSE/SFA بالقوالب الجاهزة ----
MAP_ANCHOR = '"COAG": "reports/coagulation.html",'
MAP_ADDITION = (
    '\n    "GUE": "reports/urine_exam.html",'
    '\n    "GSE": "reports/stool_exam.html",'
    '\n    "SFA": "reports/seminal_fluid.html",'
)
if content.count(MAP_ANCHOR) == 1:
    content = content.replace(MAP_ANCHOR, MAP_ANCHOR + MAP_ADDITION, 1)
    changes.append("✅ أُضيفت GUE/GSE/SFA لـ REPORT_TEMPLATE_MAP")
else:
    problems.append(f'⚠️ ما لكيت سطر "COAG": "reports/coagulation.html", مرة وحدة (عدد المطابقات: {content.count(MAP_ANCHOR)}).')

if not changes:
    print("لم يتم أي تعديل. المشاكل:")
    for p in problems:
        print(" ", p)
else:
    backup_name = f"{APP_FILE}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(APP_FILE, backup_name)
    with open(APP_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    lines_after = content.count("\n")
    print("=== النتيجة ===")
    for c in changes:
        print(c)
    if problems:
        print("\nتنبيهات:")
        for p in problems:
            print(" ", p)
    print(f"\nنسخة احتياطية: {backup_name}")
    print(f"عدد الأسطر: {lines_before} → {lines_after}")
