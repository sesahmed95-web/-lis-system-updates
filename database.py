"""
Database layer for the LIS (Laboratory Information System).
Uses SQLite (zero external dependencies) so it runs anywhere Python runs.
"""
import sqlite3
import os
import json
import hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "lis.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_ar TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,               -- admin, reception, technician, supervisor, accountant
    branch_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    specialty TEXT,
    phone TEXT,
    email TEXT,
    commission_percent REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS referral_centers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'Center'
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    gender TEXT,
    age INTEGER,
    age_unit TEXT DEFAULT 'Years',
    phone TEXT,
    email TEXT,
    address TEXT,
    national_id TEXT,
    passport_number TEXT,
    lab_card_number TEXT,
    contact_method TEXT DEFAULT 'None',
    branch_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS test_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    name_ar TEXT,
    department TEXT,
    sample_type TEXT,
    price REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_examining_test INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS test_parameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_definition_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    unit TEXT,
    result_type TEXT DEFAULT 'Numeric',   -- Numeric, Text
    highlight INTEGER DEFAULT 0,          -- 1 = shade this row yellow on printed reports (admin-chosen, not automatic)
    unit2 TEXT,                           -- optional second unit shown alongside the result on printed reports
    unit2_factor REAL,                    -- value2 = value1 * unit2_factor, computed at print time only
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

CREATE TABLE IF NOT EXISTS reference_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_parameter_id INTEGER NOT NULL,
    gender TEXT DEFAULT 'Both',
    age_from INTEGER DEFAULT 0,
    age_from_unit TEXT DEFAULT 'Years',
    age_to INTEGER DEFAULT 120,
    age_to_unit TEXT DEFAULT 'Years',
    low REAL,
    high REAL,
    range_text TEXT,
    FOREIGN KEY (test_parameter_id) REFERENCES test_parameters(id)
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_number INTEGER UNIQUE,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER,
    referral_center_id INTEGER,
    visit_type TEXT DEFAULT 'walk-in',
    fasting TEXT DEFAULT 'Undefined',
    notes TEXT,
    status TEXT DEFAULT 'Open',
    branch_id INTEGER,
    created_by INTEGER,
    created_at TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Open',
    created_at TEXT,
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE TABLE IF NOT EXISTS order_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    test_definition_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Accepted',   -- Accepted, Collected, Accessioned, In-progress, Completed, Verified, Rejected
    barcode TEXT,
    notes TEXT,
    doctor_id INTEGER,
    collected_at TEXT,
    accessioned_at TEXT,
    created_at TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_test_id INTEGER NOT NULL,
    test_parameter_id INTEGER NOT NULL,
    value_numeric REAL,
    value_text TEXT,
    flag TEXT DEFAULT 'Normal',   -- Normal, High, Low, Critical
    entered_by INTEGER,
    entered_at TEXT,
    verified_by INTEGER,
    verified_at TEXT,
    FOREIGN KEY (order_test_id) REFERENCES order_tests(id),
    FOREIGN KEY (test_parameter_id) REFERENCES test_parameters(id)
);

-- Snapshot of a result's PREVIOUS value taken right before it's overwritten,
-- so "تراجع" (undo / restore previous value) has something real to restore
-- from instead of just being a UI promise.
CREATE TABLE IF NOT EXISTS result_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    order_test_id INTEGER NOT NULL,
    test_parameter_id INTEGER NOT NULL,
    prev_value_numeric REAL,
    prev_value_text TEXT,
    prev_flag TEXT,
    changed_by INTEGER,
    changed_at TEXT,
    FOREIGN KEY (result_id) REFERENCES results(id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    total_amount REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    paid_amount REAL DEFAULT 0,
    status TEXT DEFAULT 'Unpaid',
    created_by INTEGER,
    created_at TEXT,
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    amount REAL,
    method TEXT DEFAULT 'Cash',
    user_id INTEGER,
    paid_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    entity TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS removed_order_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    test_definition_id INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    removed_by INTEGER,
    removed_at TEXT,
    restored INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ترخيص البرنامج (صف واحد فقط id=1) — انظر license_manager.py
CREATE TABLE IF NOT EXISTS license_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hardware_id TEXT,
    install_date TEXT,
    status TEXT DEFAULT 'trial',
    license_username TEXT,
    license_expiry TEXT,
    last_ip TEXT,
    last_checked TEXT
);

-- حساب المصمم (صف واحد فقط id=1) — منفصل تماماً عن جدول users العادي
CREATE TABLE IF NOT EXISTS designer_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    username TEXT,
    password_hash TEXT
);

-- سجل بكل أكواد التفعيل التي ولّدها المصمم من هذا الجهاز (توثيق فقط)
CREATE TABLE IF NOT EXISTS license_issue_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id TEXT,
    username TEXT,
    expiry TEXT,
    code TEXT,
    issued_at TEXT
);

CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS package_tests (
    package_id INTEGER NOT NULL,
    test_definition_id INTEGER NOT NULL,
    FOREIGN KEY (package_id) REFERENCES packages(id),
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_parameter_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (test_parameter_id) REFERENCES test_parameters(id)
);

CREATE TABLE IF NOT EXISTS mapcodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_parameter_id INTEGER NOT NULL,
    machine_name TEXT,
    machine_code TEXT,
    send_enabled INTEGER DEFAULT 1,
    receive_enabled INTEGER DEFAULT 1,
    FOREIGN KEY (test_parameter_id) REFERENCES test_parameters(id)
);

CREATE TABLE IF NOT EXISTS quick_add_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_definition_id INTEGER NOT NULL,
    display_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

