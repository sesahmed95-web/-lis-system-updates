# -*- coding: utf-8 -*-
"""
daily_counter.py (نسخة مصلَّحة)
================================
حساب "Number Of" — رقم تسلسل المريض بيوم زيارته. order_tests ما فيه
عمود patient_id مباشر، فلازم نوصله عبر orders -> visits (نفس طريقة
الاستعلام الرئيسي بـ _print_report_impl بالضبط).
"""

def get_patient_number_of_day(db, order_test_id):
    row = db.execute(
        "SELECT COALESCE(ot.collected_at, ot.accessioned_at) AS d, v.patient_id AS patient_id, ot.id AS id "
        "FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "WHERE ot.id=?",
        (order_test_id,),
    ).fetchone()
    if not row or not row["d"]:
        return 1

    day = row["d"][:10]
    result = db.execute(
        "SELECT COUNT(DISTINCT v.patient_id) AS n "
        "FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "WHERE substr(COALESCE(ot.collected_at, ot.accessioned_at), 1, 10) = ? "
        "AND ot.id <= ?",
        (day, row["id"]),
    ).fetchone()
    return result["n"] if result and result["n"] else 1
