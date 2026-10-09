"""
Database layer for the LIS (Laboratory Information System).
Uses SQLite (zero external dependencies) so it runs anywhere Python runs.
"""
import sqlite3
import os
import sys
import json
import hashlib
from datetime import datetime

# ============================================================================
# مكان قاعدة البيانات (lis.db) -- مشكلة خطيرة كانت هنا: os.path.dirname(__file__)
# وقت تشغيل البرنامج مغلّف بـPyInstaller بوضع --onefile يرجّع مسار مجلد
# مؤقت (Temp\_MEIxxxxx) يُفكّ فيه البرنامج مؤقتًا كل مرة تفتحه، ويُمسح هذا
# المجلد بالكامل لما تسكّر البرنامج. يعني قاعدة البيانات نفسها كانت
# تُكتب/تُقرأ من مكان يُمسح تلقائيًا -- أي بيانات (زيارات، مرضى، نتائج)
# تنكتب وأنت شغّال، تضيع بمجرد ما تسكّر الـ.exe وتفتحه من جديد!
#
# الحل القياسي: لو البرنامج مغلّف (sys.frozen موجودة، علامة PyInstaller
# الرسمية)، نستخدم مجلد ملف الـ.exe نفسه (sys.executable) بدل مجلد
# الفكّ المؤقت -- هذا المجلد ثابت ودائم. لو تشغيل مباشر بالكود (python
# app.py أو run.ps1، وضع الإنتاج الفعلي عندك)، يبقى نفس السلوك القديم
# بالضبط (بجانب ملفات الكود، __file__ يرجع مسار حقيقي ثابت في الحالتين).
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_BASE_DIR, "lis.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # المطلوب 4 (مزامنة حية بين جهاز الاستقبال وجهاز المختبر على نفس
    # الشبكة): بدون هذا، أي جهازين يحفظون بنفس اللحظة تقريبًا معرضين
    # لخطأ "database is locked". WAL يخلي القراءة والكتابة تصير بنفس
    # الوقت من أكثر من اتصال، وbusy_timeout يخلي أي اتصال ينتظر لين
    # 5 ثواني قبل لا يرمي الخطأ (بدل ما يفشل فورًا).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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

-- مكتبة الأختام والتواقيع الرقمية — يضيف المدير هنا عدد غير محدود من صور
-- الأختام/التواقيع (ختم المختبر نفسه، وختم/توقيع كل دكتور فاحص على حدة،
-- لأن كل واحد منهم يختلف عن الثاني). image_filename هو اسم الملف داخل
-- static/uploads/stamps فقط (بعد تحويله لخلفية بيضاء صلبة عند الرفع حتى لا
-- يظهر "نشازًا" فوق التقرير). linked_examining_doctor_id اختياري — لو
-- انربط بدكتور معيّن من قائمة examining_doctors_list يظهر مقترحًا تلقائيًا
-- أول ما يُختار ذلك الدكتور كفاحص للزيارة، لكن يبقى بإمكان أي مستخدم
-- اختيار أي ختم آخر يدويًا بغض النظر عن الربط. default_width/height هي
-- القياس الافتراضي بالبكسل أول مرة يُسحب فيها الختم فوق أي تقرير (يتغيّر
-- بعدها حرًا بالسحب لكل تقرير على حدة — راجع report_stamp_placements).
CREATE TABLE IF NOT EXISTS digital_stamps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,                 -- اسم مختصر يظهر بالقائمة المنسدلة، مثلاً "ختم د. خليل حمود"
    kind TEXT NOT NULL DEFAULT 'stamp',  -- stamp | signature | stamp_signature (وصف فقط، لا يتحكم بالعرض)
    linked_examining_doctor_id INTEGER,  -- ربط اختياري بدكتور من examining_doctors_list — يُلصق تلقائيًا
                                          -- بأي تقرير يظهر فيه هذا الدكتور كـ"دكتور فاحص" للزيارة (visits.examining_doctor)
    image_filename TEXT NOT NULL,        -- صورة الختم (الطبقة السفلى)
    signature_filename TEXT,             -- صورة التوقيع (الطبقة العلوية، ملاصقة لصورة الختم بدون فراغ) — اختياري
    is_lab_default INTEGER DEFAULT 0,    -- ختم المختبر الافتراضي: يُلصق تلقائيًا حتى بدون دكتور فاحص مرتبط
    default_width INTEGER DEFAULT 140,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER,
    created_at TEXT,
    FOREIGN KEY (linked_examining_doctor_id) REFERENCES examining_doctors_list(id)
);

-- الختم/التوقيع الفعلي المُلصق على تقرير معيّن (زيارة كاملة أو تحليل مفرد)،
-- مع موضعه بالضبط (pos_x/pos_y بالبكسل من الزاوية العلوية اليسرى لصفحة
-- التقرير) بعد ما يسحبه المستخدم بالماوس فوق معاينة التقرير. UNIQUE على
-- (target_type, target_id, stamp_id) يعني: لو نفس الختم انسحب مرة ثانية
-- لنفس التقرير يتحدّث موضعه فقط (upsert)، بدون أي تكرار — بينما يمكن إضافة
-- أكثر من ختم/توقيع مختلف لنفس التقرير الواحد (مثلاً ختم المختبر + توقيع
-- الدكتور الفاحص سوا) لأن كل واحد صف منفصل بـstamp_id مختلف.
CREATE TABLE IF NOT EXISTS report_stamp_placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,   -- 'visit' (تقرير موحّد لكل الزيارة) أو 'order_test' (تحليل مفرد)
    target_id INTEGER NOT NULL,
    stamp_id INTEGER NOT NULL,
    pos_x REAL NOT NULL DEFAULT 40,
    pos_y REAL NOT NULL DEFAULT 40,
    width REAL,
    placed_by INTEGER,
    placed_at TEXT,
    UNIQUE(target_type, target_id, stamp_id),
    FOREIGN KEY (stamp_id) REFERENCES digital_stamps(id)
);

-- التقارير المحفوظة (PDF) لكل زيارة، تُستخدم لأرشيف التقارير والبحث عنها لاحقًا.
CREATE TABLE IF NOT EXISTS saved_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL UNIQUE,
    patient_id INTEGER,
    full_name TEXT,
    registration_number TEXT,
    pdf_path TEXT NOT NULL,
    referring_doctor_name TEXT,
    referral_center_name TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (visit_id) REFERENCES visits(id),
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

-- موافقة الموظف على دمج نتيجة تحليل قديم (من زيارة سابقة لنفس المريض)
-- بتقرير الزيارة الجديدة — تُسجَّل فقط عند التأكيد الصريح بشاشة "زيارة
-- جديدة" (بنك تنبيه الزيارة السابقة)، ولا يوجد أي عرض تلقائي بدونها.
-- source_order_test_id يشير للتحليل القديم نفسه (من الزيارة السابقة)،
-- بغض النظر إن كان نفس التحليل معاد طلبه بالزيارة الجديدة أو لا — هذا ما
-- يسمح بعرضه كصف "Previous" جنب تحليل مطابق بالزيارة الجديدة، أو كصف
-- مستقل إضافي بنفس مجموعة القسم لو ما تكرر طلبه. UNIQUE يمنع تكرار نفس
-- الموافقة مرتين لو ضغط الموظف الزر أكثر من مرة بالغلط.
-- ملاحظة/تعليق اختياري تحت تحليل (أو باراميتر) معيّن بتقرير زيارة معيّنة.
-- لا تظهر بالتقرير المطبوع إلا إذا show=1 (زر "إظهار الملاحظة"). label اختياري
-- (مثلاً Note / Comment / أي عنوان يكتبه المستخدم، أو فاضي = بدون عنوان).
-- row_key = "<test_definition_id>|<اسم الباراميتر>".
CREATE TABLE IF NOT EXISTS report_row_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    row_key TEXT NOT NULL,
    note_text TEXT,
    note_label TEXT,
    show INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(visit_id, row_key)
);

-- عدد الزيارات السابقة (لنفس المريض ونفس التحليل) اللي تظهر نتائجها بتقرير هذي
-- الزيارة. يُحدَّد من صفحة "زيارة جديدة" (أو من شاشة إدخال النتائج لاحقًا).
-- 0 = لا تظهر أي نتيجة سابقة. غياب السطر = السلوك القديم (موافقة الدمج فقط).
-- حالة مزامنة كل زيارة مع بوابة النتائج السحابية: آخر حالة/بصمة اندفعت بنجاح، وعدد المحاولات الفاشلة.
-- العامل الخلفي (cloud_sync.py) يقارن بصمة النتائج الحالية بآخر بصمة مدفوعة؛ لو اختلفت يرسل من جديد،
-- ولو فشل (انقطاع إنترنت) يعيد المحاولة تلقائيًا لاحقًا بدون ما يضيع شي.
CREATE TABLE IF NOT EXISTS portal_state (
    visit_id INTEGER PRIMARY KEY,
    last_status TEXT,
    last_hash TEXT,
    last_pushed_at TEXT,
    last_error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try_at TEXT
);