CREATE TABLE IF NOT EXISTS host_interface_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT,          -- IN, OUT, SYSTEM
    raw_message TEXT,
    parsed_summary TEXT,
    status TEXT,             -- Processed, Unmatched, Error, Started, Empty
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS doctor_test_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL,
    test_definition_id INTEGER NOT NULL,
    price REAL NOT NULL,
    UNIQUE(doctor_id, test_definition_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

CREATE TABLE IF NOT EXISTS patient_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    visit_id INTEGER,
    status TEXT DEFAULT 'Pending',   -- Pending, Contacted, No Answer, Done
    notes TEXT,
    followup_date TEXT,
    created_at TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

-- Admin-designed printable report layouts for tests that don't have one of
-- the built-in hand-coded templates (reports/cbc.html etc). One row per
-- test_definition_id. rows_json holds an ordered list of
-- {"param_name": "...", "label": "..."} objects describing which
-- parameters appear on the printed page and in what order — either typed
-- in by hand or auto-extracted from an uploaded Word (.docx) reference
-- report. The logo/doctors header and the address footer are NEVER stored
-- here: they always come from reports/base_report.html, so every
-- admin-made report automatically carries the lab logo and letterhead.
-- أجور دكتور المختبر الفاحص لكل فحص من الفحوصات المؤهلة (is_examining_test=1)،
-- مثل Blood Film, Retic Count, BMA... يُربط بالاسم (examining_doctor على
-- الزيارة نص وليس مفتاح أجنبي) بدل معرّف الطبيب لأن قائمة هؤلاء الأطباء
-- تُدار كأسماء فقط من Management → Settings.
CREATE TABLE IF NOT EXISTS examining_doctor_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_name TEXT NOT NULL,
    test_definition_id INTEGER NOT NULL,
    rate REAL NOT NULL DEFAULT 0,
    UNIQUE(doctor_name, test_definition_id),
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

-- قائمة (دكتور المختبر الفاحص) الكاملة — تحل محل التخزين القديم كنص JSON
-- بسيط داخل جدول settings. name يبقى هو المفتاح اللي تعتمد عليه بقية
-- الجداول (examining_doctor_rates.doctor_name، visits.examining_doctor)
-- كنص وليس مفتاحاً أجنبياً، فتغيير الاسم هنا لازم ينعكس يدوياً إذا احتجت
-- تطابق أجور/زيارات قديمة. title/degree_ar/degree_en تُطبع بترويسة كل
-- تقرير (راجع get_letterhead_doctors)، وshow_on_letterhead يتحكم هل هذا
-- الدكتور يظهر بالترويسة أصلاً أو هو فقط بقائمة اختيار الفاحص بالزيارات.
CREATE TABLE IF NOT EXISTS examining_doctors_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    title TEXT DEFAULT 'الدكتور',
    degree_ar TEXT,
    degree_en TEXT,
    sort_order INTEGER DEFAULT 0,
    show_on_letterhead INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS report_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_definition_id INTEGER UNIQUE NOT NULL,
    heading TEXT,
    rows_json TEXT,
    source_docx_name TEXT,
    created_by INTEGER,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (test_definition_id) REFERENCES test_definitions(id)
);

-- طابور إرسال النتائج عبر واتساب. صف واحد لكل محاولة إرسال (نتيجة مفردة أو
-- تقرير موحّد لكل نتائج الزيارة). status يبقى 'pending' إذا ما كان في اتصال
-- إنترنت وقت الطلب أو فشلت المحاولة، وتعيد المهمّة الخلفية whatsapp_worker
-- محاولة إرسال أي صف pending كل بضع دقائق تلقائيًا؛ فيه أيضًا زر "إعادة
-- المحاولة" يدوي من صفحة الطابور.
CREATE TABLE IF NOT EXISTS whatsapp_sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    order_test_id INTEGER,           -- NULL يعني تقرير موحّد لكل نتائج الزيارة
    patient_id INTEGER NOT NULL,
    patient_name TEXT,
    phone TEXT NOT NULL,
    label TEXT,                      -- اسم التحليل أو "تقرير موحّد" للعرض بالطابور
    pdf_path TEXT,
    status TEXT DEFAULT 'pending',   -- pending, sent, failed
    error TEXT,
    attempts INTEGER DEFAULT 0,
    requested_by INTEGER,
    created_at TEXT,
    sent_at TEXT,
    FOREIGN KEY (visit_id) REFERENCES visits(id),
    FOREIGN KEY (order_test_id) REFERENCES order_tests(id),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);
