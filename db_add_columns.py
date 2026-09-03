# -*- coding: utf-8 -*-
"""
db_add_columns.py
==================
سكريبت مستقل تمامًا — يضيف الأعمدة الجديدة المطلوبة مباشرة لقاعدة البيانات
بدون لمس database.py إطلاقًا. آمن تشغّله أكثر من مرة (يتجاهل العمود إذا
كان مضاف أصلاً، ما يطيح بخطأ).

طريقة التشغيل: حطه بنفس مجلد app.py وشغّل:
    python db_add_columns.py
"""
import sqlite3
from database import get_db

COLUMNS_TO_ADD = [
    ("patients", "full_name_en", "TEXT"),
    ("reference_ranges", "note", "TEXT"),
    ("order_tests", "report_comment", "TEXT"),
    ("results", "note", "TEXT"),
]

def main():
    db = get_db()
    added, skipped = [], []
    for table, column, coltype in COLUMNS_TO_ADD:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            db.commit()
            added.append(f"{table}.{column}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                skipped.append(f"{table}.{column} (موجود أصلاً)")
            else:
                print(f"⚠️  خطأ غير متوقع بـ {table}.{column}: {e}")
    db.close()

    print("\n=== النتيجة ===")
    if added:
        print("✅ أُضيفت:")
        for a in added:
            print("   -", a)
    if skipped:
        print("⏭️  متجاوزة (موجودة أصلاً):")
        for s in skipped:
            print("   -", s)
    print("\nخلص بدون أي مشاكل.")

if __name__ == "__main__":
    main()
