# -*- coding: utf-8 -*-
"""
سكربت لمرة وحدة: يفعّل علامة "فحص مؤهل لأجر دكتور المختبر الفاحص"
(is_examining_test=1) على تحاليل amraض الدم/الفحص المجهري التسعة بالضبط —
نفس القائمة المستخدمة أصلاً بالكود (EXAM_SIGNATURE_TEST_CODES بـ app.py):
Blood Film, Blood Film and Retic Count, Retic Count, Fluid examination,
Hb Preparation, Sickling Test, BMA, BM Biopsy, WBCs differential.

هذا هو سبب عدم ظهور حقل "دكتور المختبر الفاحص" بصفحة "زيارة جديدة" رغم أن
الكود نفسه صحيح 100% — العلامة فاضية بقاعدة البيانات لهذي التحاليل.

طريقة التشغيل: بنفس مجلد app.py و database.py و lis.db:
    python enable_examining_tests.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "lis.db")

# نفس EXAM_SIGNATURE_TEST_CODES الموجودة بـ app.py حرفياً — لا تضيف/تحذف
# منها هنا بدون ما تعدّل القائمة الأصلية بـ app.py أيضًا، حتى يبقوا متطابقين.
EXAM_SIGNATURE_TEST_CODES = {
    "BF", "BFRETIC", "RETIC", "FLUIDEXAM", "HBPREP", "SICKLE", "BMA", "BMBIOPSY", "WBCDIFF",
}


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ ملف قاعدة البيانات غير موجود بهذا المسار: {DB_PATH}")
        print("   تأكد إنك حاطط هذا السكربت بنفس مجلد lis.db وشغله من نفس المجلد.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in EXAM_SIGNATURE_TEST_CODES)
    rows = conn.execute(
        f"SELECT id, code, name, is_examining_test FROM test_definitions WHERE code IN ({placeholders})",
        tuple(EXAM_SIGNATURE_TEST_CODES),
    ).fetchall()

    print("قبل التعديل:")
    found_codes = set()
    for r in rows:
        found_codes.add(r["code"])
        print(f"  #{r['id']} [{r['code']}] {r['name']!r} -> is_examining_test={r['is_examining_test']}")

    missing = EXAM_SIGNATURE_TEST_CODES - found_codes
    if missing:
        print(f"\n⚠️ تنبيه: هذي الأكواد ما لقيتها بجدول test_definitions إطلاقاً: {sorted(missing)}")
        print("   (يعني إما التحليل غير موجود بكتالوجك، أو الكود مكتوب بشكل مختلف بقاعدة بياناتك)")

    updated = 0
    for r in rows:
        if not r["is_examining_test"]:
            conn.execute("UPDATE test_definitions SET is_examining_test=1 WHERE id=?", (r["id"],))
            updated += 1

    conn.commit()

    print(f"\n✅ تم تفعيل العلامة على {updated} تحليل (كانت مفعّلة أصلاً على البقية).")
    print("\nبعد التعديل:")
    rows_after = conn.execute(
        f"SELECT id, code, name, is_examining_test FROM test_definitions WHERE code IN ({placeholders})",
        tuple(EXAM_SIGNATURE_TEST_CODES),
    ).fetchall()
    for r in rows_after:
        print(f"  #{r['id']} [{r['code']}] {r['name']!r} -> is_examining_test={r['is_examining_test']}")

    conn.close()


if __name__ == "__main__":
    main()
