# -*- coding: utf-8 -*-
"""
apply_patient_meta_vars.py
===========================
يعدّل app.py تلقائيًا (بدون ما تلصق انتَ أي شي يدويًا) لإضافة المتغيرات
الجديدة المطلوبة لتقارير GUE/GSE/SFA: sample_no, sample_time, number_of,
patient_name_en.

آمن بالتصميم:
  - يسوي نسخة احتياطية app.py.bak_<وقت> قبل أي تعديل.
  - يدور عن نص محدد (anchor) لازم يلكاه بالضبط مرة وحدة، وإلا ما يعدل
    شي إطلاقًا ويطبعلك رسالة واضحة (صفر مخاطرة تخريب لو النص مختلف).
  - يطبع عدد أسطر app.py قبل وبعد، حتى تتأكد بعينك التغيير منطقي.

طريقة التشغيل: بنفس مجلد app.py:
    python apply_patient_meta_vars.py
"""
import re
import shutil
import time

APP_FILE = "app.py"

IMPORT_ANCHOR = "save_visit_previous_merges, get_visit_previous_merges)"
IMPORT_ADDITION = "\nfrom daily_counter import get_patient_number_of_day"

# نجرب أكثر من صيغة اقتباس محتملة لنفس السطر (بعض المحررات تبدّل التنصيص)
RENDER_ANCHORS = [
    'referring_doctor_name=ot["referring_doctor_name"] or "",',
    "referring_doctor_name=ot['referring_doctor_name'] or '',",
]
RENDER_ADDITION = (
    '\n        sample_no=ot["barcode"] if "barcode" in ot.keys() else "",'
    '\n        sample_time=(ot["collected_at"] or ot["accessioned_at"] or "") if "collected_at" in ot.keys() else "",'
    '\n        number_of=get_patient_number_of_day(db, order_test_id),'
    '\n        patient_name_en=(patient["full_name_en"] if patient and "full_name_en" in patient.keys() else ""),'
)


def main():
    with open(APP_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    lines_before = content.count("\n")
    changes_made = []
    problems = []

    # ---- 1) إضافة الاستيراد ----
    count = content.count(IMPORT_ANCHOR)
    if count == 1:
        content = content.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADDITION, 1)
        changes_made.append("✅ أُضيف: from daily_counter import get_patient_number_of_day")
    elif count == 0:
        problems.append(f"❌ ما لكيت نص الاستيراد المتوقع بالملف — لم يُعدَّل شي بهذا الجزء. (بحثت عن: {IMPORT_ANCHOR!r})")
    else:
        problems.append(f"⚠️  لكيت نص الاستيراد {count} مرة (متوقع مرة وحدة بالضبط) — تجاوزت هذا التعديل لتفادي أي خطأ.")

    # ---- 2) إضافة المتغيرات لـ render_template ----
    applied_render = False
    for anchor in RENDER_ANCHORS:
        count = content.count(anchor)
        if count == 1:
            content = content.replace(anchor, anchor + RENDER_ADDITION, 1)
            changes_made.append("✅ أُضيفت المتغيرات الجديدة (sample_no, sample_time, number_of, patient_name_en) لاستدعاء render_template")
            applied_render = True
            break
        elif count > 1:
            problems.append(f"⚠️  لكيت السطر {anchor!r} أكثر من مرة ({count}) — تجاوزت هذا التعديل لتفادي أي خطأ.")
            applied_render = True  # منعنا التكرار بمحاولة الصيغة الثانية أيضًا
            break
    if not applied_render:
        problems.append("❌ ما لكيت سطر render_template المتوقع (referring_doctor_name=...) — لم يُعدَّل شي بهذا الجزء.")

    if not changes_made:
        print("لم يتم أي تعديل. المشاكل:")
        for p in problems:
            print(" ", p)
        print("\nما انسوت نسخة احتياطية لأنه ما صار أي تغيير على app.py.")
        return

    # ---- نسخة احتياطية قبل الكتابة ----
    backup_name = f"{APP_FILE}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(APP_FILE, backup_name)

    with open(APP_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    lines_after = content.count("\n")

    print("=== النتيجة ===")
    for c in changes_made:
        print(c)
    if problems:
        print("\nتنبيهات (راجعها يدويًا):")
        for p in problems:
            print(" ", p)
    print(f"\nنسخة احتياطية محفوظة بـ: {backup_name}")
    print(f"عدد أسطر app.py: {lines_before} → {lines_after} (فرق {lines_after - lines_before} سطر، متوقع حوالي 5)")
    print("\nإذا صار أي خطأ لاحقًا، انسخ النسخة الاحتياطية فوق app.py لترجع للوضع السابق مباشرة.")


if __name__ == "__main__":
    main()