"""


def migrate(conn):
    """Add any columns that older installations of this database might be missing,
    so upgrading the program never wipes existing data."""
    needed = {
        "patients": [
            ("email", "TEXT"), ("national_id", "TEXT"), ("passport_number", "TEXT"),
            ("lab_card_number", "TEXT"), ("contact_method", "TEXT DEFAULT 'None'"),
            ("title", "TEXT DEFAULT 'Mr.'"), ("travel_certificate_number", "TEXT"),
            ("age_unit", "TEXT DEFAULT 'Years'"),
        ],
        "doctors": [("email", "TEXT"), ("commission_percent", "REAL DEFAULT 0")],
        # phone: رقم واتساب مدير المختبر المُرسِل (لإرسال كشف الحساب الشهري له)
        "referral_centers": [("phone", "TEXT")],
        "order_tests": [
            ("doctor_id", "INTEGER"), ("collected_at", "TEXT"), ("accessioned_at", "TEXT"),
            ("price", "REAL"),
        ],
        "invoices": [("is_locked", "INTEGER DEFAULT 0"), ("extra_charges", "REAL DEFAULT 0")],
        "visits": [("examining_doctor", "TEXT"), ("expenses", "REAL DEFAULT 0"),
                    ("examining_doctor_fee", "REAL DEFAULT 0"), ("attending_doctor", "TEXT")],
        "test_definitions": [("is_examining_test", "INTEGER DEFAULT 0"),
                               # report_group: اسم "الريبورت المجمّع" اللي ينتمي له هذا
                               # التحليل (مثلاً "Thyroid function test" أو "Viral study")،
                               # مستقل تماماً عن حقل department. يُستخدم فقط بلوحة الطباعة
                               # المجمّعة (print_combined_panel) لتجميع التحاليل تحت عنوان
                               # فرعي محدد بدل الاعتماد على القسم العام. فاضي = يرجع
                               # للسلوك القديم (تجميع حسب department كالمعتاد).
                               ("report_group", "TEXT")],
        "reference_ranges": [("age_from_unit", "TEXT DEFAULT 'Years'"), ("age_to_unit", "TEXT DEFAULT 'Years'")],
        # unit2 / unit2_factor: وحدة ثانية اختيارية تُعرض تلقائيًا جنب النتيجة
        # الأصلية وقت الطباعة (مثلاً mg/dL بالإضافة لـ mmol/L). القيمة الثانية
        # تُحسب دائمًا = القيمة الأصلية × unit2_factor، ولا تُخزَّن بجدول
        # results أبدًا — تُحسب لحظة الطباعة فقط. فاضي = بدون وحدة ثانية
        # (السلوك القديم كما هو).
        "test_parameters": [("highlight", "INTEGER DEFAULT 0"), ("unit2", "TEXT"), ("unit2_factor", "REAL")],
        # is_trial: يميّز الترخيص التجريبي عن ترخيص العميل العادي (بالأيام)،
        # حتى يظهر شريط "متبقي كم يوم" فقط للتجريبي وليس لكل ترخيص له تاريخ انتهاء.
        # revoked_reason: سبب الإلغاء عن بُعد (يُعبّى تلقائياً لو المصمم ألغى
        # ترخيص هذا الجهاز عن بُعد عبر قائمة الإلغاء بمستودع GitHub — راجع
        # auto_updater.check_revocation و license_manager.mark_revoked).
        # is_trial: يميّز الترخيص التجريبي عن ترخيص العميل العادي (بالأيام)،
        # حتى يظهر شريط "متبقي كم يوم" فقط للتجريبي وليس لكل ترخيص له تاريخ انتهاء.
        # revoked_reason: سبب الإلغاء عن بُعد (يُعبّى تلقائياً لو المصمم ألغى
        # ترخيص هذا الجهاز عن بُعد عبر قائمة الإلغاء بمستودع GitHub — راجع
        # auto_updater.check_revocation و license_manager.mark_revoked).
        "license_info": [("is_trial", "INTEGER DEFAULT 0"), ("revoked_reason", "TEXT")],
        # heading_align / rows_align: يتحكم بها المستخدم من صفحة "مصمم
        # التقارير" — توسيط/يمين/يسار لعنوان التقرير المخصَّص ولعمود اسم
        # الفحص وقيمة النتيجة بجدول الفحوصات (custom.html فقط، التقارير
        # الجاهزة CBC/التخثر... إلخ لها تصميم ثابت منفصل).
        "report_templates": [("heading_align", "TEXT DEFAULT 'center'"), ("rows_align", "TEXT DEFAULT 'right'")],
    }
    for table, columns in needed.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    conn.commit()

    # ترحيل قائمة (دكتور المختبر الفاحص) من التخزين القديم (نص JSON بسيط
    # داخل جدول settings) إلى جدول examining_doctors_list الجديد — مرة وحدة
    # فقط (لو الجدول الجديد فاضي أصلاً)، حتى لا تضيع أسماء محفوظة سابقًا عند
    # الترقية. الشهادات (degree_ar/degree_en) تبقى فاضية بعد الترحيل — يعبّيها
    # المدير يدويًا من الشاشة الجديدة، لأن التخزين القديم أصلاً ما كان فيه
    # هذا الحقل إطلاقًا.
    already_migrated = conn.execute("SELECT COUNT(*) as c FROM examining_doctors_list").fetchone()["c"]
    if not already_migrated:
        legacy_names = []
        legacy_row = conn.execute("SELECT value FROM settings WHERE key='examining_doctors'").fetchone()
        if legacy_row and legacy_row["value"]:
            try:
                parsed = json.loads(legacy_row["value"])
                if isinstance(parsed, list):
                    legacy_names = [str(n).strip() for n in parsed if str(n).strip()]
            except (ValueError, TypeError):
                pass
        if not legacy_names:
            legacy_names = list(DEFAULT_EXAMINING_DOCTORS)
        for i, n in enumerate(legacy_names):
            conn.execute(
                "INSERT INTO examining_doctors_list (name, title, sort_order, show_on_letterhead) "
                "VALUES (?, 'الدكتور', ?, 1)",
                (n, i),
            )
        conn.commit()

    # Backfill: any order_tests row created before the "price" column existed
    # gets the test's current default price locked in, so nothing breaks.
    conn.execute(
        "UPDATE order_tests SET price = ("
        " SELECT price FROM test_definitions WHERE id = order_tests.test_definition_id"
        ") WHERE price IS NULL"
    )
    conn.commit()

    # المختبرات الي ترسل نماذج تحاليل لهذا المختبر (بدل اسم الدكتور المرسل) —
    # تُدرج مرة وحدة إذا مو موجودة أصلاً (بالاسم، بدون حساسية لحالة الأحرف)
    # حتى ما تنكرر لو migrate() انشغلت أكثر من مرة أو بقاعدة بيانات قديمة.
    default_referral_labs = ["مختبر القمة", "مختبر المنار", "مختبر ابو زينه", "مختبر مريم", "مختبر الامتياز"]
    existing_labs = {
        (row["name"] or "").strip().lower()
        for row in conn.execute("SELECT name FROM referral_centers").fetchall()
    }
    for lab_name in default_referral_labs:
        if lab_name.strip().lower() not in existing_labs:
            conn.execute("INSERT INTO referral_centers (name, type) VALUES (?, 'Lab')", (lab_name,))
    conn.commit()

    # Coagulation Tests was added after some installations were already
    # created, so it needs to be inserted into existing databases too
    # (fresh installs already get it from the catalog in seed(), which runs
    # right after this — skip here if the whole catalog is still empty).
    any_tests = conn.execute("SELECT id FROM test_definitions LIMIT 1").fetchone()
    existing_coag = conn.execute("SELECT id FROM test_definitions WHERE code='COAG'").fetchone()
    if any_tests and not existing_coag:
        cur = conn.execute(
            "INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("COAG", "Coagulation Tests", "فحوصات التخثر", "Coagulation", "Citrate", 12000),
        )
        coag_id = cur.lastrowid
        coag_params = [
            ("PT", "Sec.", "Numeric", 11, 15, None),
            ("PT Control", "Sec.", "Numeric", None, None, None),
            ("INR", "", "Numeric", 0.9, 1.26, None),
            ("PTT", "Sec.", "Numeric", 27, 40, None),
            ("PTT Control", "Sec.", "Numeric", None, None, None),
            ("Bleeding time", "Minute", "Numeric", 2, 5, None),
            ("Plasma fibrinogen con", "g/L", "Numeric", 2, 4, None),
            ("D. dimer", "µg/L", "Numeric", None, 500, None),
        ]
        for pname, unit, rtype, low, high, range_text in coag_params:
            pcur = conn.execute(
                "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
                "VALUES (?, ?, ?, ?)",
                (coag_id, pname, unit, rtype),
            )
            conn.execute(
                "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_to, low, high, range_text) "
                "VALUES (?, 'Both', 0, 120, ?, ?, ?)",
                (pcur.lastrowid, low, high, range_text),
            )
        conn.commit()

    # الشعار (logo_path) صار يُضاف افتراضيًا للتنصيبات الجديدة فقط عبر seed()،
    # فأي قاعدة بيانات موجودة من قبل هذا التحديث ما عندها هذا الإعداد إطلاقًا
    # — لهذا ما كان يظهر شعار المختبر بشاشة تسجيل الدخول رغم وجود صورة
    # الشعار فعليًا بمجلد static/uploads. نضيفه هنا فقط إذا كان غير موجود
    # (INSERT OR IGNORE) حتى لا نطغى على شعار رفعه الأدمن بنفسه، ولا يتعارض
    # مع seed() لو كانت هذي قاعدة بيانات جديدة تمامًا (migrate يشتغل قبلها).
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('logo_path', 'uploads/logo.png')")
    conn.commit()


# الفحوصات التي يظهر معها اسم "دكتور المختبر الفاحص" ويُحسب له أجر عنها —
# إذا كان الفحص موجود أصلاً بالكتالوج (بالكود) تُعلَّم فقط، وإذا كان جديدًا
# يُضاف تلقائيًا (سعر ابتدائي 0 يحدده المدير لاحقًا من كتالوج الفحوصات).
EXAMINING_TEST_DEFS = [
    ("BF", "Blood Film", "فحص لطاخة الدم", "Hematology", "Blood-EDTA"),
    ("RETIC", "Retic Count", "عد الخلايا الشبكية", "Hematology", "Blood-EDTA"),
    ("BFRETIC", "Blood Film and Retic Count", "لطاخة الدم + عد الخلايا الشبكية", "Hematology", "Blood-EDTA"),
    ("FLUIDEXAM", "Fluid examination", "فحص السوائل", "Hematology", "Fluid"),
    ("HBPREP", "Hb Preparation", "تحضير الهيموغلوبين", "Hematology", "Blood-EDTA"),
    ("SICKLE", "Sickling Test", "فحص المنجلية", "Hematology", "Blood-EDTA"),
    ("BMA", "BMA", "شفط نقي العظم", "Hematology", "Bone Marrow"),
    ("BMBIOPSY", "BM Biopsy", "خزعة نقي العظم", "Hematology", "Bone Marrow"),
]


def ensure_examining_tests(conn):
    """يضمن وجود كل الفحوصات المؤهلة لأجر (دكتور المختبر الفاحص) بالكتالوج،
    ويعلّمها is_examining_test=1. يُستدعى بكل إقلاع حتى تُضاف تلقائيًا على
    قواعد بيانات قديمة كانت موجودة قبل هذه الميزة، بدون تكرار ولا فقدان بيانات."""
    for code, name, name_ar, dept, sample_type in EXAMINING_TEST_DEFS:
        row = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if row:
            conn.execute("UPDATE test_definitions SET is_examining_test=1 WHERE id=?", (row["id"],))
        else:
            conn.execute(
                "INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price, "
                "is_active, is_examining_test) VALUES (?, ?, ?, ?, ?, 0, 1, 1)",
                (code, name, name_ar, dept, sample_type),
            )
    conn.commit()


def ensure_bfretic_parameters(conn):
    """BFRETIC ('Blood Film and Retic Count') was added to the test catalog
    without ever being given test_parameters — its results-entry page shows
    a totally empty table (nothing to type, nothing to save, nothing reaches
    the printed report) because of this. Backfills the exact same parameter
    set already used by the plain BF test. Runs on every startup but checks
    first, so it's a no-op (and never duplicates rows) once already fixed."""
    row = conn.execute("SELECT id FROM test_definitions WHERE code='BFRETIC'").fetchone()
    if not row:
        return
    test_id = row["id"]
    has_params = conn.execute(
        "SELECT COUNT(*) as c FROM test_parameters WHERE test_definition_id=?", (test_id,)
    ).fetchone()["c"]
    if has_params:
        return
    params = [
        ("Neutrophils", "%", "Numeric", None, None, None),
        ("Band", "%", "Numeric", None, None, None),
        ("Lymphocytes", "%", "Numeric", None, None, None),
        ("Metamyelocytes", "%", "Numeric", None, None, None),
        ("Monocytes", "%", "Numeric", None, None, None),
        ("Myelocytes", "%", "Numeric", None, None, None),
        ("Eosinophils", "%", "Numeric", None, None, None),
        ("Promyelocytes", "%", "Numeric", None, None, None),
        ("Atypical lymphocytes", "%", "Numeric", None, None, None),
        ("Reactive lymphocytes", "%", "Numeric", None, None, None),
        ("NRBC", "100/wbc", "Numeric", None, None, None),
        ("Basophils", "%", "Numeric", None, None, None),
        ("Blast", "%", "Numeric", None, None, None),
        ("RBC_desc", "", "Text", None, None, None),
        ("WBC_desc", "", "Text", None, None, None),
        ("Platelets_desc", "", "Text", None, None, None),
        ("Conclusion", "", "Text", None, None, None),
        ("Reticulocyte count", "%", "Numeric", None, None, None),
        ("Corrected Retic count", "%", "Numeric", None, None, None),
    ]
    for name, unit, result_type, low, high, range_text in params:
        conn.execute(
            "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, ?, ?, ?)",
            (test_id, name, unit, result_type),
        )
        param_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        if low is not None or high is not None or range_text is not None:
            conn.execute(
                "INSERT INTO reference_ranges (test_parameter_id, low, high, range_text) VALUES (?, ?, ?, ?)",
                (param_id, low, high, range_text),
            )
    conn.commit()


