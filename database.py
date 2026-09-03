# ============================================================================
# تعليمات تعديل database.py — انسخ كل جزء بالمكان المشار له بالضبط.
# ما تستبدل الملف كامل — هذا فقط الإضافات المطلوبة.
# ============================================================================

# ----------------------------------------------------------------------------
# 1) داخل def migrate(conn):  —  عدّل قاموس "needed" الموجود أصلاً (حوالي
#    السطر 492-582). هذا القاموس نفسه موجود بملفك، فقط أضف الأعمدة التالية
#    للمفاتيح المذكورة (لا تنشئ مفتاح "reference_ranges" أو "patients" جديد
#    لأنه موجود أصلاً — فقط زِد على القائمة الموجودة له):
# ----------------------------------------------------------------------------

# "patients": [ ... القائمة الموجودة أصلاً ... ,
#     ("full_name_en", "TEXT"),   # <-- ضيف هذا السطر بآخر قائمة patients
# ],

# "reference_ranges": [("age_from_unit", "TEXT DEFAULT 'Years'"), ("age_to_unit", "TEXT DEFAULT 'Years'"),
#     ("note", "TEXT"),   # <-- التعليق الطبي، يظهر قبل النسبة بين قوسين بالتقرير
# ],

# "order_tests": [("doctor_id", "INTEGER"), ("collected_at", "TEXT"), ("accessioned_at", "TEXT"), ("price", "REAL"),
#     ("report_comment", "TEXT"),   # <-- الملاحظة العامة أسفل التقرير المطبوع
# ],

# "results": [
#     ("note", "TEXT"),   # <-- جدول results ما كان إله صف بقاموس needed أصلاً، هذا مفتاح جديد كامل
# ],


# ----------------------------------------------------------------------------
# 2) بعد كتلة "Coagulation Tests" الموجودة أصلاً بدالة migrate() (تبدأ بـ
#    "any_tests = conn.execute(...)" وتنتهي بـ conn.commit() بعدها — دورها
#    بالبحث عن "existing_coag" بملفك) — ضيف الكتلة التالية مباشرة بعدها،
#    بنفس المستوى (نفس indentation)، ونفس المتغير any_tests معاد استخدامه:
# ----------------------------------------------------------------------------

_SEED_GUE_GSE_SFA = '''
    # General Urine / Stool / Seminal Fluid Examination — نفس فكرة إضافة
    # COAG أعلاه بالضبط: تُدرَج فقط إذا كانت قاعدة البيانات موجودة أصلاً
    # وناقصة هذي الفحوصات (تركيب تلقائي لأول مرة يشتغل فيها البرنامج
    # المحدَّث على قاعدة بيانات قديمة). لا تنحذف ولا تتكرر لو اشتغلت أكثر
    # من مرة (يفحص code أولاً).
    dynamic_exam_specs = [
        ("GUE", "General Urine Examination", "فحص البول العام", "Urine", "Urine", 5000, [
            ("Color", "", "Text"), ("Specific Gravity", "", "Numeric"), ("Reaction", "", "Numeric"),
            ("Glucose", "", "Text"), ("Protein", "", "Text"), ("Ketone", "", "Text"),
            ("Bile Pigment", "", "Text"), ("Urobilinogen", "eu/dl", "Text"), ("Nitrite", "", "Text"),
            ("RBCs", "/HPF", "Text"), ("PUS", "/HPF", "Text"), ("Casts", "", "Text"),
            ("Epithelial Cells", "/HPF", "Text"), ("Amorphous", "", "Text"), ("Mucus", "", "Text"),
            ("Crystals", "", "Text"), ("Parasites", "", "Text"),
        ]),
        ("GSE", "General Stool Examination", "فحص البراز العام", "Stool", "Stool", 5000, [
            ("Color", "", "Text"), ("Consistency", "", "Text"), ("Mucus", "", "Text"),
            ("Blood", "", "Text"), ("Worms", "", "Text"),
            ("Pus Cells", "/HPF", "Text"), ("RBCs", "/HPF", "Text"), ("Amoeba", "", "Text"),
            ("Giardia", "", "Text"), ("Helminthes Ova", "", "Text"), ("Undigested Food", "", "Text"),
            ("Fungi", "", "Text"),
        ]),
        ("SFA", "Seminal Fluid Analysis", "تحليل السائل المنوي", "Andrology", "Semen", 8000, [
            ("Volume", "mL", "Numeric"), ("Color", "", "Text"), ("Liquefaction Time", "min", "Numeric"),
            ("Viscosity", "", "Text"), ("pH", "", "Numeric"),
            ("Sperm Count", "Million/mL", "Numeric"), ("Total Sperm Count", "Million", "Numeric"),
            ("Active", "%", "Numeric"), ("Sluggish", "%", "Numeric"), ("Immotile", "%", "Numeric"),
            ("Normal Forms", "%", "Numeric"), ("Abnormal Forms", "%", "Numeric"),
            ("Pus Cells", "/HPF", "Text"), ("RBCs", "/HPF", "Text"), ("Agglutination", "", "Text"),
        ]),
    ]
    for code, name_en, name_ar, department, sample_type, price, params_list in dynamic_exam_specs:
        existing_exam = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if any_tests and not existing_exam:
            cur = conn.execute(
                "INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, name_en, name_ar, department, sample_type, price),
            )
            def_id = cur.lastrowid
            for pname, unit, rtype in params_list:
                conn.execute(
                    "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
                    "VALUES (?, ?, ?, ?)",
                    (def_id, pname, unit, rtype),
                )
    conn.commit()
'''
# ^ هذا نص توضيحي فقط (مو للتنفيذ المباشر) — انسخ محتوى المتغير
# _SEED_GUE_GSE_SFA (بين علامتي الاقتباس الثلاثية) والصقه كنص كود حقيقي
# (بدون علامات الاقتباس) داخل دالة migrate() مباشرة بعد كتلة COAG.


# ----------------------------------------------------------------------------
# ملاحظة: عمود "note" الجديد بجدول reference_ranges هو "التعليق الطبي" اللي
# يظهر قبل النسبة الطبيعية بالتقرير المطبوع، مثال:
#   Ovulatory phase (11 - 33 ng/mL)
# منطق التركيب هذا موجود جاهز داخل القوالب الثلاثة الجديدة (macro row()
# بكل من urine_exam.html / stool_exam.html / seminal_fluid.html) — ما
# يحتاج أي كود إضافي بـ database.py غير عمود note نفسه.
# ----------------------------------------------------------------------------
