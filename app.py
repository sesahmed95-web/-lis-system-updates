# ============================================================================
# تعليمات تعديل app.py — انسخ كل جزء بالمكان المشار له بالضبط.
# ============================================================================

# ----------------------------------------------------------------------------
# 1) REPORT_TEMPLATE_MAP (حوالي السطر 115) — ضيف 3 أسطر جديدة داخل القاموس
#    الموجود أصلاً:
# ----------------------------------------------------------------------------
"""
REPORT_TEMPLATE_MAP = {
    "CBC": "reports/cbc.html",
    "BF": "reports/blood_film.html",
    "BFRETIC": "reports/blood_film.html",
    "RETIC": "reports/retic_only.html",
    "WBCDIFF": "reports/wbc_differential.html",
    "FLUIDEXAM": "reports/fluid_examination.html",
    "COAG": "reports/coagulation.html",
    "GUE": "reports/urine_exam.html",       # <-- جديد
    "GSE": "reports/stool_exam.html",       # <-- جديد
    "SFA": "reports/seminal_fluid.html",    # <-- جديد
}
"""

# ----------------------------------------------------------------------------
# 2) بسيط تحويل صوتي عربي -> إنكليزي (اقتراح أولي قابل للتعديل يدوي دائمًا،
#    مو ترجمة نهائية مضمونة 100% — راجع الشرح اللي أرسلته سابقًا). ضيفه بأي
#    مكان بأعلى app.py قريب من الدوال المساعدة الثانية (قبل أول route):
# ----------------------------------------------------------------------------

ARABIC_NAME_TRANSLITERATION_MAP = [
    # عالج التركيبات الأطول أولاً (قبل الحرف المفرد) — الترتيب هنا مهم.
    ("عبدال", "Abdul"), ("عبد ال", "Abdul"), ("أبو", "Abu"), ("ابو", "Abu"),
    ("ال", "Al"), ("إ", "I"), ("أ", "A"), ("آ", "Aa"), ("ا", "a"),
    ("ب", "b"), ("ت", "t"), ("ث", "th"), ("ج", "j"), ("ح", "h"), ("خ", "kh"),
    ("د", "d"), ("ذ", "th"), ("ر", "r"), ("ز", "z"), ("س", "s"), ("ش", "sh"),
    ("ص", "s"), ("ض", "d"), ("ط", "t"), ("ظ", "th"), ("ع", "'"), ("غ", "gh"),
    ("ف", "f"), ("ق", "q"), ("ك", "k"), ("ل", "l"), ("م", "m"), ("ن", "n"),
    ("ه", "h"), ("و", "w"), ("ي", "y"), ("ى", "a"), ("ة", "a"), ("ء", "'"),
    (" ", " "),
]

def transliterate_arabic_name(name):
    """يرجّع اقتراح إنكليزي أولي لاسم عربي (تحويل صوتي حرف بحرف تقريبي).
    هذا اقتراح فقط يحتاج مراجعة الموظف يدويًا قبل الحفظ النهائي — أسماء
    الأشخاص عادة إلها أكثر من إملاء إنكليزي مقبول (مثال: سهاد ممكن Suhad
    أو Suhaad)، فما فيه تحويل "صحيح" وحيد مضمون لكل اسم."""
    if not name:
        return ""
    remaining = name.strip()
    out = []
    i = 0
    n = len(remaining)
    while i < n:
        matched = False
        for ar, en in ARABIC_NAME_TRANSLITERATION_MAP:
            if remaining[i:i + len(ar)] == ar:
                out.append(en)
                i += len(ar)
                matched = True
                break
        if not matched:
            out.append(remaining[i])
            i += 1
    result = "".join(out)
    # حرف كبير لأول حرف من كل كلمة
    return " ".join(w.capitalize() if w else w for w in result.split(" "))


# ----------------------------------------------------------------------------
# 3) داخل _print_report_impl — بعد السطر:
#        ranges[p["name"]] = find_reference_range(db, p["id"], ot["gender"], ot["age"], ot["age_unit"])
#    (نهاية حلقة for p in parameters:), ضيف مباشرة بعدها:
# ----------------------------------------------------------------------------
"""
    param_notes = {}
    for p in parameters:
        r = results_by_name.get(p["name"])
        param_notes[p["name"]] = (r["note"] if r is not None else "") or ""
"""