def ensure_nrbc_parameter(conn):
    """NRBC is a newly-added field for Blood Film / Blood Film and Retic Count
    / WBCs differential (unit '100/wbc'), inserted right after Promyelocytes.
    Existing databases already have BF/BFRETIC/WBCDIFF test_parameters seeded
    from before this field existed, so ensure_bfretic_parameters' has_params
    check would skip them — this backfills NRBC specifically wherever it's
    still missing, without duplicating it if already present. Runs on every
    startup; no-op once already applied."""
    for code in ("BF", "BFRETIC", "WBCDIFF"):
        row = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if not row:
            continue
        test_id = row["id"]
        exists = conn.execute(
            "SELECT id FROM test_parameters WHERE test_definition_id=? AND name='NRBC'", (test_id,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, 'NRBC', '100/wbc', 'Numeric')",
            (test_id,),
        )
    conn.commit()


def ensure_atypical_lymphocytes_parameter(conn):
    """Same backfill pattern as ensure_nrbc_parameter, for the 'Atypical
    lymphocytes' field added later to Blood Film / Blood Film and Retic
    Count / WBCs differential (unit '%'). Runs on every startup; no-op once
    already applied."""
    for code in ("BF", "BFRETIC", "WBCDIFF"):
        row = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if not row:
            continue
        test_id = row["id"]
        exists = conn.execute(
            "SELECT id FROM test_parameters WHERE test_definition_id=? AND name='Atypical lymphocytes'", (test_id,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, 'Atypical lymphocytes', '%', 'Numeric')",
            (test_id,),
        )
    conn.commit()


def ensure_reactive_lymphocytes_parameter(conn):
    """Same backfill pattern as ensure_nrbc_parameter, for the 'Reactive
    lymphocytes' field added later to Blood Film / Blood Film and Retic
    Count / WBCs differential (unit '%'). Runs on every startup; no-op once
    already applied."""
    for code in ("BF", "BFRETIC", "WBCDIFF"):
        row = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if not row:
            continue
        test_id = row["id"]
        exists = conn.execute(
            "SELECT id FROM test_parameters WHERE test_definition_id=? AND name='Reactive lymphocytes'", (test_id,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, 'Reactive lymphocytes', '%', 'Numeric')",
            (test_id,),
        )
    conn.commit()


def ensure_cbc_comment_parameter(conn):
    """Optional free-text 'Comment' field for the CBC report — lets the
    examining doctor add a short note about the CBC on the printed report
    when needed; left blank it prints nothing. Same backfill pattern as
    ensure_nrbc_parameter, for existing databases that seeded CBC before
    this field existed. Runs on every startup; no-op once already applied."""
    row = conn.execute("SELECT id FROM test_definitions WHERE code='CBC'").fetchone()
    if not row:
        return
    test_id = row["id"]
    exists = conn.execute(
        "SELECT id FROM test_parameters WHERE test_definition_id=? AND name='Comment'", (test_id,)
    ).fetchone()
    if exists:
        return
    conn.execute(
        "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, 'Comment', '', 'Text')",
        (test_id,),
    )
    conn.commit()


