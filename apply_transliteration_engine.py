# -*- coding: utf-8 -*-
"""
apply_transliteration_engine.py
=================================
يضيف محرك التحويل الصوتي (عربي -> إنكليزي) لاسم المريض، ويربطه تلقائيًا
بكل مكان يُحفظ فيه اسم مريض (new_visit, patient_new, patient_edit,
visit_edit) — بنسخة احتياطية أول، وبدون لمس أي شي غير محدد بالضبط.

المنطق: إذا الفورم أرسل حقل "patient_name_en" أو "full_name_en" يدويًا
(مستقبلاً لو أضفنا حقل تعديل يدوي بالواجهة)، يُستخدم هو كما هو. إذا لا،
يُحسب تلقائيًا بالتحويل الصوتي من الاسم العربي.

طريقة التشغيل: بنفس مجلد app.py:
    python apply_transliteration_engine.py
"""
import shutil
import time

APP_FILE = "app.py"

with open(APP_FILE, "r", encoding="utf-8") as f:
    content = f.read()

lines_before = content.count("\n")
changes = []
problems = []


def try_replace(label, old, new):
    global content
    count = content.count(old)
    if count == 1:
        content = content.replace(old, new, 1)
        changes.append(f"✅ {label}")
    else:
        problems.append(f"⚠️ {label}: عدد المطابقات {count} (متوقع 1) — تجاوزته.")


# ---- 1) إضافة محرك التحويل الصوتي نفسه ----
ENGINE_ANCHOR = "from daily_counter import get_patient_number_of_day"
ENGINE_CODE = '''

ARABIC_NAME_TRANSLITERATION_MAP = [
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
    """يرجّع اقتراح إنكليزي أولي لاسم عربي (تحويل صوتي تقريبي) — اقتراح
    فقط، قابل للتعديل يدويًا لاحقًا من الواجهة."""
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
    return " ".join(w.capitalize() if w else w for w in result.split(" "))
'''
try_replace("أُضيف محرك التحويل الصوتي (transliterate_arabic_name)",
            ENGINE_ANCHOR, ENGINE_ANCHOR + ENGINE_CODE)

# ---- 2) new_visit: INSERT INTO patients ----
try_replace(
    "new_visit: يحفظ full_name_en تلقائيًا لمريض جديد",
    '''            cur = db.execute(
                "INSERT INTO patients (full_name, gender, age, age_unit, phone, address, contact_method, "
                "title, email, national_id, passport_number, travel_certificate_number, lab_card_number, "
                "branch_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, gender, age, age_unit, phone, address, contact_method,
                 title, email, national_id, passport_number, travel_certificate_number, lab_card_number,
                 session.get("branch_id"), now),
            )''',
    '''            name_en = (request.form.get("patient_name_en") or "").strip() or transliterate_arabic_name(name)
            cur = db.execute(
                "INSERT INTO patients (full_name, full_name_en, gender, age, age_unit, phone, address, contact_method, "
                "title, email, national_id, passport_number, travel_certificate_number, lab_card_number, "
                "branch_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, name_en, gender, age, age_unit, phone, address, contact_method,
                 title, email, national_id, passport_number, travel_certificate_number, lab_card_number,
                 session.get("branch_id"), now),
            )''',
)

# ---- 3) patient_new: INSERT INTO patients ----
try_replace(
    "patient_new: يحفظ full_name_en تلقائيًا",
    '''        db.execute(
            "INSERT INTO patients (full_name, gender, age, age_unit, phone, email, address, national_id, "
            "passport_number, lab_card_number, contact_method, title, travel_certificate_number, "
            "branch_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request.form.get("full_name", "").strip(), request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("email"),
             request.form.get("address"), request.form.get("national_id"),
             request.form.get("passport_number"), request.form.get("lab_card_number"),
             request.form.get("contact_method", "None"), request.form.get("title", "Mr."),
             request.form.get("travel_certificate_number"), session.get("branch_id"), now),
        )''',
    '''        _pn_name = request.form.get("full_name", "").strip()
        _pn_name_en = (request.form.get("full_name_en") or "").strip() or transliterate_arabic_name(_pn_name)
        db.execute(
            "INSERT INTO patients (full_name, full_name_en, gender, age, age_unit, phone, email, address, national_id, "
            "passport_number, lab_card_number, contact_method, title, travel_certificate_number, "
            "branch_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_pn_name, _pn_name_en, request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("email"),
             request.form.get("address"), request.form.get("national_id"),
             request.form.get("passport_number"), request.form.get("lab_card_number"),
             request.form.get("contact_method", "None"), request.form.get("title", "Mr."),
             request.form.get("travel_certificate_number"), session.get("branch_id"), now),
        )''',
)