# ----------------------------------------------------------------------------
# 4) بنفس الدالة _print_report_impl، بآخر استدعاء render_template (يرجع كل
#    القوالب — ضيف السطرين الجديدين بأي مكان داخل الاستدعاء، هذا كل شي،
#    القوالب القديمة بتتجاهلهم بأمان لأنهم مو مستخدمين فيها):
# ----------------------------------------------------------------------------
"""
    return render_template(
        template_name,
        ot=ot, params=params, ranges=ranges, units=units, cbc_groups=cbc_groups,
        custom_rows=custom_rows, custom_heading=custom_heading,
        custom_heading_align=custom_heading_align, custom_rows_align=custom_rows_align,
        custom_unit_column=custom_unit_column,
        show_prev_values=show_prev_values, previous_visit_date=previous_visit_date,
        previous_values=previous_values, repeat_header_on_print=repeat_header_on_print,
        logo_url=logo_url, from_other_lab=from_other_lab, font_size=font_size,
        show_exam_signature=show_exam_signature,
        stamp_target_type="order_test", stamp_target_id=order_test_id,
        digital_stamps=get_digital_stamps(db),
        stamp_placements=get_stamp_placements(db, "order_test", order_test_id),
        visit_date=visit_date, sex=ot["gender"] or "", age=age_display,
        patient_name=ot["patient_name"], patient_id=ot["registration_number"],
        referring_doctor_name=ot["referring_doctor_name"] or "",
        param_notes=param_notes,                          # <-- جديد
        report_comment=ot["report_comment"] or "",         # <-- جديد
    )
"""

# ----------------------------------------------------------------------------
# 5) راوت جديد: حفظ الملاحظة العامة أسفل التقرير (order_tests.report_comment)
#    — ضيفه بأي مكان قريب من باقي راوتات order_tests (POST بسيطة):
# ----------------------------------------------------------------------------
"""
@app.route('/order-tests/<int:order_test_id>/report-comment', methods=['POST'])
def save_report_comment(order_test_id):
    db = get_db()
    comment = (request.form.get('report_comment') or '').strip()
    db.execute("UPDATE order_tests SET report_comment=? WHERE id=?", (comment, order_test_id))
    db.commit()
    return jsonify({"ok": True})
"""

# ----------------------------------------------------------------------------
# 6) راوت جديد: حفظ ملاحظة أمام باراميتر معيّن (results.note) — يحتاج معرفة
#    order_test_id + اسم الباراميتر (يوصلهم من شاشة إدخال النتائج بـ POST):
# ----------------------------------------------------------------------------
"""
@app.route('/order-tests/<int:order_test_id>/param-note', methods=['POST'])
def save_param_note(order_test_id):
    db = get_db()
    param_name = request.form.get('param_name')
    note = (request.form.get('note') or '').strip()
    tp = db.execute(
        "SELECT tp.id FROM test_parameters tp JOIN order_tests ot ON ot.test_definition_id = tp.test_definition_id "
        "WHERE ot.id=? AND tp.name=?", (order_test_id, param_name),
    ).fetchone()
    if not tp:
        return jsonify({"ok": False, "error": "parameter not found"}), 404
    row = db.execute(
        "SELECT id FROM results WHERE order_test_id=? AND test_parameter_id=?",
        (order_test_id, tp["id"]),
    ).fetchone()
    if row:
        db.execute("UPDATE results SET note=? WHERE id=?", (note, row["id"]))
    else:
        db.execute(
            "INSERT INTO results (order_test_id, test_parameter_id, note) VALUES (?, ?, ?)",
            (order_test_id, tp["id"], note),
        )
    db.commit()
    return jsonify({"ok": True})
"""

# ----------------------------------------------------------------------------
# 7) التحويل الصوتي التلقائي لاسم المريض — بالراوت اللي يسجّل/يعدّل مريض
#    جديد (ابحث عن أول مكان يسوي INSERT INTO patients أو UPDATE patients
#    بملفك)، أضف قبل الحفظ:
# ----------------------------------------------------------------------------
"""
    full_name_en = (request.form.get('full_name_en') or '').strip()
    if not full_name_en:
        full_name_en = transliterate_arabic_name(request.form.get('full_name', ''))
    # بعدها مرر full_name_en وياها بالـ INSERT/UPDATE مع full_name_en=?
"""