def ensure_coag_parameters(conn):
    """Bleeding time / Plasma fibrinogen con / D. dimer / PTT Control were
    added to the Coagulation Tests (COAG) param list after some
    installations already had COAG seeded with only PT/PT Control/INR/PTT —
    the migrate() insert-COAG-if-missing block only ever runs once (skipped
    entirely if COAG already exists), so those older installs never got the
    newer params and their result-entry screen has no row to type a value
    into for them at all. Same backfill pattern as ensure_nrbc_parameter:
    inserts by name only whatever's still missing under the existing COAG
    test, with its reference range (or none, for the two Control fields
    that never had one). Runs on every startup; no-op once already applied."""
    row = conn.execute("SELECT id FROM test_definitions WHERE code='COAG'").fetchone()
    if not row:
        return
    test_id = row["id"]
    coag_params = [
        ("PT", "Sec.", "Numeric", 11, 15, None),
        ("PT Control", "Sec.", "Numeric", None, None, None),
        ("INR", "", "Numeric", 0.9, 1.26, None),
        ("PTT", "Sec.", "Numeric", 27, 40, None),
        ("PTT Control", "Sec.", "Numeric", None, None, None),
        ("Bleeding time", "Minute", "Numeric", 2, 5, None),
        ("Plasma fibrinogen con", "g/L", "Numeric", 2, 4, None),
        ("D. dimer", "µg/L", "Numeric", None, 500, None),
    ]
    changed = False
    for pname, unit, rtype, low, high, range_text in coag_params:
        exists = conn.execute(
            "SELECT id FROM test_parameters WHERE test_definition_id=? AND name=?", (test_id, pname)
        ).fetchone()
        if exists:
            continue
        pcur = conn.execute(
            "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, ?, ?, ?)",
            (test_id, pname, unit, rtype),
        )
        if low is not None or high is not None:
            conn.execute(
                "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_to, low, high, range_text) "
                "VALUES (?, 'Both', 0, 120, ?, ?, ?)",
                (pcur.lastrowid, low, high, range_text),
            )
        changed = True
    if changed:
        conn.commit()


# Age brackets for reference ranges (and patient age) can each be entered in
# a different unit — Days/Weeks/Months/Years — since normal values for the
# same parameter differ hugely between, say, a 3-day-old newborn and a
# 30-year-old adult, and pediatric/neonatal ranges are normally published in
# days/weeks/months rather than whole years.
AGE_UNIT_DAYS = {"Hours": 1 / 24, "Days": 1, "Weeks": 7, "Months": 30, "Years": 365}


def age_to_days(value, unit):
    """Converts an age value in the given unit to an approximate number of
    days, so ages in different units can be compared on one scale. Months
    and years use 30/365-day approximations — precise enough to place a
    patient inside the right reference-range bracket; not meant for exact
    calendar arithmetic. Returns None if value is missing/invalid."""
    if value is None or value == "":
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value * AGE_UNIT_DAYS.get(unit or "Years", 365)


def find_reference_range(conn, test_parameter_id, gender, age, age_unit):
    """Picks the ONE reference-range row that actually applies to this
    patient, out of every row defined for this parameter — matching both
    gender and age bracket (each row's age_from/age_to can each be in a
    different unit). Falls back gracefully so older setups that only ever
    had one blanket range per parameter keep working exactly as before:
      1. no rows at all -> None
      2. patient age unknown -> ignore age, match on gender only
      3. no row matches this patient's age -> ignore age, fall back to
         matching on gender only across all rows (better than showing no
         range at all)
      4. among whatever's left, a row naming this patient's exact gender
         wins over a generic 'Both' row.
    """
    rows = conn.execute(
        "SELECT * FROM reference_ranges WHERE test_parameter_id=?", (test_parameter_id,)
    ).fetchall()
    if not rows:
        return None

    age_days = age_to_days(age, age_unit)

    def matches_age(row):
        if age_days is None:
            return True
        lo = age_to_days(row["age_from"], row["age_from_unit"])
        hi = age_to_days(row["age_to"], row["age_to_unit"])
        if lo is None:
            lo = 0
        if hi is None:
            hi = float("inf")
        return lo <= age_days <= hi

    candidates = [r for r in rows if matches_age(r)]
    if not candidates:
        candidates = rows

    def gender_ok(row):
        return not row["gender"] or row["gender"] == "Both" or row["gender"] == gender

    exact_gender = [r for r in candidates if r["gender"] and r["gender"] != "Both" and r["gender"] == gender]
    if exact_gender:
        return exact_gender[0]
    both_or_blank = [r for r in candidates if gender_ok(r)]
    if both_or_blank:
        return both_or_blank[0]
    return candidates[0]


def get_test_price(db, test_definition_id, doctor_id=None):
    """Price to charge for a test: the doctor's own rate if one is set for
    that doctor+test, otherwise the lab's default price."""
    if doctor_id:
        row = db.execute(
            "SELECT price FROM doctor_test_prices WHERE doctor_id=? AND test_definition_id=?",
            (doctor_id, test_definition_id),
        ).fetchone()
        if row is not None:
            return row["price"]
    row = db.execute("SELECT price FROM test_definitions WHERE id=?", (test_definition_id,)).fetchone()
    return row["price"] if row else 0.0