# ---- 4) patient_edit: UPDATE patients ----
try_replace(
    "patient_edit: يحدّث full_name_en تلقائيًا",
    '''        db.execute(
            "UPDATE patients SET full_name=?, gender=?, age=?, age_unit=?, phone=?, email=?, address=?, "
            "national_id=?, passport_number=?, lab_card_number=?, contact_method=?, title=?, "
            "travel_certificate_number=? WHERE id=?",
            (request.form.get("full_name", "").strip(), request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("email"),
             request.form.get("address"), request.form.get("national_id"),
             request.form.get("passport_number"), request.form.get("lab_card_number"),
             request.form.get("contact_method", "None"), request.form.get("title", "Mr."),
             request.form.get("travel_certificate_number"), patient_id),
        )''',
    '''        _pe_name = request.form.get("full_name", "").strip()
        _pe_name_en = (request.form.get("full_name_en") or "").strip() or transliterate_arabic_name(_pe_name)
        db.execute(
            "UPDATE patients SET full_name=?, full_name_en=?, gender=?, age=?, age_unit=?, phone=?, email=?, address=?, "
            "national_id=?, passport_number=?, lab_card_number=?, contact_method=?, title=?, "
            "travel_certificate_number=? WHERE id=?",
            (_pe_name, _pe_name_en, request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("email"),
             request.form.get("address"), request.form.get("national_id"),
             request.form.get("passport_number"), request.form.get("lab_card_number"),
             request.form.get("contact_method", "None"), request.form.get("title", "Mr."),
             request.form.get("travel_certificate_number"), patient_id),
        )''',
)

# ---- 5) visit_edit: UPDATE patients ----
try_replace(
    "visit_edit: يحدّث full_name_en تلقائيًا",
    '''        db.execute(
            "UPDATE patients SET full_name=?, gender=?, age=?, age_unit=?, phone=?, title=?, email=?, "
            "national_id=?, passport_number=?, travel_certificate_number=?, lab_card_number=? WHERE id=?",
            (request.form.get("patient_name", "").strip(), request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("title", "Mr."), request.form.get("email", "").strip(),
             request.form.get("national_id", "").strip(), request.form.get("passport_number", "").strip(),
             request.form.get("travel_certificate_number", "").strip(), request.form.get("lab_card_number", "").strip(),
             visit["patient_id"]),
        )''',
    '''        _ve_name = request.form.get("patient_name", "").strip()
        _ve_name_en = (request.form.get("patient_name_en") or "").strip() or transliterate_arabic_name(_ve_name)
        db.execute(
            "UPDATE patients SET full_name=?, full_name_en=?, gender=?, age=?, age_unit=?, phone=?, title=?, email=?, "
            "national_id=?, passport_number=?, travel_certificate_number=?, lab_card_number=? WHERE id=?",
            (_ve_name, _ve_name_en, request.form.get("gender"),
             request.form.get("age") or None, request.form.get("age_unit") or "Years",
             request.form.get("phone"), request.form.get("title", "Mr."), request.form.get("email", "").strip(),
             request.form.get("national_id", "").strip(), request.form.get("passport_number", "").strip(),
             request.form.get("travel_certificate_number", "").strip(), request.form.get("lab_card_number", "").strip(),
             visit["patient_id"]),
        )''',
)

if not changes:
    print("لم يتم أي تعديل. المشاكل:")
    for p in problems:
        print(" ", p)
else:
    backup_name = f"{APP_FILE}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(APP_FILE, backup_name)
    with open(APP_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    lines_after = content.count("\n")
    print("=== النتيجة ===")
    for c in changes:
        print(c)
    if problems:
        print("\nتنبيهات (راجعها يدويًا):")
        for p in problems:
            print(" ", p)
    print(f"\nنسخة احتياطية: {backup_name}")
    print(f"عدد الأسطر: {lines_before} → {lines_after}")
