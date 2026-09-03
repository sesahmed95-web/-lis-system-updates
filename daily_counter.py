# -*- coding: utf-8 -*-
"""
daily_counter.py
================
حساب "Number Of" — رقم تسلسل المريض بيوم زيارته (كام مريض زار المختبر
اليوم لين وصلنا لهذا المريض بالذات). ملف مستقل، ما يحتاج تعديل أي جدول.

الافتراض: عمود التاريخ المستخدم هو collected_at أو accessioned_at بجدول
order_tests (نفس الأعمدة المذكورة بملف database.py الأصلي). إذا الترقيم
طلع غلط، خبرني شنو اسم العمود الصحيح عندك وأعدل هذا الملف بس (سطر واحد).
"""

def get_patient_number_of_day(db, order_test_id):
    """يرجع رقم تسلسلي (1، 2، 3...) لهذا المريض ضمن كل المرضى اللي زاروا
    المختبر بنفس تاريخ هذا الطلب — معدود حسب أقدم مريض بنفس اليوم أولاً."""
    row = db.execute(
        "SELECT COALESCE(collected_at, accessioned_at) AS d, patient_id, id "
        "FROM order_tests WHERE id=?", (order_test_id,)
    ).fetchone()
    if not row or not row["d"]:
        return 1

    day = row["d"][:10]  # YYYY-MM-DD من بداية النص
    result = db.execute(
        "SELECT COUNT(DISTINCT patient_id) AS n FROM order_tests "
        "WHERE substr(COALESCE(collected_at, accessioned_at), 1, 10) = ? "
        "AND id <= ?",
        (day, row["id"]),
    ).fetchone()
    return result["n"] if result and result["n"] else 1