def find_or_create_doctor(db, name):
    """Look up a referring doctor by name (case-insensitive); create one
    automatically if this is the first time we see that name, so reception
    never has to pre-register a doctor before using them."""
    name = (name or "").strip()
    if not name:
        return None
    row = db.execute(
        "SELECT id FROM doctors WHERE LOWER(TRIM(full_name)) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        return row["id"]
    cur = db.execute(
        "INSERT INTO doctors (full_name, specialty, phone, email, commission_percent) "
        "VALUES (?, '', '', '', 0)",
        (name,),
    )
    db.commit()
    return cur.lastrowid


def find_or_create_referral_center(db, name):
    """Look up a referring lab (referral_centers, type='Lab') by name
    (case-insensitive); create one automatically if this is the first time
    we see that name, so reception can type a brand-new lab's name directly
    on the New Visit page instead of having to pre-register it first from
    Management → Referral Labs. Same pattern as find_or_create_doctor."""
    name = (name or "").strip()
    if not name:
        return None
    row = db.execute(
        "SELECT id FROM referral_centers WHERE LOWER(TRIM(name)) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        return row["id"]
    cur = db.execute(
        "INSERT INTO referral_centers (name, type, phone) VALUES (?, 'Lab', NULL)",
        (name,),
    )
    db.commit()
    return cur.lastrowid


def init_db():
    fresh = not os.path.exists(DB_PATH)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    migrate(conn)
    if fresh:
        seed(conn)
    ensure_examining_tests(conn)
    ensure_bfretic_parameters(conn)
    ensure_nrbc_parameter(conn)
    ensure_atypical_lymphocytes_parameter(conn)
    ensure_reactive_lymphocytes_parameter(conn)
    ensure_cbc_comment_parameter(conn)
    ensure_coag_parameters(conn)
    conn.close()


def seed(conn):
    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("INSERT INTO branches (name, name_ar) VALUES (?, ?)",
                 ("Hematologist Lab", "مختبر أمراض الدم التخصصي"))
    branch_id = conn.execute("SELECT id FROM branches LIMIT 1").fetchone()["id"]

    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                 ("app_name", "Dr. Laith Salman Hematologist Lab"))
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                 ("app_name_ar", "مختبر أمراض الدم التخصصي - د. ليث سلمان"))
    # logo_path يُضاف الآن من migrate() (يشتغل قبل seed هنا وأيضًا على كل
    # قاعدة بيانات قديمة) — لا داعي لتكراره هنا.

    users = [
        ("admin", "admin123", "System Administrator", "admin"),
        ("rec", "rec123", "Reception Desk", "reception"),
        ("tech", "tech123", "Lab Technician", "technician"),
        ("super", "super123", "Lab Supervisor", "supervisor"),
        ("acc", "acc123", "Accountant", "accountant"),
    ]
    for username, pwd, name, role in users:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, branch_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, hash_password(pwd), name, role, branch_id, now),
        )

    # حساب المصمم الافتراضي — يُنشأ تلقائياً عند أول تشغيل للبرنامج على أي
    # جهاز جديد (قاعدة بيانات فارغة)، بنفس اسم المستخدم/كلمة المرور في كل
    # نسخة تُسلَّم لأي عميل، حتى لا يحتاج المصمم لفتح /designer/setup يدوياً
    # في كل مرة.
    conn.execute(
        "INSERT INTO designer_account (id, username, password_hash) VALUES (1, ?, ?)",
        ("1983209", hash_password("احمد ابو حوراء")),
    )

    conn.execute("INSERT INTO doctors (full_name, specialty, phone) VALUES (?, ?, ?)",
                 ("Dr. Ahmed Kareem", "Internal Medicine", "+9647700000001"))
    conn.execute("INSERT INTO referral_centers (name, type) VALUES (?, ?)",
                 ("Walk-in", "Center"))

    # Test catalog: (code, name, name_ar, department, sample_type, price, [(param, unit, result_type, low, high, range_text)])
    catalog = [
        ("TSH", "TSH", "الغدة الدرقية المحفزة", "Hormones", "Serum", 15000,
         [("TSH", "uIU/mL", "Numeric", 0.4, 4.0, None)]),
        ("FT4", "T4", "الثيروكسين", "Hormones", "Serum", 15000,
         [("T4", "ng/dL", "Numeric", 0.8, 1.8, None)]),
        ("FT3", "T3", "ثلاثي يودوثيرونين", "Hormones", "Serum", 15000,
         [("T3", "pg/mL", "Numeric", 2.3, 4.2, None)]),
        ("CBC", "CBC", "تعداد دم شامل", "Hematology", "Blood-EDTA", 10000,
         [("WBCs", "X10^9/L", "Numeric", 4.0, 10.0, None),
          ("Ly", "%", "Numeric", 20, 40, None),
          ("MO", "%", "Numeric", 2.0, 10.0, None),
          ("NE", "%", "Numeric", 40, 80, None),
          ("EO", "%", "Numeric", 1.0, 6.0, None),
          ("BA", "%", "Numeric", 0.0, 2.0, None),
          ("LY#", "X10^9/uL", "Numeric", 1.0, 3.0, None),
          ("MO#", "X10^9/uL", "Numeric", 0.2, 1.0, None),
          ("NE#", "X10^9/uL", "Numeric", 2.0, 7.0, None),
          ("EO#", "X10^9/uL", "Numeric", 0.02, 0.5, None),
          ("BA#", "X10^9/uL", "Numeric", 0.01, 0.02, None),
          ("RBC", "X10^12/uL", "Numeric", 4.5, 5.5, None),
          ("HGB", "g/dl", "Numeric", 13.0, 17.0, None),
          ("HCT", "%", "Numeric", 40.0, 50.0, None),
          ("MCV", "fL", "Numeric", 83.0, 101, None),
          ("MCH", "pg", "Numeric", 27.0, 32.0, None),
          ("MCHC", "g/dL", "Numeric", 31.5, 34.5, None),
          ("RDW", "%", "Numeric", 11.6, 14.0, None),
          ("RDW-SD", "fL", "Numeric", 39.0, 46, None),
          ("PLT", "X10^9/uL", "Numeric", 150, 400, None),
          ("MPV", "fL", "Numeric", 7.0, 10.0, None),
          ("Comment", "", "Text", None, None, None)]),
        ("BF", "Blood Film", "فحص لطاخة الدم", "Hematology", "Blood-EDTA", 8000,
         [("Neutrophils", "%", "Numeric", None, None, None),
          ("Band", "%", "Numeric", None, None, None),
          ("Lymphocytes", "%", "Numeric", None, None, None),
          ("Metamyelocytes", "%", "Numeric", None, None, None),
          ("Monocytes", "%", "Numeric", None, None, None),
          ("Myelocytes", "%", "Numeric", None, None, None),
          ("Eosinophils", "%", "Numeric", None, None, None),
          ("Promyelocytes", "%", "Numeric", None, None, None),
          ("Atypical lymphocytes", "%", "Numeric", None, None, None),
          ("Reactive lymphocytes", "%", "Numeric", None, None, None),
          ("NRBC", "100/wbc", "Numeric", None, None, None),
          ("Basophils", "%", "Numeric", None, None, None),
          ("Blast", "%", "Numeric", None, None, None),
          ("RBC_desc", "", "Text", None, None, None),
          ("WBC_desc", "", "Text", None, None, None),
          ("Platelets_desc", "", "Text", None, None, None),
          ("Conclusion", "", "Text", None, None, None),
          ("Reticulocyte count", "%", "Numeric", None, None, None),
          ("Corrected Retic count", "%", "Numeric", None, None, None)]),
        ("COAG", "Coagulation Tests", "فحوصات التخثر", "Coagulation", "Citrate", 12000,
         [("PT", "Sec.", "Numeric", 11, 15, None),
          ("PT Control", "Sec.", "Numeric", None, None, None),
          ("INR", "", "Numeric", 0.9, 1.26, None),
          ("PTT", "Sec.", "Numeric", 27, 40, None),
          ("PTT Control", "Sec.", "Numeric", None, None, None),
          ("Bleeding time", "Minute", "Numeric", 2, 5, None),
          ("Plasma fibrinogen con", "g/L", "Numeric", 2, 4, None),
          ("D. dimer", "µg/L", "Numeric", None, 500, None)]),
        ("WBCDIFF", "WBCs differential", "التعداد التفريقي لكريات الدم البيضاء", "Hematology", "Blood-EDTA", 6000,
         [("Neutrophils", "%", "Numeric", None, None, None),
          ("Band", "%", "Numeric", None, None, None),
          ("Lymphocytes", "%", "Numeric", None, None, None),
          ("Metamyelocytes", "%", "Numeric", None, None, None),
          ("Monocytes", "%", "Numeric", None, None, None),
          ("Myelocytes", "%", "Numeric", None, None, None),
          ("Eosinophils", "%", "Numeric", None, None, None),
          ("Promyelocytes", "%", "Numeric", None, None, None),
          ("Atypical lymphocytes", "%", "Numeric", None, None, None),
          ("Reactive lymphocytes", "%", "Numeric", None, None, None),
          ("NRBC", "100/wbc", "Numeric", None, None, None),
          ("Basophils", "%", "Numeric", None, None, None),
          ("Blast", "%", "Numeric", None, None, None)]),
        ("FLUIDEXAM", "Fluid examination", "فحص السوائل", "Hematology", "Fluid", 7000,
         [("Specimen", "", "Text", None, None, None),
          ("Appearance", "", "Text", None, None, None),
          ("RBCs", "", "Text", None, None, None),
          ("WBC count", "", "Text", None, None, None),
          ("Neutrophils", "%", "Numeric", None, None, None),
          ("Lymphocytes", "%", "Numeric", None, None, None),
          ("Monocytes", "%", "Numeric", None, None, None),
          ("Eosinophils", "%", "Numeric", None, None, None),
          ("Basophils", "%", "Numeric", None, None, None),
          ("Others", "", "Text", None, None, None),
          ("Conclusion", "", "Text", None, None, None)]),
        ("FBS", "FBS", "سكر صائم", "BioChemistry", "Serum", 5000,
         [("FBS", "mg/dL", "Numeric", 70, 100, None)]),
        ("VITD3", "Vitamin D3 Total", "فيتامين د3", "Hormones", "Serum", 25000,
         [("Vitamin D3", "ng/mL", "Numeric", 30, 100, None)]),
        ("HIV", "HIV Ab screen", "فحص الايدز", "Viral Screen", "Serum", 8000,
         [("HIV Ab", "", "Text", None, None, "Non-Reactive")]),
        ("HBSAG", "HBs-Ag", "التهاب الكبد B", "Viral Screen", "Serum", 8000,
         [("HBs-Ag", "", "Text", None, None, "Negative")]),
        ("HCV", "HCV Ab Screen", "التهاب الكبد C", "Viral Screen", "Serum", 8000,
         [("HCV Ab", "", "Text", None, None, "Negative")]),
        ("LIPID", "Lipid Profile", "دهون الدم", "BioChemistry", "Serum", 15000,
         [("Cholesterol", "mg/dL", "Numeric", 0, 200, None),
          ("Triglycerides", "mg/dL", "Numeric", 0, 150, None),
          ("HDL", "mg/dL", "Numeric", 40, 60, None),
          ("LDL", "mg/dL", "Numeric", 0, 100, None)]),
        ("A1C", "A1c", "السكر التراكمي", "BioChemistry", "Blood-EDTA", 12000,
         [("A1c", "%", "Numeric", 4.0, 5.7, None)]),
    ]

    test_id_map = {}
    for code, name, name_ar, dept, sample_type, price, params in catalog:
        cur = conn.execute(
            "INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (code, name, name_ar, dept, sample_type, price),
        )
        test_id = cur.lastrowid
        test_id_map[code] = test_id
        for pname, unit, rtype, low, high, range_text in params:
            pcur = conn.execute(
                "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
                "VALUES (?, ?, ?, ?)",
                (test_id, pname, unit, rtype),
            )
            param_id = pcur.lastrowid
            conn.execute(
                "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_to, low, high, range_text) "
                "VALUES (?, 'Both', 0, 120, ?, ?, ?)",
                (param_id, low, high, range_text),
            )

    viral_ids = [tid for code, tid in test_id_map.items() if code in ("HIV", "HBSAG", "HCV")]
    if viral_ids:
        pkg_cur = conn.execute("INSERT INTO packages (name, code, notes) VALUES (?, ?, ?)",
                                ("Viral Screen Package", "VIRAL-PKG", "HIV + HBsAg + HCV"))
        pkg_id = pkg_cur.lastrowid
        for tid in viral_ids:
            conn.execute("INSERT INTO package_tests (package_id, test_definition_id) VALUES (?, ?)",
                         (pkg_id, tid))

    for code, sample_values in (("HIV", ["Non-Reactive", "Reactive"]),
                                 ("HBSAG", ["Negative", "Positive"]),
                                 ("HCV", ["Negative", "Positive"])):
        tid = test_id_map.get(code)
        if not tid:
            continue
        param = conn.execute("SELECT id FROM test_parameters WHERE test_definition_id=? LIMIT 1", (tid,)).fetchone()
        if param:
            for val in sample_values:
                conn.execute("INSERT INTO suggestions (test_parameter_id, content) VALUES (?, ?)",
                             (param["id"], val))

    conn.commit()


