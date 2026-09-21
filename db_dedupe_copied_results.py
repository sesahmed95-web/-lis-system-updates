# -*- coding: utf-8 -*-
"""
db_dedupe_copied_results.py
============================
سكريبت تنظيف لمرّة واحدة -- يدمج التحاليل المكررة اللي صارت بسبب الخلل
القديم بميزة "نسخ النتائج المحددة إلى الزيارة الحالية" (كل ضغطة زر كانت
تنشئ صف order_tests جديد لنفس التحليل بنفس الزيارة، بدل ما تستخدم الصف
الموجود أصلاً -- هذا الخلل انصلح بـapp.py، وهذا السكربت يرتّب البيانات
القديمة اللي انولدت وقت وجود الخلل).

لكل زيارة: يجمع order_tests اللي عندها barcode ينتهي بـ"-old" ونفس
test_definition_id ونفس order_id -- يخلي أقدم صف (أول id) هو الأساسي،
وينقل أي نتائج (results) من الصفوف المكررة الأخرى إليه (لو نفس الـparameter
موجود بالأساسي أصلاً، النسخة المكررة تُحذف كنتيجة زايدة عن الحاجة بدل نقلها)،
وبعدين يحذف صفوف order_tests المكررة الفاضية.

آمن تشغّله أكثر من مرة -- إذا ماكو تكرار، ما يغيّر شي.

طريقة التشغيل: حطه بنفس مجلد app.py وشغّل:
    python db_dedupe_copied_results.py
"""
from database import get_db


def main():
    db = get_db()

    dup_groups = db.execute(
        "SELECT order_id, test_definition_id, barcode, GROUP_CONCAT(id) as ids, COUNT(*) as c "
        "FROM order_tests WHERE barcode LIKE '%-old' "
        "GROUP BY order_id, test_definition_id, barcode HAVING c > 1"
    ).fetchall()

    if not dup_groups:
        print("ماكو أي تحاليل مكررة (نتيجة النسخ) بقاعدة البيانات -- كلشي نظيف.")
        db.close()
        return

    merged_tests = 0
    merged_results = 0
    deleted_extra_results = 0

    for g in dup_groups:
        ids = sorted(int(x) for x in g["ids"].split(","))
        keep_id = ids[0]
        extra_ids = ids[1:]

        for extra_id in extra_ids:
            extra_results = db.execute(
                "SELECT * FROM results WHERE order_test_id=?", (extra_id,)
            ).fetchall()
            for r in extra_results:
                already = db.execute(
                    "SELECT id FROM results WHERE order_test_id=? AND test_parameter_id=?",
                    (keep_id, r["test_parameter_id"]),
                ).fetchone()
                if already:
                    # نفس الـparameter موجود أصلاً بالصف المحفوظ -- نتيجة
                    # زايدة عن الحاجة (نفس القيمة تكرار)، نحذفها فقط.
                    db.execute("DELETE FROM results WHERE id=?", (r["id"],))
                    deleted_extra_results += 1
                else:
                    # parameter غير موجود بالصف المحفوظ بعد -- ننقله إليه.
                    db.execute("UPDATE results SET order_test_id=? WHERE id=?", (keep_id, r["id"]))
                    merged_results += 1
            db.execute("DELETE FROM order_tests WHERE id=?", (extra_id,))
            merged_tests += 1

    db.commit()
    db.close()

    print("\n=== النتيجة ===")
    print(f"✅ عدد صفوف order_tests المكررة اللي انحذفت: {merged_tests}")
    print(f"✅ عدد النتائج اللي انتقلت للصف الأساسي: {merged_results}")
    print(f"✅ عدد النتائج المكررة (نفس القيمة) اللي انحذفت: {deleted_extra_results}")
    print("\nخلص بدون أي مشاكل.")


if __name__ == "__main__":
    main()