-- عدّاد تسلسل رقم العينة: صف لكل "فترة" (مثلاً 2026-09-28 للتصفير اليومي) — آخر رقم مُستخدم.
CREATE TABLE IF NOT EXISTS sample_counters (
    period_key TEXT PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS visit_prev_prefs (
    visit_id INTEGER PRIMARY KEY,
    prev_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS visit_previous_merges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL,
    source_order_test_id INTEGER NOT NULL,
    approved_by INTEGER,
    approved_at TEXT,
    UNIQUE(visit_id, source_order_test_id),
    FOREIGN KEY (visit_id) REFERENCES visits(id),
    FOREIGN KEY (source_order_test_id) REFERENCES order_tests(id)
);

-- ============================================================================
-- تخصيص مظهر التقرير المطبوع (سحب باراميتر، لون/خط/حجم نتيجة، إزاحة
-- الصفحة، موضع الختم...) — راجع editor_script بـ exam_report_shared.html
-- و get_report_layout/save_report_layout بـ app.py.
-- scope='test'       : scope_id = test_definition_id — يطبّق على كل مريض
--                       عنده هذا التحليل (التصميم "الافتراضي" الجديد).
-- scope='order_test'  : scope_id = order_test_id — استثناء خاص بمريض واحد
--                       بالذات فقط، يتفوّق دائمًا على تخصيص scope='test'
--                       لو موجود، ولا يأثر على أي مريض ثاني إطلاقًا.
-- layout_json: نص JSON حر الشكل (param_order, param_overrides بالاسم
-- {color, font_family, font_size, label}, section_order, page_offset_mm,
-- stamp_pos) — قابل للتوسّع بدون أي تعديل بقاعدة البيانات مستقبلاً.
-- ============================================================================
CREATE TABLE IF NOT EXISTS report_layout_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    scope_id INTEGER NOT NULL,
    layout_json TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT,
    UNIQUE(scope, scope_id)
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
            # full_name_en: الاسم الإنكليزي — app.py يقرأ/يكتب هذا العمود
            # أصلاً (تسجيل مريض جديد، تعديل مريض، تعديل زيارة، وطباعة
            # التقرير عبر _pt_en_row) لكن العمود ما كان مُضافًا هنا بقاعدة
            # البيانات، فكان أي حفظ لمريض أو طباعة تقرير سينهار فورًا
            # بخطأ "no such column: full_name_en". هذا العمود هو الإصلاح.
            ("full_name_en", "TEXT"),
            # تاريخ الميلاد (اختياري): يُكتب بصفحة زيارة جديدة ويحسب العمر تلقائيًا
            ("birth_date", "TEXT"),
        ],
        "doctors": [("email", "TEXT"), ("commission_percent", "REAL DEFAULT 0")],
        "digital_stamps": [
            # signature_filename: صورة توقيع منفصلة تُلصق فوق صورة الختم
            # (image_filename) مباشرة — فوقه بدون أي فراغ بينهما (touching) —
            # كوحدة واحدة تُسحب وتُحرَّك سوا دائمًا (مو ختمين منفصلين). لو
            # فاضي، يبقى السلوك القديم: صورة وحدة فقط (image_filename).
            ("signature_filename", "TEXT"),
            # is_lab_default: علامة "هذا هو ختم المختبر الافتراضي" — يُلصق
            # تلقائيًا بأي تقرير مفعّل له صندوق الختم (enable_stamp_widget)
            # حتى لو ما فيه دكتور فاحص مرتبط أصلاً. يُسمح بختم مختبري وحد فقط
            # فعليًا (يُفعَّل بمصمم الأختام؛ تفعيل ختم جديد يلغي القديم تلقائيًا).
            ("is_lab_default", "INTEGER DEFAULT 0"),
        ],
        # phone: رقم واتساب مدير المختبر المُرسِل (لإرسال كشف الحساب الشهري له)
        "referral_centers": [("phone", "TEXT")],
        "order_tests": [
            ("doctor_id", "INTEGER"), ("collected_at", "TEXT"), ("accessioned_at", "TEXT"),
            ("price", "REAL"),
            # report_comment: الميزة أُلغيت نهائيًا — العمود يبقى موجودًا
            # (بدون DROP) لعدم فقدان بيانات قديمة، لكن لا يُقرأ ولا يُكتب
            # فيه بعد الآن من أي مكان بالبرنامج.
            ("report_comment", "TEXT"),
            # analyzer: اسم الجهاز الحر اللي اشتغل عليه هذا التحليل تحديداً
            # بهذي الزيارة (E411 / Pure / Beckman 520 DX...) — يُختار وقت
            # إدخال النتيجة، لأن نفس التحليل ممكن يشتغل بجهاز مختلف بين
            # زيارة وأخرى. فاضي = بدون تحديد جهاز (يرجع find_reference_range
            # للنسبة العامة كالمعتاد). راجع find_reference_range بـ database.py.
            ("analyzer", "TEXT"),
            # selected_param_ids: طلب بارامترات معيّنة بس من داخل تحليل متعدد
            # الباراميترات (مثلاً PT وINR بس من Coagulation)، بدل التحليل
            # كامل — نص "id,id,id" (معرّفات test_parameters). NULL/فاضي =
            # السلوك الافتراضي القديم تمامًا: كل باراميترات هذا التحليل
            # مطلوبة (لا يتغير أي طلب قديم). راجع شاشة "زيارة جديدة" (سهم ▾
            # جنب كل تحليل) وحساب order_test_price بـ app.py.
            ("selected_param_ids", "TEXT"),
            # tube_barcode: باركود العينة/الأنبوب المشترك — كل التحاليل
            # بنفس الزيارة اللي تحتاج نفس نوع العينة (sample_type، مثل
            # Serum أو EDTA أو Citrate) تاخذ نفس القيمة هنا، بدل باركود
            # مستقل لكل تحليل لحاله. الهدف: أنبوب واحد فعلي = باركود واحد
            # يغطّي كل التحاليل المسحوبة منه (كيمياء/هرمونات/فايروسات/
            # فيتامينات/دلائل ورمية = Serum، كل تحاليل التخثر = Plasma/
            # Citrate، وCBC وBlood film وHb Electrophoresis وH.preparation
            # وSickling test وRetic count وBMA = EDTA). يُنشأ تلقائيًا أول
            # مرة تُطبع فيها باركودات عينات هذي الزيارة (راجع
            # print_sample_barcodes بـapp.py). عمود "barcode" الأصلي يبقى
            # موجودًا وغير متأثر — لطباعة باركود إضافي لتحليل وحيد بس عند
            # الحاجة.
            ("tube_barcode", "TEXT"),
            # fee_waived: علامة "تحليل مجاني" -- الدكتور الفاحص لا يتقاضى أجرًا
            # عن هذا التحليل بالذات لهذه الزيارة (يبقى التحليل يُطبع ويُحفظ
            # بالتقرير كالمعتاد -- فقط يُستثنى من حساب أجر دكتور المختبر
            # الفاحص visits.examining_doctor_fee). يُبدَّل من زر محمي بكلمة
            # مرور خاصة (راجع fee_waiver_password_hash بجدول settings وشاشة
            # الإعدادات). 0 افتراضيًا لكل التحاليل القديمة والجديدة.
            ("fee_waived", "INTEGER DEFAULT 0"),
            # hidden_from_log: يُبدَّل مع fee_waived نفسه (سؤال إضافي وقت
            # الضغط على زر "🆓 تحليل مجاني": "يدخل ضمن سجل المرضى اليومي؟").
            # ملاحظة: استثناء السعر من الحسابات (يومي/شهري/نصف سنوي/سنوي)
            # يعتمد على fee_waived لحاله (أي تحليل مجاني يُستثنى ماديًا
            # بكل الأحوال، ظاهر أو مخفي). hidden_from_log يتحكم فقط هل
            # اسم التحليل يظهر بعمود "التحاليل" بصفحة daily_report أم
            # يختفي منها كليًا -- بالحالتين نتيجته تبقى محفوظة بجدول
            # results عادي وتقدر تطبعها/تبحث عنها بأي وقت. لا علاقة له
            # بفاتورة المريض نفسها (خارج نطاق هذا الحقل).
            ("hidden_from_log", "INTEGER DEFAULT 0"),
            # forwarded_lab_name / forwarded_cost (المطلوب 3): لو هذا
            # التحليل بالذات ما يُنفَّذ فعليًا بمختبرك (مثل البرولاكتين
            # الذي يُرسَل لمختبر القمة مثلاً) -- تسجّل هون اسم المختبر
            # المُرسَل إليه وكلفته، ليُحسَب ضمن "الصرفيات" بالتقرير اليومي/
            # الشهري تلقائيًا (راجع recompute_visit_forwarded_expenses
            # بـapp.py). فاضي = هذا التحليل يُنفَّذ بمختبرك مباشرة (السلوك
            # الافتراضي القديم، بلا أي تغيير). التقرير المطبوع للمريض نفسه
            # لا يتأثر إطلاقًا بهذا الحقل -- يبقى يُطبع بقالب مختبرك (نفس
            # الشعار والدكاترة) بغض النظر عن مكان الإرسال الفعلي.
            ("forwarded_lab_name", "TEXT"), ("forwarded_cost", "REAL DEFAULT 0"),
            # sent_to_reception / sent_to_reception_at: علامة "أُرسلت لشاشة
            # الاستقبال" -- تُبدَّل من زر 📤 بصفحة Orders (شاشة المختبر) بعد ما
            # تكتمل نتيجة هذا التحليل (Completed/Verified). بمجرد ما تُرسَل،
            # يختفي هذا التحليل من القائمة الافتراضية بصفحة Orders (يبقى
            # موجود فعليًا بقاعدة البيانات ويظهر لو استخدم أي موظف مربع
            # البحث)، ويظهر بصفحة النتائج بشاشة الاستقبال جاهزًا للطباعة
            # والتسليم للمريض. راجع send_order_test_to_reception بـapp.py.
            ("sent_to_reception", "INTEGER DEFAULT 0"), ("sent_to_reception_at", "TEXT"),
            # reception_seen: هل موظف الاستقبال "شاف" هذا الإرسال أصلاً
            # (يصير 0 عند الإرسال، ويرجع 1 بعد ما يظهر إشعار/رنة الجرس له
            # مرة وحدة). يتحكم بعداد الإشعارات غير المقروءة بشريط شاشة
            # الاستقبال. الافتراضي 1 لأي صف قديم قبل هذي الميزة (ما يطلع
            # إشعار وهمي عن نتائج قديمة أصلاً).
            ("reception_seen", "INTEGER DEFAULT 1"),
            # printed_at: أول لحظة انفتحت فيها صفحة طباعة هذا التحليل فعليًا
            # (طباعة مفردة أو ضمن حزمة نتائج الزيارة المجمّعة) -- تُستخدم مع
            # ot.status لمنع أي تعديل لاحق على النتيجة أو معلومات المريض
            # إلا بدخول يوزر/باسورد حساب مسؤول أو مشرف حقيقي (راجع
            # _check_completed_result_gate بـapp.py). NULL = لسا ما انطبعت.
            ("printed_at", "TEXT"),
        ],
        "invoices": [("is_locked", "INTEGER DEFAULT 0"), ("extra_charges", "REAL DEFAULT 0")],
        "visits": [("examining_doctor", "TEXT"), ("expenses", "REAL DEFAULT 0"),
                    ("examining_doctor_fee", "REAL DEFAULT 0"), ("attending_doctor", "TEXT"),
                    # حقول "المعلومات الصحية" الجديدة بشاشة "زيارة جديدة" — خاصة
                    # بكل زيارة تحديداً (تختلف من زيارة لأخرى لنفس المريض)، لذلك
                    # على جدول visits وليس patients.
                    ("weight", "REAL"), ("height", "REAL"), ("symptoms", "TEXT"),
                    ("disease", "TEXT"), ("therapy", "TEXT"),
                    # الزيارة المنزلية (Home Visit): علامة + عنوان + أجرة إضافية
                    # خاصة بهذي الزيارة فقط.
                    ("is_home_visit", "INTEGER DEFAULT 0"), ("home_visit_address", "TEXT"),
                    ("home_visit_fee", "REAL DEFAULT 0"),
                    # رقم العينة (Sample No.) الخاص بالزيارة: يُدخَل/يُولَّد بصفحة "زيارة جديدة"
                    # ويتسلسل من جديد حسب فترة التصفير بالإعدادات (يومي/شهري/سنوي/بدون).
                    ("sample_no", "TEXT"),
                    # رمز بوابة النتائج (QR للمريض): عشوائي طويل، يُولَّد مرة وحدة لكل زيارة (cloud_sync.py).
                    ("portal_token", "TEXT"),
                    # وقت ظهور النتائج المتوقع (اختياري) — يحدده الاستقبال بصفحة زيارة جديدة، يظهر بورقة QR/بوابة المريض
                    ("expected_ready_at", "TEXT")],
        "test_definitions": [("is_examining_test", "INTEGER DEFAULT 0"),
                               # short_name: اختصار يدوي يحدده الأدمن لهذا التحليل تحديدًا
                               # (مثال: "PT" بدل "زمن البروثرومبين") — يُستخدم فقط بملصق
                               # باركود الأنبوب لما يختار المستخدم وضع "مختصر" لأسماء
                               # التحاليل (راجع خيار "أسماء التحاليل" بشريط إعدادات صفحة
                               # front_desk/print_sample_barcodes.html، ودالة
                               # print_sample_barcodes بـapp.py). فاضي = يرجع تلقائيًا
                               # لتقصير اسم التحليل الكامل بعدد أحرف ثابت (بدون اختصار
                               # طبي معتمد) بدل ما يختفي الاسم كليًا.
                               ("short_name", "TEXT"),
                               # report_group: اسم "الريبورت المجمّع" اللي ينتمي له هذا
                               # التحليل (مثلاً "Thyroid function test" أو "Viral study")،
                               # مستقل تماماً عن حقل department. يُستخدم فقط بلوحة الطباعة
                               # المجمّعة (print_combined_panel) لتجميع التحاليل تحت عنوان
                               # فرعي محدد بدل الاعتماد على القسم العام. فاضي = يرجع
                               # للسلوك القديم (تجميع حسب department كالمعتاد).
                               ("report_group", "TEXT"),
                               # enable_stamp_widget: تفعيل/تعطيل صندوق "إضافة
                               # ختم / توقيع" (partials/stamp_picker.html) لهذا
                               # التحليل تحديداً — ينطبق على كل أنواع التقارير
                               # (CBC، Blood film، مخصص...). الافتراضي 0
                               # (معطّل) لكل التحاليل القديمة والجديدة، حتى لا
                               # يظهر الصندوق أبداً إلا إذا فعّله المدير صراحةً
                               # من صفحة مصمم التقارير.
                               ("enable_stamp_widget", "INTEGER DEFAULT 0"),
                               # خيارات الختم/التوقيع لكل تحليل (مصمم التقارير > "خيارات الختم والتوقيع"):
                               # show_lab_stamp / show_doctor_stamp: الافتراضي 1 = نفس السلوك
                               # القديم تمامًا (يلصق ختم المختبر وختم الدكتور الفاحص تلقائيًا)،
                               # و0 = لا يُلصق ذاك النوع تلقائيًا لهذا التحليل.
                               # hide_signature_box: 1 = يخفي صندوق التوقيع الفاضي الثابت.
                               # signature_position: left/center/right (فاضي = الافتراضي القديم).
                               ("show_lab_stamp", "INTEGER DEFAULT 1"),
                               ("show_doctor_stamp", "INTEGER DEFAULT 1"),
                               ("hide_signature_box", "INTEGER DEFAULT 0"),
                               ("signature_position", "TEXT"),
                               # panel_color / panel_page_break: تخصيص اختياري
                               # لهذا التحليل بـ"اللوحة المجمّعة" (combined_panel
                               # — لما تُطبع أكثر من تحليل سوا بنفس الورقة).
                               # panel_color يلوّن اسم ونتيجة كل باراميتر تابع
                               # لهذا التحليل بالجدول المجمّع؛ panel_page_break
                               # يجبر أول صف تابع له يبدأ بأعلى صفحة جديدة.
                               # فاضي/0 = السلوك الافتراضي بدون أي تغيير.
                               ("panel_color", "TEXT"), ("panel_page_break", "INTEGER DEFAULT 0"),
                               # report_style: لو 'generic_exam' يطبع هذا التحليل عبر
                               # reports/generic_exam.html (قوالب فحص عام قابل للبناء
                               # كامل من صفحة المعاينة نفسها — سحب أقسام/باراميترات،
                               # بدون كتابة قالب HTML يدوي أصلاً) بدل مسار "مصمم
                               # التقارير" العام. راجع _print_report_impl بـ app.py
                               # وشرح كامل بأعلى reports/generic_exam.html.
                               ("report_style", "TEXT"),
                               # done_by_note: سطر "Done by ..." اختياري لهذا التحليل
                               # تحديداً (مثلاً "Done by Beckman 520 DX")، يُدار من
                               # مصمم التقارير أو صفحة النسب الطبيعية. فاضي = لا
                               # يظهر أبداً. يُطبع بـ.footer-block (base_report.html)
                               # بكل قوالب التقارير (custom/CBC/panel/exam). بديل
                               # عن reference_ranges.source_note المتوقف عرضه.
                               ("done_by_note", "TEXT"),
                               # row_spacing (المطلوب 8): المسافة بين صفوف
                               # الباراميترات بتقرير هذا التحليل — 'tight' /
                               # 'normal' / 'loose' أو رقم بكسل حر (نص رقمي).
                               # فاضي/NULL = نفس الافتراضي القديم بكل قالب
                               # (لا يتغير أي تقرير قديم). يُطبّق على exam rows،
                               # custom cards، CBC، combined panel — راجع
                               # row_spacing_px بـapp.py لتحويلها لبكسل فعلي.
                               ("row_spacing", "TEXT")],
        # patient_id: نسبة طبيعية خاصة بمريض واحد بالذات (حالات خاصة/علاج) —
        # NULL يعني نسبة عامة تنطبق على كل المرضى كالمعتاد. تتفوّق على أي
        # نسبة عامة لنفس الباراميتر لو موجودة (راجع find_reference_range).
        # range_label: تسمية اختيارية توضّح سبب النسبة الخاصة (مثلاً "مرضى
        # الكورتيزون") — عرض فقط، لا تدخل بمنطق المطابقة.
        # analyzer: اسم الجهاز الحر (E411 / Pure / Beckman 520 DX...) —
        # NULL يعني نسبة عامة بغض النظر عن الجهاز. أولوية المطابقة الكاملة:
        # نسبة المريض الخاصة > نسبة نفس الجهاز > النسبة العامة.
        "reference_ranges": [("age_from_unit", "TEXT DEFAULT 'Years'"), ("age_to_unit", "TEXT DEFAULT 'Years'"),
                              ("patient_id", "INTEGER"), ("range_label", "TEXT"), ("analyzer", "TEXT"),
                              ("note", "TEXT")],
        # unit2 / unit2_factor: وحدة ثانية اختيارية تُعرض تلقائيًا جنب النتيجة
        # الأصلية وقت الطباعة (مثلاً mg/dL بالإضافة لـ mmol/L). القيمة الثانية
        # تُحسب دائمًا = القيمة الأصلية × unit2_factor، ولا تُخزَّن بجدول
        # results أبدًا — تُحسب لحظة الطباعة فقط. فاضي = بدون وحدة ثانية
        # (السلوك القديم كما هو).
        "test_parameters": [("highlight", "INTEGER DEFAULT 0"), ("unit2", "TEXT"), ("unit2_factor", "REAL"),
                             # panel_color / panel_page_break: نفس فكرة أعمدة
                             # test_definitions بنفس الاسم، بس هنا على مستوى
                             # الباراميتر المفرد — يسمح بتلوين/فصل صفحة
                             # لباراميتر وحدة بس داخل تحليل متعدد الباراميترات
                             # (مثل NRBC بس داخل Blood film) عند ظهوره باللوحة
                             # المجمّعة، بدل تلوين كل التحليل سوا.
                             ("panel_color", "TEXT"), ("panel_page_break", "INTEGER DEFAULT 0"),
                             # sort_order: ترتيب عرض الباراميتر داخل تحليله (بشاشة
                             # إدخال النتائج وبالتقرير المطبوع) — رقم أصغر يظهر
                             # أولاً. الافتراضي 0 لكل الباراميترات القديمة، فيبقى
                             # ترتيبها كما هو (حسب id) حتى يعدّلها المدير يدويًا من
                             # صفحة "ترتيب الباراميترات" الجديدة.
                             ("sort_order", "INTEGER DEFAULT 0"),
                             # display_label (المطلوب 9ب): تسمية عرض بديلة تُطبع
                             # بدل name الأصلي بكل القوالب (exam rows، CBC،
                             # combined panel، وcustom.html كـfallback لو ما
                             # فيه label مضبوط أصلاً من مصمم التقارير rows_json).
                             # فاضي = يبقى name الأصلي كالسابق. لا يغيّر name
                             # الحقيقي المستخدم بحفظ/قراءة النتائج نفسها.
                             ("display_label", "TEXT"),
                             # report_column: رقم العمود المفضّل للباراميتر بالتقرير (1 أو 2)،
                             # فاضي = تلقائي. يُحفظ من مصمم التقارير.
                             ("report_column", "TEXT"),
                             # value_align (المطلوب 11): موضع رقم النتيجة —
                             # near_name / center / near_unit. NULL/فاضي = نفس
                             # السلوك الحالي القديم تمامًا (لا يتغير أي تقرير
                             # قديم). راجع resolve_value_align بـapp.py.
                             ("value_align", "TEXT"),
                             # price: سعر هذا الباراميتر لحاله — يُستخدم فقط
                             # لما يطلب الموظف بارامترات معيّنة من تحليل متعدد
                             # الباراميترات بدل التحليل كامل (سهم ▾ بشاشة
                             # "زيارة جديدة" — راجع order_tests.selected_param_ids
                             # أعلاه). NULL = لسا ما تحدد سعره؛ الموظف يقدر
                             # يكتبه أول مرة يختاره بشاشة الطلب نفسها وينحفظ
                             # هنا تلقائيًا لكل الطلبات الجاية. لا علاقة له
                             # بسعر التحليل الكامل (test_definitions.price).
                             ("price", "REAL")],
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
        "report_templates": [("heading_align", "TEXT DEFAULT 'center'"), ("rows_align", "TEXT DEFAULT 'right'"),
                              # unit_column: تخطيط أعمدة بديل لهذا التقرير تحديداً —
                              # لو مفعّل (1)، عمود الوحدة ينفصل عن عمود النتيجة
                              # ويصير بأقصى اليمين لحاله، والنتيجة توسّط بعمودها،
                              # بدل الوضع الافتراضي (0) اللي تكون فيه الوحدة
                              # ملتصقة بنهاية النتيجة بنفس العمود.
                              ("unit_column", "INTEGER DEFAULT 0")],
        # font_size: تجاوز اختياري لحجم خط اسم/شهادة هذا الدكتور تحديداً
        # بترويسة التقرير (بالبكسل). فاضي (NULL) = يرث الحجم العام
        # letterhead_font_size من الإعدادات كالسابق تماماً — هذا العمود لا
        # يغيّر أي تصميم محفوظ إلا إذا عبّاه المدير صراحةً من شاشة إدارة
        # الدكاترة لدكتور معيّن.
        "examining_doctors_list": [("font_size", "INTEGER")],
        # note: ملاحظة قصيرة أمام باراميتر واحد بالذات (زر 📝 بتقارير الفحص
        # GUE/GSE/SFA — راجع exam_row بـ exam_report_shared.html)، مستقلة
        # تمامًا عن order_tests.report_comment (الملاحظة العامة للتقرير كامل).
        # note_label: تسمية اختيارية للملاحظة (Comment / فاضي = بدون عنوان).
        # note_visible: الكتابة والإظهار بالطباعة خطوتان منفصلتان (0=مخفية، 1=ظاهرة).
        "results": [("note", "TEXT"), ("note_label", "TEXT"), ("note_visible", "INTEGER DEFAULT 0")],
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

    # GUE / GSE / SFA (فحص البول العام، فحص البراز العام، تحليل السائل
    # المنوي) — تقارير طباعة ثابتة جديدة (reports/urine_exam.html،
    # reports/stool_exam.html، reports/seminal_fluid.html — راجع
    # REPORT_TEMPLATE_MAP بـ app.py) بدل مسار "مصمم التقارير" العام. أسماء
    # الباراميترات هنا يجب أن تطابق بالضبط أسماء macro_names/micro_names
    # المكتوبة داخل تلك القوالب (حساسة لحالة الأحرف والمسافات) حتى تظهر كل
    # نتيجة تحت قسمها الصحيح بالتقرير المطبوع. لا يُنشئ التحليل من الصفر لو
    # كان موجودًا أصلاً (بأي اسم/قسم عدّله المستخدم) — فقط يُكمّل الباراميترات
    # الناقصة له (بدون تكرار لو الاسم موجود أصلاً، بغض النظر عمّن أضافه).
    exam_test_specs = [
        ("GUE", "General Urine Examination", "فحص البول العام", "Others", "Urine", [
            ("Color", "", "Text", None, None, "Yellow"),
            ("Specific Gravity", "", "Numeric", 1.005, 1.030, None),
            ("Reaction (pH)", "", "Numeric", 5.0, 8.0, None),
            ("Glucose", "", "Text", None, None, "Negative"),
            ("Protein", "", "Text", None, None, "Negative"),
            ("Ketone", "", "Text", None, None, "Negative"),
            ("Bile Pigment", "", "Text", None, None, "Negative"),
            ("Urobilinogen", "eu/dl", "Numeric", 0.2, 1.0, None),
            ("Nitrite", "", "Text", None, None, "Negative"),
            ("RBCs", "/HPF", "Text", None, None, "0-2"),
            ("PUS", "/HPF", "Text", None, None, "0-5"),
            ("Casts", "", "Text", None, None, "Nil"),
            ("Epithelial Cells", "/HPF", "Text", None, None, "0-2"),
            ("Amorphous", "", "Text", None, None, "Nil"),
            ("Mucus", "", "Text", None, None, "Nil"),
            ("Crystals", "", "Text", None, None, "Nil"),
            ("Parasites / Others", "", "Text", None, None, "Nil"),
        ]),
        ("GSE", "General Stool Examination", "فحص البراز العام", "Others", "Stool", [
            ("Color", "", "Text", None, None, "Brown"),
            ("Consistency", "", "Text", None, None, "Formed"),
            ("Mucus", "", "Text", None, None, "Nil"),
            ("Blood", "", "Text", None, None, "Nil"),
            ("Worms / Helminths", "", "Text", None, None, "Nil"),
            ("Pus Cells", "/HPF", "Text", None, None, "0-2"),
            ("RBCs", "", "Text", None, None, "Nil"),
            ("Amoeba (E. histolytica)", "", "Text", None, None, "Not seen"),
            ("Giardia lamblia", "", "Text", None, None, "Not seen"),
            ("Helminthes Ova", "", "Text", None, None, "Not seen"),
            ("Undigested Food Particles", "", "Text", None, None, "Nil"),
            ("Fungi / Yeast", "", "Text", None, None, "Nil"),
        ]),
        ("SFA", "Seminal Fluid Analysis", "تحليل السائل المنوي", "Others", "Semen", [
            ("Volume", "mL", "Numeric", 1.5, 5.0, None),
            ("Color / Appearance", "", "Text", None, None, "Grey-white / Opalescent"),
            ("Liquefaction Time", "min", "Numeric", 15, 30, None),
            ("Viscosity", "", "Text", None, None, "Normal"),
            ("pH", "", "Numeric", 7.2, 8.0, None),
            ("Sperm Count", "M/mL", "Numeric", None, None, "≥ 16 Million/mL"),
            ("Total Sperm Count", "M", "Numeric", None, None, "≥ 39 Million/ejaculate"),
            ("Active (Progressive)", "%", "Numeric", None, None, "≥ 30%"),
            ("Sluggish (Non-progressive)", "%", "Numeric", None, None, None),
            ("Immotile", "%", "Numeric", None, None, None),
            ("Normal Forms", "%", "Numeric", None, None, "≥ 4%"),
            ("Abnormal Forms", "%", "Numeric", None, None, None),
            ("Pus Cells", "/HPF", "Text", None, None, "< 1 Million/mL"),
            ("RBCs", "/HPF", "Text", None, None, "Nil"),
            ("Agglutination", "", "Text", None, None, "Nil"),
        ]),
    ]
    for code, name, name_ar, department, sample_type, param_specs in exam_test_specs:
        existing_def = conn.execute(
            "SELECT id FROM test_definitions WHERE code=?", (code,)
        ).fetchone()
        if existing_def:
            test_def_id = existing_def["id"]
        else:
            cur = conn.execute(
                "INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, name, name_ar, department, sample_type, 0),
            )
            test_def_id = cur.lastrowid
        existing_param_names = {
            row["name"] for row in conn.execute(
                "SELECT name FROM test_parameters WHERE test_definition_id=?", (test_def_id,)
            ).fetchall()
        }
        for pname, unit, rtype, low, high, range_text in param_specs:
            if pname in existing_param_names:
                continue
            pcur = conn.execute(
                "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
                "VALUES (?, ?, ?, ?)",
                (test_def_id, pname, unit, rtype),
            )
            if low is not None or high is not None or range_text is not None:
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