def get_report_template(db, test_definition_id):
    return db.execute(
        "SELECT * FROM report_templates WHERE test_definition_id=?", (test_definition_id,)
    ).fetchone()


def save_report_template(db, test_definition_id, heading, rows_json, source_docx_name, user_id,
                          heading_align=None, rows_align=None):
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_report_template(db, test_definition_id)
    heading_align = heading_align or "center"
    rows_align = rows_align or "right"
    if existing:
        db.execute(
            "UPDATE report_templates SET heading=?, rows_json=?, source_docx_name=COALESCE(?, source_docx_name), "
            "heading_align=?, rows_align=?, updated_at=? WHERE test_definition_id=?",
            (heading, rows_json, source_docx_name, heading_align, rows_align, now, test_definition_id),
        )
    else:
        db.execute(
            "INSERT INTO report_templates (test_definition_id, heading, rows_json, source_docx_name, "
            "heading_align, rows_align, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (test_definition_id, heading, rows_json, source_docx_name, heading_align, rows_align, user_id, now, now),
        )
    db.commit()


def get_setting(db, key, default=""):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(db, key, value):
    existing = db.execute("SELECT key FROM settings WHERE key=?", (key,)).fetchone()
    if existing:
        db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    else:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))


DEFAULT_EXAMINING_DOCTORS = ["د.خليل حمود", "د.هدى نصيف", "د.اسراء عبد الاقر"]


def get_examining_doctors_full(db):
    """كل دكاترة الفحص بكل تفاصيلهم (اسم/لقب/شهادة عربي/شهادة انكليزي/ترتيب/
    هل يظهر بترويسة التقرير) مرتبين حسب الترتيب اليدوي (sort_order)."""
    return db.execute(
        "SELECT * FROM examining_doctors_list ORDER BY sort_order, id"
    ).fetchall()


