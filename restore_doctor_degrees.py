# -*- coding: utf-8 -*-
"""
سكربت لمرة وحدة: يرجّع شهادات دكاترة الفحص الثلاثة (عربي/انكليزي) بقاعدة
البيانات، بنفس النص اللي كان موجود بالتقارير القديمة قبل ما تنمسح.

طريقة التشغيل:
1. حط هذا الملف بنفس مجلد المشروع (جنب app.py و database.py و lis.db)
2. أوقف السيرفر (Ctrl+C) إذا كان شغال
3. شغل: python restore_doctor_degrees.py
4. شغل السيرفر من جديد وجرب تطبع تقرير للتأكد
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "lis.db")

# كل سطر بالقيمة يطبع بسطر منفصل تحت الاسم بالتقرير (القالب يستبدل \n بـ <br>)
DOCTORS_DEGREES = [
    {
        "match": "خليل",  # يبحث عن دكتور اسمه يحتوي هذا النص
        "degree_ar": "بكالوريوس طب وجراحة عامة\nطبيب ممارس امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nHematopathologist",
    },
    {
        "match": "اسراء",
        "degree_ar": "بكالوريوس طب وجراحة عامة\nاختصاص امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nF.I.B.M.S Hematopathologist",
    },
    {
        "match": "هدى",
        "degree_ar": "بكالوريوس طب وجراحة عامة\nاختصاص امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nM.SC.Hematopathologist",
    },
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ ملف قاعدة البيانات غير موجود بهذا المسار: {DB_PATH}")
        print("   تأكد إنك حاطط هذا السكربت بنفس مجلد lis.db وشغله من نفس المجلد.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT id, name, degree_ar, degree_en FROM examining_doctors_list").fetchall()
    print("قبل التعديل:")
    for r in rows:
        print(f"  #{r['id']} {r['name']!r} -> degree_ar={r['degree_ar']!r}, degree_en={r['degree_en']!r}")

    updated = 0
    for row in rows:
        for target in DOCTORS_DEGREES:
            if target["match"] in row["name"]:
                conn.execute(
                    "UPDATE examining_doctors_list SET degree_ar=?, degree_en=? WHERE id=?",
                    (target["degree_ar"], target["degree_en"], row["id"]),
                )
                updated += 1
                break

    conn.commit()

    print(f"\n✅ تم تحديث {updated} دكتور.")
    print("\nبعد التعديل:")
    rows_after = conn.execute("SELECT id, name, degree_ar, degree_en FROM examining_doctors_list").fetchall()
    for r in rows_after:
        print(f"  #{r['id']} {r['name']!r} -> degree_ar={r['degree_ar']!r}, degree_en={r['degree_en']!r}")

    conn.close()


if __name__ == "__main__":
    main()