def ensure_retic_parameters(conn):
    """RETIC ('Retic Count' المفرد -- بدون لطاخة الدم) اتسجّل بالكتالوج ضمن
    EXAMINING_TEST_DEFS لكن ما انزرع له test_parameters إطلاقًا (خلافًا عن
    BFRETIC اللي عنده ensure_bfretic_parameters أعلاه)، فشاشة إدخال نتيجته
    تطلع فاضية تمامًا -- ماكو مكان أصلاً ينزل بيه Reticulocyte count.
    يزرع له:
      - Reticulocyte count % (تُدخل يدويًا من الجهاز/العدّ اليدوي)
      - HCT % (قيمة المريض الفعلية وقت هذا التحليل -- تُستخدم فقط لحساب
        Corrected Retic count، وما تُطبع لحالها بالتقرير)
      - Corrected Retic count % (تُحسب تلقائيًا بـsave_order_test_results
        بملف app.py، ما تُدخل يدويًا إلا لو المستخدم كتب قيمة بنفسه)
    نفس أسلوب ensure_bfretic_parameters تمامًا: يفحص أول هل عنده parameters
    مسبقًا حتى ما يتكرر على قاعدة بيانات مشغّلة هذا السكربت أكثر من مرة."""
    row = conn.execute("SELECT id FROM test_definitions WHERE code='RETIC'").fetchone()
    if not row:
        return
    test_id = row["id"]
    has_params = conn.execute(
        "SELECT COUNT(*) as c FROM test_parameters WHERE test_definition_id=?", (test_id,)
    ).fetchone()["c"]
    if has_params:
        return
    params = [
        ("Reticulocyte count", "%", "Numeric", None, None, None),
        ("HCT", "%", "Numeric", None, None, None),
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


def ensure_basophils_after_eosinophils_order(conn):
    """طلب المستخدم: بكل تحاليل الـDifferential (Blood Film / Blood Film and
    Retic Count / WBC Differential / Fluid Examination) لازم يظهر Basophils
    مباشرة بعد Eosinophils بترتيب العرض والطباعة وإدخال النتائج. يعتمد على
    عمود test_parameters.sort_order (يُقرأ بكل الأماكن اللي تجيب باراميترات
    تحليل معيّن — انظر ORDER BY sort_order, id بـ app.py). يشتغل بمطابقة اسم
    تام (بأي حالة أحرف، بدون حساسية للجمع/المفرد: Basophil/Basophils) حتى ما
    يتأثر بأي تحليل الاسمين فيه غير موجودين (متل بعض حالات Fluid Examination
    اللي ما تحتوي Differential أصلاً — يتم تجاوزه بصمت). يعيد ترقيم كل
    باراميترات التحليل بالكامل حسب ترتيبها الحالي (sort_order ثم id) مع
    إزاحة Basophils بس لموقعه الجديد — يبقى ثابت (idempotent) لو انشغل أكثر
    من مرة، وما يغيّر ترتيب أي باراميتر ثاني فيما بينهم."""
    def norm(name):
        return (name or "").strip().lower().rstrip("s")

    for code in ("BF", "BFRETIC", "WBCDIFF", "FLUIDEXAM"):
        row = conn.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if not row:
            continue
        test_id = row["id"]
        params = conn.execute(
            "SELECT id, name FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id",
            (test_id,),
        ).fetchall()
        names = [norm(p["name"]) for p in params]
        if "eosinophil" not in names or "basophil" not in names:
            continue  # هذا التحليل ما فيه الاثنين (مثلاً بعض إعدادات Fluid Examination) — تجاوزه

        eo_idx = names.index("eosinophil")
        ba_idx = names.index("basophil")
        if ba_idx == eo_idx + 1:
            continue  # مرتب صح أصلاً — لا شي يسوى (يخلي التشغيل مكرر بأمان)

        ordered = list(params)
        basophil_row = ordered.pop(ba_idx)
        new_eo_idx = ordered.index(next(p for p in ordered if norm(p["name"]) == "eosinophil"))
        ordered.insert(new_eo_idx + 1, basophil_row)

        for i, p in enumerate(ordered):
            conn.execute("UPDATE test_parameters SET sort_order=? WHERE id=?", (i + 1, p["id"]))
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


def find_reference_range(conn, test_parameter_id, gender, age, age_unit, patient_id=None, analyzer=None):
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

    patient_id / analyzer (both optional, default None so every existing
    call site keeps working untouched): before any of the age/gender logic
    above, the candidate pool is narrowed by specificity —
      1. rows pinned to this exact patient_id (a private range for a
         special case/treatment) win over everything else for this
         parameter, if any exist.
      2. otherwise, rows pinned to this exact analyzer name (and not
         pinned to any patient) win — e.g. Ferritin on 'E411' vs 'Pure'.
      3. otherwise, the general rows (no patient_id, no analyzer) are used
         — the original behaviour.
    Only after narrowing to one of these pools does the existing age/gender
    matching run, so a private/analyzer range still needs to match the
    patient's age+gender like any other row.
    """
    rows = conn.execute(
        "SELECT * FROM reference_ranges WHERE test_parameter_id=?", (test_parameter_id,)
    ).fetchall()
    if not rows:
        return None

    if patient_id:
        patient_rows = [r for r in rows if r["patient_id"] == patient_id]
    else:
        patient_rows = []
    if patient_rows:
        rows = patient_rows
    else:
        if analyzer:
            analyzer_rows = [
                r for r in rows
                if not r["patient_id"] and r["analyzer"] and r["analyzer"] == analyzer
            ]
        else:
            analyzer_rows = []
        if analyzer_rows:
            rows = analyzer_rows
        else:
            general_rows = [r for r in rows if not r["patient_id"] and not r["analyzer"]]
            # لو ما فيه ولا صف عام أصلاً لهذا الباراميتر (كل الصفوف مخصصة
            # لمريض أو جهاز معيّن) — نرجع لأي صف غير مخصص لمريض ثاني، أفضل
            # من إرجاع None بلا أي مدى طبيعي إطلاقاً.
            rows = general_rows or [r for r in rows if not r["patient_id"]] or rows

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


def ensure_interface_accounts(conn):
    """المطلوب (استبدال نظام تسجيل الدخول الشخصي بواجهات الاستقبال/
    المختبر/الاثنين معًا): عشرات الأماكن بـapp.py تكتب session["user_id"]
    مباشرة لتسجيل "مين سوى شنو" (entered_by، log_action...الخ). بدل ما
    نلمس كل تلك الأماكن (خطر كبير)، نسوي حساب "ظل" واحد بجدول users
    لكل واجهة (Reception/Lab/Together) يُنشأ تلقائيًا أول مرة بس، ويُستخدم
    داخليًا فقط (ما يُدخَل بيه من شاشة تسجيل دخول عادية) -- بمجرد ما
    المستخدم يدخل واجهة معيّنة من الشاشة الرئيسية، جلسته تُربط بحساب تلك
    الواجهة تلقائيًا، فيبقى كل الكود القديم يشتغل بدون أي تعديل."""
    accounts = [
        ("__interface_reception__", "حساب واجهة الاستقبال"),
        ("__interface_lab__", "حساب واجهة المختبر"),
        ("__interface_both__", "حساب واجهة الاستقبال والمختبر معًا"),
    ]
    for username, full_name in accounts:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) "
                "VALUES (?, ?, ?, 'admin', 1, ?)",
                (username, hash_password(os.urandom(16).hex()), full_name, datetime.now().isoformat(timespec="seconds")),
            )
    conn.commit()


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
    ensure_retic_parameters(conn)
    ensure_interface_accounts(conn)
    ensure_nrbc_parameter(conn)
    ensure_atypical_lymphocytes_parameter(conn)
    ensure_reactive_lymphocytes_parameter(conn)
    ensure_basophils_after_eosinophils_order(conn)
    ensure_cbc_comment_parameter(conn)
    ensure_coag_parameters(conn)
    ensure_vldl_parameter(conn)
    apply_client_preset(conn)
    conn.close()


# مفاتيح مسموح لملف التجهيز المسبق (portal_preset.json) يضبطها — لا شي غيرها.
_PRESET_KEYS = {
    "app_name", "app_name_ar", "lab_phone", "lab_address",
    "portal_enabled", "portal_mode", "portal_url", "portal_api_key", "portal_pdf_enabled",
    "portal_default_hours", "portal_ready_when", "portal_retention_days",
}


def apply_client_preset(conn):
    """تجهيز عميل جديد قبل تسليمه البرنامج: ملف portal_preset.json بجانب lis.db (تنشئه أداة
    tools/make_client_package.py) يضبط اسم المختبر وإعدادات بوابة النتائج مرة وحدة عند أول تشغيل،
    ثم يُعاد تسميته إلى portal_preset.applied.json حتى لا يتكرر ولا يطغى على تعديلات العميل لاحقًا.
    ما يكون أبدًا ضمن مستودع التحديثات (يحتوي مفتاح سري خاص بالعميل)."""
    import json
    path = os.path.join(_BASE_DIR, "portal_preset.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        values = data.get("settings", {}) if isinstance(data, dict) else {}
        for key, value in values.items():
            if key in _PRESET_KEYS and value is not None:
                v = str(value).strip()
                if key == "portal_url":
                    v = v.rstrip("/")
                row = conn.execute("SELECT key FROM settings WHERE key=?", (key,)).fetchone()
                if row:
                    conn.execute("UPDATE settings SET value=? WHERE key=?", (v, key))
                else:
                    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, v))
        conn.commit()
        os.replace(path, os.path.join(_BASE_DIR, "portal_preset.applied.json"))
    except (OSError, ValueError):
        pass   # ملف تالف: نتجاهله ولا نوقف تشغيل البرنامج


def ensure_vldl_parameter(conn):
    """يضيف معامل VLDL لتحليل Lipid Profile (LIPID) للقواعد الموجودة مسبقًا —
    هذا المعامل غير موجود أصلاً بقاعدة البيانات القديمة، ويُحسب تلقائيًا من
    Triglycerides ÷ 5 بواجهة إدخال النتائج. يعمل مرة واحدة فقط؛ لا شيء يحدث
    إذا كان المعامل مضافًا مسبقًا. المدى الطبيعي (low/high) يُضاف بجدول
    reference_ranges المنفصل (نفس أسلوب باقي معاملات الاختبارات)، وليس بجدول
    test_parameters نفسه."""
    row = conn.execute("SELECT id FROM test_definitions WHERE code='LIPID'").fetchone()
    if not row:
        return
    test_id = row["id"]
    param_row = conn.execute(
        "SELECT id FROM test_parameters WHERE test_definition_id=? AND name='VLDL'", (test_id,)
    ).fetchone()
    if param_row:
        return
    cur = conn.execute(
        "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
        "VALUES (?, 'VLDL', 'mg/dL', 'Numeric')",
        (test_id,),
    )
    param_id = cur.lastrowid
    conn.execute(
        "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_from_unit, "
        "age_to, age_to_unit, low, high) VALUES (?, 'Both', 0, 'Years', 120, 'Years', 2, 30)",
        (param_id,),
    )
    conn.commit()


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
                          heading_align=None, rows_align=None, unit_column=0):
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_report_template(db, test_definition_id)
    heading_align = heading_align or "center"
    rows_align = rows_align or "right"
    unit_column = 1 if unit_column else 0
    if existing:
        db.execute(
            "UPDATE report_templates SET heading=?, rows_json=?, source_docx_name=COALESCE(?, source_docx_name), "
            "heading_align=?, rows_align=?, unit_column=?, updated_at=? WHERE test_definition_id=?",
            (heading, rows_json, source_docx_name, heading_align, rows_align, unit_column, now, test_definition_id),
        )
    else:
        db.execute(
            "INSERT INTO report_templates (test_definition_id, heading, rows_json, source_docx_name, "
            "heading_align, rows_align, unit_column, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (test_definition_id, heading, rows_json, source_docx_name, heading_align, rows_align, unit_column, user_id, now, now),
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


def save_saved_report(db, visit_id, patient_id, full_name, registration_number,
                       pdf_path, referring_doctor_name=None, referral_center_name=None):
    """يحفظ (أو يحدّث) مسار PDF المحفوظ لزيارة معيّنة في أرشيف التقارير."""
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_saved_report(db, visit_id)
    if existing:
        db.execute(
            "UPDATE saved_reports SET patient_id=?, full_name=?, registration_number=?, "
            "pdf_path=?, referring_doctor_name=?, referral_center_name=?, updated_at=? "
            "WHERE visit_id=?",
            (patient_id, full_name, registration_number, pdf_path,
             referring_doctor_name, referral_center_name, now, visit_id)
        )
    else:
        db.execute(
            "INSERT INTO saved_reports (visit_id, patient_id, full_name, registration_number, "
            "pdf_path, referring_doctor_name, referral_center_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (visit_id, patient_id, full_name, registration_number, pdf_path,
             referring_doctor_name, referral_center_name, now, now)
        )
    db.commit()


def get_saved_report(db, visit_id):
    """يرجع صف التقرير المحفوظ لزيارة معيّنة، أو None إذا ما كان موجود."""
    return db.execute(
        "SELECT * FROM saved_reports WHERE visit_id=?", (visit_id,)
    ).fetchone()


def search_saved_reports(db, q):
    """يبحث عن التقارير المحفوظة بالاسم أو رقم التسجيل أو رقم المريض.
    إذا q فاضي، يرجع كل التقارير مرتبة من الأحدث للأقدم."""
    if not q:
        return db.execute(
            "SELECT * FROM saved_reports ORDER BY updated_at DESC"
        ).fetchall()
    like = f"%{q}%"
    return db.execute(
        "SELECT * FROM saved_reports "
        "WHERE full_name LIKE ? OR registration_number LIKE ? OR patient_id LIKE ? "
        "ORDER BY updated_at DESC",
        (like, like, like)
    ).fetchall()


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


def add_examining_doctor_full(db, name, title, degree_ar, degree_en, show_on_letterhead, font_size=None):
    """يضيف دكتور فحص جديد بكامل تفاصيله من شاشة إدارة الدكاترة.
    font_size: تجاوز اختياري لحجم خط اسمه/شهادته بالترويسة (بكسل)؛ فاضي
    (None) يعني يرث الحجم العام letterhead_font_size من الإعدادات كالمعتاد."""
    name = (name or "").strip()
    if not name:
        return
    max_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) as m FROM examining_doctors_list"
    ).fetchone()["m"]
    db.execute(
        "INSERT INTO examining_doctors_list (name, title, degree_ar, degree_en, sort_order, show_on_letterhead, font_size) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, (title or "").strip() or "الدكتور", degree_ar, degree_en,
         max_order + 1, 1 if show_on_letterhead else 0, font_size),
    )
    db.commit()


def update_examining_doctor(db, doctor_id, name, title, degree_ar, degree_en, show_on_letterhead, font_size=None):
    db.execute(
        "UPDATE examining_doctors_list SET name=?, title=?, degree_ar=?, degree_en=?, show_on_letterhead=?, font_size=? "
        "WHERE id=?",
        ((name or "").strip(), (title or "").strip() or "الدكتور", degree_ar, degree_en,
         1 if show_on_letterhead else 0, font_size, doctor_id),
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


def recompute_examining_doctor_fee(db, visit_id):
    """يعيد حساب أجر دكتور المختبر الفاحص لكل زيارة من الفحوصات الحالية
    غير الملغى أجرها فقط (fee_waived=0) ويحدّث visits.examining_doctor_fee
    مباشرة. يُستدعى بعد أي تبديل لعلامة "تحليل مجاني" (راجع
    toggle_order_test_fee_waiver بـapp.py) وأيضًا من شاشة تعديل الزيارة
    بدل الحساب اليدوي القديم، حتى يبقى المصدر الوحيد لهذا الحساب مكانًا
    واحدًا. لا يستدعي commit بنفسه -- الطرف المستدعي يتحكم بذلك."""
    visit = db.execute("SELECT examining_doctor FROM visits WHERE id=?", (visit_id,)).fetchone()
    if not visit:
        return 0.0
    order = db.execute("SELECT id FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
    test_ids = []
    if order:
        test_ids = [
            r["test_definition_id"] for r in db.execute(
                "SELECT test_definition_id FROM order_tests WHERE order_id=? "
                "AND (fee_waived IS NULL OR fee_waived=0)",
                (order["id"],),
            ).fetchall()
        ]
    fee = compute_examining_doctor_fee(db, visit["examining_doctor"], test_ids)
    db.execute("UPDATE visits SET examining_doctor_fee=? WHERE id=?", (fee, visit_id))
    return fee


# ------------------------------------------------------------------------
# مكتبة الأختام والتواقيع الرقمية (digital_stamps) + مواضعها فوق كل تقرير
# (report_stamp_placements). راجع تعريف الجدولين بأعلى SCHEMA لشرح كامل.
# ------------------------------------------------------------------------
def get_digital_stamps(db, kind=None, active_only=True):
    """كل الأختام/التواقيع المحفوظة، مع اسم الدكتور المرتبط بيها (إن وجد)
    لعرضه بالقائمة المنسدلة. kind لو انمرر يفلتر فقط 'stamp' أو 'signature'
    أو 'stamp_signature'؛ active_only=False تُستخدم بشاشة الإدارة نفسها حتى
    يقدر المدير يشوف/يفعّل الأختام الموقوفة أيضًا."""
    q = ("SELECT ds.*, edl.name as doctor_name FROM digital_stamps ds "
         "LEFT JOIN examining_doctors_list edl ON edl.id = ds.linked_examining_doctor_id WHERE 1=1")
    params = []
    if active_only:
        q += " AND ds.is_active=1"
    if kind:
        q += " AND ds.kind=?"
        params.append(kind)
    q += " ORDER BY ds.sort_order, ds.id"
    return db.execute(q, params).fetchall()


def get_digital_stamp(db, stamp_id):
    return db.execute("SELECT * FROM digital_stamps WHERE id=?", (stamp_id,)).fetchone()


def add_digital_stamp(db, label, kind, image_filename, linked_examining_doctor_id=None,
                       default_width=140, created_by=None, signature_filename=None, is_lab_default=False):
    max_order = db.execute("SELECT COALESCE(MAX(sort_order), -1) as m FROM digital_stamps").fetchone()["m"]
    now = datetime.now().isoformat(timespec="seconds")
    if is_lab_default:
        # ختم مختبر افتراضي وحد بس بأي وقت — تفعيل هذا يلغي أي ختم مختبر
        # افتراضي قديم تلقائيًا (بدون ما يحذفه، فقط يوقف تلقائيته).
        db.execute("UPDATE digital_stamps SET is_lab_default=0 WHERE is_lab_default=1")
    cur = db.execute(
        "INSERT INTO digital_stamps (label, kind, linked_examining_doctor_id, image_filename, "
        "signature_filename, is_lab_default, default_width, sort_order, is_active, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (label, kind, linked_examining_doctor_id or None, image_filename, signature_filename,
         1 if is_lab_default else 0, default_width, max_order + 1, created_by, now),
    )
    db.commit()
    return cur.lastrowid


def update_digital_stamp(db, stamp_id, label, kind, linked_examining_doctor_id=None, is_active=True,
                          is_lab_default=False):
    """تعديل بيانات ختم موجود بدون تغيير صوره (تغيير الصور نفسها يكون
    بحذف الختم وإضافته من جديد، تفاديًا لتعقيد استبدال الملفات على القرص)."""
    if is_lab_default:
        db.execute("UPDATE digital_stamps SET is_lab_default=0 WHERE is_lab_default=1 AND id!=?", (stamp_id,))
    db.execute(
        "UPDATE digital_stamps SET label=?, kind=?, linked_examining_doctor_id=?, is_active=?, is_lab_default=? WHERE id=?",
        (label, kind, linked_examining_doctor_id or None, 1 if is_active else 0,
         1 if is_lab_default else 0, stamp_id),
    )
    db.commit()


def find_stamps_for_report(db, examining_doctor_name):
    """يرجّع قائمة الأختام اللي يُفترض تُلصق تلقائيًا فوق تقرير معيّن —
    بدون أي تدخّل يدوي — بناءً على:
      1) الختم المرتبط باسم "الدكتور الفاحص" المُختار لهذي الزيارة تحديدًا
         (visits.examining_doctor، مطابقة بالاسم مع examining_doctors_list)
      2) + ختم المختبر الافتراضي (is_lab_default) إن وُجد — يُضاف دائمًا
         بغض النظر عن وجود دكتور فاحص من عدمه.
    تُستدعى فقط لو ما فيه أي إلصاق يدوي محفوظ مسبقًا لهذا التقرير بالذات
    (راجع get_stamp_placements بـapp.py قبل استدعاء هذي) — حتى لا تتجاوز
    أي تحريك يدوي سواه المستخدم بنفسه."""
    results = []
    if examining_doctor_name:
        doctor_row = db.execute(
            "SELECT id FROM examining_doctors_list WHERE name=?", (examining_doctor_name,)
        ).fetchone()
        if doctor_row:
            results.extend(db.execute(
                "SELECT * FROM digital_stamps WHERE linked_examining_doctor_id=? AND is_active=1",
                (doctor_row["id"],),
            ).fetchall())
    lab_stamp = db.execute(
        "SELECT * FROM digital_stamps WHERE is_lab_default=1 AND is_active=1 LIMIT 1"
    ).fetchone()
    if lab_stamp:
        results.append(lab_stamp)
    return results


def delete_digital_stamp(db, stamp_id):
    """يحذف الختم من المكتبة وأي أماكن لصقه سابقًا فوق تقارير — لا يحذف
    ملف الصورة نفسه من القرص (يبقى الطرف المستدعي بـapp.py مسؤول عن ذلك
    إن أراد، عبر image_filename المرجَع من get_digital_stamp قبل الحذف)."""
    db.execute("DELETE FROM report_stamp_placements WHERE stamp_id=?", (stamp_id,))
    db.execute("DELETE FROM digital_stamps WHERE id=?", (stamp_id,))
    db.commit()


def get_stamp_placements(db, target_type, target_id):
    """كل الأختام/التواقيع الملصوقة حاليًا فوق تقرير معيّن (زيارة أو تحليل
    مفرد)، بمواضعها بالضبط — تُستخدم لرسمها فوق معاينة/طباعة التقرير."""
    return db.execute(
        "SELECT rsp.*, ds.image_filename, ds.signature_filename, ds.label, ds.kind, ds.default_width "
        "FROM report_stamp_placements rsp JOIN digital_stamps ds ON ds.id = rsp.stamp_id "
        "WHERE rsp.target_type=? AND rsp.target_id=? ORDER BY rsp.id",
        (target_type, target_id),
    ).fetchall()


def upsert_stamp_placement(db, target_type, target_id, stamp_id, pos_x, pos_y, width=None, placed_by=None):
    """يضيف ختمًا جديدًا فوق التقرير أو يحدّث موضعه لو كان ملصوقًا أصلاً
    (نفس stamp_id لنفس target) — بهذا السحب المتكرر لنفس الختم يحرّكه فقط
    بدل ما يكرره. يرجّع id الصف بعد الإضافة/التحديث."""
    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO report_stamp_placements (target_type, target_id, stamp_id, pos_x, pos_y, width, "
        "placed_by, placed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(target_type, target_id, stamp_id) DO UPDATE SET "
        "pos_x=excluded.pos_x, pos_y=excluded.pos_y, width=excluded.width, "
        "placed_by=excluded.placed_by, placed_at=excluded.placed_at",
        (target_type, target_id, stamp_id, pos_x, pos_y, width, placed_by, now),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM report_stamp_placements WHERE target_type=? AND target_id=? AND stamp_id=?",
        (target_type, target_id, stamp_id),
    ).fetchone()["id"]


def remove_stamp_placement(db, placement_id):
    db.execute("DELETE FROM report_stamp_placements WHERE id=?", (placement_id,))
    db.commit()


# ============== تخصيص مظهر التقرير المطبوع (report_layout_overrides) ==============
# راجع شرح الجدول بأعلى SCHEMA. الدمج دائمًا: تخصيص المريض المفرد
# (scope='order_test') يتفوّق على تخصيص نوع التحليل (scope='test') حقل
# حقل — مو استبدال كامل — حتى لو المريض بدّل بس اللون، يبقى الترتيب
# والخط المحفوظين على مستوى التحليل كما هم.
def _get_layout_row(db, scope, scope_id):
    row = db.execute(
        "SELECT layout_json FROM report_layout_overrides WHERE scope=? AND scope_id=?",
        (scope, scope_id),
    ).fetchone()
    if not row:
        return {}
    try:
        parsed = json.loads(row["layout_json"])
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def get_raw_layout(db, scope, scope_id):
    """نفس _get_layout_row لكن عامة (تُستخدم مباشرة من app.py — شاشة تحرير
    التقرير تحتاج القيم الخام غير المدموجة لكل مستوى على حدة، عكس
    get_report_layout اللي ترجّع نسخة مدموجة جاهزة للطباعة فقط)."""
    return _get_layout_row(db, scope, scope_id)


def get_report_layout(db, test_definition_id, order_test_id):
    """يرجّع (merged_layout, has_patient_override). merged_layout جاهز
    يُمرَّر مباشرة كمتغيّر Jinja report_layout للقالب. has_patient_override
    يتحكم بإظهار زر "إرجاع لتصميم افتراضي" (يظهر فقط لو فيه استثناء خاص
    فعلاً بهذا المريض)."""
    test_layout = _get_layout_row(db, "test", test_definition_id)
    patient_layout = _get_layout_row(db, "order_test", order_test_id)
    merged = dict(test_layout)
    for key, value in patient_layout.items():
        if key == "param_overrides" and isinstance(value, dict):
            merged_po = dict(test_layout.get("param_overrides", {}))
            for pname, pval in value.items():
                merged_row = dict(merged_po.get(pname, {}))
                merged_row.update(pval)
                merged_po[pname] = merged_row
            merged["param_overrides"] = merged_po
        else:
            merged[key] = value
    return merged, bool(patient_layout)


def save_report_layout(db, scope, scope_id, layout_dict, user_id=None):
    layout_json = json.dumps(layout_dict, ensure_ascii=False)
    now = datetime.now().isoformat(timespec="seconds")
    existing = db.execute(
        "SELECT id FROM report_layout_overrides WHERE scope=? AND scope_id=?", (scope, scope_id)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE report_layout_overrides SET layout_json=?, updated_by=?, updated_at=? WHERE id=?",
            (layout_json, user_id, now, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO report_layout_overrides (scope, scope_id, layout_json, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope, scope_id, layout_json, user_id, now),
        )
    db.commit()


def reset_report_layout(db, scope, scope_id):
    db.execute("DELETE FROM report_layout_overrides WHERE scope=? AND scope_id=?", (scope, scope_id))
    db.commit()


# ============== أسلوب جدول النتائج (Style A / Style B) + الأعمدة الإضافية ==============
RESULT_STYLES = ("a1", "a2", "b_grid", "b_compact")

RESULT_LABEL_DEFAULTS = {
    "a1": {"test": "Test", "result": "Result", "unit": "Unit", "range": "Normal Range",
           "normal_range": "Normal Range", "previous": "PREVIOUS RESULT", "control": "Control"},
    "a2": {"test": "Test Name", "result": "Result", "unit": "Unit", "range": "Reference Range",
           "normal_range": "Reference Range", "previous": "Previous Result", "control": "Control"},
    "b_grid": {"test": "Test Name", "conv": "Conventional Units", "si": "SI Units",
               "normal_range": "Normal Range", "previous": "Previous Result", "control": "Control"},
    "b_compact": {"normal_range": "Normal Range", "previous": "Previous Result", "control": "Control"},
}

RESULT_LAYOUT_DEFAULTS = {
    "style": "b_grid",          # الافتراضي = شكل custom_v2 الحالي (Style B matching image 1)
    "labels": {},               # style -> {key: text} تسميات مخصصة تتغلب على الافتراضي
    "extra_cols": [],           # [{"id","title","after","show"}]
    "colors": {"head_bg": "", "head_text": "", "name": "", "result": "", "prev": "", "line": "", "label": ""},
    "prev_count": 2,
    "prev_default_show": 1,
    "theme": "default",         # default | green (ألوان الصور المخصصة) | custom (ألواني اليدوية)
    "prev_order": "desc",       # desc = الأحدث أولاً ، asc = الأقدم أولاً
    "dept_headings": "auto",    # auto (A نعم / B لا) | show | hide
    "merged_title": "تقرير الكيمياء الحيوية والهرمونات والفيتامينات",
    "merged_exclude": "",       # فاضي = القائمة الافتراضية (MERGED_EXCLUDE_DEFAULT)
    # المسافة (بالبكسل) بين قيمة النتيجة ووحدتها -- إعداد مستقل عن الثيم (مو لون)
    # فينطبق بكل الأحوال على الأساليب الأربعة سوا.
    "unit_gap": 6,
    "show_prev_visit_line": 0,  # سطر "زيارة سابقة بتاريخ: ..." القديم أسفل التقرير (اختياري، مخفي افتراضيًا)
}


def get_result_layout(db):
    """إعداد أسلوب جدول النتائج (عام لكل التقارير)."""
    raw = get_setting(db, "result_layout_json", "")
    cfg = json.loads(json.dumps(RESULT_LAYOUT_DEFAULTS))
    if raw:
        try:
            saved = json.loads(raw)
        except (TypeError, ValueError):
            saved = {}
        if isinstance(saved, dict):
            for k in ("style", "prev_count", "prev_default_show", "show_prev_visit_line", "theme", "prev_order",
                      "dept_headings", "merged_title", "merged_exclude", "unit_gap"):
                if k in saved:
                    cfg[k] = saved[k]
            if isinstance(saved.get("labels"), dict):
                cfg["labels"] = saved["labels"]
            if isinstance(saved.get("extra_cols"), list):
                cfg["extra_cols"] = [c for c in saved["extra_cols"] if isinstance(c, dict) and c.get("id")]
            if isinstance(saved.get("colors"), dict):
                cfg["colors"].update({k: str(v) for k, v in saved["colors"].items() if k in cfg["colors"]})
    if cfg["style"] not in RESULT_STYLES:
        cfg["style"] = "b_grid"
    try:
        cfg["prev_count"] = max(0, min(20, int(cfg["prev_count"])))
    except (TypeError, ValueError):
        cfg["prev_count"] = 2
    cfg["prev_default_show"] = 1 if str(cfg.get("prev_default_show", 1)) in ("1", "True", "true") else 0
    try:
        cfg["unit_gap"] = max(0, min(40, int(cfg.get("unit_gap", 6))))
    except (TypeError, ValueError):
        cfg["unit_gap"] = 6
    if cfg["theme"] not in ("default", "green", "custom"):
        cfg["theme"] = "default"
    if cfg["prev_order"] not in ("asc", "desc"):
        cfg["prev_order"] = "desc"
    if cfg["dept_headings"] not in ("auto", "show", "hide"):
        cfg["dept_headings"] = "auto"
    cfg["show_prev_visit_line"] = 1 if str(cfg.get("show_prev_visit_line", 0)) in ("1", "True", "true") else 0
    return cfg


def effective_labels(cfg, style=None):
    style = style or cfg["style"]
    out = dict(RESULT_LABEL_DEFAULTS.get(style, {}))
    for k, v in (cfg.get("labels", {}).get(style, {}) or {}).items():
        if v is not None and str(v).strip() != "":
            out[k] = str(v).strip()
    return out


def save_result_layout(db, cfg):
    set_setting(db, "result_layout_json", json.dumps(cfg, ensure_ascii=False))
    db.commit()


def get_extra_col_values(db):
    """{extra_id: {"<test_definition_id>|<param name>": نص}} — قيم الأعمدة الإضافية لكل باراميتر."""
    raw = get_setting(db, "result_extra_values_json", "")
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save_extra_col_values(db, data):
    set_setting(db, "result_extra_values_json", json.dumps(data, ensure_ascii=False))
    db.commit()


def _fmt_date_dmy(iso):
    try:
        dt = datetime.fromisoformat(iso)
        return f"{dt.day:02d}/{dt.month:02d}/{dt.year}"
    except (TypeError, ValueError):
        return iso or ""


def get_previous_history(db, visit_id, test_definition_id, limit=2, order="desc"):
    """آخر `limit` نتائج سابقة لنفس المريض (نفس الشخص بالـ id أو بالاسم+العمر)
    لنفس التحليل، من زيارات أقدم من الزيارة الحالية. ترجع
    {اسم الباراميتر: [{"date": "14/02/2026", "value": ...}, ...]} (الأحدث أولاً)."""
    if not limit or limit < 1:
        return {}
    cur = db.execute(
        "SELECT v.created_at, v.patient_id, p.full_name, p.age FROM visits v "
        "JOIN patients p ON p.id = v.patient_id WHERE v.id=?", (visit_id,)).fetchone()
    if not cur:
        return {}
    cands = db.execute(
        "SELECT ot.id AS otid, v.id AS vid, v.created_at FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE ot.test_definition_id=? AND v.id<>? AND v.created_at < ? "
        "AND ot.status IN ('Completed','Verified') "
        "AND (v.patient_id=? OR (LOWER(TRIM(p.full_name))=LOWER(TRIM(?)) AND p.age=?)) "
        "ORDER BY v.created_at DESC, ot.id DESC",
        (test_definition_id, visit_id, cur["created_at"], cur["patient_id"], cur["full_name"] or "", cur["age"]),
    ).fetchall()
    seen_visits, chosen = set(), []
    for c in cands:
        if c["vid"] in seen_visits:
            continue
        seen_visits.add(c["vid"])
        chosen.append(c)
        if len(chosen) >= limit:
            break
    if order == "asc":
        chosen = list(reversed(chosen))
    hist = {}
    for c in chosen:
        rows = db.execute(
            "SELECT r.value_text, r.value_numeric, tp.name AS pname FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
            (c["otid"],)).fetchall()
        for r in rows:
            val = r["value_text"] if r["value_text"] not in (None, "") else r["value_numeric"]
            if val in (None, ""):
                continue
            hist.setdefault(r["pname"], []).append({"date": _fmt_date_dmy(c["created_at"]), "value": val})
    return hist


def get_row_notes(db, visit_id):
    rows = db.execute(
        "SELECT row_key, note_text, note_label, show FROM report_row_notes WHERE visit_id=?", (visit_id,)
    ).fetchall()
    return {r["row_key"]: {"text": r["note_text"] or "", "label": r["note_label"] or "",
                           "show": bool(r["show"])} for r in rows}


def save_row_note(db, visit_id, row_key, text, label, show):
    now = datetime.now().isoformat(timespec="seconds")
    text = (text or "").strip()
    if not text:
        db.execute("DELETE FROM report_row_notes WHERE visit_id=? AND row_key=?", (visit_id, row_key))
    else:
        db.execute(
            "INSERT INTO report_row_notes (visit_id, row_key, note_text, note_label, show, updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(visit_id, row_key) DO UPDATE SET "
            "note_text=excluded.note_text, note_label=excluded.note_label, show=excluded.show, "
            "updated_at=excluded.updated_at",
            (visit_id, row_key, text, (label or "").strip(), 1 if show else 0, now))
    db.commit()


THEME_PRESETS = {
    "default": {},
    # ألوان الصور "Custom colors": شريط أخضر، أسماء بنفسجية، نتائج برتقالية، سابقة بتركوازي
    "green": {"head_bg": "#065F46", "head_text": "#FFFFFF", "name": "#6D28D9", "result": "#C2410C",
              "prev": "#0F766E", "label": "#065F46"},
}

# تحاليل ما تدخل التقرير الشامل (تُطابَق بكود التحليل أو اسمه، حروف صغيرة/كبيرة سواء)
MERGED_EXCLUDE_DEFAULT = [
    "cbc", "blood film", "retic", "bma", "bmp", "bone marrow", "fluid",
    "hb.h", "hb h", "hbh", "electroph", "sickl",
]


def merged_exclude_keywords(cfg):
    raw = (cfg.get("merged_exclude") or "").strip()
    kws = [ln.strip().lower() for ln in raw.splitlines() if ln.strip()]
    return kws or list(MERGED_EXCLUDE_DEFAULT)


def resolve_theme_colors(cfg, theme=None):
    theme = theme or cfg.get("theme", "default")
    out = dict(THEME_PRESETS.get(theme, {}))
    if theme == "custom":
        out = {k: v for k, v in cfg.get("colors", {}).items() if v}
    return out


def get_visit_prev_pref(db, visit_id):
    r = db.execute("SELECT prev_count FROM visit_prev_prefs WHERE visit_id=?", (visit_id,)).fetchone()
    return None if r is None else int(r["prev_count"])


def set_visit_prev_pref(db, visit_id, count):
    count = max(0, min(20, int(count)))
    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO visit_prev_prefs (visit_id, prev_count, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(visit_id) DO UPDATE SET prev_count=excluded.prev_count, updated_at=excluded.updated_at",
        (visit_id, count, now))
    db.commit()
    return count


def effective_prev_count(db, visit_id, cfg, has_merge=False):
    """عدد الزيارات السابقة الفعلي لهذي الزيارة: اختيار الموظف إن وُجد (0 = إلغاء)،
    وإلا لو فيه موافقة دمج قديمة → الافتراضي من الإعدادات، وإلا 0 (لا عرض تلقائي)."""
    pref = get_visit_prev_pref(db, visit_id)
    if pref is not None:
        return pref
    return cfg["prev_count"] if has_merge else 0


# ============== رقم العينة (Sample No.) ==============
def get_sample_no_settings(db):
    pad = get_setting(db, "sample_no_padding", "3")
    return {
        "reset": get_setting(db, "sample_no_reset", "daily"),        # daily | monthly | yearly | never
        "prefix": get_setting(db, "sample_no_prefix", ""),
        "date_part": get_setting(db, "sample_no_date_part", "none"),  # none | yymmdd | yymm | yy
        "padding": int(pad) if str(pad).isdigit() else 3,
    }


def _sample_period_key(reset, dt):
    if reset == "daily":
        return dt.strftime("%Y-%m-%d")
    if reset == "monthly":
        return dt.strftime("%Y-%m")
    if reset == "yearly":
        return dt.strftime("%Y")
    return "all"


def format_sample_no(cfg, dt, seq):
    date_fmt = {"yymmdd": "%y%m%d", "yymm": "%y%m", "yy": "%y"}.get(cfg["date_part"], "")
    return f"{cfg['prefix']}{dt.strftime(date_fmt) if date_fmt else ''}{str(seq).zfill(cfg['padding'])}"


def peek_next_sample_no(db, now=None):
    """الرقم التالي (بدون حجزه) — يظهر مسبقًا بحقل صفحة زيارة جديدة."""
    now = now or datetime.now()
    cfg = get_sample_no_settings(db)
    row = db.execute("SELECT last_value FROM sample_counters WHERE period_key=?",
                     (_sample_period_key(cfg["reset"], now),)).fetchone()
    return format_sample_no(cfg, now, (row["last_value"] if row else 0) + 1)


def allocate_sample_no(db, now=None):
    """يحجز الرقم التالي فعليًا (يزيد العدّاد) ويرجّعه."""
    now = now or datetime.now()
    cfg = get_sample_no_settings(db)
    key = _sample_period_key(cfg["reset"], now)
    db.execute("INSERT OR IGNORE INTO sample_counters (period_key, last_value) VALUES (?, 0)", (key,))
    db.execute("UPDATE sample_counters SET last_value = last_value + 1 WHERE period_key=?", (key,))
    seq = db.execute("SELECT last_value FROM sample_counters WHERE period_key=?", (key,)).fetchone()["last_value"]
    return format_sample_no(cfg, now, seq)


def resolve_visit_sample_no(db, typed, now=None):
    """النص المكتوب بالحقل: فاضي أو نفس الرقم المقترح ← نحجز الرقم التلقائي؛
    رقم مختلف (كتبه الموظف يدويًا) ← نحفظه كما هو بدون ما نحرّك العدّاد."""
    typed = (typed or "").strip()[:40]
    if not typed or typed == peek_next_sample_no(db, now):
        return allocate_sample_no(db, now)
    return typed


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)


# ============== دمج نتائج الزيارة السابقة (visit_previous_merges) ==============
def find_last_visit_by_name_age(db, full_name, age, exclude_patient_id=None):
    """آخر زيارة سابقة (الأحدث) لمريض بنفس الاسم الثلاثي + العمر بالضبط —
    تُستخدم بشاشة 'زيارة جديدة' لحظة كتابة الاسم والعمر لاكتشاف مراجعة
    سابقة. exclude_patient_id اختياري (مو مستخدم حاليًا، محجوز لو احتجنا
    نستثني نفس بطاقة المريض المختارة يدويًا مستقبلاً)."""
    return db.execute(
        "SELECT v.id as visit_id, v.created_at, p.id as patient_id, p.full_name, p.age, p.age_unit, p.gender "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "WHERE LOWER(TRIM(p.full_name)) = LOWER(TRIM(?)) AND p.age = ? "
        "ORDER BY v.created_at DESC LIMIT 1",
        (full_name or "", age),
    ).fetchone()


def get_visit_completed_tests(db, visit_id):
    """كل تحاليل هذي الزيارة اللي عندها نتيجة مكتملة/معتمدة — تُستخدم لعرض
    خيارات الدمج (Biochemistry/Hormones/...) أو رسالة إعلامية بس
    (Blood Film/Retic/...) بشاشة 'زيارة جديدة'."""
    return db.execute(
        "SELECT ot.id as order_test_id, ot.test_definition_id, td.name as test_name, "
        "td.code as test_code, td.department FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "WHERE ot.order_id IN (SELECT id FROM orders WHERE visit_id=?) "
        "AND ot.status IN ('Completed', 'Verified') ORDER BY ot.id",
        (visit_id,),
    ).fetchall()


def save_visit_previous_merges(db, visit_id, source_order_test_ids):
    """يسجّل موافقة الموظف على دمج كل تحليل قديم اختاره (من نافذة تنبيه
    الزيارة السابقة) — يُستدعى مرة وحدة بعد إنشاء الزيارة الجديدة."""
    now = datetime.now().isoformat(timespec="seconds")
    for otid in source_order_test_ids:
        try:
            db.execute(
                "INSERT OR IGNORE INTO visit_previous_merges "
                "(visit_id, source_order_test_id, approved_by, approved_at) VALUES (?, ?, ?, ?)",
                (visit_id, int(otid), None, now),
            )
        except (TypeError, ValueError):
            continue
    db.commit()


def get_visit_previous_merges(db, visit_id):
    """كل التحاليل القديمة الموافَق على دمجها بهذي الزيارة تحديدًا، مع
    اسم التحليل وقسمه وتاريخ زيارتها الأصلية ونتائجها — تُستخدم من طبقة
    التقارير (المفرد والمجمّع) لعرض صف/بطاقة 'Previous' فقط لما توجد
    موافقة صريحة، بدون أي عرض تلقائي."""
    rows = db.execute(
        "SELECT vpm.source_order_test_id, ot.test_definition_id, td.name as test_name, "
        "td.code as test_code, td.department, v.created_at as source_visit_created_at "
        "FROM visit_previous_merges vpm "
        "JOIN order_tests ot ON ot.id = vpm.source_order_test_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id JOIN visits v ON v.id = o.visit_id "
        "WHERE vpm.visit_id=?",
        (visit_id,),
    ).fetchall()
    out = []
    for row in rows:
        results = db.execute(
            "SELECT r.*, tp.name as param_name FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
            (row["source_order_test_id"],),
        ).fetchall()
        try:
            dt = datetime.fromisoformat(row["source_visit_created_at"])
            date_display = f"{dt.day}/{dt.month}/{dt.year}"
        except (TypeError, ValueError):
            date_display = row["source_visit_created_at"] or ""
        out.append({
            "source_order_test_id": row["source_order_test_id"],
            "test_definition_id": row["test_definition_id"],
            "test_name": row["test_name"],
            "test_code": row["test_code"],
            "department": row["department"],
            "date_display": date_display,
            "results": {r["param_name"]: (r["value_text"] if r["value_text"] not in (None, "") else r["value_numeric"]) for r in results},
        })
    return out