def get_examining_doctors(db):
    """قائمة (دكتور المختبر الفاحص) — أسماء فقط، بنفس التوقيع القديم، لقوائم
    الاختيار السريع بشاشات الزيارات والفواتير. مصدرها الآن جدول
    examining_doctors_list (مرتبة sort_order)؛ إذا كان فاضي تمامًا (حالة
    نادرة) ترجع القائمة الافتراضية القديمة بدل قائمة فاضية."""
    rows = get_examining_doctors_full(db)
    if rows:
        return [r["name"] for r in rows]
    return list(DEFAULT_EXAMINING_DOCTORS)


def get_letterhead_doctors(db):
    """فقط الدكاترة اللي يُفعَّل لهم عرض بترويسة التقرير المطبوع، مرتبين
    حسب الترتيب اليدوي — تُستخدم بـ inject_globals لحقن letterhead_doctors
    بكل قوالب reports/* تلقائيًا."""
    return db.execute(
        "SELECT * FROM examining_doctors_list WHERE show_on_letterhead=1 ORDER BY sort_order, id"
    ).fetchall()


def set_examining_doctors(db, names):
    """يستبدل القائمة كاملة بأسماء فقط (يبقى موجود للتوافق القديم فقط).
    يحافظ على شهادة/لقب/ظهور بالترويسة لأي اسم موجود مسبقًا بنفس الحروف."""
    existing = {r["name"]: r for r in get_examining_doctors_full(db)}
    db.execute("DELETE FROM examining_doctors_list")
    cleaned = list(dict.fromkeys(n.strip() for n in names if (n or "").strip()))
    for i, n in enumerate(cleaned):
        old = existing.get(n)
        db.execute(
            "INSERT INTO examining_doctors_list (name, title, degree_ar, degree_en, sort_order, show_on_letterhead) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (n, old["title"] if old else "الدكتور", old["degree_ar"] if old else None,
             old["degree_en"] if old else None, i, old["show_on_letterhead"] if old else 1),
        )
    db.commit()


def add_examining_doctor(db, name):
    """يضيف اسم طبيب جديد لقائمة (دكتور المختبر الفاحص) إن لم يكن موجودًا أصلاً،
    حتى يظهر فورًا بقوائم اختيار الطبيب الفاحص بشاشة (زيارة جديدة) دون
    الحاجة للذهاب لإعدادات النظام أولًا. يُضاف بدون شهادة ومن دون إظهار
    بترويسة التقرير تلقائيًا (المدير يفعّلها يدويًا لاحقًا إذا أراد)."""
    name = (name or "").strip()
    if name and name not in get_examining_doctors(db):
        max_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) as m FROM examining_doctors_list"
        ).fetchone()["m"]
        db.execute(
            "INSERT INTO examining_doctors_list (name, title, sort_order, show_on_letterhead) "
            "VALUES (?, 'الدكتور', ?, 0)",
            (name, max_order + 1),
        )
        db.commit()
    return get_examining_doctors(db)


def add_examining_doctor_full(db, name, title, degree_ar, degree_en, show_on_letterhead):
    """يضيف دكتور فحص جديد بكامل تفاصيله من شاشة إدارة الدكاترة."""
    name = (name or "").strip()
    if not name:
        return
    max_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) as m FROM examining_doctors_list"
    ).fetchone()["m"]
    db.execute(
        "INSERT INTO examining_doctors_list (name, title, degree_ar, degree_en, sort_order, show_on_letterhead) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, (title or "").strip() or "الدكتور", degree_ar, degree_en,
         max_order + 1, 1 if show_on_letterhead else 0),
    )
    db.commit()


def update_examining_doctor(db, doctor_id, name, title, degree_ar, degree_en, show_on_letterhead):
    db.execute(
        "UPDATE examining_doctors_list SET name=?, title=?, degree_ar=?, degree_en=?, show_on_letterhead=? "
        "WHERE id=?",
        ((name or "").strip(), (title or "").strip() or "الدكتور", degree_ar, degree_en,
         1 if show_on_letterhead else 0, doctor_id),
    )
    db.commit()


def delete_examining_doctor(db, doctor_id):
    db.execute("DELETE FROM examining_doctors_list WHERE id=?", (doctor_id,))
    db.commit()


def move_examining_doctor(db, doctor_id, direction):
    """يبدّل ترتيب هذا الدكتور مع جاره بالقائمة (فوق أو تحت) —
    direction: 'up' أو 'down'. يُستخدم بدل السحب-والإفلات لتفادي الاعتماد
    على مكتبة جافاسكربت خارجية بأداة تعمل بدون إنترنت."""
    rows = list(get_examining_doctors_full(db))
    ids = [r["id"] for r in rows]
    if doctor_id not in ids:
        return
    idx = ids.index(doctor_id)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if swap_idx < 0 or swap_idx >= len(rows):
        return
    a, b = rows[idx], rows[swap_idx]
    db.execute("UPDATE examining_doctors_list SET sort_order=? WHERE id=?", (b["sort_order"], a["id"]))
    db.execute("UPDATE examining_doctors_list SET sort_order=? WHERE id=?", (a["sort_order"], b["id"]))
    db.commit()


def get_examining_tests(db):
    """الفحوصات التي يظهر معها اسم دكتور المختبر الفاحص ويُحسب له أجر عنها."""
    return db.execute(
        "SELECT * FROM test_definitions WHERE is_examining_test=1 AND is_active=1 ORDER BY name"
    ).fetchall()


def get_examining_rates_map(db):
    """{doctor_name: {test_definition_id(str): rate}} — لكل الأطباء الفاحصين."""
    rows = db.execute("SELECT doctor_name, test_definition_id, rate FROM examining_doctor_rates").fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["doctor_name"], {})[str(r["test_definition_id"])] = r["rate"]
    return out


def set_examining_doctor_rate(db, doctor_name, test_definition_id, rate):
    db.execute(
        "INSERT INTO examining_doctor_rates (doctor_name, test_definition_id, rate) VALUES (?, ?, ?) "
        "ON CONFLICT(doctor_name, test_definition_id) DO UPDATE SET rate=excluded.rate",
        (doctor_name, test_definition_id, rate),
    )
    db.commit()


def compute_examining_doctor_fee(db, doctor_name, test_ids):
    """يحسب إجمالي أجر دكتور المختبر الفاحص عن الفحوصات المؤهلة المختارة فقط
    (الفحوصات غير المؤهلة لا تُحسب حتى لو كان اسم الدكتور مختارًا)."""
    doctor_name = (doctor_name or "").strip()
    if not doctor_name or not test_ids:
        return 0.0
    eligible_ids = {row["id"] for row in get_examining_tests(db)}
    total = 0.0
    for tid in test_ids:
        try:
            tid_int = int(tid)
        except (TypeError, ValueError):
            continue
        if tid_int not in eligible_ids:
            continue
        row = db.execute(
            "SELECT rate FROM examining_doctor_rates WHERE doctor_name=? AND test_definition_id=?",
            (doctor_name, tid_int),
        ).fetchone()
        if row is not None:
            total += row["rate"] or 0
    return total


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
