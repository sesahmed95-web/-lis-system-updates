from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_file, jsonify
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape
from io import BytesIO
import os
import json
import re
import subprocess
import webbrowser
import shutil
import sqlite3
import tempfile
import zipfile

from database import (get_db, init_db, hash_password, get_setting, set_setting,
                       get_test_price, find_or_create_doctor, find_or_create_referral_center,
                       get_report_template, save_report_template,
                       get_examining_doctors, set_examining_doctors, add_examining_doctor,
                       get_examining_doctors_full, add_examining_doctor_full,
                       update_examining_doctor, delete_examining_doctor, move_examining_doctor,
                       get_letterhead_doctors,
                       get_examining_tests, get_examining_rates_map,
                       set_examining_doctor_rate, compute_examining_doctor_fee,
                       recompute_examining_doctor_fee,
                       find_reference_range,
                       save_saved_report, get_saved_report, search_saved_reports,
                       get_digital_stamps, get_digital_stamp, add_digital_stamp,
                       update_digital_stamp, delete_digital_stamp,
                       get_stamp_placements, upsert_stamp_placement, remove_stamp_placement,
                       get_report_layout, save_report_layout, reset_report_layout, get_raw_layout,
                       find_last_visit_by_name_age, get_visit_completed_tests,
                       save_visit_previous_merges, get_visit_previous_merges)
from daily_counter import get_patient_number_of_day

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


# قاموس أسماء عربية/عراقية شائعة جاهزة بترجمتها الإنكليزية المعتمدة —
# هذا هو الحل العملي الوحيد لمشكلة الحروف المتحركة القصيرة غير المكتوبة
# بالعربي (مثال: "سمر" حروفها فقط س-م-ر، ما فيها أي حرف يدل على الفتحة بين
# الحروف، فالخوارزمية الحرف-بحرف تطلعها "Smr" مهما حاولنا نحسّنها، لأنها
# فعليًا ما "ترى" الحركة القصيرة). لأي اسم موجود هنا، تُستخدم هذي الترجمة
# مباشرة بدل الخوارزمية. القائمة قابلة للتوسيع من الإعدادات (راجع
# get_name_translit_overrides) بدون الحاجة لتعديل الكود لكل اسم جديد.
COMMON_NAME_TRANSLITERATIONS = {
    "سمر": "Samar", "عمر": "Omar", "بشرى": "Bushra", "بشار": "Bashar",
    "زهراء": "Zahraa", "زهرة": "Zahra", "نور": "Noor", "نورا": "Noora",
    "هدى": "Huda", "رنا": "Rana", "رشا": "Rasha", "دينا": "Dina", "هبة": "Hiba",
    "سارة": "Sara", "سارا": "Sara", "مريم": "Mariam", "ليلى": "Layla",
    "فاطمة": "Fatima", "زينب": "Zainab", "خديجة": "Khadija", "عائشة": "Aisha",
    "آية": "Aya", "أمل": "Amal", "امل": "Amal", "أسماء": "Asmaa", "اسماء": "Asmaa",
    "ياسمين": "Yasmin", "شيماء": "Shaimaa", "إيمان": "Eman", "ايمان": "Eman",
    "منى": "Mona", "سلمى": "Salma", "لينا": "Lina", "رغد": "Raghad",
    "تبارك": "Tabarak", "ملك": "Malak", "جنى": "Jana", "غدير": "Ghadeer",
    "بتول": "Batool", "دعاء": "Duaa", "ابتسام": "Ibtisam", "وفاء": "Wafaa",
    "أحمد": "Ahmed", "احمد": "Ahmed", "محمد": "Mohammed", "محمود": "Mahmoud",
    "علي": "Ali", "حسين": "Hussein", "حسن": "Hassan", "كريم": "Karim",
    "يوسف": "Yousif", "إبراهيم": "Ibrahim", "ابراهيم": "Ibrahim",
    "عبدالله": "Abdullah", "عبد الله": "Abdullah", "خالد": "Khalid",
    "سعد": "Saad", "سعيد": "Saeed", "طارق": "Tariq", "زياد": "Ziad",
    "مصطفى": "Mustafa", "مهند": "Mohanad", "منتظر": "Muntadher",
    "حيدر": "Haider", "قاسم": "Qasim", "جعفر": "Jafar", "ثامر": "Thamer",
    "وليد": "Walid", "سامر": "Samer", "زيد": "Zaid", "فراس": "Firas",
    "عدنان": "Adnan", "رياض": "Riyadh", "باسل": "Basil", "نبيل": "Nabil",
    "أنور": "Anwar", "انور": "Anwar", "جاسم": "Jasim", "كاظم": "Kadhim",
    "صادق": "Sadiq", "ناصر": "Nasser", "فؤاد": "Fouad", "غانم": "Ghanim",
    "رعد": "Raad", "سيف": "Saif", "أمير": "Ameer", "امير": "Ameer",
    "دانيال": "Daniel", "آدم": "Adam", "ادم": "Adam", "يحيى": "Yahya",
    "عمار": "Ammar", "فادي": "Fadi", "رافد": "Rafid", "أنس": "Anas", "انس": "Anas",
    "بلال": "Bilal", "سلام": "Salam", "حازم": "Hazim", "ماجد": "Majid",
}


def get_name_translit_overrides(db):
    """تصحيحات ترجمة أسماء يضيفها المختبر بنفسه من الإعدادات (سطر لكل اسم
    بصيغة "عربي=إنكليزي") — تأخذ أولوية حتى فوق القاموس الجاهز أعلاه،
    فتسمح بتصحيح أي اسم يطلع غلط دون الحاجة لتعديل الكود."""
    raw = get_setting(db, "name_translit_overrides", "")
    overrides = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        ar, _, en = line.partition("=")
        ar, en = ar.strip(), en.strip()
        if ar and en:
            overrides[ar] = en
    return overrides


def _translit_word_fallback(word):
    """الخوارزمية الاحتياطية حرف-بحرف — تُستخدم فقط للكلمات غير الموجودة
    بالقاموس أعلاه ولا بتصحيحات الإعدادات. تحشر حرف "a" تخمينيًا بين حرفين
    ساكنين متتاليين (زي "سمر" لو ما كانت بالقاموس: s+m+r → Samar) لتقريب
    النطق، لكنها تبقى تخمينًا وليست مضمونة الدقة 100% — العربي المكتوب
    عادة ما يحدد الحركات القصيرة أصلاً، فمافي خوارزمية تقدر "تخمّنها" دايمًا
    صح؛ التغطية المضمونة الوحيدة هي عبر القاموس/تصحيحات الإعدادات أعلاه."""
    if not word:
        return ""
    chunks = []
    i, n = 0, len(word)
    while i < n:
        matched = False
        for ar, en in ARABIC_NAME_TRANSLITERATION_MAP:
            if ar != " " and word[i:i + len(ar)] == ar:
                chunks.append(en)
                i += len(ar)
                matched = True
                break
        if not matched:
            chunks.append(word[i])
            i += 1

    def has_vowel(chunk):
        return any(c in "aeiou" for c in chunk.lower())

    out = []
    for idx, chunk in enumerate(chunks):
        if (
            idx > 0 and chunk and out and out[-1]
            and not has_vowel(chunk) and not has_vowel(out[-1])
            and out[-1][-1].isalpha() and chunk[0].isalpha()
        ):
            out.append("a")
        out.append(chunk)
    return "".join(out)


def transliterate_arabic_name(name, db=None):
    """يرجّع اقتراح إنكليزي لاسم عربي — اقتراح قابل للتعديل يدويًا لاحقًا من
    الواجهة. الأولوية: (1) تصحيحات الإعدادات الخاصة بهذا المختبر، (2) قاموس
    الأسماء الشائعة الجاهز، (3) خوارزمية تقريبية حرف-بحرف لأي اسم غير معروف
    (راجع _translit_word_fallback لسبب كونها تقريبية وليست مضمونة الدقة —
    محدودية بالعربي نفسه، مو بالكود). تُطبَّق كلمة-كلمة حتى تشتغل مع الأسماء
    المركّبة (اسم + اسم أب + اسم جد...الخ)."""
    if not name:
        return ""
    if db is None:
        try:
            db = get_db()
        except Exception:
            db = None
    overrides = get_name_translit_overrides(db) if db is not None else {}
    words_out = []
    for word in name.strip().split(" "):
        if not word:
            continue
        if word in overrides:
            words_out.append(overrides[word])
        elif word in COMMON_NAME_TRANSLITERATIONS:
            words_out.append(COMMON_NAME_TRANSLITERATIONS[word])
        else:
            words_out.append(_translit_word_fallback(word).capitalize())
    return " ".join(words_out)



from translations import t
from barcode_gen import generate_code39, generate_code128, generate_qr
import astm_host
import license_manager
import auto_updater
import secrets
import faulthandler

# ------------------------------------------------------------------------
# شبكة أمان لتسجيل كراش أعمق من خطأ بايثون العادي (segfault/stack overflow
# نادر يقفل العملية كاملة بدون أي traceback بالتيرمينال) — faulthandler
# فقط، بدون أي errorhandler عام (كان سبب كسر كل الصفحات بمحاولة سابقة).
# يُكتب بملف crash_log.txt بمجلد البرنامج نفسه — راجعه أول شي لو انغلق
# البرنامج فجأة بدون أي رسالة حمراء بالتيرمينال.
_CRASH_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_log.txt")
try:
    _crash_log_file = open(_CRASH_LOG_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_crash_log_file, all_threads=True)
except Exception:
    _crash_log_file = None

app = Flask(__name__)
# مفتاح جلسة عشوائي مختلف بكل مرة يُشغَّل فيها السيرفر فعليًا (وليس نفس
# نص ثابت دائمًا) — بهذا الشكل أي كوكي دخول قديم صار غير صالح تلقائيًا بعد
# أي إعادة تشغيل حقيقية للبرنامج (إعادة تشغيل الجهاز، إيقاف ثم تشغيل من
# جديد...)، فيُطلب اسم المستخدم وكلمة المرور من جديد بشكل مضمون، بدل أن
# يبقى المتصفح مسجّل دخول تلقائيًا لأشهر لمجرد أن الكوكي القديم لسا شغّال.
app.secret_key = secrets.token_hex(32)
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 days when "remember me" is checked

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_LOGO_EXT = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
# صور الأختام/التواقيع — بدون svg (نحتاج نفتحها بمكتبة الصور Pillow لتحويل
# أي خلفية شفافة/ملوّنة إلى خلفية بيضاء صلبة، وsvg متجه وليس بكسلي فلا يدعمه
# نفس المسار).
ALLOWED_STAMP_EXT = {"png", "jpg", "jpeg", "webp"}
STAMPS_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "stamps")
os.makedirs(STAMPS_UPLOAD_DIR, exist_ok=True)
# صور خلفية شاشة الترحيب (dashboard) — صور فوتوغرافية بس، بدون svg/gif
# (svg ما إله فايدة كخلفية ممتدة، وgif المتحرك يشتت الانتباه بشاشة ترحيب).
ALLOWED_DASHBOARD_BG_EXT = {"png", "jpg", "jpeg", "webp"}


def _save_stamp_image_on_white_bg(file_storage, stamp_id):
    """يحفظ صورة الختم/التوقيع المرفوعة كملف PNG بخلفية بيضاء صلبة دائمًا —
    حتى لو الصورة الأصلية عندها خلفية شفافة (PNG) أو ملوّنة (خلفية زرقاء/
    رمادية من سكنر)، لأن ختم/توقيع بخلفية غير بيضاء يظهر "نشازًا" واضحًا
    فوق التقرير الأبيض. يفتح الصورة بمكتبة Pillow، يدمجها فوق طبقة بيضاء
    (فتُصبح أي شفافية بيضاء تلقائيًا)، ثم يحفظها باسم ثابت stamp_<id>.png
    داخل static/uploads/stamps. يرجّع اسم الملف النهائي فقط (بدون المسار
    الكامل) ليُخزَّن بعمود digital_stamps.image_filename.

    يتطلب: pip install Pillow (لو غير مثبّت أصلاً على جهاز السيرفر)."""
    from PIL import Image

    img = Image.open(file_storage.stream).convert("RGBA")
    white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white_bg.alpha_composite(img)
    flattened = white_bg.convert("RGB")

    filename = f"stamp_{stamp_id}.png"
    flattened.save(os.path.join(STAMPS_UPLOAD_DIR, filename), format="PNG")
    return filename

ROLE_LABELS = {
    "admin": "Administrator",
    "reception": "Reception",
    "technician": "Lab Technician",
    "supervisor": "Lab Supervisor",
    "accountant": "Accountant",
}

# مدد الترخيص الجاهزة المعروضة بلوحة المصمم عند توليد كود لعميل — نقطة
# #12. المفتاح هو قيمة <option value="..."> بفورم designer_generate،
# والقيمة (label, days): days=None تعني ترخيص دائم فعلي (بدون تاريخ
# انتهاء إطلاقاً، يُخزَّن كـ "PERM" داخل الكود نفسه — راجع
# license_manager.generate_activation_code). التعديل هنا فقط ينعكس تلقائياً
# على القائمة المنسدلة بـ designer/panel.html.
LICENSE_DURATION_PRESETS = {
    "trial": ("تجريبي (3 أيام)", license_manager.TRIAL_DAYS),
    "1day": ("يوم واحد", 1),
    "3days": ("3 أيام", 3),
    "1month": ("شهر", 30),
    "3months": ("3 أشهر", 90),
    "6months": ("6 أشهر", 180),
    "1year": ("سنة", 365),
    "permanent": ("دائم (بدون تاريخ انتهاء)", None),
}
app.jinja_env.globals["LICENSE_DURATION_PRESETS"] = LICENSE_DURATION_PRESETS

# دكتور المختبر الفاحص — the examining lab doctor for a visit (separate from
# the external "referring" doctor already tracked via doctor_id/doctors
# table). Editable now from Management → Settings; this constant is only the
# bootstrap default used the first time (see database.get_examining_doctors).
EXAMINING_DOCTORS = ["د.خليل حمود", "د.هدى نصيف", "د.اسراء عبد الاقر"]

# ------------------------------------------------------------- print reports --
# Maps a test_definitions.code to the printable report template that
# reproduces the lab's paper letterhead for that report type.
REPORT_TEMPLATE_MAP = {
    "CBC": "reports/cbc.html",
    "BF": "reports/blood_film.html",
    "BFRETIC": "reports/blood_film.html",
    "RETIC": "reports/retic_only.html",
    "WBCDIFF": "reports/wbc_differential.html",
    "FLUIDEXAM": "reports/fluid_examination.html",
    "COAG": "reports/coagulation.html",
    "GUE": "reports/urine_exam.html",
    "GSE": "reports/stool_exam.html",
    "SFA": "reports/seminal_fluid.html",
}

# نفس القوائم Macroscopic/Microscopic المكتوبة داخل reports/urine_exam.html،
# reports/stool_exam.html، reports/seminal_fluid.html — نسخة مصدرها الوحيد
# هنا بـ Python (بدل التكرار داخل كل قالب) حتى يقدر _build_exam_sections
# يفرز الباراميترات ويرتبها (مع احترام تخصيص المستخدم عبر تصميم/معاينة
# التقرير: تحريك باراميتر لقسم ثاني، إعادة ترتيب) قبل ما توصل للقالب أصلاً.
# أي تعديل مستقبلي على هذي القوائم يكفي هنا فقط — القوالب تلقائيًا تتبعه.
EXAM_SECTION_NAMES = {
    "GUE": {
        "macro": ["Color", "Specific Gravity", "Reaction (pH)", "Glucose", "Protein", "Ketone",
                  "Bile Pigment", "Urobilinogen", "Nitrite"],
        "micro": ["RBCs", "PUS", "Casts", "Epithelial Cells", "Amorphous", "Mucus", "Crystals",
                  "Parasites", "Parasites / Others"],
    },
    "GSE": {
        "macro": ["Color", "Consistency", "Mucus", "Blood", "Worms", "Worms / Helminths"],
        "micro": ["Pus Cells", "RBCs", "Amoeba (E. histolytica)", "Giardia lamblia", "Helminthes Ova",
                  "Undigested Food Particles", "Fungi", "Fungi / Yeast"],
    },
    "SFA": {
        "macro": ["Volume", "Color", "Color / Appearance", "Liquefaction Time", "Viscosity", "pH"],
        "micro": ["Sperm Count", "Total Sperm Count", "Active", "Active (Progressive)", "Sluggish",
                  "Sluggish (Non-progressive)", "Immotile", "Normal Forms", "Abnormal Forms",
                  "Pus Cells", "RBCs", "Agglutination"],
    },
}


def _build_exam_sections(test_code, params, report_layout):
    """يفرز params لقسمين (macro/micro) حسب EXAM_SECTION_NAMES، مع احترام:
    - report_layout['param_section'][اسم الباراميتر]: يفرض قسم مختلف عن
      الافتراضي (نقل باراميتر من Macroscopic لـ Microscopic أو العكس، من
      لوحة تعديل المعاينة). هذا المفتاح الصحيح والوحيد لهذا الغرض.
    - report_layout['section_order'] القديم: كان يُستخدم لنفس الغرض (dict
      بنفس الشكل)، لكن اسمه تعارض مع مفهوم ثانٍ مختلف كليًا (ترتيب عرض
      الأقسام كقائمة نصوص بقوالب أخرى) وانخزنت له قيمة list بالغلط بقاعدة
      بيانات بعض التحاليل، مما كان يسبب AttributeError دائم عند كل طباعة/
      معاينة لذاك التحليل من هذيك اللحظة فصاعدًا. لهذا صار القسم يتجاهل أي
      قيمة بـ section_order إلا إذا كانت dict فعلاً (توافق قديم آمن) —
      وأي نوع بيانات غلط (list أو غيره) يُتجاهل بهدوء بدل ما يكسر الطباعة.
    - report_layout['param_order'][اسم الباراميتر]: رقم ترتيب صريح ضمن
      قسمه — الباراميترات غير المرتّبة يدويًا تحافظ على ترتيبها الأصلي
      نسبةً لبعضها (sort مستقر) وتُذيّل قائمة قسمها. نفس الحماية من نوع
      بيانات غلط مطبّقة هنا كمان.
    الباراميترات غير المذكورة إطلاقًا بـ EXAM_SECTION_NAMES (أُضيفت لاحقًا
    لهذا التحليل من كتالوج التحاليل) تنزل افتراضيًا بقسم Microscopic —
    بنفس سلوك حلقة "الباقي" القديمة بالقوالب.
    """
    names = EXAM_SECTION_NAMES.get(test_code, {"macro": [], "micro": []})
    report_layout = report_layout if isinstance(report_layout, dict) else {}
    section_overrides = report_layout.get("param_section")
    if not isinstance(section_overrides, dict):
        legacy = report_layout.get("section_order")
        section_overrides = legacy if isinstance(legacy, dict) else {}
    param_order = report_layout.get("param_order")
    if not isinstance(param_order, dict):
        param_order = {}

    def default_section(pname):
        if pname in names["macro"]:
            return "macro"
        return "micro"

    macro_list, micro_list = [], []
    for p in params:
        section = section_overrides.get(p["name"], default_section(p["name"]))
        (macro_list if section == "macro" else micro_list).append(p)

    def sort_key(p):
        return param_order.get(p["name"], 10_000)

    macro_list.sort(key=sort_key)
    micro_list.sort(key=sort_key)
    return macro_list, micro_list


# Blood Film and Retic Count are two SEPARATE orderable tests, but when both
# are ordered for the same visit they should print as ONE Blood-Film-shaped
# report (which already has the Reticulocyte/Corrected Retic fields built
# in) instead of two separate pages. If Retic Count is ordered on its own
# (no Blood Film for that visit), it prints its own small standalone report.
BF_RETIC_LINK = {"BF": "RETIC", "RETIC": "BF"}

# Test codes whose printed report gets a blank stamp/signature space for the
# examining doctor (Blood Film, Blood Film + Retic, standalone Retic, Fluid
# examination, Hb Preparation, Sickling, BMA, BM Biopsy, WBC Differential) —
# kept in sync with EXAMINING_TEST_DEFS (the tests a doctor is paid to
# personally examine), since every one of those needs a stamp/signature line
# on its printed report. CBC and the other non-examining report types don't
# get this box.
EXAM_SIGNATURE_TEST_CODES = {"BF", "BFRETIC", "RETIC", "FLUIDEXAM", "HBPREP", "SICKLE", "BMA", "BMBIOPSY", "WBCDIFF",
                              "GUE", "GSE", "SFA"}

# CBC results are grouped on the printed report with a blank spacer row
# between each group, matching the reference report layout.
CBC_ROW_GROUPS = [
    ["WBCs", "NE", "Ly", "MO", "BA", "EO", "NE#", "LY#", "MO#", "BA#", "EO#"],
    ["RBC", "HGB", "HCT", "MCV", "MCH", "MCHC", "RDW", "RDW-SD"],
    ["PLT", "MPV"],
]

# الوحدة الثانية لنتيجة التحليل (مثلاً mg/dL بالإضافة لـ mmol/L) — بعض
# التحاليل تُكتب نتيجتها بوحدتين بنفس الوقت (خصوصًا الكيمياء والهرمونات).
# tp.unit2 و tp.unit2_factor يُضبطان مرة وحدة من صفحة إدارة الوحدات لكل
# باراميتر (اختياري تمامًا)، والقيمة الثانية تُحسب تلقائيًا وقت الطباعة:
# value2 = value1 * unit2_factor. لتحويل عكسي (وحدة أساسية أصغر لوحدة ثانية
# أكبر) استخدم معامل أصغر من 1 بدل قسمة منفصلة — النتيجة نفسها رياضيًا.
def format_unit2_value(value, factor):
    """يرجع نص القيمة المحوّلة للوحدة الثانية، أو None إذا ما ينطبق التحويل
    (نتيجة غير رقمية، أو ما فيه معامل محفوظ لهذا الباراميتر)."""
    if factor in (None, "") or value in (None, ""):
        return None
    try:
        converted = float(value) * float(factor)
    except (TypeError, ValueError):
        return None
    if converted == int(converted):
        return str(int(converted))
    return f"{converted:.3f}".rstrip("0").rstrip(".")


# يحوّل حقل range_text (نفس الحقل الحر الموجود أصلاً بجدول reference_ranges)
# إلى قائمة مستويات جاهزة للعرض بشكل "Normal Range" مفصّل بالتقرير، بدل
# كتابته كسطر نص واحد فقط. الصيغة المتوقعة بخانة range_text: كل مستوى
# بسطر مستقل "التسمية: القيمة" — مثال (زي Triglycerides بالنموذج المرجعي):
#   Borderline high: 150 - 199
#   Normal: Less than 150
#   High: 200 - 499
#   Very high: More than 500
# وسطر بدون ":" (أو حقل range_text بسطر وحيد فقط، مثل "166 - 507") يُعرض
# كقيمة بسيطة بلا تسمية — بنفس شكل باقي التحاليل العادية (Cortisol, TSH...).
def parse_range_tiers(text):
    if not text:
        return []
    tiers = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            label, _, value = line.partition(":")
            tiers.append({"label": label.strip(), "value": value.strip()})
        else:
            tiers.append({"label": None, "value": line})
    return tiers


def _fmt_range_num(n):
    """يشيل .0 الزايدة من الأرقام الصحيحة بس يبقي الكسور كما هي (15 مو 15.0،
    بس 4.8 تضل 4.8) — يُستخدم فقط لبناء نص range_text من قيم رقمية."""
    if n is None:
        return ""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    return str(int(f)) if f.is_integer() else str(f)


def _parse_tier_numeric(value):
    """يحاول يفك نص تيير مثل '11 - 33' أو '11-33' لرقمين (low, high).
    يرجّع (None, None) لو النص مو بصيغة رقم-رقم صافية (مثلاً 'Negative') —
    يبقى بهذي الحالة كنص حر (raw) بدل ما ينكسر."""
    if not value:
        return None, None
    m = re.match(r"^\s*([\-+]?[\d.]+)\s*-\s*([\-+]?[\d.]+)\s*$", value.strip())
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


def reference_range_tiers(row):
    """يفكّك صف reference_ranges وحدة لقائمة 'تييرات' موحّدة (المطلوب: صفحة
    Reference Ranges الجديدة — كل حالة/طور فسيولوجي بسطر مستقل قابل للتحرير
    لحاله)، بغض النظر هل الصف مخزّن بـrange_text (أسطر Label: value متعددة،
    نفس فكرة parse_range_tiers) أو بس بعمودي low/high العاديين (حالة الصف
    البسيط بلا تسميات). كل عنصر: {label, low, high, raw} — raw يبقى النص
    الأصلي إذا قيمة التيير مو 'رقم - رقم' صافية (مثلاً 'Negative')."""
    if row["range_text"]:
        out = []
        for tier in parse_range_tiers(row["range_text"]):
            lo, hi = _parse_tier_numeric(tier["value"])
            out.append({"label": tier["label"], "low": lo, "high": hi,
                        "raw": tier["value"] if lo is None else None})
        return out
    if row["low"] is not None or row["high"] is not None:
        return [{"label": None, "low": row["low"], "high": row["high"], "raw": None}]
    return []


def serialize_range_tiers(tiers):
    """عكس reference_range_tiers: يبني (range_text, low, high) الجاهزين
    للحفظ بصف reference_ranges من قائمة تييرات. لو تيير واحد بس بدون تسمية،
    يُخزَّن بعمودي low/high العاديين مباشرة (بدون range_text) — نفس الأسلوب
    القديم البسيط، حتى لا نعقّد الحالة الشائعة (باراميتر بلا أطوار/حالات).
    لو أكثر من تيير أو فيه تسمية، يُبنى range_text (سطر لكل تيير)، وlow/high
    العاديين ياخذوهم من أول تيير بلا تسمية إن وُجد (تُستخدم بحساب الفلاك
    التلقائي High/Low/Critical — التسميات الثانية بس عرض/طباعة، ما تُستخدم
    بتمييز الفلاك تلقائيًا، نفس قيد النظام الحالي)."""
    tiers = [t for t in tiers if t.get("label") or t.get("low") is not None
             or t.get("high") is not None or t.get("raw")]
    if not tiers:
        return None, None, None
    if len(tiers) == 1 and not tiers[0].get("label"):
        t = tiers[0]
        return None, t.get("low"), t.get("high")
    lines = []
    for t in tiers:
        if t.get("raw"):
            value = t["raw"]
        elif t.get("low") is not None and t.get("high") is not None:
            value = f"{_fmt_range_num(t['low'])} - {_fmt_range_num(t['high'])}"
        elif t.get("low") is not None:
            value = f"> {_fmt_range_num(t['low'])}"
        elif t.get("high") is not None:
            value = f"< {_fmt_range_num(t['high'])}"
        else:
            value = ""
        lines.append(f"{t['label']}: {value}" if t.get("label") else value)
    base = next((t for t in tiers if not t.get("label")), None)
    return "\n".join(lines), (base["low"] if base else None), (base["high"] if base else None)


def get_known_analyzers(db):
    """قائمة أجهزة التحليل المحفوظة بالإعدادات (سطر لكل جهاز) — تُستخدم
    كمقترحات (datalist) بحقل الجهاز وقت إدخال النتيجة وبصفحة النسب الطبيعية."""
    raw = get_setting(db, "known_analyzers", "")
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def get_known_units(db):
    """قائمة كل الوحدات المستخدمة فعليًا حاليًا بأي باراميتر بالبرنامج
    (مقترحات datalist بصفحة النسب الطبيعية — المطلوب 6: تعديل/اختيار وحدة
    القياس لكل باراميتر مباشرة من نفس بطاقته، بدل الاضطرار للذهاب لصفحة
    "تعديل الوحدات" المنفصلة كل مرة)."""
    rows = db.execute(
        "SELECT DISTINCT unit FROM test_parameters WHERE unit IS NOT NULL AND TRIM(unit) != '' ORDER BY unit"
    ).fetchall()
    return [r["unit"] for r in rows]


AGE_UNIT_FULL_WORD = {"Hours": "Hour", "Days": "Day", "Weeks": "Week", "Months": "Month", "Years": "Year"}


def format_age_display(age, age_unit):
    """يبني نص عمر المريض المطبوع بالتقرير — كلمة كاملة ("Year") مو حرف
    مختصر ("Y") بناءً على طلب المستخدم، مع مسافة بينه وبين الرقم."""
    if age in (None, ""):
        return ""
    word = AGE_UNIT_FULL_WORD.get(age_unit or "Years", "Year")
    return f"{age} {word}"


# متاح مباشرة كدالة Jinja (parse_range_tiers(text)) حتى تقدر القوالب اللي
# تبني عرض المدى الطبيعي بنفسها (exam_row بـ exam_report_shared.html) تفكّ
# range_text متعدد الأسطر بدون الحاجة لتمرير النسخة المفكوكة يدويًا من
# Python لكل صف — نفس الدالة المستخدمة بجانب custom_rows/combined_panel.
app.jinja_env.globals["parse_range_tiers"] = parse_range_tiers


# ألوان تلوين رقم النتيجة تلقائيًا حسب flag (المطلوب 2) — المستخدم صراحة
# رفض أي قاعدة ألوان ثابتة بالكود وطلب يختار هو اللونين بنفسه من الإعدادات
# (راجع flag_color_high/flag_color_low بصفحة settings.html)، فـ"تلوين
# ثابت" مو صحيح هنا. أبقينا فقط فكرة "هل التلوين مفعّل أصلاً"
# (auto_flag_color_enabled) من الشغل الجديد لأنها إضافة مفيدة ومستقلة.
# Normal ما تدخل هذا القاموس عمدًا — يعني بدون تلوين، كالسابق.
def build_flag_color_map(db):
    high = get_setting(db, "flag_color_high", "#D40000")
    low = get_setting(db, "flag_color_low", "#B58900")
    return {"High": high, "Critical": high, "Low": low}


def get_report_flag_settings(db):
    """(auto_flag_color_enabled, show_result_flag, flag_color_map) لطباعة أي
    تقرير — راجع شرح كامل عند مفتاحي هذا الإعداد بصفحة settings.html (بطاقة
    "تلوين رقم النتيجة" و"إظهار كلمة High/Low/Critical"). auto_flag_color_enabled
    افتراضيًا معطّل (0) — اختياري بالكامل، المدير لازم يفعّله يدويًا من
    الإعدادات إذا يريده. show_result_flag افتراضيًا معطّل (0) بنفس الشكل.
    flag_color_map يُبنى من لونين يختارهما المدير بنفسه (settings)، لا قاعدة
    ثابتة بالكود.
    """
    return (
        get_setting(db, "auto_flag_color_enabled", "0") == "1",
        get_setting(db, "show_result_flag", "0") == "1",
        build_flag_color_map(db),
    )



ROW_SPACING_PRESETS = {"tight": 4, "normal": 8, "loose": 14}


# تحاليل الكيمياء/الفيتامينات/الفايروسات/الدلائل الورمية تطبع بتصميم جدول
# مختلف (Test Name / Conventional Units / SI Units، مع Normal Range تحت كل
# تحليل) بناءً على طلب المستخدم — يُكتشف تلقائيًا من اسم "Department" لهذا
# التحليل بكتالوج التحاليل، فما يحتاج أي إعداد يدوي إضافي لكل تحليل. لو
# تحليل معيّن ما انطبق عليه رغم إنه فعلاً كيمياء/فيتامينات/فايروسات/دلائل
# ورمية، عدّل حقل "Department" له بكتالوج التحاليل ليتضمن إحدى الكلمات
# بالقائمة تحت (عربي أو إنكليزي)، أو أضف كلمة جديدة للقائمة.
ORDER_STYLE_DEPT_KEYWORDS = [
    "chem", "كيمياء", "بايوكيمستري", "biochem",
    "vitamin", "فيتامين",
    "virus", "virolog", "فايروس", "فيروس", "serolog",
    "tumor", "marker", "ورمي", "دلائل",
]


def uses_order_style_report(department, report_style=None):
    """True لو هذا التحليل يطبع بالتصميم الجديد (جدول Conventional/SI Units
    المُصلَّح -- custom_v2.html). التصميم القديم (custom.html) فيه خلل تراكب
    بصري بالمدى الطبيعي (نقطة 7/8) فصار custom_v2 هو الافتراضي لكل التحاليل
    الآن -- مو بس تحاليل الكيمياء/الفيتامينات كما كان سابقًا. report_style
    يقدر يلغيه يدويًا فقط: 'classic' يرجّع تحليل معيّن للتصميم القديم لو
    احتجته لسبب ما."""
    if report_style == "classic":
        return False
    return True


def row_spacing_px(raw_value):
    """يحوّل test_definitions.row_spacing (المطلوب 8) لبكسل فعلي — يقبل
    درجة جاهزة (tight/normal/loose) أو رقم بكسل حر مكتوب كنص. يرجع None
    لو فاضي/NULL/غير صالح، وهذا مقصود: القوالب تستخدم None لتترك التباعد
    الافتراضي القديم لكل قالب كما هو تمامًا (بدون أي inline style إضافي)،
    حتى ما يتغير شكل أي تقرير قديم لم يُضبط له شي بعد."""
    if not raw_value:
        return None
    raw_value = str(raw_value).strip()
    if raw_value in ROW_SPACING_PRESETS:
        return ROW_SPACING_PRESETS[raw_value]
    try:
        px = int(float(raw_value))
        return max(0, min(60, px))
    except (TypeError, ValueError):
        return None


def resolve_label(param_row, override_label=None):
    """اسم العرض النهائي لباراميتر (المطلوب 9ب) — الأولوية: تسمية مخصصة
    لهذا الصف بالذات إن وُجدت (override_label — مثلاً rows_json.label
    بـcustom.html، أو param_overrides.label بexam rows) ← display_label
    المحفوظة على test_parameters نفسها (تنطبق بكل مكان يُطبع فيه هذا
    الباراميتر) ← الاسم الأصلي name كالسابق تمامًا لو ما فيه أي تخصيص."""
    if override_label:
        return override_label
    if param_row is not None:
        try:
            dl = param_row["display_label"]
        except (KeyError, IndexError, TypeError):
            dl = None
        if dl:
            return dl
        return param_row["name"]
    return ""


VALUE_ALIGN_CSS = {"near_name": "left", "center": "center", "near_unit": "right"}


def resolve_value_align(param_row):
    """محاذاة CSS لرقم النتيجة (المطلوب 11) حسب test_parameters.value_align
    — NULL/فاضي/قيمة غير معروفة = None (يعني اترك السلوك الافتراضي القديم
    لهذا القالب كما هو بدون أي inline style إضافي، حتى ما يتغير أي تقرير
    قديم لم يُضبط له شي بعد)."""
    if param_row is None:
        return None
    try:
        va = param_row["value_align"]
    except (KeyError, IndexError, TypeError):
        va = None
    return VALUE_ALIGN_CSS.get(va)


app.jinja_env.globals["resolve_label"] = resolve_label
app.jinja_env.globals["uses_order_style_report"] = uses_order_style_report
app.jinja_env.globals["resolve_value_align"] = resolve_value_align
app.jinja_env.globals["VALUE_ALIGN_CSS"] = VALUE_ALIGN_CSS


ALLOWED_DOCX_EXT = {"docx"}

# نص الكليشة الجاهز لزر "Normal" بحقول وصف RBC/WBC/Platelets بتقرير الـ Blood
# film (شاشة إدخال النتائج المفردة والمجمّعة). عدّل النص هنا فقط وينعكس
# تلقائيًا بكل شاشات الإدخال دون أي تعديل إضافي بالقوالب. الزر يعبّي الحقل
# بهذا النص، ويبقى قابلاً للتعديل الكامل بعدها (نفس أي حقل نصي عادي).
NORMAL_CLICHE_TEXT = {
    "RBC_desc": "Normochromic normocytic",
    "WBC_desc": "Normal count and morphology",
    "Platelets_desc": "Within normal limits",
}
app.jinja_env.globals["NORMAL_CLICHE_TEXT"] = NORMAL_CLICHE_TEXT

# أسماء الأشهر بالتسمية العراقية/الشامية المتداولة (بدل كانون الثاني/يناير
# الرسمية أو January/February الإنكليزية) — نقطة #11. تُستخدم كـ Jinja
# filter بأي قالب: {{ "2026-08"|iraqi_month }} أو {{ 8|iraqi_month }} تعطي
# "آب"، و IRAQI_MONTHS متاح كـ global لبناء قوائم اختيار الأشهر (dropdown)
# بنفس التسمية مباشرة من القالب.
IRAQI_MONTHS = {
    1: "كانون الثاني", 2: "شباط", 3: "آذار", 4: "نيسان",
    5: "أيار", 6: "حزيران", 7: "تموز", 8: "آب",
    9: "أيلول", 10: "تشرين الأول", 11: "تشرين الثاني", 12: "كانون الأول",
}
app.jinja_env.globals["IRAQI_MONTHS"] = IRAQI_MONTHS


@app.template_filter("iraqi_month")
def iraqi_month_filter(value):
    """يحوّل شهرًا لاسمه العراقي. يقبل: رقم شهر مباشر (1-12)، أو نص تاريخ
    يبدأ بصيغة 'YYYY-MM' (مثل قيمة ?month المستخدمة بالتقارير الشهرية)،
    أو أي نص تاريخ/ISO يبدأ بنفس الصيغة. أي قيمة غير مفهومة تُرجع فاضية
    بدل ما تكسر الصفحة."""
    if value in (None, ""):
        return ""
    if isinstance(value, int):
        return IRAQI_MONTHS.get(value, "")
    s = str(value)
    try:
        if len(s) >= 7 and s[4] == "-":
            return IRAQI_MONTHS.get(int(s[5:7]), "")
        return IRAQI_MONTHS.get(int(s), "")
    except (ValueError, IndexError):
        return ""

# رموز التمييز الملوّنة بحقل الـ Conclusion (نجمة وأسهم وعلامتي استفهام/تعجب)
# — يضيفها المستخدم بنفسه من زر التنسيق فوق حقل الاستنتاج بشاشات إدخال
# النتائج (المفردة والمجمّعة). "key" هو المعرّف المستخدم بجدول settings
# و"label" هو الاسم العربي اللي يظهر بشاشة Management → Settings.
# CONCLUSION_MARKER_DEFAULT_COLORS تحت هو اللون الافتراضي فقط — المدير يكدر
# يغيّر أي لون من شاشة الإعدادات، والقيمة المحفوظة هناك (settings key:
# "conclusion_marker_colors", JSON) هي اللي تُستخدم فعليًا وقت الطباعة/العرض
# عبر get_conclusion_marker_colors(db). الأزرار تُدرج الرمز في موضع المؤشر
# بالضبط (بدون فرض سطر جديد)، فالرمز ممكن يطلع بأي مكان بالسطر — لهيك
# التلوين يفحص كل رمز بالسطر أينما وجد، مو بس إذا كان ببداية السطر.
CONCLUSION_MARKERS = [
    {"key": "star", "char": "★", "label": "نجمة حمراء", "default_color": "#D40000"},
    {"key": "arrow", "char": "→", "label": "سهم مفرد", "default_color": "#1F3B7A"},
    {"key": "arrow_left", "char": "◄", "label": "سهم يسار (اختياري)", "default_color": "#1F3B7A"},
    {"key": "arrow_double", "char": "⇒", "label": "سهم مزدوج", "default_color": "#1F3B7A"},
    {"key": "triangle", "char": "▶", "label": "سهم مثلث", "default_color": "#1F3B7A"},
    {"key": "question", "char": "?", "label": "علامة استفهام", "default_color": "#E67E22"},
    {"key": "exclaim", "char": "!", "label": "علامة تعجب", "default_color": "#8E44AD"},
]
CONCLUSION_MARKER_DEFAULT_COLORS = {m["char"]: m["default_color"] for m in CONCLUSION_MARKERS}
_CONCLUSION_MARKER_PATTERN = re.compile(
    "|".join(re.escape(m) for m in CONCLUSION_MARKER_DEFAULT_COLORS)
)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def get_conclusion_marker_colors(db):
    """يرجع dict {رمز: لون hex} بعد دمج الألوان الافتراضية مع أي تعديل
    حفظه المدير من شاشة Management → Settings (مخزّن كـ JSON بجدول
    settings تحت المفتاح conclusion_marker_colors: {key: hex})."""
    colors = dict(CONCLUSION_MARKER_DEFAULT_COLORS)
    raw = get_setting(db, "conclusion_marker_colors", "")
    if raw:
        try:
            saved = json.loads(raw)
        except (ValueError, TypeError):
            saved = {}
        for m in CONCLUSION_MARKERS:
            val = saved.get(m["key"])
            if val and _HEX_COLOR_RE.match(val):
                colors[m["char"]] = val
    return colors


@app.template_filter("render_conclusion")
def render_conclusion_filter(text):
    """يحوّل نص حقل الـ Conclusion (بأسطره كما كتبها المستخدم بالضبط) إلى
    HTML آمن للطباعة: كل رمز نجمة/سهم بأي موضع بالسطر يُلوَّن الرمز نفسه
    فقط بلونه (المحفوظ من شاشة الإعدادات أو الافتراضي)، وباقي السطر يبقى
    بلونه الطبيعي، والأسطر تُفصل بـ <br> حتى يطبع كل سطر لحاله بدل ما
    ينضغط كلها بسطر وحد متل الـ HTML العادي. كل النص غير الرمز يُهرَّب
    (escape) بشكل طبيعي — ما في أي HTML يُنفَّذ من داخل النص المكتوب نفسه."""
    if not text:
        return ""
    colors = get_conclusion_marker_colors(get_db())
    lines = str(text).split("\n")
    rendered = []
    for line in lines:
        pos = 0
        parts = []
        for m in _CONCLUSION_MARKER_PATTERN.finditer(line):
            if m.start() > pos:
                parts.append(str(escape(line[pos:m.start()])))
            color = colors[m.group()]
            parts.append(
                '<span class="conclusion-marker" style="color:'
                + color + ';">' + str(escape(m.group())) + "</span>"
            )
            pos = m.end()
        if pos < len(line):
            parts.append(str(escape(line[pos:])))
        rendered.append("".join(parts))
    return Markup("<br>".join(rendered))

# The department names that get the extra "previous result per parameter"
# column on the printed report (in addition to the previous-visit date that
# every report shows), AND that get the printed report's repeating letterhead
# when a result overflows onto a second page (see repeat_header_on_print in
# print_report). Covers Chemistry, Hormones, Vitamins, Tumor Markers,
# Virology and Coagulation — the quantifiable/serology departments the lab
# wants tracked over time / laid out as multi-line result cards. Hematology
# (CBC, Blood Film, WBC Differential, Fluid examination, and the other big
# dedicated-template reports) never goes through either feature — they don't
# call find_previous_reference and print_report never sets
# repeat_header_on_print for them — so they're unaffected either way. Matches
# loosely (Arabic or English, any casing) so it keeps working no matter how
# an admin later spells a new department.
PREVIOUS_VALUE_DEPARTMENT_KEYWORDS = (
    "chem", "كيمياء",
    "coagul", "تخثر",
    "hormone", "هرمون",
    "vitamin", "فيتامين",
    "virology", "viral", "فايروس", "فيروس",
    "tumor", "tumour", "marker", "دلائل", "ورمي",
)


def department_shows_previous_values(department):
    d = (department or "").lower()
    return any(k in d for k in PREVIOUS_VALUE_DEPARTMENT_KEYWORDS)


# الترتيب الافتراضي لتحاليل شاشة "إدخال النتائج" حسب القسم — يُستخدم فقط
# لأي تحليل غير مذكور صراحةً بإعداد "ترتيب التحاليل بشاشة إدخال النتائج"
# اليدوي (results_entry_test_order)؛ لو ذاك الإعداد فاضي بالكامل، يصير هذا
# الترتيب هو الافتراضي الوحيد. مطابقة كلمات مفتاحية (عربي/انكليزي، أي حالة
# أحرف) نفس أسلوب PREVIOUS_VALUE_DEPARTMENT_KEYWORDS فوق — تشتغل بغض النظر
# شلون كتب الأدمن اسم القسم بالضبط بكتالوج التحاليل. أي قسم ما يطابق ولا
# مجموعة (مثلاً قسم نادر أو Other) يظهر بالأخير.
# الترتيب المطلوب: كيمياء ← فايروسات ← هرمونات ← فيتامينات ← تخثر ← أمراض الدم.
DEPARTMENT_PRIORITY_KEYWORDS = [
    ("chem", "كيمياء"),                              # 1) Chemistry
    ("virology", "viral", "فايروس", "فيروس"),        # 2) Virology
    ("hormone", "هرمون"),                             # 3) Hormones
    ("vitamin", "فيتامين"),                           # 4) Vitamins
    ("coagul", "تخثر"),                               # 5) Coagulation
    ("hemat", "دم"),                                  # 6) Hematology / blood diseases
]


def department_priority_rank(department):
    d = (department or "").lower()
    for i, keywords in enumerate(DEPARTMENT_PRIORITY_KEYWORDS):
        if any(k in d for k in keywords):
            return i
    return len(DEPARTMENT_PRIORITY_KEYWORDS)  # قسم غير معروف/غير مذكور أعلاه — يظهر بالأخير


def _check_completed_result_gate(db, form):
    """المطلوب 2: تعديل نتيجة مكتملة (order_tests.status == 'Completed')
    محمي بكلمة مرور خاصة (نفس مبدأ ميزة "تحليل مجاني" -- إعداد منفصل
    fee_waiver_gate_password_hash من صفحة الإعدادات). الواجهة الأمامية
    (result_entry.html) أصلاً تسأل عنها وترسلها بحقل gate_password، لكن
    السيرفر ما كان يتحقق منها فعليًا قبل هذا التعديل -- أي شخص يقدر يتجاوز
    الفحص بس بتعطيل الجافاسكربت أو بإرسال الطلب مباشرة. يرجع (ok, error).
    """
    stored_hash = get_setting(db, "fee_waiver_gate_password_hash", "")
    if not stored_hash:
        return False, "لم تُضبط كلمة مرور حماية تعديل النتائج المكتملة بعد -- اضبطها من صفحة الإعدادات أولاً."
    entered = form.get("gate_password", "")
    if hash_password(entered) != stored_hash:
        return False, "كلمة مرور الحماية غير صحيحة -- التعديل مرفوض."
    return True, None



    """يجيب آخر قيمة HCT مُدخلة ضمن تحليل CBC لنفس الزيارة (إن وجدت)، تُستخدم
    لحساب Corrected Retic count تلقائيًا من Reticulocyte count. يرجع None إذا
    ما كان فيه CBC بعد أو ما دخلت قيمة HCT."""
    row = db.execute(
        "SELECT r.value_numeric FROM results r "
        "JOIN test_parameters tp ON tp.id = r.test_parameter_id "
        "JOIN order_tests ot ON ot.id = r.order_test_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "WHERE o.visit_id = ? AND td.code = 'CBC' AND tp.name = 'HCT' "
        "AND r.value_numeric IS NOT NULL "
        "ORDER BY r.id DESC LIMIT 1",
        (visit_id,),
    ).fetchone()
    return row["value_numeric"] if row else None

def get_normal_hct(db, gender, age, age_unit):
    """يجيب متوسط المدى الطبيعي لـ HCT (من جدول القيم المرجعية reference_ranges)
    حسب عمر وجنس المريض — يُستخدم أساسًا لحساب Corrected Retic count بدل رقم
    ثابت واحد لكل الأعمار. يرجع None إذا ما كان فيه مدى مرجعي مطابق."""
    param = db.execute(
        "SELECT tp.id FROM test_parameters tp "
        "JOIN test_definitions td ON td.id = tp.test_definition_id "
        "WHERE td.code = 'CBC' AND tp.name = 'HCT' LIMIT 1"
    ).fetchone()
    if not param:
        return None
    rng = find_reference_range(db, param["id"], gender, age, age_unit)
    if not rng or rng["low"] is None or rng["high"] is None:
        return None
    return (rng["low"] + rng["high"]) / 2.0


def find_previous_reference(db, full_name, age, gender, test_definition_id, department,
                             exclude_visit_id, before_created_at):
    """Find this patient's most recent EARLIER visit that has a completed
    result for the same test — matched strictly on full name + age + gender
    (not just patients.id, since reception may have re-registered a
    returning patient as a new row) and dated before the current visit.

    Returns (previous_visit_date_str_or_None, {param_name: previous_value}).
    The values dict is only populated for Chemistry/Coagulation-type
    departments; every other department gets the date only.
    """
    row = db.execute(
        "SELECT ot.id as order_test_id, v.created_at as visit_created_at "
        "FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE ot.test_definition_id = ? "
        "AND LOWER(TRIM(p.full_name)) = LOWER(TRIM(?)) "
        "AND p.age = ? AND p.gender = ? "
        "AND v.id != ? AND v.created_at < ? "
        "AND ot.status IN ('Completed', 'Verified') "
        "ORDER BY v.created_at DESC LIMIT 1",
        (test_definition_id, full_name or "", age, gender, exclude_visit_id, before_created_at or ""),
    ).fetchone()
    if not row:
        return None, {}

    try:
        dt = datetime.fromisoformat(row["visit_created_at"])
        prev_date = f"{dt.day}/{dt.month}/{dt.year}"
    except (TypeError, ValueError):
        prev_date = row["visit_created_at"] or ""

    prev_values = {}
    if department_shows_previous_values(department):
        prev_results = db.execute(
            "SELECT r.*, tp.name as param_name FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
            (row["order_test_id"],),
        ).fetchall()
        for r in prev_results:
            val = r["value_text"] if r["value_text"] not in (None, "") else r["value_numeric"]
            prev_values[r["param_name"]] = "" if val is None else val
    return prev_date, prev_values


# ---------------------------------------------------------------- helpers --
def current_lang():
    return session.get("lang", "en")


@app.context_processor
def inject_globals():
    db = get_db()
    lang = current_lang()
    brand_name = get_setting(db, "app_name_ar" if lang == "ar" else "app_name", t(lang, "app_name"))
    logo_path = get_setting(db, "logo_path", "")
    logo_url = url_for("static", filename=logo_path) if logo_path else None
    # خلفية شاشة الترحيب (dashboard) — اختيارية، تُرفع من Management → الإعدادات
    # (بطاقة "خلفية شاشة الترحيب")، نفس أسلوب الشعار logo_path أعلاه بالضبط.
    # محقونة هنا عالمياً حتى تتوفر بـ dashboard.html دون تمريرها يدويًا من route.
    dashboard_bg_path = get_setting(db, "dashboard_bg_path", "")
    dashboard_bg_url = url_for("static", filename=dashboard_bg_path) if dashboard_bg_path else None
    # تعتيم/ضبابية طبقة الخلفية فوق الصورة أو التدرّج بشاشة الترحيب —
    # قابلة للتحكم من الإعدادات (بطاقة خلفية شاشة الترحيب)، القيم
    # الافتراضية (62%، 2px) هي بالضبط القيم اللي كانت ثابتة بالكود سابقاً.
    dashboard_bg_overlay_opacity = get_setting(db, "dashboard_bg_overlay_opacity", "62")
    dashboard_bg_blur = get_setting(db, "dashboard_bg_blur", "2")
    # موضع الصورة (أي جزء منها يبقى بمنتصف الشاشة عند القص) -- إضافة سابقة
    # لم تُحذف، بس مو موجودة بآخر نسخة رفعها المستخدم؛ أعدتها هنا لحد ما
    # يتأكد إذا يريدها يبقى أو يشيلها نهائيًا (سألته صراحة قبل الحذف).
    dashboard_bg_position = get_setting(db, "dashboard_bg_position", "center")
    # عنوان وهاتف المختبر — اختياريان، يُضبطان مرة وحدة من الإعدادات (بطاقة
    # العلامة التجارية) ويظهران تلقائيًا بأي قالب يحتاجهم (خصوصًا فاتورة
    # A5 — نقطة #10) بدون تمريرهما يدويًا من كل route.
    lab_address = get_setting(db, "lab_address", "")
    lab_phone = get_setting(db, "lab_phone", "")
    # ارتفاع/عرض خلايا جدول نتائج التقرير (Test/Result/Control/Unit...) — يتحكم
    # بيها الأدمن من Management → Settings، تنطبق تلقائيًا على كل التقارير
    # لأنها محقونة هنا بدل تمريرها يدويًا بكل route.
    report_row_pad = get_setting(db, "report_row_pad", "5")
    report_col_pad = get_setting(db, "report_col_pad", "12")
    # المسافة بين ترويسة الدكاترة وصندوق معلومات المريض (patient-info-v2)،
    # وعرض عمود تسمية الحقل بنفس الصندوق (يتحكم بمدى قرب القيمة من تسميتها
    # زي "Patient Name:") — محقونان هنا بنفس أسلوب report_row_pad أعلاه
    # فينطبقان على كل التقارير المطبوعة دفعة وحدة.
    patient_info_top_gap = get_setting(db, "patient_info_top_gap", "4")
    patient_info_label_width = get_setting(db, "patient_info_label_width", "108")
    # المسافة العمودية بين كل سطر وسطر بصندوق معلومات المريض نفسه (بين
    # "Patient Name" و"Age" مثلاً) — منفصلة عن المسافة فوق الصندوق كله.
    patient_info_row_gap = get_setting(db, "patient_info_row_gap", "3")
    # المسافة الأفقية بين عمود بيانات المريض الأيمن والأيسر (Patient
    # Name/Age/Sex... مقابل Sample No./Patient No....) — كانت ثابتة 36px
    # بالكود، صارت الحين قابلة للتحكم بنفس أسلوب بقية إعدادات التباعد.
    patient_info_col_gap = get_setting(db, "patient_info_col_gap", "36")
    # نمط الخط تحت عناوين التقارير (.report-heading/.report-title) —
    # المستخدم يعاني تكرارًا من مشاكل عرض بصرية بهذا الخط تختلف باختلاف
    # المتصفح/الطابعة، فبدل ملاحقة كل شكوى شكل جديدة، صار قابل للتحكم
    # الكامل من الإعدادات: solid (افتراضي، متصل)، dashed (متقطع بنمط
    # واضح ومقصود)، أو none (بدون خط إطلاقًا).
    report_underline_style = get_setting(db, "report_underline_style", "solid")
    # دكاترة الفحص المُفعَّل لهم "إظهار بترويسة التقرير" — تُحقن هنا تلقائيًا
    # حتى تنعرض بترويسة أي تقرير مطبوع (reports/*.html) بدون تمريرها يدويًا
    # من كل route. راجع Management → الإعدادات → إدارة قائمة الدكاترة.
    letterhead_doctors = get_letterhead_doctors(db)
    letterhead_font_size = get_setting(db, "letterhead_font_size", "14")
    letterhead_font_family = get_setting(db, "letterhead_font_family", "Segoe UI, Tahoma, Arial, sans-serif")
    # حجم خط اسم التحليل وحجم خط النتيجة بكل التقارير المطبوعة — نفس أسلوب
    # letterhead_font_size أعلاه: محقونة هنا مرة وحدة فتنطبق تلقائيًا على كل
    # قوالب reports/* (وbase_report.html) دون تمريرها يدويًا من كل route.
    test_name_font_size = get_setting(db, "test_name_font_size", "16")
    result_value_font_size = get_setting(db, "result_value_font_size", "16")
    # موضع/حجم الشعار بترويسة كل تقرير مطبوع — إعدادان عامان محقونان هنا
    # مرة وحدة، بنفس أسلوب باقي إعدادات التقرير.
    logo_position = get_setting(db, "logo_position", "right")
    logo_width = get_setting(db, "logo_width", "100")
    # حالة "التحديث التلقائي" الحالية — تُحقن هنا حتى يظهر زر التبديل بشريط
    # الأعلى (base.html، بجانب اسم المستخدم) بأي صفحة بدون تمريرها يدويًا.
    auto_update_enabled = get_setting(db, "auto_update_enabled", "1") == "1"
    # لون/خلفية الواجهة العامة (المطلوب: تغيير ألوان الخلفية بكل صفحات
    # البرنامج -- الشريط الجانبي، صفحة زيارة جديدة، وبقية الصفحات -- مو
    # بس شاشة الترحيب). محقونة هنا بنفس أسلوب باقي إعدادات التخصيص، وتُحقن
    # كمتغيرات CSS بـ:root من base.html فتنطبق تلقائيًا على أي عنصر
    # بالصفحات يستخدم أصلاً var(--primary) أو var(--page-bg) بملف
    # static/css/style.css. أي لون hex ثابت مكتوب مباشرة داخل قالب معيّن
    # (بدل ما يستخدم متغير CSS) ما يتأثر تلقائيًا -- يحتاج تحويله لمتغير
    # لحاله أول.
    theme_primary_color = get_setting(db, "theme_primary_color", "#205072")
    theme_page_bg_color = get_setting(db, "theme_page_bg_color", "#F3F6F8")
    license_banner = None
    if "user_id" in session:
        lic = license_manager.check_license(db)
        # الشريط التحذيري "متبقي كم يوم" يظهر فقط للترخيص التجريبي، وليس
        # لأي ترخيص عادي (حتى لو كان له تاريخ انتهاء بعد سنة مثلاً).
        if lic["status"] == "active" and lic.get("is_trial") and lic.get("days_left") is not None:
            license_banner = f"متبقي {lic['days_left']} يوم على انتهاء الفترة التجريبية"
    db.close()
    return dict(t=lambda key: t(lang, key), lang=lang,
                current_user=session.get("full_name"), current_role=session.get("role"),
                brand_name=brand_name, logo_url=logo_url,
                dashboard_bg_url=dashboard_bg_url,
                dashboard_bg_overlay_opacity=dashboard_bg_overlay_opacity,
                dashboard_bg_blur=dashboard_bg_blur,
                dashboard_bg_position=dashboard_bg_position,
                lab_address=lab_address, lab_phone=lab_phone,
                report_row_pad=report_row_pad, report_col_pad=report_col_pad,
                patient_info_top_gap=patient_info_top_gap,
                patient_info_label_width=patient_info_label_width,
                patient_info_row_gap=patient_info_row_gap,
                patient_info_col_gap=patient_info_col_gap,
                report_underline_style=report_underline_style,
                letterhead_doctors=letterhead_doctors,
                letterhead_font_size=letterhead_font_size,
                letterhead_font_family=letterhead_font_family,
                test_name_font_size=test_name_font_size,
                result_value_font_size=result_value_font_size,
                logo_position=logo_position,
                logo_width=logo_width,
                auto_update_enabled=auto_update_enabled,
                theme_primary_color=theme_primary_color,
                theme_page_bg_color=theme_page_bg_color,
                license_banner=license_banner,
                # أيقونة المصمم العائمة: تظهر فقط لمن سجّل دخوله فعلاً من
                # /designer/login بنفس المتصفح (session['designer_id']).
                # المستخدمين العاديين (admin, reception...) ما عندهم هذا
                # المفتاح بالسيشن أبداً، فالأيقونة ما تظهر عندهم إطلاقاً.
                is_designer=bool(session.get("designer_id")))


def login_required(view):
    """بعد استبدال نظام تسجيل الدخول الشخصي (نقطة 3 الموسّعة): "تسجيل
    الدخول" صار يعني ببساطة "دخل من إحدى بطاقات الشاشة الرئيسية" --
    session["interface"] هو المرجع الحقيقي الآن، مو session["user_id"]
    (اللي يبقى موجود لأغراض ثانية فقط -- حساب الواجهة "الظل"، راجع
    ensure_interface_accounts بـdatabase.py)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "interface" not in session:
            return redirect(url_for("landing"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """كل الصفحات اللي كانت محمية بأدوار admin/supervisor/accountant
    القديمة صارت -- بقرار صريح من العميل -- مسموحة لواجهتي "مختبر"
    و"الاثنين معًا" بس (بدون تمييز فني/مسؤول حاليًا)، وممنوعة عن
    "استقبال". الأسماء الممرَّرة (roles) ما عادت تُستخدم فعليًا، أبقيتها
    بالتوقيع فقط حتى ما نضطر نلمس الـ85 مكان اللي يستخدمون هذا الديكوريتر
    بكل أنحاء الملف -- التغيير صار بمكان واحد هنا بس."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "interface" not in session:
                return redirect(url_for("landing"))
            if session.get("interface") not in ("lab", "both"):
                flash("هذي الصفحة متاحة فقط لواجهة المختبر أو الاثنين معًا.")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def designer_required(view):
    """يحمي لوحة المصمم فقط — منفصلة تماماً عن نظام المستخدمين/الأدوار
    العادي في البرنامج (users/session['role']). لا أحد غير من يعرف اسم
    المستخدم وكلمة المرور الخاصين بالمصمم (المُنشَأين مرة واحدة عبر
    /designer/setup) يقدر يدخل هذه اللوحة."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("designer_id"):
            return redirect(url_for("designer_login"))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def enforce_license():
    # المسارات المستثناة من فحص الترخيص: الملفات الثابتة، ولوحة المصمم نفسها
    # (المصمم لازم يقدر يدخلها حتى لو الترخيص منتهي عشان يولّد كود جديد)،
    # وشاشة القفل/التفعيل نفسها (وإلا صار حلقة تحويل لا نهائية).
    endpoint = request.endpoint or ""

    # لو صار تحديث تلقائي بالخلفية وأعاد تشغيل البرنامج، هذا يعرض رسالة
    # نجاح لأول مستخدم يفتح أي صفحة بعدها (بدون ما يحتاج يدخل لوحة
    # المصمم إطلاقاً)، ثم يمسح العلامة فوراً حتى ما تتكرر بكل صفحة.
    if endpoint != "static":
        _db = get_db()
        _pending = get_setting(_db, "auto_update_pending_banner", "")
        if _pending:
            set_setting(_db, "auto_update_pending_banner", "")
            _db.commit()
            flash(f"✅ تم تحديث البرنامج تلقائياً إلى الإصدار {_pending} بنجاح.")
        _db.close()

    if (endpoint == "static"
            or endpoint.startswith("designer_")
            or endpoint in ("license_locked", "license_activate", "set_lang")):
        return
    db = get_db()
    lic = license_manager.check_license(db)
    db.close()
    if lic["status"] in ("expired", "hardware_mismatch", "pending", "revoked"):
        session.pop("user_id", None)
        session.pop("interface", None)
        return redirect(url_for("license_locked"))


@app.before_request
def enforce_interface_scope():
    """فصل واجهة "استقبال" عن واجهة "مختبر" (بدون لمس أي من الـ69 صفحة
    المحمية بـ@login_required فقط) -- استخدام بادئة الرابط بدل تعديل كل
    صفحة براسها: /front-desk/* خاص بالاستقبال، /workbench/* خاص
    بالمختبر. "الاثنين معًا" والمصمم ما عندهم أي قيد. مسجّل بعد
    enforce_license فوق حتى فحص الترخيص يشتغل أول شي دائمًا."""
    interface = session.get("interface")
    if not interface or interface == "both":
        return
    path = request.path
    if interface == "reception" and path.startswith("/workbench"):
        flash("هذي الصفحة خاصة بواجهة المختبر فقط.")
        return redirect(url_for("dashboard"))
    if interface == "lab" and path.startswith("/front-desk"):
        flash("هذي الصفحة خاصة بواجهة الاستقبال فقط.")
        return redirect(url_for("dashboard"))


def log_action(action, entity, entity_id, details=""):
    db = get_db()
    db.execute(
        "INSERT INTO audit_logs (user_id, action, entity, entity_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session.get("user_id"), action, entity, entity_id, details, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


def next_registration_number(db):
    row = db.execute("SELECT MAX(registration_number) AS m FROM visits").fetchone()
    return (row["m"] or 18999) + 1


def doctor_pricing_context(db):
    """Everything the new-visit / edit-visit pages need to auto-fill the
    referring doctor field and switch prices live in the browser:
    - doctors: list of {id, full_name} for the autocomplete list
    - doctor_prices: {doctor_id: {test_id: price}} overrides per doctor
    - doctor_name_to_id: {lowercased full_name: id} so the page can match
      what reception typed to an existing doctor without another request
    """
    doctors = db.execute("SELECT id, full_name FROM doctors ORDER BY full_name").fetchall()
    doctors = [{"id": d["id"], "full_name": d["full_name"]} for d in doctors]

    overrides = db.execute("SELECT doctor_id, test_definition_id, price FROM doctor_test_prices").fetchall()
    doctor_prices = {}
    for row in overrides:
        doctor_prices.setdefault(str(row["doctor_id"]), {})[str(row["test_definition_id"])] = row["price"]

    doctor_name_to_id = {d["full_name"].strip().lower(): d["id"] for d in doctors}

    return doctors, doctor_prices, doctor_name_to_id


# --------------------------------------------------------------- auth ------
@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in ("en", "ar"):
        session["lang"] = lang
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/")
def landing():
    """الشاشة الرئيسية (المطلوب: شاشة تفتح بعد تشغيل البرنامج، فيها ثلاث
    خيارات كبطاقات مصوّرة -- استقبال/مختبر/الاثنين معًا -- بدل ما يوصل
    المستخدم لصفحة تسجيل الدخول العادية مباشرة). عامة بدون تسجيل دخول
    (نفس مبدأ /login) -- لو المستخدم مسجّل دخول أصلاً بجلسة سابقة (تذكرني)
    نوديه للوحة التحكم فورًا بدون ما نعرض له هذي الشاشة من جديد.
    """
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    db = get_db()
    ctx = {
        "landing_title": get_setting(db, "landing_title", "نظام الإدارة المتكامل"),
        "landing_gradient_color1": get_setting(db, "landing_gradient_color1", "#0f172a"),
        "landing_gradient_color2": get_setting(db, "landing_gradient_color2", "#205072"),
        "reception_needs_password": bool(get_setting(db, "interface_reception_password_hash", "")),
        "lab_needs_password": bool(get_setting(db, "interface_lab_password_hash", "")),
    }
    for key in ("reception", "lab", "together"):
        img_path = get_setting(db, f"landing_{key}_image_path", "")
        ctx[f"landing_{key}_image"] = url_for("static", filename=img_path) if img_path else None
    return render_template("landing.html", **ctx)


@app.route("/enter/<interface>", methods=["POST"])
def landing_enter(interface):
    """الضغط على إحدى بطاقات الشاشة الرئيسية -- بعد استبدال نظام تسجيل
    الدخول الشخصي بالكامل (نقطة 3 الموسّعة): كلمة مرور الواجهة (لو
    مضبوطة بالإعدادات) هي التحقق الوحيد الآن، وتدخل الواجهة مباشرة --
    بدون أي شاشة تسجيل دخول شخصي بعدها. الاسم الحر (operator_name)
    اختياري، يُحفظ بالجلسة فقط لغرض "مين سوى شنو" بسجلات التدقيق (يُدمج
    مع حساب الواجهة "الظل" -- راجع ensure_interface_accounts)."""
    if interface not in ("reception", "lab", "both"):
        return redirect(url_for("landing"))
    db = get_db()
    if interface != "both":
        stored_hash = get_setting(db, f"interface_{interface}_password_hash", "")
        if stored_hash:
            entered = request.form.get("password", "")
            if hash_password(entered) != stored_hash:
                flash("كلمة مرور هذي الواجهة غير صحيحة.")
                return redirect(url_for("landing"))
    shadow_username = f"__interface_{interface}__"
    shadow_user = db.execute("SELECT * FROM users WHERE username=?", (shadow_username,)).fetchone()
    if not shadow_user:
        # طبقة أمان إضافية -- ensure_interface_accounts أصلاً تسوي هذا
        # أول إقلاع، لكن لو لأي سبب ما انسوّت (قاعدة بيانات قديمة جدًا
        # قبل هذا التحديث)، ننشئها هسه بدل ما نطيح بخطأ.
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) "
            "VALUES (?, ?, ?, 'admin', 1, ?)",
            (shadow_username, hash_password(os.urandom(16).hex()),
             {"reception": "حساب واجهة الاستقبال", "lab": "حساب واجهة المختبر",
              "both": "حساب واجهة الاستقبال والمختبر معًا"}[interface],
             datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        shadow_user = db.execute("SELECT * FROM users WHERE username=?", (shadow_username,)).fetchone()

    operator_name = (request.form.get("operator_name") or "").strip()
    session["user_id"] = shadow_user["id"]
    session["role"] = "admin"
    session["branch_id"] = shadow_user["branch_id"]
    session["interface"] = interface
    session["full_name"] = operator_name or shadow_user["full_name"]
    session["operator_name"] = operator_name
    session.permanent = True
    log_action("EnterInterface", "user", shadow_user["id"], f"interface={interface} operator={operator_name}")
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
        if user and user["password_hash"] == hash_password(password):
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            session["branch_id"] = user["branch_id"]
            session.permanent = bool(request.form.get("remember"))
            log_action("Login", "user", user["id"])
            # لو المستخدم اختار واحد من بطاقات الشاشة الرئيسية (استقبال/
            # مختبر/الاثنين معًا) قبل لا يوصل لصفحة الدخول هذي، نطبّق
            # اختياره فورًا ونروح مباشرة للوحة التحكم بدون ما نسأله مرة
            # ثانية بصفحة interface_choose. الدخول المباشر بـ/login (بدون
            # المرور بالشاشة الرئيسية أول) يبقى يشتغل متل ما كان -- يودّيه
            # لصفحة الاختيار بعد الدخول كالمعتاد.
            pending_interface = session.pop("pending_interface", None)
            if pending_interface in ("reception", "lab", "both"):
                session["interface"] = pending_interface
                return redirect(url_for("dashboard"))
            return redirect(url_for("interface_choose"))
        error = t(current_lang(), "invalid_login")
    return render_template("login.html", error=error)


@app.route("/interface/choose")
@login_required
def interface_choose():
    """شاشة اختيار صفة الدخول (المطلوب 3): استقبال/مختبر/الاثنين معًا.
    فلترة عرض فقط لأقسام القائمة الجانبية -- ما تغيّر صلاحيات اليوزر
    الفعلية (role) إطلاقًا. تبديل الواجهة لاحقًا (من نفس هذي الصفحة عبر
    زر "تبديل الواجهة" بأسفل القائمة) يحتاج كلمة مرور خاصة بتلك الواجهة
    (تُضبط من صفحة الإعدادات) -- اختيار "الاثنين معًا" ما يحتاج كلمة مرور
    لأنه أوسع خيار (كل الأقسام)، فمافيه شي يُقيَّد عنه."""
    db = get_db()
    reception_configured = bool(get_setting(db, "interface_reception_password_hash", ""))
    lab_configured = bool(get_setting(db, "interface_lab_password_hash", ""))
    return render_template("interface_choose.html", current_interface=session.get("interface"),
                            reception_configured=reception_configured, lab_configured=lab_configured)


@app.route("/interface/set", methods=["POST"])
@login_required
def interface_set():
    choice = request.form.get("interface")
    if choice not in ("reception", "lab", "both"):
        flash("اختيار غير صحيح.")
        return redirect(url_for("interface_choose"))
    db = get_db()
    if choice != "both":
        setting_key = f"interface_{choice}_password_hash"
        stored_hash = get_setting(db, setting_key, "")
        if stored_hash:
            entered = request.form.get("password", "")
            if hash_password(entered) != stored_hash:
                flash("كلمة مرور هذي الواجهة غير صحيحة.")
                return redirect(url_for("interface_choose"))
        # لو ما فيه كلمة مرور مضبوطة لهذي الواجهة بعد، تُقبل بدون كلمة مرور
        # (بدل ما تصير الميزة كلها معطّلة لين الأدمن يضبطها من الإعدادات).
    # تبديل حساب الجلسة "الظل" لنفس واجهة الاختيار الجديد -- حتى entered_by
    # وaudit_logs يبقون متوافقين مع الواجهة الفعلية بعد التبديل (نفس مبدأ
    # landing_enter بالضبط).
    shadow_username = f"__interface_{choice}__"
    shadow_user = db.execute("SELECT * FROM users WHERE username=?", (shadow_username,)).fetchone()
    if shadow_user:
        session["user_id"] = shadow_user["id"]
        session["full_name"] = session.get("operator_name") or shadow_user["full_name"]
    session["interface"] = choice
    log_action("SetInterface", "user", session["user_id"], choice)
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    if "user_id" in session:
        log_action("Logout", "user", session["user_id"])
    session.clear()
    return redirect(url_for("landing"))


# ---------------------------------------------------- license (client side) --
@app.route("/license/locked")
def license_locked():
    db = get_db()
    lic = license_manager.check_license(db)
    db.close()
    return render_template("license_locked.html", lic=lic)


@app.route("/license/activate", methods=["POST"])
def license_activate():
    username = request.form.get("username", "")
    code = request.form.get("code", "")
    db = get_db()
    ok, err = license_manager.apply_activation(db, username, code)
    db.close()
    if ok:
        flash("تم تفعيل الترخيص بنجاح، يمكنك تسجيل الدخول الآن")
        return redirect(url_for("login"))
    flash(err or "فشل التفعيل")
    return redirect(url_for("license_locked"))


# --------------------------------------------------------- designer panel --
@app.route("/designer/setup", methods=["GET", "POST"])
def designer_setup():
    db = get_db()
    if license_manager.designer_exists(db):
        db.close()
        return redirect(url_for("designer_login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or len(password) < 6:
            error = "أدخل اسم مستخدم وكلمة مرور لا تقل عن 6 أحرف"
        elif password != confirm:
            error = "كلمتا المرور غير متطابقتين"
        else:
            license_manager.create_designer_account(db, username, password)
            db.close()
            flash("تم إنشاء حساب المصمم — سجّل الدخول الآن")
            return redirect(url_for("designer_login"))
    db.close()
    return render_template("designer/setup.html", error=error)


@app.route("/designer/login", methods=["GET", "POST"])
def designer_login():
    db = get_db()
    if not license_manager.designer_exists(db):
        db.close()
        return redirect(url_for("designer_setup"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if license_manager.verify_designer(db, username, password):
            session["designer_id"] = 1
            session["designer_username"] = username
            db.close()
            return redirect(url_for("designer_panel"))
        error = "بيانات الدخول غير صحيحة"
    db.close()
    return render_template("designer/login.html", error=error)


@app.route("/designer/logout")
def designer_logout():
    session.pop("designer_id", None)
    session.pop("designer_username", None)
    return redirect(url_for("designer_login"))


@app.route("/designer")
@designer_required
def designer_panel():
    db = get_db()
    lic = license_manager.check_license(db)
    issue_log = db.execute("SELECT * FROM license_issue_log ORDER BY id DESC LIMIT 50").fetchall()
    update_info = {
        "local_version": auto_updater.get_local_version(),
        "configured": auto_updater.is_configured(),
        "enabled": get_setting(db, "auto_update_enabled", "1") == "1",
        "last_check": get_setting(db, "auto_update_last_check", ""),
        "last_status": get_setting(db, "auto_update_last_status", ""),
        "branch": auto_updater.get_update_branch(db),
        "default_branch": auto_updater.GITHUB_BRANCH,
        "custom_channel": get_setting(db, "update_channel", ""),
    }
    github_write_token = get_setting(db, "github_write_token", "")
    github_read_token = get_setting(db, "github_read_token", "")
    revoked_licenses = {}
    revocation_error = None
    if github_write_token and auto_updater.is_configured():
        try:
            revoked_licenses = auto_updater.fetch_revocation_list()
        except Exception as e:
            revocation_error = str(e)
    branding = {
        "app_name": get_setting(db, "app_name", ""),
        "app_name_ar": get_setting(db, "app_name_ar", ""),
        "logo_path": get_setting(db, "logo_path", ""),
    }
    db.close()
    return render_template(
        "designer/panel.html", lic=lic, issue_log=issue_log,
        this_hw=license_manager.get_hardware_id(), this_ip=license_manager.get_local_ip(),
        update_info=update_info, github_write_token=github_write_token,
        github_read_token=github_read_token,
        revoked_licenses=revoked_licenses, revocation_error=revocation_error,
        branding=branding,
    )


@app.route("/designer/github-token", methods=["POST"])
@designer_required
def designer_save_github_token():
    """يحفظ توكن GitHub بصلاحية كتابة محلياً بجدول settings بجهاز المصمم
    فقط — منفصل تماماً عن توكن القراءة (settings.github_read_token، راجع
    /designer/github-read-token تحت) المشحون مع نسخة كل عميل. هذا التوكن
    لا يُشحن أبداً مع أي نسخة تُسلَّم لعميل، فيبقى فقط بقاعدة بيانات جهاز
    المصمم نفسه."""
    db = get_db()
    token = request.form.get("github_write_token", "").strip()
    set_setting(db, "github_write_token", token)
    db.commit()
    db.close()
    flash("تم حفظ توكن الكتابة." if token else "تم مسح توكن الكتابة.")
    return redirect(url_for("designer_panel"))


@app.route("/designer/github-read-token", methods=["POST"])
@designer_required
def designer_save_github_read_token():
    """يحفظ توكن القراءة (اللي يستخدمه هذا الجهاز بالذات لفحص/تنزيل
    التحديثات من GitHub) بجدول settings المحلي فقط — أبداً لا يُكتب بأي
    ملف كود يدخل بـ git push، حتى لا يكتشفه GitHub تلقائياً كسر مسرّب
    ويُلغيه (هذا بالضبط سبب انقطاع التحديث المتكرر قبل هذا التعديل).
    يُطبَّق فوراً بذاكرة هذا التشغيل عبر configure_token() بدون أي حاجة
    لإعادة تشغيل البرنامج."""
    db = get_db()
    token = request.form.get("github_read_token", "").strip()
    set_setting(db, "github_read_token", token)
    db.commit()
    db.close()
    auto_updater.configure_token(token)
    flash("تم حفظ توكن القراءة وتفعيله فوراً." if token else "تم مسح توكن القراءة.")
    return redirect(url_for("designer_panel"))


# تعديل سريع لاسم المختبر (عربي/إنكليزي) والشعار مباشرة من لوحة المصمم —
# بعد رفع تحديث لعميل معيّن، يضبط المصمم هويته الصحيحة بنفس الصفحة اللي
# رفع منها التحديث، بدون ما يحتاج يفتح "الإدارة ← الإعدادات" كخطوة منفصلة.
# يستخدم بالضبط نفس مفاتيح settings (app_name, app_name_ar, logo_path)
# ونفس منطق حفظ الشعار المستخدم بصفحة الإعدادات العادية (app_settings)،
# فالقيمتين مصدرهما واحد بغض النظر من وين تُعدَّل.
@app.route("/designer/branding", methods=["POST"])
@designer_required
def designer_save_branding():
    db = get_db()
    name_en = request.form.get("app_name", "").strip()
    name_ar = request.form.get("app_name_ar", "").strip()
    if name_en:
        set_setting(db, "app_name", name_en)
    if name_ar:
        set_setting(db, "app_name_ar", name_ar)

    file = request.files.get("logo")
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext in ALLOWED_LOGO_EXT:
            filename = secure_filename(f"logo.{ext}")
            for old_ext in ALLOWED_LOGO_EXT:
                old_path = os.path.join(UPLOAD_DIR, f"logo.{old_ext}")
                if os.path.exists(old_path):
                    os.remove(old_path)
            file.save(os.path.join(UPLOAD_DIR, filename))
            set_setting(db, "logo_path", f"uploads/{filename}")
        else:
            flash("امتداد الشعار غير مدعوم. استخدم PNG, JPG, GIF, SVG أو WEBP.")

    db.commit()
    db.close()
    flash("تم حفظ اسم المختبر/الشعار.")
    return redirect(url_for("designer_panel"))


@app.route("/designer/revoke", methods=["POST"])
@designer_required
def designer_revoke_license():
    db = get_db()
    write_token = get_setting(db, "github_write_token", "")
    hardware_id = request.form.get("hardware_id", "").strip()
    reason = request.form.get("reason", "").strip()
    if not hardware_id:
        flash("أدخل معرّف جهاز العميل المطلوب إلغاء ترخيصه")
    else:
        try:
            auto_updater.push_revocation(write_token, hardware_id, reason, revoke=True)
            flash(f"تم إرسال إلغاء الترخيص لجهاز {hardware_id} — راح يوصله أول ما يتصل بالنت (لازم يكون \"مربوط بالإنترنت\" مفعّل عنده).")
        except Exception as e:
            flash(f"⚠️ تعذر إلغاء الترخيص عن بُعد: {e}")
    db.close()
    return redirect(url_for("designer_panel"))


@app.route("/designer/revoke/<path:hardware_id>/restore", methods=["POST"])
@designer_required
def designer_restore_license(hardware_id):
    db = get_db()
    write_token = get_setting(db, "github_write_token", "")
    try:
        auto_updater.push_revocation(write_token, hardware_id, None, revoke=False)
        flash(f"تم رفع الإلغاء عن جهاز {hardware_id} — يقدر يفعّل ببرنامجه بكود جديد أول ما يتصل بالنت.")
    except Exception as e:
        flash(f"⚠️ تعذر رفع الإلغاء: {e}")
    db.close()
    return redirect(url_for("designer_panel"))


@app.route("/designer/update/push", methods=["POST"])
@designer_required
def designer_push_update():
    """يرسل أمر تحديث فوري لجهاز عميل واحد بالذات (مستقل عن بقية العملاء)
    — لا ينتظر دورة الفحص التلقائي (كل CHECK_INTERVAL_HOURS)، بل يُطبَّق أول
    ما يتصل ذلك الجهاز بالنت (أو فوراً لو ضغط عنده زر 'تحقق من تحديث
    الآن'). يعتمد فعلياً على أن يكون ذلك الجهاز 'مربوط بالإنترنت' من لوحة
    المصمم عنده، ويستخدم نفس توكن الكتابة المستخدَم لإلغاء التراخيص عن بُعد."""
    db = get_db()
    write_token = get_setting(db, "github_write_token", "")
    hardware_id = request.form.get("hardware_id", "").strip()
    if not hardware_id:
        flash("أدخل معرّف جهاز العميل المطلوب إرسال التحديث له")
    else:
        try:
            auto_updater.push_update_signal(write_token, hardware_id)
            flash(f"تم إرسال أمر تحديث فوري لجهاز {hardware_id} — راح يُطبَّق أول ما يتصل بالنت "
                  f"(لازم يكون \"مربوط بالإنترنت\" مفعّل عنده، أو يضغط هو زر \"تحقق من تحديث الآن\").")
        except Exception as e:
            flash(f"⚠️ تعذر إرسال أمر التحديث: {e}")
    db.close()
    return redirect(url_for("designer_panel"))


@app.route("/designer/update/channel", methods=["POST"])
@designer_required
def designer_update_channel():
    """يضبط 'قناة التحديث' (اسم الفرع بمستودع GitHub) لهذا الجهاز بالذات.
    اتركه فاضي حتى يرجع يتابع الفرع العام (GITHUB_BRANCH، افتراضياً main)
    زي باقي العملاء. عبّي اسم فرع خاص (مثلاً client-alkut) حتى يستلم هذا
    الجهاز فقط تحديثات ذلك الفرع دون بقية العملاء."""
    db = get_db()
    channel = request.form.get("update_channel", "").strip()
    set_setting(db, "update_channel", channel)
    db.commit()
    db.close()
    if channel:
        flash(f"تم ضبط هذا الجهاز على قناة تحديث خاصة: {channel} — لن يتأثر بتحديثات main العامة إلا هذا الفرع.")
    else:
        flash("تم إرجاع هذا الجهاز لمتابعة قناة التحديث العامة (main) مثل بقية العملاء.")
    return redirect(url_for("designer_panel"))


@app.route("/designer/update/toggle", methods=["POST"])
@designer_required
def designer_update_toggle():
    """يشغّل/يوقف "ربط هذا الجهاز بالإنترنت" — أي تفعيل الفحص الدوري
    التلقائي للتحديثات من GitHub. هذا الأمر خاص بلوحة المصمم فقط ولا
    يظهر أبداً للمستخدمين العاديين (admin/reception)."""
    db = get_db()
    currently_on = get_setting(db, "auto_update_enabled", "0") == "1"
    set_setting(db, "auto_update_enabled", "0" if currently_on else "1")
    db.commit()
    db.close()
    flash("تم فصل البرنامج عن التحديث التلقائي" if currently_on else "تم ربط البرنامج بالإنترنت — سيتحقق تلقائياً من التحديثات دورياً")
    return redirect(url_for("designer_panel"))


@app.route("/designer/update/check-now", methods=["POST"])
@designer_required
def designer_update_check_now():
    """فحص فوري يدوي (زر احتياطي) — يشتغل بغض النظر عن حالة الربط
    التلقائي، مفيد لتجربة الاتصال أو لتنزيل تحديث فوراً بدون انتظار.
    يفحص أيضاً قائمة الإلغاء البعيدة لهذا الجهاز نفسه بنفس الفحص (مفيد
    لو المصمم يجرّب الميزة على جهازه هو قبل ما يعتمد عليها مع عميل)."""
    db = get_db()
    if not auto_updater.is_configured():
        flash("⚠️ لم يتم إعداد بيانات GitHub بعد داخل auto_updater.py")
    else:
        result = auto_updater.check_and_apply(db, force_apply=True)
        auto_updater.check_revocation(db)
        auto_updater.check_update_signal(db)
        flash(result["message"])
    db.close()
    return redirect(url_for("designer_panel"))


@app.route("/designer/generate", methods=["POST"])
@designer_required
def designer_generate():
    hardware_id = request.form.get("hardware_id", "").strip().upper()
    username = request.form.get("username", "").strip()
    expiry_mode = request.form.get("expiry_mode")

    if not hardware_id or not username:
        flash("أدخل معرّف الجهاز واسم المستخدم")
        return redirect(url_for("designer_panel"))

    preset = LICENSE_DURATION_PRESETS.get(expiry_mode)
    if not preset:
        flash("مدة ترخيص غير صالحة — اختر مدة من القائمة")
        return redirect(url_for("designer_panel"))

    _label, days = preset
    is_trial = expiry_mode == "trial"
    # days=None يعني ترخيص دائم فعلي (بدون تاريخ انتهاء) — license_manager
    # يخزّنه كـ "PERM" داخل الكود نفسه ويتحقق منه محلياً دون أي اعتماد على
    # تاريخ. الإلغاء عن بُعد (designer_revoke_license) يبقى شغّال بنفس
    # الطريقة حتى مع ترخيص دائم، فهو ليس "بلا رجعة".
    expiry_date = None if days is None else (date.today() + timedelta(days=days)).isoformat()

    code = license_manager.generate_activation_code(hardware_id, expiry_date, is_trial=is_trial)
    db = get_db()
    license_manager.log_issued_code(db, hardware_id, username, expiry_date, code)
    db.close()
    return render_template(
        "designer/generated.html", username=username, code=code,
        hardware_id=hardware_id, expiry_date=expiry_date,
    )


@app.route("/designer/issue-log/<int:log_id>/delete", methods=["POST"])
@designer_required
def designer_delete_issue_log(log_id):
    """حذف سطر واحد من سجل أكواد التفعيل المولَّدة — لا يلغي الترخيص نفسه
    عند العميل (الكود المفعّل عنده يبقى شغّال)، فقط ينظّف السجل المعروض
    بلوحة المصمم."""
    db = get_db()
    db.execute("DELETE FROM license_issue_log WHERE id=?", (log_id,))
    db.commit()
    db.close()
    flash("تم حذف السطر من السجل.")
    return redirect(url_for("designer_panel"))


@app.route("/designer/change-password", methods=["POST"])
@designer_required
def designer_change_password():
    new_password = request.form.get("new_password", "")
    confirm = request.form.get("confirm", "")
    if len(new_password) < 6 or new_password != confirm:
        flash("تحقق من كلمة المرور الجديدة (6 أحرف على الأقل ومتطابقة)")
        return redirect(url_for("designer_panel"))
    db = get_db()
    license_manager.change_designer_password(db, new_password)
    db.close()
    flash("تم تغيير كلمة مرور المصمم")
    return redirect(url_for("designer_panel"))


# ---------------------------------------------------------- dashboard ------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    visits_today = db.execute(
        "SELECT COUNT(*) c FROM visits WHERE substr(created_at,1,10)=?", (today,)
    ).fetchone()["c"]
    revenue_today = db.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE substr(paid_at,1,10)=?", (today,)
    ).fetchone()["s"]
    pending_results = db.execute(
        "SELECT COUNT(*) c FROM order_tests WHERE status IN ('Accepted','In-progress')"
    ).fetchone()["c"]
    critical_count = db.execute(
        "SELECT COUNT(*) c FROM results WHERE flag='Critical' AND verified_at IS NULL"
    ).fetchone()["c"]
    recent_visits = db.execute(
        "SELECT v.registration_number, p.id as patient_id, p.full_name, v.status, v.created_at "
        "FROM visits v JOIN patients p ON p.id=v.patient_id "
        "ORDER BY v.id DESC LIMIT 8"
    ).fetchall()
    return render_template("dashboard.html", visits_today=visits_today, revenue_today=revenue_today,
                            pending_results=pending_results, critical_count=critical_count,
                            recent_visits=recent_visits)


# --------------------------------------------------------------- front desk
@app.route("/front-desk/new-visit", methods=["GET", "POST"])
@login_required
def new_visit():
    db = get_db()
    if request.method == "POST":
        # زر "✅ تم سحب العينة" إلزامي بهذي الصفحة (نقطة #9) — يمثّل تأكيد
        # الاستقبال إنه سحب العينة فعليًا وقت تسجيل الزيارة (حالة شائعة
        # بالمختبرات الصغيرة حيث الاستقبال هو نفسه يسحب العينة). لو ما
        # انضغط، نرفض الحفظ من السيرفر (مو بس تحقق JS بالواجهة) قبل أي
        # INSERT بقاعدة البيانات. تأثيره: order_tests تُنشأ مباشرة بحالة
        # 'Collected' (بدل 'Accepted' الافتراضية) فتتخطى طابور "سحب
        # العينة" وتظهر مباشرة بطابور "استلام العينة" — راجع
        # samples_collection/samples_accession لنفس منطق الحالتين.
        sample_collected = request.form.get("sample_collected") == "1"
        if not sample_collected:
            error_msg = "لازم تأكيد \"تم سحب العينة\" قبل حفظ الزيارة."
            if request.headers.get("X-LIS-Ajax") == "1":
                return jsonify({"ok": False, "error": error_msg}), 400
            flash(error_msg)
            return redirect(url_for("new_visit"))

        name = request.form.get("patient_name", "").strip()
        title = request.form.get("title", "Mr.")
        gender = request.form.get("gender", "")
        age = request.form.get("age") or None
        age_unit = request.form.get("age_unit") or "Years"
        phone = request.form.get("phone", "")
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "")
        national_id = request.form.get("national_id", "").strip()
        passport_number = request.form.get("passport_number", "").strip()
        travel_certificate_number = request.form.get("travel_certificate_number", "").strip()
        lab_card_number = request.form.get("lab_card_number", "").strip()
        fasting = request.form.get("fasting", "Undefined")
        notes = request.form.get("notes", "")
        # المعلومات الصحية (Health Information) — خاصة بهذي الزيارة تحديداً.
        weight = request.form.get("weight") or None
        height = request.form.get("height") or None
        symptoms = request.form.get("symptoms", "")
        disease = request.form.get("disease", "")
        therapy = request.form.get("therapy", "")
        # الزيارة المنزلية (Home Visit)
        is_home_visit = 1 if request.form.get("is_home_visit") == "1" else 0
        home_visit_address = request.form.get("home_visit_address", "") if is_home_visit else ""
        try:
            home_visit_fee = float(request.form.get("home_visit_fee") or 0) if is_home_visit else 0.0
        except ValueError:
            home_visit_fee = 0.0
        examining_doctor = request.form.get("examining_doctor", "")
        expenses = request.form.get("expenses") or 0
        # حقل "الدكتور الفاحص" (attending_doctor) صار نفس "دكتور المختبر
        # الفاحص" (examining_doctor) — كانا حقلين منفصلين بالشاشة سابقًا
        # وصار واحد بس بناءً على طلب المستخدم، وهذا العمود يُملأ تلقائيًا
        # بنفس القيمة حتى يبقى عمود "الزيارات" شغّالاً بدون أي تغيير.
        attending_doctor = examining_doctor
        contact_method = request.form.get("contact_method", "None")
        test_ids = request.form.getlist("tests")
        now = datetime.now().isoformat(timespec="seconds")

        # الطبيب المُحيل (خارجي) — إذا هذا أول مرة يذكر اسمه، ينحفظ تلقائيًا
        # بجدول الأطباء حتى يظهر بالاقتراحات بالمرات الجاية.
        referring_doctor_id = find_or_create_doctor(db, request.form.get("doctor_name", ""))

        # المختبر المُرسِل لهذه العينة (لو النموذج وارد من مختبر ثاني مو من
        # مراجع مباشر) — تُستخدم فقط للمحاسبة الداخلية بين المختبرين؛ اسم
        # هذا المختبر ما ينطبع بأي تقرير أبدًا (راجع print_report/from_other_lab).
        # يُكتب كاسم حر (نفس أسلوب حقل الدكتور المُحيل) بدل قائمة منسدلة
        # ثابتة، فيُنشأ المختبر تلقائيًا بأول مرة يُذكر اسمه — ما تحتاج
        # الاستقبال تضيفه مسبقًا من صفحة إدارة المختبرات المُحيلة.
        referral_center_id = find_or_create_referral_center(db, request.form.get("referral_lab_name", ""))

        # إذا اختار موظف الاستقبال مريضًا سبق أن زار المختبر (من نتائج البحث
        # الفوري)، تُستخدم بطاقته الحالية بدل إنشاء بطاقة مريض مكررة جديدة.
        existing_patient_id = request.form.get("existing_patient_id") or None
        patient_id = None
        if existing_patient_id:
            existing = db.execute(
                "SELECT id FROM patients WHERE id=?", (existing_patient_id,)
            ).fetchone()
            if existing:
                patient_id = existing["id"]

        if patient_id is None:
            name_en = (request.form.get("patient_name_en") or "").strip() or transliterate_arabic_name(name)
            cur = db.execute(
                "INSERT INTO patients (full_name, full_name_en, gender, age, age_unit, phone, address, contact_method, "
                "title, email, national_id, passport_number, travel_certificate_number, lab_card_number, "
                "branch_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, name_en, gender, age, age_unit, phone, address, contact_method,
                 title, email, national_id, passport_number, travel_certificate_number, lab_card_number,
                 session.get("branch_id"), now),
            )
            patient_id = cur.lastrowid

        examining_doctor_fee = compute_examining_doctor_fee(db, examining_doctor, test_ids)

        reg_number = next_registration_number(db)
        visit_type = "home-visit" if is_home_visit else "walk-in"
        cur = db.execute(
            "INSERT INTO visits (registration_number, patient_id, doctor_id, referral_center_id, visit_type, fasting, notes, "
            "examining_doctor, expenses, examining_doctor_fee, attending_doctor, weight, height, symptoms, disease, therapy, "
            "is_home_visit, home_visit_address, home_visit_fee, status, branch_id, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?, ?)",
            (reg_number, patient_id, referring_doctor_id, referral_center_id, visit_type, fasting, notes, examining_doctor, expenses,
             examining_doctor_fee, attending_doctor, weight, height, symptoms, disease, therapy,
             is_home_visit, home_visit_address, home_visit_fee, session.get("branch_id"), session["user_id"], now),
        )
        visit_id = cur.lastrowid

        order_cur = db.execute("INSERT INTO orders (visit_id, status, created_at) VALUES (?, 'Open', ?)",
                                (visit_id, now))
        order_id = order_cur.lastrowid

        total = 0.0
        for tid in test_ids:
            test = db.execute("SELECT * FROM test_definitions WHERE id=?", (tid,)).fetchone()
            if not test:
                continue
            # طلب بارامترات معيّنة بس من هذا التحليل (سهم ▾ بالواجهة) بدل
            # التحليل كامل — selected_params_<tid> يوصل "id,id,id" لو
            # استُخدم، وإلا فاضي (السلوك الافتراضي القديم: التحليل كامل).
            # السعر يُحسب من قاعدة البيانات دائماً (مجموع أسعار البارامترات
            # المختارة فعلاً)، ما نثق بأي مجموع جاي من الواجهة.
            selected_params_raw = (request.form.get(f"selected_params_{tid}") or "").strip()
            selected_param_ids = None
            if selected_params_raw:
                try:
                    pid_list = [int(x) for x in selected_params_raw.split(",") if x.strip()]
                except ValueError:
                    pid_list = []
                if pid_list:
                    placeholders = ",".join("?" * len(pid_list))
                    prows = db.execute(
                        f"SELECT id, price FROM test_parameters WHERE id IN ({placeholders}) AND test_definition_id=?",
                        (*pid_list, tid),
                    ).fetchall()
                    if prows:
                        price = sum((r["price"] or 0) for r in prows)
                        selected_param_ids = ",".join(str(r["id"]) for r in prows)
                    else:
                        price = get_test_price(db, tid, referring_doctor_id)
                else:
                    price = get_test_price(db, tid, referring_doctor_id)
            else:
                price = get_test_price(db, tid, referring_doctor_id)
            barcode = f"{reg_number}{tid.zfill(3)}"
            # الحالة تبدأ 'Collected' مباشرة (مو 'Accepted') لأن زر "تم سحب
            # العينة" الإلزامي فوق تأكد إنها انسحبت فعليًا هذي اللحظة —
            # فتتخطى طابور "سحب العينة" وتظهر مباشرة بطابور "استلام العينة".
            db.execute(
                "INSERT INTO order_tests (order_id, test_definition_id, status, barcode, price, doctor_id, "
                "collected_at, created_at, selected_param_ids) VALUES (?, ?, 'Collected', ?, ?, ?, ?, ?, ?)",
                (order_id, tid, barcode, price, referring_doctor_id, now, now, selected_param_ids),
            )
            total += price or 0

        # أجرة الزيارة المنزلية الإضافية (إن فُعِّلت) تُضاف لمجموع الفحوصات
        # قبل حساب الفاتورة، بنفس أسلوب أي بند إضافي بالمجموع.
        total += home_visit_fee

        # "المبلغ الكلي" بصفحة الزيارة الجديدة يبدأ محسوبًا تلقائيًا من
        # مجموع أسعار التحاليل المختارة، بس موظف الاستقبال يقدر يعدّله يدويًا
        # (مثلاً لخصم أو تسوية) — الفرق بين المجموع الفعلي والمبلغ المُعدَّل
        # يُسجَّل بعمودي discount_amount/extra_charges حتى يبقى مجموع أسعار
        # التحاليل الأصلي محفوظًا للمراجعة.
        computed_total = total
        total_override_raw = request.form.get("total_amount_input")
        try:
            total_override = float(total_override_raw) if total_override_raw not in (None, "") else None
        except ValueError:
            total_override = None
        invoice_total = total_override if (total_override is not None and total_override >= 0) else computed_total
        discount_amount = max(0.0, computed_total - invoice_total)
        extra_charges = max(0.0, invoice_total - computed_total)

        # "الواصل" — أي مبلغ استلمه الاستقبال نقدًا وقت تسجيل الزيارة نفسها.
        # يُسجَّل كدفعة فعلية بجدول payments (نفس آلية /billing/pay) حتى يظهر
        # بسجلات المحاسبة والتقارير، و"الباقي" يُحسب تلقائيًا من الفرق.
        try:
            paid_amount = float(request.form.get("paid_amount") or 0)
        except ValueError:
            paid_amount = 0.0
        paid_amount = max(0.0, paid_amount)
        if invoice_total > 0:
            paid_amount = min(paid_amount, invoice_total)
            invoice_status = "Paid" if paid_amount >= invoice_total else ("Partial" if paid_amount > 0 else "Unpaid")
        else:
            invoice_status = "Paid" if paid_amount <= 0 else "Partial"

        inv_cur = db.execute(
            "INSERT INTO invoices (visit_id, total_amount, discount_amount, extra_charges, paid_amount, status, "
            "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (visit_id, invoice_total, discount_amount, extra_charges, paid_amount, invoice_status,
             session["user_id"], now),
        )
        invoice_id = inv_cur.lastrowid

        if paid_amount > 0:
            db.execute(
                "INSERT INTO payments (invoice_id, amount, method, user_id, paid_at) VALUES (?, ?, 'Cash', ?, ?)",
                (invoice_id, paid_amount, session["user_id"], now),
            )
            log_action("Payment", "invoice", invoice_id, f"amount={paid_amount} (at registration)")


        if contact_method != "None":
            db.execute(
                "INSERT INTO patient_followups (patient_id, visit_id, status, followup_date, created_at) "
                "VALUES (?, ?, 'Pending', ?, ?)",
                (patient_id, visit_id, now[:10], now),
            )

        db.commit()
        log_action("Create", "visit", visit_id, f"reg#{reg_number}")
        log_action("Collect", "visit", visit_id, f"sample_collected_at_registration reg#{reg_number}")
        flash(f"Visit #{reg_number} created successfully.")

        # موافقة الموظف على دمج نتائج تحاليل قديمة (من آخر زيارة سابقة
        # لنفس المريض) بتقرير هذي الزيارة الجديدة — تُسجَّل هنا بس عند
        # التأكيد الصريح من بنك تنبيه الزيارة السابقة بشاشة "زيارة جديدة"،
        # راجع visit_previous_merges لتفاصيل الآلية.
        merge_ids_raw = request.form.get("merge_previous_order_test_ids", "").strip()
        if merge_ids_raw:
            merge_ids = [x for x in merge_ids_raw.split(",") if x.strip().isdigit()]
            if merge_ids:
                save_visit_previous_merges(db, visit_id, merge_ids)

        # إذا اختار موظف الاستقبال تضمين زيارة/زيارات سابقة مع هذي الزيارة
        # الجديدة بجدول موحّد، يروح مباشرة لصفحة الجدول الموحّد بدل قائمة الزيارات.
        include_visit_ids = request.form.get("include_visit_ids", "").strip()
        if include_visit_ids:
            all_ids = [visit_id_str for visit_id_str in include_visit_ids.split(",") if visit_id_str.strip().isdigit()]
            all_ids.append(str(visit_id))
            redirect_url = url_for("combined_visits_report", visit_ids=",".join(all_ids))
        else:
            redirect_url = url_for("visits_list")

        # صفحة "زيارة جديدة" تُرسل الفورم بـ AJAX حتى تقدر تعرض زر "طباعة
        # الباركود" وتطبع من نفس الصفحة (بدون فتح تبويب/متصفح جديد) قبل ما
        # تنتقل لقائمة الزيارات. لو الطلب اجى بالطريقة العادية (بدون JS)،
        # نكمل بنفس سلوك التحويل المباشر كما كان سابقًا.
        if request.headers.get("X-LIS-Ajax") == "1":
            return jsonify({
                "ok": True,
                "visit_id": visit_id,
                "registration_number": reg_number,
                "patient_name": name,
                "redirect_url": redirect_url,
            })

        return redirect(redirect_url)

    tests = db.execute("SELECT * FROM test_definitions WHERE is_active=1 ORDER BY department, name").fetchall()
    quick_items = db.execute(
        "SELECT td.id, td.name FROM quick_add_items q JOIN test_definitions td ON td.id = q.test_definition_id "
        "WHERE q.is_active=1 ORDER BY q.display_order"
    ).fetchall()
    doctors, doctor_prices, doctor_name_to_id = doctor_pricing_context(db)
    test_default_prices = {str(tst["id"]): tst["price"] for tst in tests}
    examining_test_ids = [row["id"] for row in get_examining_tests(db)]
    referral_labs = db.execute(
        "SELECT * FROM referral_centers WHERE name != 'Walk-in' ORDER BY name"
    ).fetchall()
    return render_template("front_desk/new_visit.html", tests=tests, quick_items=quick_items,
                            examining_doctors=get_examining_doctors(db), doctors=doctors,
                            doctor_prices=doctor_prices, doctor_name_to_id=doctor_name_to_id,
                            test_default_prices=test_default_prices,
                            examining_test_ids=examining_test_ids,
                            examining_rates=get_examining_rates_map(db),
                            referral_labs=referral_labs)


@app.route("/front-desk/patients")
@login_required
def patients_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    query = "SELECT * FROM patients "
    params = []
    if q:
        query += "WHERE full_name LIKE ? OR phone LIKE ? OR national_id LIKE ? "
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
    query += "ORDER BY id DESC LIMIT 200"
    patients = db.execute(query, params).fetchall()
    return render_template("front_desk/patients.html", patients=patients, q=q)


@app.route("/front-desk/patients/new", methods=["GET", "POST"])
@login_required
def patient_new():
    db = get_db()
    if request.method == "POST":
        now = datetime.now().isoformat(timespec="seconds")
        _pn_name = request.form.get("full_name", "").strip()
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
        )
        db.commit()
        flash("Patient added.")
        return redirect(url_for("patients_list"))
    return render_template("front_desk/patient_form.html", patient=None, requires_gate=False)


@app.route("/front-desk/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
def patient_edit(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        return "Not found", 404
    # المطلوب 2: تعديل بيانات مريض كل نتائجه مكتملة (ومطبوعة) محمي بنفس
    # كلمة مرور حماية النتائج المكتملة أعلاه -- إذا هذا المريض عنده تحليل
    # واحد ع الأقل وكلها Completed/Verified، لازم كلمة المرور. مريض جديد
    # أو عنده تحليل لسا Pending يبقى تعديله حر بدون أي قيد زيادة عن
    # المعتاد. نحسبها هنا مرة وحدة، تُستخدم بالـGET (لتظهر حقل الباسورد
    # بالفورم أصلاً) وبالـPOST (للتحقق الفعلي).
    all_tests = db.execute(
        "SELECT ot.status FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
        "JOIN visits v ON v.id=o.visit_id WHERE v.patient_id=?",
        (patient_id,),
    ).fetchall()
    requires_gate = bool(all_tests) and all(t["status"] in ("Completed", "Verified") for t in all_tests)
    if request.method == "POST":
        if requires_gate:
            ok, err = _check_completed_result_gate(db, request.form)
            if not ok:
                flash(err)
                return redirect(url_for("patient_edit", patient_id=patient_id))
        _pe_name = request.form.get("full_name", "").strip()
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
        )
        db.commit()
        log_action("Update", "patient", patient_id)
        flash("Patient updated.")
        return redirect(url_for("patients_list"))
    return render_template("front_desk/patient_form.html", patient=patient, requires_gate=requires_gate)


@app.route("/front-desk/patients/<int:patient_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_patient(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        return "Not found", 404
    # لا نحذف المريض إذا عنده زيارات مسجّلة (بيها نتائج/فواتير مرتبطة)، حتى
    # لا تبقى سجلات يتيمة. نمنع الحذف بهذي الحالة ونعرض عدد الزيارات.
    linked_visits = db.execute("SELECT COUNT(*) c FROM visits WHERE patient_id=?", (patient_id,)).fetchone()["c"]
    if linked_visits:
        flash(f"لا يمكن حذف هذا المريض لأنه مرتبط بـ {linked_visits} زيارة. "
              f"احذف تلك الزيارات أولاً إذا تريد حذفه فعلاً.")
        return redirect(url_for("patients_list"))
    db.execute("DELETE FROM patients WHERE id=?", (patient_id,))
    db.commit()
    log_action("Delete", "patient", patient_id, patient["full_name"])
    flash("تم حذف المريض.")
    return redirect(url_for("patients_list"))


# بحث سريع عن مريض سبق أن زار المختبر: يعرض كل زياراته السابقة والفحوصات
# التي أجراها، ويسمح للأدمن حصراً باختيار نتائج قديمة (تحليل واحد أو أكثر،
# من أي زيارة سابقة) ونسخها إلى أحدث زيارة للمريض — وليس الزيارة كاملة.
@app.route("/front-desk/patients/<int:patient_id>/history", methods=["GET", "POST"])
@login_required
def patient_history(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        return "Not found", 404

    if request.method == "POST":
        if session.get("role") != "admin":
            flash("نسخ نتائج قديمة إلى الزيارة الحالية صلاحية خاصة بالأدمن فقط.")
            return redirect(url_for("patient_history", patient_id=patient_id))

        selected_result_ids = request.form.getlist("copy_result")
        if not selected_result_ids:
            flash("لم تحدد أي نتيجة لنسخها.")
            return redirect(url_for("patient_history", patient_id=patient_id))

        latest_visit = db.execute(
            "SELECT v.*, o.id as order_id FROM visits v JOIN orders o ON o.visit_id = v.id "
            "WHERE v.patient_id=? ORDER BY v.id DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
        if not latest_visit:
            flash("لا توجد زيارة حالية لهذا المريض لنسخ النتائج إليها.")
            return redirect(url_for("patient_history", patient_id=patient_id))

        now = datetime.now().isoformat(timespec="seconds")
        copied = 0
        for result_id in selected_result_ids:
            old_result = db.execute(
                "SELECT r.*, ot.test_definition_id, ot.barcode FROM results r "
                "JOIN order_tests ot ON ot.id = r.order_test_id WHERE r.id=?",
                (result_id,),
            ).fetchone()
            if not old_result:
                continue
            reg = latest_visit["registration_number"]
            tid = old_result["test_definition_id"]
            new_barcode = f"{reg}{str(tid).zfill(3)}-old"

            # نفس هذا التحليل قد يكون انتسخ مسبقًا (نفس المريض، نفس الزيارة
            # الحالية) -- إما بضغطة سابقة لنفس الزر، أو لأن التحليل نفسه فيه
            # أكثر من parameter وكل واحد يُنسخ بضغطة منفصلة. بدون هذا الفحص،
            # كل ضغطة كانت تنشئ صف order_tests جديد بنفس الـbarcode، فيطلع
            # نفس التحليل مكرر بعدة جداول منفصلة بصفحة سجل الزيارات (الخلل
            # المُبلَّغ عنه). نعيد استخدام صف order_tests الموجود أصلاً لهذا
            # الـbarcode بهذي الزيارة إذا كان موجود، بدل إنشاء صف جديد كل مرة.
            existing_ot = db.execute(
                "SELECT id FROM order_tests WHERE order_id=? AND barcode=?",
                (latest_visit["order_id"], new_barcode),
            ).fetchone()
            if existing_ot:
                new_order_test_id = existing_ot["id"]
            else:
                cur = db.execute(
                    "INSERT INTO order_tests (order_id, test_definition_id, status, barcode, notes, created_at) "
                    "VALUES (?, ?, 'Completed', ?, ?, ?)",
                    (latest_visit["order_id"], tid, new_barcode, "نتيجة منسوخة من زيارة سابقة", now),
                )
                new_order_test_id = cur.lastrowid

            # وبنفس المنطق -- نفس الـparameter لنفس صف order_tests هذا قد
            # يكون انتسخ مسبقًا هو نفسه؛ نحدّثه بدل تكراره كصف results جديد.
            existing_result = db.execute(
                "SELECT id FROM results WHERE order_test_id=? AND test_parameter_id=?",
                (new_order_test_id, old_result["test_parameter_id"]),
            ).fetchone()
            if existing_result:
                db.execute(
                    "UPDATE results SET value_numeric=?, value_text=?, flag=?, entered_by=?, entered_at=? "
                    "WHERE id=?",
                    (old_result["value_numeric"], old_result["value_text"], old_result["flag"],
                     session["user_id"], now, existing_result["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, "
                    "entered_by, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (new_order_test_id, old_result["test_parameter_id"], old_result["value_numeric"],
                     old_result["value_text"], old_result["flag"], session["user_id"], now),
                )
            copied += 1
        db.commit()
        log_action("CopyOldResults", "visit", latest_visit["id"], f"{copied} نتيجة من زيارات سابقة")
        flash(f"تم نسخ {copied} نتيجة إلى الزيارة الحالية #{latest_visit['registration_number']}.")
        return redirect(url_for("visit_edit", visit_id=latest_visit["id"]))

    visits = db.execute(
        "SELECT v.* FROM visits v WHERE v.patient_id=? ORDER BY v.id DESC", (patient_id,),
    ).fetchall()
    visit_data = []
    for v in visits:
        order_tests = db.execute(
            "SELECT ot.id, ot.barcode, td.name as test_name, td.id as test_definition_id "
            "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
            "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE o.visit_id=?",
            (v["id"],),
        ).fetchall()
        tests_with_results = []
        for ot in order_tests:
            results = db.execute(
                "SELECT r.*, tp.name as param_name, tp.unit FROM results r "
                "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
                (ot["id"],),
            ).fetchall()
            tests_with_results.append({"order_test": ot, "results": results})
        visit_data.append({"visit": v, "tests": tests_with_results})

    return render_template("front_desk/patient_history.html", patient=patient, visit_data=visit_data)


# بحث موحّد بالصفحة الرئيسية: يبحث بثلاث فئات مرة وحدة — اسم مريض (يظهر
# تفاصيله عبر رابط سجله)، اسم طبيب مُحيل، واسم مختبر مُرسِل (الأخيرين
# يوديان لقائمة زياراتهما مرتبة بالأحدث تاريخًا ووقتًا عبر فلتر
# doctor_id/referral_center_id بصفحة "الزيارات" — راجع visits_list أعلاه).
@app.route("/api/dashboard/search")
@login_required
def api_dashboard_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"patients": [], "doctors": [], "referral_labs": []})
    db = get_db()
    patients = db.execute(
        "SELECT p.id, p.full_name, p.gender, p.age, p.age_unit, p.phone, "
        "(SELECT MAX(v.created_at) FROM visits v WHERE v.patient_id = p.id) as last_visit_at "
        "FROM patients p WHERE p.full_name LIKE ? ORDER BY p.full_name LIMIT 6",
        (f"%{q}%",),
    ).fetchall()
    doctors = db.execute(
        "SELECT d.id, d.full_name, d.phone, "
        "(SELECT MAX(v.created_at) FROM visits v WHERE v.doctor_id = d.id) as last_visit_at "
        "FROM doctors d WHERE d.full_name LIKE ? "
        "ORDER BY last_visit_at IS NULL, last_visit_at DESC LIMIT 6",
        (f"%{q}%",),
    ).fetchall()
    referral_labs = db.execute(
        "SELECT rc.id, rc.name, rc.phone, "
        "(SELECT MAX(v.created_at) FROM visits v WHERE v.referral_center_id = rc.id) as last_visit_at "
        "FROM referral_centers rc WHERE rc.name LIKE ? AND rc.name != 'Walk-in' "
        "ORDER BY last_visit_at IS NULL, last_visit_at DESC LIMIT 6",
        (f"%{q}%",),
    ).fetchall()
    return jsonify({
        "patients": [dict(r) for r in patients],
        "doctors": [dict(r) for r in doctors],
        "referral_labs": [dict(r) for r in referral_labs],
    })


# بحث فوري (Live search) يُستخدم من شاشة "زيارة جديدة": بمجرد كتابة اسم
# المريض يبحث عن أي مطابقة سابقة بجدول المرضى، حتى لا تنفتح بطاقة مريض
# مكررة لشخص سبق أن راجع المختبر.
@app.route("/api/patients/search")
@login_required
def api_patients_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        "SELECT p.id, p.full_name, p.gender, p.age, p.age_unit, p.phone, p.address, "
        "(SELECT MAX(v.created_at) FROM visits v WHERE v.patient_id = p.id) as last_visit_at, "
        "(SELECT v2.id FROM visits v2 WHERE v2.patient_id = p.id ORDER BY v2.created_at DESC LIMIT 1) as last_visit_id "
        "FROM patients p WHERE p.full_name LIKE ? ORDER BY p.full_name LIMIT 8",
        (f"%{q}%",),
    ).fetchall()
    # لكل مريض مطابق بالاسم، نجيب أسماء تحاليل آخر زيارة له (مو كل الزيارات
    # — بس آخر وحدة، تكفي كتمييز سريع) حتى يقدر موظف الاستقبال يفرّق فورًا
    # بين شخصين بنفس الاسم بالضبط عن طريق نوع التحليل أو تاريخ آخر زيارة،
    # دون فتح كل سجل على حدة. هذا لا يغيّر أو يحذف أي بيانات — قراءة فقط.
    out = []
    for r in rows:
        d = dict(r)
        last_tests = []
        if d.get("last_visit_id"):
            last_tests = [t["name"] for t in db.execute(
                "SELECT DISTINCT td.name FROM order_tests ot "
                "JOIN orders o ON o.id = ot.order_id "
                "JOIN test_definitions td ON td.id = ot.test_definition_id "
                "WHERE o.visit_id=? LIMIT 6",
                (d["last_visit_id"],),
            ).fetchall()]
        d["last_visit_tests"] = last_tests
        d.pop("last_visit_id", None)
        out.append(d)
    return jsonify(out)


# ملخص زيارات مريض سبق أن راجع (تُستدعى من شاشة "زيارة جديدة" بعد اختيار
# مطابقة من البحث الفوري) — تاريخ كل زيارة والتحاليل التي أُجريت بها، حتى
# تظهر أزرار مشاهدة / طباعة / تضمين لكل زيارة قديمة.

# كشف زيارة سابقة لنفس المريض (بمطابقة الاسم الثلاثي + العمر بالضبط) لحظة
# كتابة الاسم والعمر بشاشة "زيارة جديدة" — تُرجع بس آخر زيارة (الأحدث، لا
# كل التاريخ)، وتحاليلها المكتملة مقسّمة لمجموعتين حسب سياسة الدمج:
# "mergeable" (Biochemistry/Hormones/Vitamins/Virology/Tumor Marker/
# Coagulation — نفس PREVIOUS_VALUE_DEPARTMENT_KEYWORDS) يعرضها الموظف
# كخيارات دمج اختيارية، و"info_only" (Blood Film/Retic/Fluid Exam/BMA/
# BMB — نفس REPORT_TEMPLATE_MAP) تُعرض كرسالة إعلامية بس بدون أي خيار
# دمج. أي تحليل من قسم غير مذكور بأي من القائمتين يُهمَل بصمت (لا داعي
# له بهذا التنبيه أصلاً).
@app.route("/api/patients/previous-visit-check")
@login_required
def api_previous_visit_check():
    full_name = (request.args.get("full_name") or "").strip()
    age_raw = (request.args.get("age") or "").strip()
    if not full_name or not age_raw:
        return jsonify({"found": False})
    try:
        age = float(age_raw)
    except ValueError:
        return jsonify({"found": False})

    db = get_db()
    match = find_last_visit_by_name_age(db, full_name, age)
    if not match:
        return jsonify({"found": False})

    try:
        dt = datetime.fromisoformat(match["created_at"])
        date_display = f"{dt.day}/{dt.month}/{dt.year}"
    except (TypeError, ValueError):
        date_display = match["created_at"] or ""

    tests = get_visit_completed_tests(db, match["visit_id"])
    mergeable, info_only = [], []
    for tst in tests:
        if department_shows_previous_values(tst["department"]):
            results = db.execute(
                "SELECT r.*, tp.name as param_name FROM results r "
                "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=? LIMIT 1",
                (tst["order_test_id"],),
            ).fetchone()
            summary = ""
            if results:
                val = results["value_text"] if results["value_text"] not in (None, "") else results["value_numeric"]
                summary = f"{results['param_name']}: {val}" if val not in (None, "") else ""
            mergeable.append({
                "order_test_id": tst["order_test_id"], "name": tst["test_name"], "summary": summary,
            })
        elif tst["test_code"] in REPORT_TEMPLATE_MAP:
            info_only.append({"order_test_id": tst["order_test_id"], "name": tst["test_name"]})

    return jsonify({
        "found": True,
        "patient_id": match["patient_id"],
        "date_display": date_display,
        "mergeable": mergeable,
        "info_only": info_only,
    })


@app.route("/api/patients/<int:patient_id>/visits-summary")
@login_required
def api_patient_visits_summary(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        return jsonify({"error": "not found"}), 404
    visits = db.execute(
        "SELECT v.id, v.registration_number, v.created_at FROM visits v "
        "WHERE v.patient_id=? ORDER BY v.id DESC LIMIT 10",
        (patient_id,),
    ).fetchall()
    visits_out = []
    for v in visits:
        tests = db.execute(
            "SELECT td.name FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
            "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE o.visit_id=? ORDER BY td.name",
            (v["id"],),
        ).fetchall()
        has_results = db.execute(
            "SELECT COUNT(*) c FROM results r JOIN order_tests ot ON ot.id = r.order_test_id "
            "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
            (v["id"],),
        ).fetchone()["c"] > 0
        visits_out.append({
            "id": v["id"],
            "registration_number": v["registration_number"],
            "created_at": v["created_at"],
            "tests": [t["name"] for t in tests],
            "has_results": has_results,
        })
    return jsonify({
        "patient": {
            "id": patient["id"], "full_name": patient["full_name"], "gender": patient["gender"],
            "age": patient["age"], "age_unit": patient["age_unit"], "phone": patient["phone"],
            "address": patient["address"],
        },
        "visits": visits_out,
    })


@app.route("/front-desk/results")
@login_required
def results_list():
    db = get_db()
    # فلترة اختيارية قادمة من بطاقات الرئيسية:
    # - "pending": زيارات فيها تحليل واحد على الأقل لسا حالته Accepted أو
    #   In-progress — نفس المعيار بالضبط المستخدم بعدّاد "نتائج قيد الإنجاز"
    #   بالرئيسية (dashboard()), حتى يطابق العدد المعروض هناك عدد الصفوف هنا.
    # - "critical": زيارات فيها نتيجة واحدة على الأقل flag='Critical' ولسا
    #   verified_at فاضي — نفس معيار عدّاد "تنبيهات حرجة" بالرئيسية بالضبط.
    filter_type = request.args.get("filter", "")
    query = (
        "SELECT v.id as visit_id, v.registration_number, v.created_at, p.full_name as patient_name, "
        "COUNT(ot.id) as tests_count, "
        "SUM(CASE WHEN ot.status IN ('Completed', 'Verified') THEN 1 ELSE 0 END) as done_count, "
        "SUM(CASE WHEN ot.status = 'Verified' THEN 1 ELSE 0 END) as verified_count, "
        "GROUP_CONCAT(ot.id || ':' || td.name, '||') as tests_list "
        "FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
    )
    filter_label = None
    if filter_type == "pending":
        query += (
            "WHERE v.id IN ("
            "  SELECT o2.visit_id FROM order_tests ot2 "
            "  JOIN orders o2 ON o2.id = ot2.order_id "
            "  WHERE ot2.status IN ('Accepted','In-progress')"
            ") "
        )
        filter_label = "زيارات فيها نتائج قيد الإنجاز"
    elif filter_type == "critical":
        query += (
            "WHERE v.id IN ("
            "  SELECT o2.visit_id FROM order_tests ot2 "
            "  JOIN orders o2 ON o2.id = ot2.order_id "
            "  JOIN results r2 ON r2.order_test_id = ot2.id "
            "  WHERE r2.flag='Critical' AND r2.verified_at IS NULL"
            ") "
        )
        filter_label = "زيارات فيها تنبيهات حرجة غير مُصادَق عليها"
    query += "GROUP BY v.id ORDER BY v.id DESC LIMIT 200"
    rows = db.execute(query).fetchall()
    return render_template("front_desk/results.html", rows=rows, filter_type=filter_type,
                            filter_label=filter_label)


@app.route("/front-desk/followups")
@login_required
def followups_list():
    db = get_db()
    status_filter = request.args.get("status", "")
    query = (
        "SELECT f.id, f.status, f.notes, f.followup_date, p.full_name, p.phone, "
        "v.registration_number "
        "FROM patient_followups f JOIN patients p ON p.id = f.patient_id "
        "LEFT JOIN visits v ON v.id = f.visit_id "
    )
    params = []
    if status_filter:
        query += "WHERE f.status = ? "
        params.append(status_filter)
    query += "ORDER BY f.id DESC LIMIT 200"
    rows = db.execute(query, params).fetchall()
    return render_template("front_desk/followups.html", rows=rows, status_filter=status_filter)


@app.route("/front-desk/followups/<int:followup_id>/update", methods=["POST"])
@login_required
def followup_update(followup_id):
    db = get_db()
    status = request.form.get("status", "Pending")
    notes = request.form.get("notes", "")
    db.execute("UPDATE patient_followups SET status=?, notes=? WHERE id=?", (status, notes, followup_id))
    db.commit()
    log_action("UpdateFollowup", "patient_followup", followup_id, status)
    flash("Followup updated.")
    return redirect(url_for("followups_list"))



@app.route("/management/doctors", methods=["GET", "POST"])
@roles_required("admin")
def doctors_list():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO doctors (full_name, specialty, phone, email, commission_percent) "
            "VALUES (?, ?, ?, ?, ?)",
            (request.form.get("full_name", "").strip(), request.form.get("specialty"),
             request.form.get("phone"), request.form.get("email"),
             float(request.form.get("commission_percent") or 0)),
        )
        db.commit()
        flash("Doctor added.")
        return redirect(url_for("doctors_list"))
    doctors = db.execute("SELECT * FROM doctors ORDER BY full_name").fetchall()
    return render_template("management/doctors.html", doctors=doctors)


@app.route("/management/doctors/<int:doctor_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_doctor(doctor_id):
    db = get_db()
    doctor = db.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
    if not doctor:
        return "Not found", 404
    # لا نحذف الطبيب إذا مرتبط بزيارات أو طلبات موجودة فعلاً، حتى لا تبقى
    # سجلات يتيمة (orphaned) بالزيارات القديمة. بهذي الحالة نمنع الحذف
    # ونعرض للمستخدم عدد السجلات المرتبطة.
    linked_visits = db.execute("SELECT COUNT(*) c FROM visits WHERE doctor_id=?", (doctor_id,)).fetchone()["c"]
    linked_orders = db.execute("SELECT COUNT(*) c FROM order_tests WHERE doctor_id=?", (doctor_id,)).fetchone()["c"]
    if linked_visits or linked_orders:
        flash(f"لا يمكن حذف هذا الطبيب لأنه مرتبط بـ {linked_visits} زيارة و {linked_orders} طلب تحليل. "
              f"احذف/عدّل تلك السجلات أولاً إذا تريد حذفه فعلاً.")
        return redirect(url_for("doctors_list"))
    db.execute("DELETE FROM doctor_test_prices WHERE doctor_id=?", (doctor_id,))
    db.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
    db.commit()
    log_action("Delete", "doctor", doctor_id, doctor["full_name"])
    flash("تم حذف الطبيب.")
    return redirect(url_for("doctors_list"))


@app.route("/management/doctors/<int:doctor_id>/rates", methods=["GET", "POST"])
@roles_required("admin", "accountant")
def doctor_rates(doctor_id):
    db = get_db()
    doctor = db.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
    if not doctor:
        return "Not found", 404
    if request.method == "POST":
        test_id = request.form.get("test_id")
        price = request.form.get("price", "").strip()
        if price == "":
            # حقل فارغ = رجّع هذا التحليل لسعر المختبر الافتراضي لهذا الطبيب
            db.execute("DELETE FROM doctor_test_prices WHERE doctor_id=? AND test_definition_id=?",
                       (doctor_id, test_id))
            flash("Price reset to the default lab rate for this test.")
        else:
            db.execute(
                "INSERT INTO doctor_test_prices (doctor_id, test_definition_id, price) VALUES (?, ?, ?) "
                "ON CONFLICT(doctor_id, test_definition_id) DO UPDATE SET price=excluded.price",
                (doctor_id, test_id, float(price)),
            )
            flash("Doctor's price updated.")
        db.commit()
        return redirect(url_for("doctor_rates", doctor_id=doctor_id))

    tests = db.execute("SELECT * FROM test_definitions WHERE is_active=1 ORDER BY department, name").fetchall()
    overrides = {
        row["test_definition_id"]: row["price"]
        for row in db.execute(
            "SELECT test_definition_id, price FROM doctor_test_prices WHERE doctor_id=?", (doctor_id,)
        ).fetchall()
    }
    return render_template("management/doctor_rates.html", doctor=doctor, tests=tests, overrides=overrides)


@app.route("/management/doctors/<int:doctor_id>/statement")
@roles_required("admin")
def doctor_statement(doctor_id):
    db = get_db()
    doctor = db.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    rows = db.execute(
        "SELECT ot.id, td.name as test_name, COALESCE(ot.price, td.price) as price, "
        "p.full_name as patient_name, ot.created_at "
        "FROM order_tests ot JOIN test_definitions td ON td.id=ot.test_definition_id "
        "JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id "
        "JOIN patients p ON p.id=v.patient_id "
        "WHERE ot.doctor_id=? AND substr(ot.created_at,1,7)=? ORDER BY ot.created_at",
        (doctor_id, month),
    ).fetchall()
    total = sum((r["price"] or 0) for r in rows)
    commission_due = total * ((doctor["commission_percent"] or 0) / 100)
    return render_template("management/doctor_statement.html", doctor=doctor, rows=rows, month=month,
                            total=total, commission_due=commission_due)



@app.route("/management/examining-doctor-rates")
@roles_required("admin", "accountant")
def examining_doctor_rates_list():
    db = get_db()
    names = get_examining_doctors(db)
    rates_map = get_examining_rates_map(db)
    eligible_count = len(get_examining_tests(db))
    doctors_summary = [
        {"name": n, "configured_count": len(rates_map.get(n, {}))} for n in names
    ]
    return render_template("management/examining_doctor_rates_list.html",
                            doctors_summary=doctors_summary, eligible_count=eligible_count)


@app.route("/management/examining-doctor-rates/<doctor_name>", methods=["GET", "POST"])
@roles_required("admin", "accountant")
def examining_doctor_rates(doctor_name):
    db = get_db()
    if doctor_name not in get_examining_doctors(db):
        return "Not found", 404
    if request.method == "POST":
        test_id = request.form.get("test_id")
        rate = request.form.get("rate", "").strip()
        set_examining_doctor_rate(db, doctor_name, int(test_id), float(rate or 0))
        flash("تم تحديث أجر الدكتور الفاحص لهذا الفحص.")
        return redirect(url_for("examining_doctor_rates", doctor_name=doctor_name))

    tests = get_examining_tests(db)
    rates = get_examining_rates_map(db).get(doctor_name, {})
    return render_template("management/examining_doctor_rates.html", doctor_name=doctor_name,
                            tests=tests, rates=rates)


@app.route("/management/examining-doctor-rates/<doctor_name>/statement")
@roles_required("admin", "accountant")
def examining_doctor_statement(doctor_name):
    db = get_db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    rows = db.execute(
        "SELECT v.registration_number, v.examining_doctor_fee, v.created_at, p.full_name "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "WHERE v.examining_doctor=? AND substr(v.created_at,1,7)=? AND v.examining_doctor_fee > 0 "
        "ORDER BY v.created_at",
        (doctor_name, month),
    ).fetchall()
    total = sum((r["examining_doctor_fee"] or 0) for r in rows)
    return render_template("management/examining_doctor_statement.html", doctor_name=doctor_name,
                            rows=rows, month=month, total=total)


@app.route("/management/referral-labs", methods=["GET", "POST"])
@roles_required("admin")
def referral_labs_list():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name:
            flash("اسم المختبر إلزامي.")
            return redirect(url_for("referral_labs_list"))
        exists = db.execute(
            "SELECT id FROM referral_centers WHERE LOWER(TRIM(name))=LOWER(?)", (name,)
        ).fetchone()
        if exists:
            flash("هذا المختبر مضاف أصلاً.")
        else:
            db.execute("INSERT INTO referral_centers (name, type, phone) VALUES (?, 'Lab', ?)",
                       (name, phone or None))
            db.commit()
            flash("تمت إضافة المختبر.")
        return redirect(url_for("referral_labs_list"))

    labs = db.execute(
        "SELECT * FROM referral_centers WHERE name != 'Walk-in' ORDER BY name"
    ).fetchall()
    return render_template("management/referral_labs.html", labs=labs)


@app.route("/management/referral-labs/<int:center_id>/phone", methods=["POST"])
@roles_required("admin")
def referral_lab_update_phone(center_id):
    db = get_db()
    phone = request.form.get("phone", "").strip()
    db.execute("UPDATE referral_centers SET phone=? WHERE id=?", (phone or None, center_id))
    db.commit()
    flash("تم تحديث رقم واتساب المختبر.")
    return redirect(url_for("referral_labs_list"))


def _referral_lab_statement_data(db, center_id, month):
    """يرجّع (lab, rows, by_day, by_test, total) لكشف حساب مختبر مُرسِل معيّن
    عن شهر معيّن — كل تحليل بكل نموذج وارد منه بهذا الشهر، مجمّع يوميًا
    (لمتابعة الحساب أول بأول) ومجمّع حسب نوع التحليل (لملخص نهاية الشهر)."""
    lab = db.execute("SELECT * FROM referral_centers WHERE id=?", (center_id,)).fetchone()
    if not lab:
        return None, [], [], [], 0.0

    rows = db.execute(
        "SELECT ot.id, td.name as test_name, COALESCE(ot.price, td.price) as price, "
        "p.full_name as patient_name, v.registration_number, v.created_at "
        "FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE v.referral_center_id=? AND substr(v.created_at,1,7)=? "
        "ORDER BY v.created_at",
        (center_id, month),
    ).fetchall()

    day_map = {}
    test_map = {}
    total = 0.0
    for r in rows:
        price = r["price"] or 0
        total += price
        day_key = (r["created_at"] or "")[:10]
        d = day_map.setdefault(day_key, {"date": day_key, "count": 0, "subtotal": 0.0})
        d["count"] += 1
        d["subtotal"] += price
        tname = r["test_name"]
        tm = test_map.setdefault(tname, {"test_name": tname, "count": 0, "subtotal": 0.0})
        tm["count"] += 1
        tm["subtotal"] += price

    by_day = sorted(day_map.values(), key=lambda x: x["date"])
    by_test = sorted(test_map.values(), key=lambda x: -x["subtotal"])
    return lab, rows, by_day, by_test, total


@app.route("/management/referral-labs/<int:center_id>/statement")
@roles_required("admin", "accountant")
def referral_lab_statement(center_id):
    db = get_db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    lab, rows, by_day, by_test, total = _referral_lab_statement_data(db, center_id, month)
    if not lab:
        return "Not found", 404
    return render_template("management/referral_lab_statement.html", lab=lab, rows=rows,
                            by_day=by_day, by_test=by_test, total=total, month=month)


@app.route("/management/referral-labs/<int:center_id>/statement/pdf")
@roles_required("admin", "accountant")
def referral_lab_statement_pdf(center_id):
    import pdf_export

    db = get_db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    lab, rows, by_day, by_test, total = _referral_lab_statement_data(db, center_id, month)
    if not lab:
        return "Not found", 404
    html_content = render_template("management/print_referral_lab_statement.html", lab=lab,
                                    by_day=by_day, by_test=by_test, total=total, month=month)
    pdf_path = pdf_export.make_temp_pdf_path(f"reflab{center_id}_{month}")
    try:
        pdf_export.html_to_pdf(html_content, request.url_root, pdf_path)
    except Exception as exc:
        flash(f"❌ تعذّر توليد ملف PDF لكشف الحساب: {exc}")
        return redirect(url_for("referral_lab_statement", center_id=center_id, month=month))
    log_action("PDF", "referral_center", center_id, f"statement {month}")
    safe_name = re.sub(r"[^\w\-]+", "_", lab["name"])
    return send_file(pdf_path, as_attachment=True, download_name=f"{safe_name}_{month}.pdf")


@app.route("/management/referral-labs/<int:center_id>/statement/whatsapp", methods=["POST"])
@roles_required("admin", "accountant")
def referral_lab_statement_whatsapp(center_id):
    import pdf_export

    db = get_db()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    lab, rows, by_day, by_test, total = _referral_lab_statement_data(db, center_id, month)
    if not lab:
        return "Not found", 404
    if not lab["phone"]:
        flash("لا يوجد رقم واتساب مسجّل لهذا المختبر — أضِفه أولًا من نفس هذي الصفحة.")
        return redirect(url_for("referral_labs_list"))

    html_content = render_template("management/print_referral_lab_statement.html", lab=lab,
                                    by_day=by_day, by_test=by_test, total=total, month=month)
    pdf_path = pdf_export.make_temp_pdf_path(f"reflab{center_id}_{month}")
    try:
        pdf_export.html_to_pdf(html_content, request.url_root, pdf_path)
    except Exception as exc:
        flash(f"❌ تعذّر توليد ملف PDF لإرساله: {exc}")
        return redirect(url_for("referral_lab_statement", center_id=center_id, month=month))

    opened_wa, _ = _open_whatsapp_with_pdf(
        lab["phone"], pdf_path, get_setting(db, "whatsapp_country_code", "964")
    )
    if opened_wa:
        flash(f"📎 جهّزنا كشف حساب {month} وفتحنا واتساب على رقم {lab['name']} — اسحب الملف من نافذة المجلد وأرسله يدويًا.")
        log_action("WhatsAppSend", "referral_center", center_id, f"statement {month} opened")
    else:
        flash("❌ تعذّر فتح تطبيق واتساب — تأكد إنه مثبّت على هذا الجهاز.")
        log_action("WhatsAppSend", "referral_center", center_id, f"statement {month} failed")
    return redirect(url_for("referral_lab_statement", center_id=center_id, month=month))


@app.route("/front-desk/visits")
@login_required
def visits_list():
    db = get_db()
    q = request.args.get("q", "").strip()
    show_all = request.args.get("all") == "1"
    # فلترة اختيارية بطبيب مُحيل أو مختبر مُرسِل — تُستخدم من نتائج بحث
    # الرئيسية (بحث باسم طبيب/مختبر) لعرض كل زياراته مرتبة بالأحدث تاريخًا
    # ووقتًا، بغض النظر عن يوم الزيارة (بعكس الوضع الافتراضي المقتصر على
    # اليوم الحالي فقط).
    doctor_id = request.args.get("doctor_id", type=int)
    referral_center_id = request.args.get("referral_center_id", type=int)
    filter_label = None
    if doctor_id:
        row = db.execute("SELECT full_name FROM doctors WHERE id=?", (doctor_id,)).fetchone()
        if row:
            filter_label = f"زيارات الدكتور المُحيل: {row['full_name']}"
    elif referral_center_id:
        row = db.execute("SELECT name FROM referral_centers WHERE id=?", (referral_center_id,)).fetchone()
        if row:
            filter_label = f"زيارات المختبر المُرسِل: {row['name']}"

    query = (
        "SELECT v.id, v.registration_number, p.full_name, p.gender, p.age, p.phone, "
        "v.status, v.created_at, v.attending_doctor, "
        "(SELECT COALESCE(SUM(ot.price),0) FROM order_tests ot "
        " JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=v.id) as total, "
        # الواصل (المبلغ المدفوع فعليًا) والإجمالي الفعلي بالفاتورة (بعد أي
        # خصم/رسوم إضافية) — يُستخدمان بالقالب لعرض "الواصل" و"الباقي" بدل
        # حقل "المدفوع" القديم. LEFT JOIN لأن بعض الزيارات القديمة قد لا
        # تملك صف فاتورة.
        "COALESCE(i.paid_amount, 0) as paid_amount, i.total_amount as invoice_total "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN invoices i ON i.visit_id = v.id "
    )
    params = []
    conditions = []
    if doctor_id:
        conditions.append("v.doctor_id=?")
        params.append(doctor_id)
    elif referral_center_id:
        conditions.append("v.referral_center_id=?")
        params.append(referral_center_id)
    elif q:
        conditions.append("(p.full_name LIKE ? OR p.phone LIKE ? OR v.registration_number LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    elif not show_all:
        # الصفحة تعرض زيارات اليوم الحالي فقط افتراضيًا — تُصفَّر تلقائيًا كل
        # يوم جديد. السجل الكامل لكل الأيام السابقة يبقى متوفرًا دائمًا عبر
        # صفحة "السجلات" (التقرير اليومي)، أو بالبحث بالاسم/الرقم هنا.
        today = date.today().isoformat()
        conditions.append("substr(v.created_at,1,10)=?")
        params.append(today)
    if conditions:
        query += "WHERE " + " AND ".join(conditions) + " "
    query += "ORDER BY v.created_at DESC, v.id DESC LIMIT 100"
    visits = db.execute(query, params).fetchall()
    return render_template("front_desk/visits.html", visits=visits, q=q, show_all=show_all,
                            filter_label=filter_label)

@app.route("/front-desk/visits/<int:visit_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_visit(visit_id):
    """حذف زيارة بالكامل مع كل ما يتبعها (طلبات، نتائج، فواتير، مدفوعات،
    متابعات، إرسالات واتساب)، ثم — إذا صار المريض بلا أي زيارة أخرى — يُحذف
    المريض نفسه فينحذف من صفحة/أيقونة المرضى، وكذلك إذا صار الدكتور المرسل
    (doctor_id) غير مرتبط بأي زيارة أو طلب تحليل آخر يُحذف هو الآخر تلقائيًا."""
    db = get_db()
    visit = db.execute("SELECT * FROM visits WHERE id=?", (visit_id,)).fetchone()
    if not visit:
        return "Not found", 404

    patient_id = visit["patient_id"]
    doctor_id = visit["doctor_id"]

    order_ids = [r["id"] for r in db.execute("SELECT id FROM orders WHERE visit_id=?", (visit_id,)).fetchall()]
    if order_ids:
        placeholders = ",".join("?" * len(order_ids))
        order_test_ids = [r["id"] for r in db.execute(
            f"SELECT id FROM order_tests WHERE order_id IN ({placeholders})", order_ids
        ).fetchall()]
        if order_test_ids:
            ot_placeholders = ",".join("?" * len(order_test_ids))
            db.execute(f"DELETE FROM result_history WHERE order_test_id IN ({ot_placeholders})", order_test_ids)
            db.execute(f"DELETE FROM results WHERE order_test_id IN ({ot_placeholders})", order_test_ids)
        db.execute(f"DELETE FROM order_tests WHERE order_id IN ({placeholders})", order_ids)
    db.execute("DELETE FROM orders WHERE visit_id=?", (visit_id,))
    db.execute(
        "DELETE FROM payments WHERE invoice_id IN (SELECT id FROM invoices WHERE visit_id=?)",
        (visit_id,),
    )
    db.execute("DELETE FROM invoices WHERE visit_id=?", (visit_id,))
    db.execute("DELETE FROM removed_order_tests WHERE visit_id=?", (visit_id,))
    db.execute("DELETE FROM patient_followups WHERE visit_id=?", (visit_id,))
    db.execute("DELETE FROM whatsapp_sends WHERE visit_id=?", (visit_id,))
    db.execute("DELETE FROM visits WHERE id=?", (visit_id,))
    db.commit()
    log_action("Delete", "visit", visit_id, visit["registration_number"])

    # المريض: يُحذف فقط إذا ما عنده أي زيارة أخرى، حتى ما نحذف مريض له سجل
    # فعلي بزيارات ثانية.
    remaining_visits = db.execute(
        "SELECT COUNT(*) c FROM visits WHERE patient_id=?", (patient_id,)
    ).fetchone()["c"]
    if remaining_visits == 0:
        patient = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if patient:
            db.execute("DELETE FROM patient_followups WHERE patient_id=?", (patient_id,))
            db.execute("DELETE FROM patients WHERE id=?", (patient_id,))
            db.commit()
            log_action("Delete", "patient", patient_id, patient["full_name"])

    # الدكتور المرسل: يُحذف فقط إذا ما بقى مرتبط بأي زيارة أو طلب تحليل آخر.
    if doctor_id:
        linked_visits = db.execute(
            "SELECT COUNT(*) c FROM visits WHERE doctor_id=?", (doctor_id,)
        ).fetchone()["c"]
        linked_orders = db.execute(
            "SELECT COUNT(*) c FROM order_tests WHERE doctor_id=?", (doctor_id,)
        ).fetchone()["c"]
        if not linked_visits and not linked_orders:
            doctor = db.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
            if doctor:
                db.execute("DELETE FROM doctor_test_prices WHERE doctor_id=?", (doctor_id,))
                db.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
                db.commit()
                log_action("Delete", "doctor", doctor_id, doctor["full_name"])

    flash("تم حذف الزيارة، والمريض والدكتور المرسل أيضًا إذا صاروا بلا أي زيارات أخرى مرتبطة.")
    return redirect(url_for("visits_list"))


@app.route("/front-desk/visits/<int:visit_id>/edit", methods=["GET", "POST"])
@login_required
def visit_edit(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name, p.gender, p.age, p.age_unit, p.phone, p.title, p.email, "
        "p.national_id, p.passport_number, p.travel_certificate_number, p.lab_card_number "
        "FROM visits v JOIN patients p ON p.id = v.patient_id WHERE v.id=?", (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404
    order = db.execute("SELECT * FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()

    if request.method == "POST":
        if invoice and invoice["is_locked"]:
            flash("This invoice is locked and cannot be edited.")
            return redirect(url_for("visits_list"))

        _ve_name = request.form.get("patient_name", "").strip()
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
        )
        referring_doctor_id = find_or_create_doctor(db, request.form.get("doctor_name", ""))
        doctor_changed = referring_doctor_id != visit["doctor_id"]

        examining_doctor = request.form.get("examining_doctor", "")
        # نفس منطق شاشة "زيارة جديدة" — attending_doctor يتبع examining_doctor
        # تلقائيًا الآن بعد ما صار حقلاً واحدًا بالشاشة.
        attending_doctor = examining_doctor
        referral_center_id = find_or_create_referral_center(db, request.form.get("referral_lab_name", ""))
        # المعلومات الصحية + الزيارة المنزلية — نفس حقول شاشة "زيارة جديدة".
        weight = request.form.get("weight") or None
        height = request.form.get("height") or None
        symptoms = request.form.get("symptoms", "")
        disease = request.form.get("disease", "")
        therapy = request.form.get("therapy", "")
        is_home_visit = 1 if request.form.get("is_home_visit") == "1" else 0
        home_visit_address = request.form.get("home_visit_address", "") if is_home_visit else ""
        try:
            home_visit_fee = float(request.form.get("home_visit_fee") or 0) if is_home_visit else 0.0
        except ValueError:
            home_visit_fee = 0.0
        db.execute(
            "UPDATE visits SET doctor_id=?, referral_center_id=?, fasting=?, notes=?, examining_doctor=?, "
            "expenses=?, attending_doctor=?, weight=?, height=?, symptoms=?, disease=?, therapy=?, "
            "is_home_visit=?, home_visit_address=?, home_visit_fee=? WHERE id=?",
            (referring_doctor_id, referral_center_id, request.form.get("fasting", "Undefined"), request.form.get("notes", ""),
             examining_doctor, request.form.get("expenses") or 0, attending_doctor,
             weight, height, symptoms, disease, therapy,
             is_home_visit, home_visit_address, home_visit_fee, visit_id))

        new_test_id = request.form.get("add_test")
        if new_test_id:
            test = db.execute("SELECT * FROM test_definitions WHERE id=?", (new_test_id,)).fetchone()
            if test:
                reg = visit["registration_number"]
                barcode = f"{reg}{new_test_id.zfill(3)}"
                price = get_test_price(db, new_test_id, referring_doctor_id)
                db.execute(
                    "INSERT INTO order_tests (order_id, test_definition_id, status, barcode, price, doctor_id, created_at) "
                    "VALUES (?, ?, 'Accepted', ?, ?, ?, ?)",
                    (order["id"], new_test_id, barcode, price, referring_doctor_id,
                     datetime.now().isoformat(timespec="seconds")),
                )

        # نعيد حساب أجر دكتور المختبر الفاحص حسب كل الفحوصات الحالية بالزيارة
        # (بعد أي حذف/إضافة) واسم الدكتور الفاحص المختار حاليًا.
        # (تحاليل "مجانية" fee_waived=1 تُستثنى تلقائيًا من هذا الحساب --
        # راجع recompute_examining_doctor_fee بـdatabase.py.)
        recompute_examining_doctor_fee(db, visit_id)

        # إذا انتغيّر الطبيب المُحيل، نعيد تسعير كل التحاليل الموجودة أصلاً
        # بالزيارة حسب جدول أسعار الطبيب الجديد (أو السعر الافتراضي إذا ماكو
        # طبيب / ماكو سعر خاص إله).
        if doctor_changed:
            existing = db.execute(
                "SELECT id, test_definition_id FROM order_tests WHERE order_id=?", (order["id"],)
            ).fetchall()
            for row in existing:
                new_price = get_test_price(db, row["test_definition_id"], referring_doctor_id)
                db.execute("UPDATE order_tests SET price=?, doctor_id=? WHERE id=?",
                           (new_price, referring_doctor_id, row["id"]))

        extra_charges = float(request.form.get("extra_charges") or 0)
        discount_amount = float(request.form.get("discount_amount") or 0)
        new_total = db.execute(
            "SELECT COALESCE(SUM(ot.price),0) as total FROM order_tests ot WHERE ot.order_id=?",
            (order["id"],),
        ).fetchone()["total"]
        # أجرة الزيارة المنزلية (إن فُعِّلت) تُضاف لمجموع الفحوصات، نفس أسلوب
        # شاشة "زيارة جديدة" — منفصلة عن حقل "Extra Charges" اليدوي.
        new_total += home_visit_fee
        if invoice:
            db.execute(
                "UPDATE invoices SET total_amount=?, extra_charges=?, discount_amount=? WHERE id=?",
                (new_total + extra_charges, extra_charges, discount_amount, invoice["id"]),
            )
        db.commit()
        log_action("Update", "visit", visit_id)
        flash("Visit updated.")
        return redirect(url_for("visits_list"))

    order_tests = db.execute(
        "SELECT ot.id, ot.status, ot.test_definition_id, ot.fee_waived, ot.hidden_from_log, td.name, td.is_examining_test, "
        "COALESCE(ot.price, td.price) as price "
        "FROM order_tests ot JOIN test_definitions td ON td.id = ot.test_definition_id WHERE ot.order_id=?",
        (order["id"] if order else 0,),
    ).fetchall()
    all_tests = db.execute("SELECT * FROM test_definitions WHERE is_active=1 ORDER BY department, name").fetchall()
    current_doctor_name = ""
    if visit["doctor_id"]:
        d = db.execute("SELECT full_name FROM doctors WHERE id=?", (visit["doctor_id"],)).fetchone()
        current_doctor_name = d["full_name"] if d else ""
    current_referral_lab_name = ""
    if visit["referral_center_id"]:
        rl = db.execute("SELECT name FROM referral_centers WHERE id=?", (visit["referral_center_id"],)).fetchone()
        current_referral_lab_name = rl["name"] if rl else ""
    doctors, doctor_prices, doctor_name_to_id = doctor_pricing_context(db)
    test_default_prices = {str(tst["id"]): tst["price"] for tst in all_tests}
    last_removed_row = db.execute(
        "SELECT rot.*, td.name as test_name FROM removed_order_tests rot "
        "JOIN test_definitions td ON td.id = rot.test_definition_id "
        "WHERE rot.visit_id=? AND rot.restored=0 ORDER BY rot.id DESC LIMIT 1",
        (visit_id,),
    ).fetchone()
    last_removed = dict(last_removed_row) if last_removed_row else None

    examining_test_ids = [row["id"] for row in get_examining_tests(db)]
    referral_labs = db.execute(
        "SELECT * FROM referral_centers WHERE name != 'Walk-in' ORDER BY name"
    ).fetchall()
    return render_template("front_desk/visit_edit.html", visit=visit, order_tests=order_tests,
                            all_tests=all_tests, invoice=invoice, examining_doctors=get_examining_doctors(db),
                            doctors=doctors, doctor_prices=doctor_prices, doctor_name_to_id=doctor_name_to_id,
                            current_doctor_name=current_doctor_name,
                            current_referral_lab_name=current_referral_lab_name,
                            test_default_prices=test_default_prices,
                            last_removed=last_removed, examining_test_ids=examining_test_ids,
                            examining_rates=get_examining_rates_map(db), referral_labs=referral_labs,
                            fee_waiver_configured=bool(get_setting(db, "fee_waiver_password_hash", "")))


@app.route("/front-desk/visits/<int:visit_id>/order-tests/<int:order_test_id>/price", methods=["POST"])
@login_required
def visit_update_test_price(visit_id, order_test_id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if invoice and invoice["is_locked"]:
        flash("This invoice is locked and cannot be edited.")
        return redirect(url_for("visit_edit", visit_id=visit_id))
    try:
        new_price = float(request.form.get(f"price_{order_test_id}"))
    except (TypeError, ValueError):
        flash("Invalid price.")
        return redirect(url_for("visit_edit", visit_id=visit_id))
    order_test = db.execute("SELECT * FROM order_tests WHERE id=?", (order_test_id,)).fetchone()
    if not order_test:
        return "Not found", 404
    db.execute("UPDATE order_tests SET price=? WHERE id=?", (new_price, order_test_id))
    if invoice:
        order = db.execute("SELECT * FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
        new_total = db.execute(
            "SELECT COALESCE(SUM(ot.price),0) as total FROM order_tests ot WHERE ot.order_id=?",
            (order["id"],),
        ).fetchone()["total"]
        db.execute(
            "UPDATE invoices SET total_amount=? WHERE id=?",
            (new_total + (invoice["extra_charges"] or 0), invoice["id"]),
        )
    db.commit()
    log_action("Update", "order_test_price", order_test_id)
    flash("Price updated.")
    return redirect(url_for("visit_edit", visit_id=visit_id))


@app.route("/front-desk/visits/<int:visit_id>/remove-test/<int:order_test_id>", methods=["POST"])
@login_required
def visit_remove_test(visit_id, order_test_id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if invoice and invoice["is_locked"]:
        flash("This invoice is locked.")
        return redirect(url_for("visit_edit", visit_id=visit_id))

    ot_row = db.execute("SELECT * FROM order_tests WHERE id=?", (order_test_id,)).fetchone()
    if not ot_row:
        return redirect(url_for("visit_edit", visit_id=visit_id))
    # المطلوب 2: حذف تحليل مكتمل (نتيجته جاهزة ومحفوظة) محمي بنفس كلمة
    # مرور حماية النتائج المكتملة أعلاه.
    if ot_row["status"] in ("Completed", "Verified"):
        ok, err = _check_completed_result_gate(db, request.form)
        if not ok:
            flash(err)
            return redirect(url_for("visit_edit", visit_id=visit_id))
    result_rows = db.execute("SELECT * FROM results WHERE order_test_id=?", (order_test_id,)).fetchall()
    snapshot = {
        "order_test": dict(ot_row),
        "results": [dict(r) for r in result_rows],
    }
    now = datetime.now().isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO removed_order_tests (visit_id, order_id, test_definition_id, snapshot, removed_by, removed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (visit_id, ot_row["order_id"], ot_row["test_definition_id"], json.dumps(snapshot), session["user_id"], now),
    )

    db.execute("DELETE FROM results WHERE order_test_id=?", (order_test_id,))
    db.execute("DELETE FROM order_tests WHERE id=?", (order_test_id,))
    order = db.execute("SELECT * FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
    new_total = db.execute(
        "SELECT COALESCE(SUM(ot.price),0) as total FROM order_tests ot WHERE ot.order_id=?",
        (order["id"],),
    ).fetchone()["total"]
    if invoice:
        db.execute("UPDATE invoices SET total_amount=? WHERE id=?",
                   (new_total + (invoice["extra_charges"] or 0), invoice["id"]))
    db.commit()
    log_action("RemoveTest", "order_test", order_test_id)
    flash("Test removed from visit. You can undo this from the visit edit page.")
    return redirect(url_for("visit_edit", visit_id=visit_id))


@app.route("/front-desk/visits/<int:visit_id>/undo-remove-test", methods=["POST"])
@login_required
def visit_undo_remove_test(visit_id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if invoice and invoice["is_locked"]:
        flash("This invoice is locked.")
        return redirect(url_for("visit_edit", visit_id=visit_id))

    last_removed = db.execute(
        "SELECT * FROM removed_order_tests WHERE visit_id=? AND restored=0 ORDER BY id DESC LIMIT 1",
        (visit_id,),
    ).fetchone()
    if not last_removed:
        flash("Nothing to undo.")
        return redirect(url_for("visit_edit", visit_id=visit_id))

    snapshot = json.loads(last_removed["snapshot"])
    ot = snapshot["order_test"]
    cur = db.execute(
        "INSERT INTO order_tests (order_id, test_definition_id, status, barcode, notes, doctor_id, "
        "collected_at, accessioned_at, price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ot["order_id"], ot["test_definition_id"], ot["status"], ot["barcode"], ot["notes"],
         ot["doctor_id"], ot["collected_at"], ot["accessioned_at"], ot.get("price"), ot["created_at"]),
    )
    new_order_test_id = cur.lastrowid
    for r in snapshot["results"]:
        db.execute(
            "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, "
            "entered_by, entered_at, verified_by, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_order_test_id, r["test_parameter_id"], r["value_numeric"], r["value_text"], r["flag"],
             r["entered_by"], r["entered_at"], r["verified_by"], r["verified_at"]),
        )
    db.execute("UPDATE removed_order_tests SET restored=1 WHERE id=?", (last_removed["id"],))

    order = db.execute("SELECT * FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
    new_total = db.execute(
        "SELECT COALESCE(SUM(ot.price),0) as total FROM order_tests ot WHERE ot.order_id=?",
        (order["id"],),
    ).fetchone()["total"]
    if invoice:
        db.execute("UPDATE invoices SET total_amount=? WHERE id=?",
                   (new_total + (invoice["extra_charges"] or 0), invoice["id"]))
    db.commit()
    log_action("UndoRemoveTest", "order_test", new_order_test_id)
    flash("Test restored.")
    return redirect(url_for("visit_edit", visit_id=visit_id))



@app.route("/barcode/<code>.png")
def barcode_image(code):
    img = generate_code39(code)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


def _visit_barcode_context(db, visit_id):
    """Visit + its ordered tests, used to build the visit barcode label
    (both the print page and the Code128/QR image endpoints)."""
    visit = db.execute(
        "SELECT v.*, p.full_name, p.age, p.age_unit, p.gender FROM visits v "
        "JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return None, None
    tests = db.execute(
        "SELECT td.name, td.name_ar, td.code FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
        (visit_id,),
    ).fetchall()
    # ساعة السحب: أوّل collected_at مسجّل بين تحاليل الزيارة، وإن ما كانت
    # العيّنة مسحوبة بعد نرجع لوقت إنشاء الزيارة كبديل.
    draw_row = db.execute(
        "SELECT MIN(ot.collected_at) as draw_time FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=? AND ot.collected_at IS NOT NULL",
        (visit_id,),
    ).fetchone()
    draw_time = (draw_row["draw_time"] if draw_row else None) or visit["created_at"]
    return visit, tests, draw_time


@app.route("/front-desk/visits/<int:visit_id>/barcode/code128.png")
@login_required
def visit_barcode_code128(visit_id):
    # Code128 (English/Latin only) carries the registration number plus the
    # English test codes -- this is what lab scanners/instruments read.
    db = get_db()
    visit, tests, draw_time = _visit_barcode_context(db, visit_id)
    if not visit:
        return "Not found", 404
    test_codes = [row["code"] for row in tests if row["code"]]
    reg = visit["registration_number"]
    payload = f"{reg}|{','.join(test_codes)}" if test_codes else str(reg)
    img = generate_code128(payload, caption=str(reg))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/front-desk/visits/<int:visit_id>/barcode/qr.png")
@login_required
def visit_barcode_qr(visit_id):
    # QR carries the Arabic content (Code128 cannot represent it): the
    # patient's full (triple) name plus the Arabic names of their tests.
    db = get_db()
    visit, tests, draw_time = _visit_barcode_context(db, visit_id)
    if not visit:
        return "Not found", 404
    test_names_ar = [(row["name_ar"] or row["name"]) for row in tests]
    lines = [visit["full_name"]]
    if test_names_ar:
        lines.append("، ".join(test_names_ar))
    img = generate_qr("\n".join(lines))
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/front-desk/visits/<int:visit_id>/print/barcode")
@login_required
def print_visit_barcode(visit_id):
    db = get_db()
    visit, tests, draw_time = _visit_barcode_context(db, visit_id)
    if not visit:
        return "Not found", 404
    return render_template("front_desk/print_visit_barcode.html", visit=visit, tests=tests, draw_time=draw_time)


@app.route("/api/barcode/<code>")
@login_required
def api_barcode_lookup(code):
    """يرجّع معلومات المريض كاملة + كل التحاليل المرتبطة بهذا الباركود —
    سواء كان باركود أنبوب مشترك (tube_barcode، يغطي عدة تحاليل بنفس نوع
    العينة) أو باركود تحليل فردي قديم (barcode). مصمَّم ليكون نقطة وصول
    لأي جهاز/برنامج وسيط خارجي (Middleware) يقرأ الباركود من الأنبوب ويريد
    يعرف شنو التحاليل المطلوبة ولمين، بدون الحاجة يفتح الواجهة."""
    db = get_db()
    rows = db.execute(
        "SELECT ot.id as order_test_id, ot.status, ot.barcode, ot.tube_barcode, "
        "td.name as test_name, td.sample_type, td.department, "
        "p.id as patient_id, p.full_name, p.full_name_en, p.age, p.age_unit, p.gender, "
        "v.id as visit_id, v.registration_number "
        "FROM order_tests ot JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE ot.tube_barcode=? OR ot.barcode=?",
        (code, code),
    ).fetchall()
    if not rows:
        return jsonify({"ok": False, "error": "لا يوجد باركود مطابق"}), 404
    first = rows[0]
    return jsonify({
        "ok": True,
        "barcode": code,
        "patient": {
            "id": first["patient_id"], "name": first["full_name"], "name_en": first["full_name_en"],
            "age": first["age"], "age_unit": first["age_unit"], "gender": first["gender"],
        },
        "visit": {"id": first["visit_id"], "registration_number": first["registration_number"]},
        "tests": [
            {"order_test_id": r["order_test_id"], "name": r["test_name"], "sample_type": r["sample_type"],
             "department": r["department"], "status": r["status"]}
            for r in rows
        ],
    })


@app.route("/public/results-board")
def public_results_board():
    """شاشة عرض عامة (بدون تسجيل دخول) — تُفتح على شاشة/تلفزيون خارجي
    بصالة الانتظار، تعرض التحاليل المكتملة اليوم بشكل مباشر، وتتحدث
    تلقائيًا كل دقيقة. لا تحتاج صلاحية عمداً لأنها مصممة للعرض العام
    بمواجهة المراجعين، مو للموظفين."""
    return render_template("public/results_board.html")


@app.route("/api/public/completed-today")
def api_public_completed_today():
    """يرجّع آخر التحاليل المكتملة اليوم (اسم المريض + اسم التحليل + وقت
    الإنجاز) — يغذّي شاشة العرض العامة أعلاه. يعتمد وقت آخر نتيجة أُدخلت
    فعليًا (results.entered_at) كـ"وقت الإنجاز"، مو وقت تسجيل الزيارة."""
    db = get_db()
    rows = db.execute(
        "SELECT ot.id as order_test_id, p.full_name, td.name as test_name, "
        "MAX(r.entered_at) as completed_at "
        "FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN results r ON r.order_test_id = ot.id "
        "WHERE ot.status IN ('Completed', 'Verified') "
        "AND date(r.entered_at) = date('now', 'localtime') "
        "GROUP BY ot.id "
        "ORDER BY completed_at DESC "
        "LIMIT 30"
    ).fetchall()
    return jsonify([
        {"order_test_id": r["order_test_id"], "patient_name": r["full_name"],
         "test_name": r["test_name"], "completed_at": r["completed_at"]}
        for r in rows
    ])


@app.route("/front-desk/print-barcode")
@login_required
def print_barcode_finder():
    """صفحة بحث سريعة: اكتب اسم المريض، تطلعلك آخر زياراته والتحاليل
    المطلوبة بيها، وتضغط زر لتطبع باركوداتها — مفيدة لو تلف باركود أصلي
    وتحتاج تعيد طباعته بسرعة بدون الرجوع لسجل الزيارة الكامل."""
    return render_template("front_desk/print_barcode_finder.html")


@app.route("/api/patients/<int:patient_id>/recent-visits")
@login_required
def api_patient_recent_visits(patient_id):
    """يرجّع آخر بضع زيارات لمريض معيّن مع أسماء تحاليل كل زيارة — تغذّي
    صفحة "طباعة باركود" السريعة (البحث بالاسم)."""
    db = get_db()
    visits = db.execute(
        "SELECT id, registration_number, created_at FROM visits "
        "WHERE patient_id=? ORDER BY created_at DESC LIMIT 10",
        (patient_id,),
    ).fetchall()
    out = []
    for v in visits:
        tests = [t["name"] for t in db.execute(
            "SELECT DISTINCT td.name FROM order_tests ot "
            "JOIN orders o ON o.id = ot.order_id "
            "JOIN test_definitions td ON td.id = ot.test_definition_id "
            "WHERE o.visit_id=?",
            (v["id"],),
        ).fetchall()]
        out.append({
            "visit_id": v["id"], "registration_number": v["registration_number"],
            "created_at": v["created_at"], "tests": tests,
        })
    return jsonify(out)


@app.route("/front-desk/visits/<int:visit_id>/print/samples")
@login_required
def print_sample_barcodes(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name FROM visits v JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404
    rows = db.execute(
        "SELECT ot.id, ot.barcode, ot.tube_barcode, td.name as test_name, td.sample_type FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
        (visit_id,),
    ).fetchall()

    # تجميع تحاليل هذي الزيارة حسب نوع العينة (sample_type) — كل التحاليل
    # اللي تحتاج نفس الأنبوب (Serum مثلاً) تشترك بباركود وحد بدل باركود
    # مستقل لكل تحليل، لأن فعليًا هي نفس الأنبوب المسحوب مرة وحدة. تحليل
    # بدون sample_type محدد (فاضي) ياخذ باركوده الفردي القديم لحاله، لأننا
    # ما نعرف أكيد أي أنبوب يشاركه.
    groups = {}
    ungrouped = []
    for r in rows:
        stype = (r["sample_type"] or "").strip()
        if not stype:
            ungrouped.append(r)
            continue
        groups.setdefault(stype, []).append(r)

    reg_number = visit["registration_number"]
    tube_samples = []
    next_index = 1
    for stype in sorted(groups.keys()):
        group_rows = groups[stype]
        existing = next((r["tube_barcode"] for r in group_rows if r["tube_barcode"]), None)
        if existing:
            tube_barcode = existing
        else:
            tube_barcode = f"{reg_number}T{next_index}"
            next_index += 1
            ids = [r["id"] for r in group_rows]
            placeholders = ",".join("?" * len(ids))
            db.execute(f"UPDATE order_tests SET tube_barcode=? WHERE id IN ({placeholders})",
                       (tube_barcode, *ids))
        tube_samples.append({
            "sample_type": stype,
            "barcode": tube_barcode,
            "test_names": [r["test_name"] for r in group_rows],
        })
    if next_index > 1:
        db.commit()

    # تحاليل بلا sample_type محدد — ما نعرف أي أنبوب تشاركه بأمان، فتطلع
    # كل وحدة بكارد مستقل لحالها (بباركودها الفردي الأصلي)، بدل ما تختفي
    # كليًا من العرض الرئيسي.
    for r in ungrouped:
        tube_samples.append({
            "sample_type": r["test_name"],  # ما فيه نوع عينة معروف، فنعرض اسم التحليل نفسه كتوضيح
            "barcode": r["barcode"],
            "test_names": [r["test_name"]],
        })

    # باركودات فردية لكل تحليل لحاله — تبقى متوفرة كخيار إضافي (زر منفصل
    # بالقالب) لمن يحتاج يطبع باركود وحيد لتحليل معيّن بس (مثلاً لإرسال
    # عينة لمختبر مُحيل لتحليل واحد فقط)، بدون ما يأثر على السلوك الافتراضي
    # الجديد (باركود واحد لكل أنبوب).
    individual_samples = [
        {"barcode": r["barcode"], "test_name": r["test_name"], "sample_type": r["sample_type"]}
        for r in rows
    ]

    return render_template(
        "front_desk/print_sample_barcodes.html", visit=visit,
        tube_samples=tube_samples, individual_samples=individual_samples,
        samples=individual_samples,  # توافق مع أي نسخة قديمة من القالب لسا تستخدم "samples"
    )


@app.route("/front-desk/visits/<int:visit_id>/print/invoice")
@login_required
def print_invoice(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name, p.age, p.gender, p.phone, "
        "rc.name as referral_center_name "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id "
        "WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404
    items = db.execute(
        "SELECT td.name, td.name_ar, COALESCE(ot.price, td.price) as price FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
        (visit_id,),
    ).fetchall()
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    doctor = None
    if visit["doctor_id"]:
        doctor = db.execute("SELECT * FROM doctors WHERE id=?", (visit["doctor_id"],)).fetchone()
    return render_template("front_desk/print_invoice.html", visit=visit, items=items,
                            invoice=invoice, doctor=doctor)


# طباعة تحاليل ونتائج زيارة واحدة فقط (تُستخدم من زر "طباعة" أمام أي زيارة
# سابقة تظهر بشاشة "زيارة جديدة" عند العثور على المريض بالبحث الفوري).
@app.route("/front-desk/visits/<int:visit_id>/print/results")
@login_required
def print_visit_results(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name, p.age, p.age_unit, p.gender, p.phone, "
        "rc.name as referral_center_name FROM visits v "
        "JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404
    # نفس منطق from_other_lab بصفحة print_report: نعرض العبارة فقط، وما
    # نطبع اسم المختبر المرسل بأي مكان بهذي الصفحة (الجدول الموحّد للزيارة).
    from_other_lab = bool(visit["referral_center_id"]) and visit["referral_center_name"] not in (None, "", "Walk-in")
    # completed_only=1: يُستخدم من زرّي "طباعة/إرسال كل النتائج المكتملة" أعلى
    # شاشة إدخال النتائج، حتى لا تُطبع/تُرسل تحاليل لسا بانتظار الإدخال أو
    # الاعتماد ضمن نفس الملف.
    completed_only = request.args.get("completed_only") == "1"
    query = (
        "SELECT ot.id, ot.barcode, ot.status, td.name as test_name, td.name_ar as test_name_ar "
        "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE o.visit_id=?"
    )
    order_tests = db.execute(query, (visit_id,)).fetchall()
    if completed_only:
        order_tests = [ot for ot in order_tests if ot["status"] in ("Completed", "Verified")]
    tests_with_results = []
    for ot in order_tests:
        results = db.execute(
            "SELECT r.*, tp.name as param_name, tp.unit FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
            (ot["id"],),
        ).fetchall()
        tests_with_results.append({"order_test": ot, "results": results})
    return render_template("front_desk/print_visit_results.html", visit=visit,
                            tests_with_results=tests_with_results, from_other_lab=from_other_lab,
                            completed_only=completed_only)


# "طباعة كل النتائج المكتملة" بشاشة إدخال النتائج — بدل الجدول الموحّد
# العام (print_visit_results فوق، الذي لا يستخدم تصميم التقرير الخاص بكل
# تحليل)، هذا الزر يفتح لكل تحليل مكتمل تقريره المخصّص الحقيقي (نفس
# print_report المستخدم من زر "🖨 طباعة التقرير" أسفل كل تحليل مباشرة) —
# كل واحد بنافذة/تبويب منفصلة، حتى يطابق شكل التقرير المطبوع تماماً شكل
# تقرير نفس التحليل لو طبعته لحاله. صفحة "مُشغّل" خفيفة فقط تفتح الروابط
# تلقائياً + تعرضها كروابط احتياطية لو المتصفح منع النوافذ المنبثقة.
@app.route("/front-desk/visits/<int:visit_id>/print/results-bundle")
@login_required
def print_visit_results_bundle(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name, p.phone FROM visits v JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404

    order_tests = db.execute(
        "SELECT ot.id, ot.status, td.code as test_code, td.name as test_name, td.department as test_department "
        "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "WHERE o.visit_id=? AND ot.status IN ('Completed', 'Verified') ORDER BY ot.id",
        (visit_id,),
    ).fetchall()

    # نفس منطق الترتيب المستخدم بشاشة "إدخال النتائج" بالضبط (ترتيب يدوي من
    # الإعدادات إن وُجد، وإلا حسب أولوية القسم: كيمياء ← فايروسات ← هرمونات ←
    # فيتامينات ← تخثر ← أمراض الدم) — كانت هذي الصفحة تستخدم ترتيب الإضافة
    # الخام (ot.id) فقط بدون أي فرز، فتفتح التقارير بترتيب عشوائي لا علاقة له
    # بترتيب شاشة الإدخال.
    order_pref_raw = get_setting(db, "results_entry_test_order", "")
    order_pref = [ln.strip() for ln in order_pref_raw.splitlines() if ln.strip()]
    if order_pref:
        rank = {name: i for i, name in enumerate(order_pref)}
        order_tests = sorted(
            order_tests,
            key=lambda row: (
                rank.get(row["test_name"], len(order_pref)),
                department_priority_rank(row["test_department"]),
                row["id"],
            ),
        )
    else:
        order_tests = sorted(
            order_tests,
            key=lambda row: (department_priority_rank(row["test_department"]), row["id"]),
        )

    # تجنّب فتح تقرير "لطاخة الدم" مرتين لو الزيارة فيها BF وRETIC كتحليلين
    # منفصلين (بدل BFRETIC الموحّد) — print_report أصلاً يدمجهم بتقرير واحد
    # لو فتحت أي وحدة منهم (انظر BF_RETIC_LINK)، فنكتفي هنا برابط واحد بس.
    seen_codes = set()
    reports = []
    for ot in order_tests:
        code = ot["test_code"]
        if code in BF_RETIC_LINK and BF_RETIC_LINK[code] in seen_codes:
            continue
        seen_codes.add(code)
        reports.append({"order_test_id": ot["id"], "test_name": ot["test_name"]})

    return render_template("front_desk/print_results_bundle.html", visit=visit, reports=reports)


# يبني ملف HTML واحد مدمج من كل التقاريـر المصممة الحقيقية (نفس تصميم
# كل تحليل بالضبط لو طُبع لحاله عبر print_report) لكل تحليل مكتمل بهذي
# الزيارة — يُستخدم لتوليد PDF واحد (أرشفة/واتساب) بدل الجدول العام
# البسيط القديم (print_visit_results)، الذي لا يعكس تصميم أي تقرير.
# نفس منطق الترتيب ودمج Blood Film/Retic المستخدم بصفحة "طباعة كل
# النتائج المكتملة" (print_visit_results_bundle فوق) بالضبط، حتى يطابق
# ملف الـPDF المُرسَل/المؤرشف شكل وترتيب نفس التقارير المعروضة هناك.
# يرجّع None لو ما فيه أي تحليل مكتمل بعد (أو تعذّر توليد أي تقرير منها).
def _build_combined_designed_reports_html(visit_id):
    db = get_db()
    order_tests = db.execute(
        "SELECT ot.id, ot.status, td.code as test_code, td.name as test_name, td.department as test_department "
        "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "WHERE o.visit_id=? AND ot.status IN ('Completed', 'Verified') ORDER BY ot.id",
        (visit_id,),
    ).fetchall()
    order_pref_raw = get_setting(db, "results_entry_test_order", "")
    order_pref = [ln.strip() for ln in order_pref_raw.splitlines() if ln.strip()]
    if order_pref:
        rank = {name: i for i, name in enumerate(order_pref)}
        order_tests = sorted(
            order_tests,
            key=lambda row: (
                rank.get(row["test_name"], len(order_pref)),
                department_priority_rank(row["test_department"]),
                row["id"],
            ),
        )
    else:
        order_tests = sorted(
            order_tests,
            key=lambda row: (department_priority_rank(row["test_department"]), row["id"]),
        )

    seen_codes = set()
    order_test_ids = []
    for ot in order_tests:
        code = ot["test_code"]
        if code in BF_RETIC_LINK and BF_RETIC_LINK[code] in seen_codes:
            continue
        seen_codes.add(code)
        order_test_ids.append(ot["id"])

    head_html = None
    body_sections = []
    for otid in order_test_ids:
        try:
            report_html = print_report(otid)
        except Exception:
            continue
        if not isinstance(report_html, str):
            continue  # print_report رجّع redirect (لا يوجد تصميم لهذا التحليل) — نتجاهله بصمت ونكمل الباقي
        head_match = re.search(r"<head\b[^>]*>(.*?)</head>", report_html, re.S)
        body_match = re.search(r"<body\b[^>]*>(.*?)</body>", report_html, re.S)
        if not body_match:
            continue
        if head_html is None and head_match:
            head_html = head_match.group(1)
        page_break = "" if not body_sections else ' style="page-break-before:always;"'
        body_sections.append(f"<div{page_break}>{body_match.group(1)}</div>")

    if not body_sections:
        return None
    return (
        "<!DOCTYPE html><html lang=\"ar\" dir=\"rtl\"><head>"
        + (head_html or "")
        + "</head><body>"
        + "".join(body_sections)
        + "</body></html>"
    )


# الجدول الموحّد: يدمج نتائج زيارة أو أكثر (عادة زيارة قديمة + الزيارة الجديدة)
# بصفحة واحدة، صف لكل باراميتر وعمود لكل زيارة، حتى تتضح مقارنة النتائج عبر
# الزمن دون الحاجة لنسخ أي بيانات فعليًا داخل قاعدة البيانات.
@app.route("/front-desk/visits/combined")
@login_required
def combined_visits_report():
    ids_param = request.args.get("visit_ids", "")
    visit_ids = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
    if not visit_ids:
        return "لم يتم تحديد أي زيارات لعرضها بجدول موحّد.", 400
    db = get_db()
    placeholders = ",".join("?" * len(visit_ids))
    visits = db.execute(
        f"SELECT v.*, p.full_name, p.age, p.age_unit, p.gender, rc.name as referral_center_name FROM visits v "
        f"JOIN patients p ON p.id = v.patient_id "
        f"LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id "
        f"WHERE v.id IN ({placeholders}) "
        f"ORDER BY v.created_at ASC",
        visit_ids,
    ).fetchall()
    if not visits:
        return "Not found", 404
    # إذا أي زيارة من الزيارات المدموجة بهذا الجدول أصلها نموذج وارد من
    # مختبر آخر، نعرض نفس العبارة الانكليزية أسفل الجدول (بدون ذكر اسم
    # المختبر بأي مكان).
    from_other_lab = any(
        v["referral_center_id"] and v["referral_center_name"] not in (None, "", "Walk-in") for v in visits
    )

    param_order = []
    param_rows = {}
    for v in visits:
        order_tests = db.execute(
            "SELECT ot.id FROM order_tests ot JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
            (v["id"],),
        ).fetchall()
        for ot in order_tests:
            results = db.execute(
                "SELECT r.*, tp.name as param_name, tp.unit FROM results r "
                "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE r.order_test_id=?",
                (ot["id"],),
            ).fetchall()
            for r in results:
                key = r["param_name"]
                if key not in param_rows:
                    param_rows[key] = {"unit": r["unit"], "values": {}}
                    param_order.append(key)
                display_value = r["value_text"] if r["value_text"] else r["value_numeric"]
                param_rows[key]["values"][v["id"]] = {"value": display_value, "flag": r["flag"]}

    return render_template("front_desk/combined_report.html", visits=visits,
                            param_order=param_order, param_rows=param_rows, patient=visits[0],
                            from_other_lab=from_other_lab)


def period_breakdown(db, group_len, base_where, base_params):
    """يجمع الزيارات حسب فترة زمنية (يوم أو شهر) — يرجع صفوف فيها الدخل
    والصرفيات والصافي لكل فترة فرعية، بالإضافة إلى إجمالي الفترة كاملة.
    group_len: طول substr(created_at) المستخدم للتجميع (10=يوم، 7=شهر).
    base_where/base_params: شرط SQL لتحديد الفترة الكبيرة (مثلاً شهر معين أو سنة معينة).

    أي تحليل معلَّم "مجاني" (fee_waived=1) يُستثنى بالكامل من "revenue" هنا
    -- سواء كان معلَّم "يظهر بالسجل" أو "مخفي عنه" (hidden_from_log لا
    علاقة له بالمبلغ إطلاقًا، فقط يتحكم هل اسم التحليل يظهر بعمود
    التحاليل بصفحة daily_report أم لا -- راجع daily_report أدناه).

    expenses هنا يبقى بالمعنى القديم تمامًا (صرفيات + أجور الفاحصين مجموعة
    سوا) — أي قالب موجود يعرضه مباشرة ما ينكسر ولا تتغيّر قيمته. أضفنا
    examining_fees كحقل جديد إضافي بس، يعرض أجور الأطباء الفاحصين لحالها
    (المطلوب: "تُذكر بصفحات الحسابات").
    """
    revenue_rows = db.execute(
        f"SELECT substr(v.created_at,1,{group_len}) as period, "
        f"COALESCE(SUM(COALESCE(ot.price, td.price)),0) as revenue, COUNT(DISTINCT v.id) as visits_count "
        f"FROM visits v JOIN orders o ON o.visit_id=v.id JOIN order_tests ot ON ot.order_id=o.id "
        f"JOIN test_definitions td ON td.id=ot.test_definition_id "
        f"WHERE (ot.fee_waived IS NULL OR ot.fee_waived=0) AND {base_where} GROUP BY period", base_params,
    ).fetchall()
    expense_rows = db.execute(
        f"SELECT substr(v.created_at,1,{group_len}) as period, "
        f"COALESCE(SUM(v.expenses),0) as other_expenses, "
        f"COALESCE(SUM(v.examining_doctor_fee),0) as examining_fees "
        f"FROM visits v WHERE {base_where} GROUP BY period", base_params,
    ).fetchall()
    # forwarded_rows (المطلوب 3): كلفة أي تحليل انسحبت عينته بمختبرك لكن
    # أُرسلت فعليًا لمختبر آخر لإجرائها (راجع order_tests.forwarded_cost
    # بـdatabase.py) -- تُجمع هنا حسب نفس الفترة وتُضاف لـ"other_expenses"
    # تلقائيًا، بدون أي حاجة لإدخالها يدويًا بحقل visits.expenses.
    forwarded_rows = db.execute(
        f"SELECT substr(v.created_at,1,{group_len}) as period, "
        f"COALESCE(SUM(ot.forwarded_cost),0) as forwarded_cost "
        f"FROM visits v JOIN orders o ON o.visit_id=v.id JOIN order_tests ot ON ot.order_id=o.id "
        f"WHERE {base_where} GROUP BY period", base_params,
    ).fetchall()
    forwarded_by_period = {r["period"]: (r["forwarded_cost"] or 0) for r in forwarded_rows}
    data = {}
    for r in revenue_rows:
        data[r["period"]] = {"period": r["period"], "revenue": r["revenue"],
                              "visits_count": r["visits_count"], "expenses": 0.0, "examining_fees": 0.0}
    for r in expense_rows:
        data.setdefault(r["period"], {"period": r["period"], "revenue": 0.0,
                                       "visits_count": 0, "expenses": 0.0, "examining_fees": 0.0})
        # "expenses" يبقى بالضبط بنفس معناه القديم (المجموع الكلي) حتى ما
        # ينكسر أي قالب موجود يعرضه مباشرة — examining_fees إضافة جديدة
        # جنبه بس، مو بديلة عنه. forwarded تُضاف هنا أيضًا لنفس "expenses"
        # الإجمالي (نفس منطق examining_fees تمامًا).
        forwarded_here = forwarded_by_period.get(r["period"], 0)
        data[r["period"]]["expenses"] = r["other_expenses"] + r["examining_fees"] + forwarded_here
        data[r["period"]]["examining_fees"] = r["examining_fees"]
    rows = sorted(data.values(), key=lambda x: x["period"])
    for r in rows:
        r["net"] = r["revenue"] - r["expenses"]
    totals = {
        "revenue": sum(r["revenue"] for r in rows),
        "expenses": sum(r["expenses"] for r in rows),
        "examining_fees": sum(r["examining_fees"] for r in rows),
        "visits_count": sum(r["visits_count"] for r in rows),
    }
    totals["net"] = totals["revenue"] - totals["expenses"]
    return rows, totals


@app.route("/reports/daily")
@login_required
def daily_report():
    db = get_db()
    report_date = request.args.get("date", date.today().isoformat())
    visits = db.execute(
        "SELECT v.id, v.registration_number, v.examining_doctor, v.expenses, v.examining_doctor_fee, "
        "v.notes, p.full_name, p.gender, p.age FROM visits v "
        "JOIN patients p ON p.id = v.patient_id "
        "WHERE substr(v.created_at,1,10)=? ORDER BY v.registration_number",
        (report_date,),
    ).fetchall()

    rows = []
    grand_total = 0
    grand_expenses = 0
    grand_examining_fees = 0
    grand_remaining = 0
    for v in visits:
        # نجيب كل التحاليل بدون أي فلترة أول (نحتاج fee_waived و
        # hidden_from_log لحالهم لنفصل بين "المبلغ" و"العرض بالعمود"):
        # - fee_waived=1: يُستثنى سعره من "total" (الدخل) بكل الأحوال،
        #   سواء ظاهر أو مخفي بالسجل.
        # - hidden_from_log=1: يُستثنى اسمه من عمود "التحاليل" (ما يظهر
        #   إطلاقًا بهذا التقرير)، مع بقاء نتيجته محفوظة بقاعدة البيانات.
        items = db.execute(
            "SELECT td.name, td.code as test_code, td.is_examining_test, "
            "COALESCE(ot.price, td.price) as price, ot.doctor_id, "
            "ot.fee_waived, ot.hidden_from_log, ot.forwarded_cost FROM order_tests ot "
            "JOIN test_definitions td ON td.id = ot.test_definition_id "
            "JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
            (v["id"],),
        ).fetchall()
        visible_items = [i for i in items if not i["hidden_from_log"]]
        test_names = ", ".join(
            i["name"] + (" (مجاني)" if i["fee_waived"] else "") for i in visible_items
        )
        total = sum((i["price"] or 0) for i in items if not i["fee_waived"])
        grand_total += total
        # forwarded_cost لكل تحليل بهذي الزيارة أُرسل فعليًا لمختبر آخر
        # (المطلوب 3) -- يُضاف لصرفيات هذي الزيارة بالتقرير اليومي، بنفس
        # طريقة period_breakdown() أعلاه المستخدمة بالتقارير الشهرية/نصف
        # السنوية/السنوية (كانت ناقصة هون فقط بالتقرير اليومي).
        forwarded_total = sum((i["forwarded_cost"] or 0) for i in items)
        row_expenses = (v["expenses"] or 0) + forwarded_total
        row_examining_fee = v["examining_doctor_fee"] or 0
        grand_expenses += row_expenses
        grand_examining_fees += row_examining_fee
        doctor_names = set()
        for i in visible_items:
            if i["doctor_id"]:
                d = db.execute("SELECT full_name FROM doctors WHERE id=?", (i["doctor_id"],)).fetchone()
                if d:
                    doctor_names.add(d["full_name"])
        # دكتور المختبر الفاحص + نوع التحليل بين قوسين بنفس الحقل (المطلوب 2)
        # -- نفس المعيار الكانوني المستخدم أصلاً بـshow_exam_signature أعلاه
        # (test_code ضمن EXAM_SIGNATURE_TEST_CODES أو is_examining_test=1)
        # حتى تبقى "أي تحليل يحتاج توقيع دكتور فاحص" معرَّفة بمكان واحد
        # بمنطق واحد بكل التطبيق، بدل معيارين مختلفين لنفس الفكرة.
        exam_names = [
            i["name"] for i in visible_items
            if i["test_code"] in EXAM_SIGNATURE_TEST_CODES or bool(i["is_examining_test"])
        ]
        examining_doctor_display = v["examining_doctor"] or "-"
        if v["examining_doctor"] and exam_names:
            examining_doctor_display = f"{v['examining_doctor']} ({', '.join(exam_names)})"

        # عمود "الباقي": المبلغ المتبقي فعليًا بعد خصم أي دفعة/خصم مسجّلة
        # على فاتورة هذي الزيارة -- بنفس معادلة "المتبقي" بالفاتورة المفردة
        # (total_amount - discount_amount - paid_amount). لو ما فيه فاتورة
        # مسجَّلة أصلاً لهذي الزيارة (حالة نادرة)، الباقي = سعر التحاليل
        # الكلي (total) بما إنه ما انسجّل أي دفع/خصم بعد.
        invoice = db.execute(
            "SELECT total_amount, discount_amount, paid_amount FROM invoices WHERE visit_id=?",
            (v["id"],),
        ).fetchone()
        if invoice:
            remaining = (invoice["total_amount"] or 0) - (invoice["discount_amount"] or 0) - (invoice["paid_amount"] or 0)
        else:
            remaining = total
        grand_remaining += remaining

        rows.append({
            "reg": v["registration_number"], "name": v["full_name"],
            "gender": v["gender"] or "-", "age": v["age"] if v["age"] is not None else "-",
            "tests": test_names, "total": total, "doctors": ", ".join(doctor_names),
            "examining_doctor": examining_doctor_display,
            "expenses": row_expenses + row_examining_fee,  # توافق قديم: أي قالب لسا يستخدم "expenses" وحده يشتغل متل قبل تمامًا
            "expenses_only": row_expenses,
            "examining_fee": row_examining_fee,
            "remaining": remaining,
            "notes": v["notes"] or "",
        })

    grand_total_expenses = grand_expenses + grand_examining_fees
    return render_template("front_desk/daily_report.html", rows=rows, report_date=report_date,
                            grand_total=grand_total, grand_expenses=grand_total_expenses,
                            grand_expenses_only=grand_expenses, grand_examining_fees=grand_examining_fees,
                            grand_net=grand_total - grand_total_expenses, grand_remaining=grand_remaining)


@app.route("/reports/monthly")
@roles_required("admin", "accountant", "supervisor")
def monthly_report():
    db = get_db()
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    rows, totals = period_breakdown(db, 10, "substr(v.created_at,1,7)=?", (month,))
    return render_template("front_desk/monthly_report.html", rows=rows, totals=totals, month=month)


@app.route("/reports/half-year")
@roles_required("admin", "accountant", "supervisor")
def half_year_report():
    db = get_db()
    year = request.args.get("year", str(date.today().year))
    half = request.args.get("half", "1" if date.today().month <= 6 else "2")
    start_month, end_month = (1, 6) if half == "1" else (7, 12)
    rows, totals = period_breakdown(
        db, 7,
        "substr(v.created_at,1,4)=? AND CAST(substr(v.created_at,6,2) AS INTEGER) BETWEEN ? AND ?",
        (year, start_month, end_month),
    )
    return render_template("front_desk/half_year_report.html", rows=rows, totals=totals, year=year, half=half)


@app.route("/reports/annual")
@roles_required("admin", "accountant", "supervisor")
def annual_report():
    db = get_db()
    year = request.args.get("year", str(date.today().year))
    rows, totals = period_breakdown(db, 7, "substr(v.created_at,1,4)=?", (year,))
    return render_template("front_desk/annual_report.html", rows=rows, totals=totals, year=year)



@app.route("/workbench/samples-collection")
@login_required
def samples_collection():
    db = get_db()
    order_tests = db.execute(
        "SELECT ot.id, ot.barcode, ot.status, td.name as test_name, td.sample_type, "
        "p.full_name as patient_name, v.registration_number "
        "FROM order_tests ot JOIN test_definitions td ON td.id=ot.test_definition_id "
        "JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id "
        "JOIN patients p ON p.id=v.patient_id WHERE ot.status='Accepted' ORDER BY ot.id DESC"
    ).fetchall()
    return render_template("workbench/samples_collection.html", order_tests=order_tests)


@app.route("/workbench/samples-collection/<int:order_test_id>/collect", methods=["POST"])
@login_required
def collect_sample(order_test_id):
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("UPDATE order_tests SET status='Collected', collected_at=? WHERE id=?", (now, order_test_id))
    db.commit()
    log_action("Collect", "order_test", order_test_id)
    flash("Sample marked as collected.")
    return redirect(url_for("samples_collection"))


@app.route("/workbench/order-tests/<int:order_test_id>/forward", methods=["GET", "POST"])
@login_required
def order_test_forward(order_test_id):
    """صفحة "إرسال هذا التحليل لمختبر آخر" (المطلوب 3): تحليل مثل
    البرولاكتين اللي عيّنته تُرسل فعليًا لمختبر القمة لإجرائه هناك --
    تُسجَّل هنا اسم المختبر المُرسَل إليه وكلفته، فتُحسب تلقائيًا ضمن
    صرفيات الزيارة بكل التقارير (اليومي/الشهري/نصف السنوي/السنوي) بدون
    أي إدخال يدوي إضافي بحقل الصرفيات العام. التقرير المطبوع للمريض نفسه
    لا يتأثر إطلاقًا -- يبقى يُطبع بقالب مختبرك (نفس الشعار والدكاترة)
    بغض النظر عن مكان الإرسال الفعلي، لأن forwarded_lab_name/forwarded_cost
    عمودين خاصّين بـorder_tests فقط ولا يُستخدَمان بأي قالب تقرير مريض.
    """
    db = get_db()
    ot = db.execute(
        "SELECT ot.*, td.name as test_name, p.full_name as patient_name, v.registration_number "
        "FROM order_tests ot JOIN test_definitions td ON td.id=ot.test_definition_id "
        "JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id "
        "JOIN patients p ON p.id=v.patient_id WHERE ot.id=?",
        (order_test_id,),
    ).fetchone()
    if not ot:
        return "Not found", 404

    if request.method == "POST":
        lab_name = (request.form.get("forwarded_lab_name") or "").strip() or None
        cost_raw = (request.form.get("forwarded_cost") or "").strip()
        try:
            cost = float(cost_raw) if cost_raw else 0
        except ValueError:
            cost = 0
        db.execute(
            "UPDATE order_tests SET forwarded_lab_name=?, forwarded_cost=? WHERE id=?",
            (lab_name, cost, order_test_id),
        )
        db.commit()
        log_action("ForwardTest", "order_tests", order_test_id,
                    f"lab={lab_name} cost={cost}" if lab_name else "cleared")
        flash("تم حفظ بيانات الإرسال." if lab_name else "تم إلغاء الإرسال لمختبر آخر لهذا التحليل.")
        return redirect(url_for("order_test_forward", order_test_id=order_test_id))

    return render_template("workbench/order_test_forward.html", ot=ot)


@app.route("/workbench/samples-accession")
@login_required
def samples_accession():
    db = get_db()
    order_tests = db.execute(
        "SELECT ot.id, ot.barcode, ot.status, td.name as test_name, td.sample_type, td.department, "
        "p.full_name as patient_name, v.registration_number "
        "FROM order_tests ot JOIN test_definitions td ON td.id=ot.test_definition_id "
        "JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id "
        "JOIN patients p ON p.id=v.patient_id WHERE ot.status='Collected' ORDER BY ot.id DESC"
    ).fetchall()
    return render_template("workbench/samples_accession.html", order_tests=order_tests)


@app.route("/workbench/samples-accession/<int:order_test_id>/accept", methods=["POST"])
@login_required
def accept_sample(order_test_id):
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("UPDATE order_tests SET status='Accessioned', accessioned_at=? WHERE id=?", (now, order_test_id))
    db.commit()
    log_action("Accession", "order_test", order_test_id)
    flash("Sample accepted for testing.")
    return redirect(url_for("samples_accession"))



@app.route("/workbench/orders")
@login_required
def orders_list():
    db = get_db()
    status = request.args.get("status", "")
    # فلتر التاريخ: يبقى ثابت بين الزيارات المتكررة للصفحة (محفوظ بالجلسة)
    # لحد ما المستخدم نفسه يغيّره صراحة — ما يرجع لـ"اليوم" تلقائيًا، لأن
    # بعض التحاليل تتأخر عدة أيام وتحتاج تبقى ظاهرة بالقائمة. فاضي (زر
    # "الكل") = بدون أي فلتر تاريخ إطلاقًا.
    if "date" in request.args:
        order_date = request.args.get("date", "").strip()
        session["orders_date_filter"] = order_date
    else:
        order_date = session.get("orders_date_filter", "")
    query = (
        "SELECT ot.id, ot.barcode, ot.status, ot.created_at, ot.fee_waived, ot.hidden_from_log, "
        "td.name as test_name, td.code as test_code, td.department, td.sample_type, td.is_examining_test, "
        "p.full_name as patient_name, v.registration_number "
        "FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
    )
    conditions = []
    params = []
    if status:
        conditions.append("ot.status = ?")
        params.append(status)
    if order_date:
        conditions.append("substr(ot.created_at,1,10) = ?")
        params.append(order_date)
    if conditions:
        query += "WHERE " + " AND ".join(conditions) + " "
    query += "ORDER BY ot.id DESC LIMIT 150"
    order_tests = db.execute(query, params).fetchall()
    fee_waiver_configured = bool(get_setting(db, "fee_waiver_password_hash", ""))
    return render_template("workbench/orders.html", order_tests=order_tests, status=status, order_date=order_date,
                            fee_waiver_configured=fee_waiver_configured)


@app.route("/workbench/orders/<int:order_test_id>/delete", methods=["POST"])
@roles_required("supervisor")
def delete_order_test(order_test_id):
    """يمسح تحليل مطلوب لحاله (سطر وحد من قائمة Orders) — لا يمسح الزيارة
    ولا التحاليل الثانية المرتبطة فيها، فقط هذا التحليل بالذات (مثلاً طلب
    خطأ بالغلط). يمسح أي نتائج مدخلة له مسبقًا أيضًا حتى لا تبقى نتائج
    يتيمة بقاعدة البيانات."""
    db = get_db()
    ot = db.execute("SELECT id FROM order_tests WHERE id=?", (order_test_id,)).fetchone()
    if not ot:
        flash("هذا الطلب غير موجود أصلاً.")
        return redirect(url_for("orders_list"))
    db.execute("DELETE FROM results WHERE order_test_id=?", (order_test_id,))
    db.execute("DELETE FROM order_tests WHERE id=?", (order_test_id,))
    db.commit()
    log_action("DeleteOrderTest", "order_tests", order_test_id, "")
    flash("تم حذف هذا الطلب.")
    return redirect(url_for("orders_list"))


@app.route("/workbench/orders/<int:order_test_id>/toggle-fee-waiver", methods=["POST"])
@login_required
def toggle_order_test_fee_waiver(order_test_id):
    """تبديل علامة "تحليل مجاني" (بدون أجر لدكتور المختبر الفاحص، وبدون
    احتساب سعر التحليل نفسه ضمن أي حساب يومي/شهري/نصف سنوي/سنوي) لتحليل
    واحد بالذات -- محمي بكلمة مرور خاصة تُضبط من صفحة الإعدادات
    (fee_waiver_password_hash)، حتى لا يقدر أي شخص بالمختبر يلعب فيها.
    عند التفعيل يُسأل أيضًا (hide_from_log) هل يظهر اسم هذا التحليل بعمود
    "التحاليل" بالسجل اليومي أم يختفي منه كليًا -- بالحالتين تبقى نتيجته
    محفوظة بقاعدة البيانات وتُطبع عاديًا بتقرير المريض. الاسم المُدخَل
    (person_name) يُسجَّل بسجل التدقيق فقط للمراجعة -- لا يوجد تحقق من
    قائمة أسماء مغلقة."""
    db = get_db()
    ot = db.execute(
        "SELECT ot.id, ot.fee_waived, o.visit_id FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id WHERE ot.id=?",
        (order_test_id,),
    ).fetchone()
    if not ot:
        return {"ok": False, "error": "هذا الطلب غير موجود"}, 404

    stored_hash = get_setting(db, "fee_waiver_password_hash", "")
    if not stored_hash:
        return {"ok": False, "error": "لم تُضبط كلمة مرور هذه الميزة بعد -- اضبطها من صفحة الإعدادات أولاً."}, 400

    entered_password = request.form.get("password", "")
    if hash_password(entered_password) != stored_hash:
        return {"ok": False, "error": "كلمة المرور غير صحيحة."}, 403

    entered_name = (request.form.get("person_name") or "").strip()
    new_val = 0 if ot["fee_waived"] else 1
    hide_from_log = 1 if (new_val == 1 and request.form.get("hide_from_log") == "1") else 0
    db.execute(
        "UPDATE order_tests SET fee_waived=?, hidden_from_log=? WHERE id=?",
        (new_val, hide_from_log, order_test_id),
    )
    recompute_examining_doctor_fee(db, ot["visit_id"])
    db.commit()
    log_action("ToggleFeeWaiver", "order_tests", order_test_id,
               f"waived={new_val} hidden_from_log={hide_from_log} by={entered_name}")
    return {"ok": True, "fee_waived": new_val, "hidden_from_log": hide_from_log}


def save_order_test_results(db, ot, parameters, form, user_id, field_prefix="", patient_id=None):
    """يحفظ نتائج تحليل واحد (order_test) من بيانات نموذج مُرسل، بنفس منطق
    الأعلام (Flag) والمرجعيات وتسجيل التأريخ المستخدم بشاشة إدخال النتائج —
    مشتركة بين شاشة الإدخال المفردة وشاشة الإدخال المُجمّع لكل تحاليل الزيارة
    معًا، حتى لا يتكرر نفس المنطق الحساس بمكانين. تعيد True إذا أُدخلت/عُدّلت
    أي قيمة فعليًا لهذا التحليل.

    patient_id: يُمرَّر لـfind_reference_range حتى تُستخدم النسبة الطبيعية
    الخاصة بهذا المريض تحديداً لو موجودة (المطلوب 5) — اختياري، None يعني
    نفس السلوك القديم (نسبة عامة/حسب الجهاز فقط).

    الجهاز (analyzer): يُقرأ من حقل form["{field_prefix}analyzer"] لو
    موجود ويُحفظ على order_tests.analyzer قبل حساب أي flag، حتى يُستخدم
    فورًا بنفس هذا الحفظ (المطلوب 6). حقل غير موجود بالفورم إطلاقاً (شاشة
    قديمة ما عندها هذا الحقل) لا يغيّر شي؛ حقل موجود وفاضي يمسح القيمة
    المحفوظة سابقاً.
    """
    analyzer_field = f"{field_prefix}analyzer"
    if analyzer_field in form:
        analyzer_value = form.get(analyzer_field, "").strip() or None
        db.execute("UPDATE order_tests SET analyzer=? WHERE id=?", (analyzer_value, ot["id"]))
    else:
        analyzer_value = ot["analyzer"] if "analyzer" in ot.keys() else None

    now = datetime.now().isoformat(timespec="seconds")
    touched = False
    for param in parameters:
        field = f"{field_prefix}param_{param['id']}"
        value = form.get(field, "").strip()
        if value == "":
            continue
        touched = True
        rng = find_reference_range(db, param["id"], ot["gender"], ot["age"], ot["age_unit"],
                                    patient_id=patient_id, analyzer=analyzer_value)
        flag = "Normal"
        value_numeric = None
        value_text = None
        if param["result_type"] == "Numeric":
            try:
                value_numeric = float(value)
                if rng and rng["low"] is not None and value_numeric < rng["low"]:
                    flag = "Low"
                elif rng and rng["high"] is not None and value_numeric > rng["high"]:
                    flag = "High"
                    if rng["high"] and value_numeric > rng["high"] * 2:
                        flag = "Critical"
            except ValueError:
                value_text = value
        else:
            value_text = value

        existing = db.execute(
            "SELECT id, value_numeric, value_text, flag FROM results WHERE order_test_id=? AND test_parameter_id=?",
            (ot["id"], param["id"]),
        ).fetchone()
        if existing:
            if existing["value_numeric"] != value_numeric or existing["value_text"] != value_text:
                db.execute(
                    "INSERT INTO result_history (result_id, order_test_id, test_parameter_id, "
                    "prev_value_numeric, prev_value_text, prev_flag, changed_by, changed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (existing["id"], ot["id"], param["id"], existing["value_numeric"],
                     existing["value_text"], existing["flag"], user_id, now),
                )
            db.execute(
                "UPDATE results SET value_numeric=?, value_text=?, flag=?, entered_by=?, entered_at=? WHERE id=?",
                (value_numeric, value_text, flag, user_id, now, existing["id"]),
            )
        else:
            db.execute(
                "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, "
                "flag, entered_by, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ot["id"], param["id"], value_numeric, value_text, flag, user_id, now),
            )

    # RETIC ("Retic Count" المفرد فقط): يحتسب Corrected Retic count تلقائيًا
    # من Reticulocyte count وHCT (راجع ensure_retic_parameters بـdatabase.py
    # وتعليق _apply_retic_correction أدناه للتفاصيل الكاملة).
    if "test_code" in ot.keys() and ot["test_code"] == "RETIC":
        _apply_retic_correction(db, ot, parameters, form, field_prefix, user_id, now, patient_id)

    return touched


def _apply_retic_correction(db, ot, parameters, form, field_prefix, user_id, now, patient_id):
    """يحسب Corrected Retic count تلقائيًا لتحليل Retic Count (RETIC):

        Corrected Retic % = Reticulocyte count % × (HCT الفعلي ÷ HCT الطبيعي
                                                      حسب عمر/جنس المريض)

    "HCT الطبيعي" يُسحب من نفس جداول Reference Ranges العمرية الجاهزة
    (find_reference_range على باراميتر HCT نفسه بهذا التحليل) — منتصف
    المدى (low+high)/2، أو أي طرف موجود لو الثاني فاضي.

    لا يُطبَّق شي إذا:
      - Reticulocyte count أو HCT غير مُدخلين (لا بهذا الإرسال ولا سابقًا).
      - المستخدم كتب هو نفسه قيمة بحقل "Corrected Retic count" بهذا
        الإرسال -- قيمته اليدوية تبقى كما هي (already handled by the
        main loop above)، ما تُستبدَل بالمحسوبة.

    لو الناتج المحسوب أقل من Reticulocyte count الأصلي، تُخزَّن ملاحظة
    قصيرة بعمود results.note لصف Corrected Retic count -- تظهر بالتقرير
    كنص عادي قابل للحذف من معاينة الطباعة (editable-label) بدون أي زر
    جديد. لو الشرط ما انطبق (تصحيح لاحق رفع الناتج)، تُمحى الملاحظة
    القديمة تلقائيًا حتى لا تبقى ملاحظة قديمة غير صحيحة.
    """
    by_name = {p["name"]: p for p in parameters}
    retic_param = by_name.get("Reticulocyte count")
    hct_param = by_name.get("HCT")
    corrected_param = by_name.get("Corrected Retic count")
    if not (retic_param and hct_param and corrected_param):
        return  # قاعدة بيانات قديمة ما انزرعت لها هذي الحقول بعد

    corrected_field = f"{field_prefix}param_{corrected_param['id']}"
    if (form.get(corrected_field, "") or "").strip() != "":
        return  # المستخدم كتب قيمة يدوية بنفسه -- لا نستبدلها بالمحسوبة

    def _current_numeric(param):
        field = f"{field_prefix}param_{param['id']}"
        submitted = (form.get(field, "") or "").strip()
        if submitted != "":
            try:
                return float(submitted)
            except ValueError:
                return None
        existing = db.execute(
            "SELECT value_numeric FROM results WHERE order_test_id=? AND test_parameter_id=?",
            (ot["id"], param["id"]),
        ).fetchone()
        return existing["value_numeric"] if existing else None

    retic_value = _current_numeric(retic_param)
    hct_value = _current_numeric(hct_param)
    if retic_value is None or hct_value is None:
        return

    normal_range = find_reference_range(db, hct_param["id"], ot["gender"], ot["age"], ot["age_unit"],
                                         patient_id=patient_id)
    normal_hct = None
    if normal_range:
        low, high = normal_range["low"], normal_range["high"]
        if low is not None and high is not None:
            normal_hct = (low + high) / 2
        elif low is not None:
            normal_hct = low
        elif high is not None:
            normal_hct = high
    if not normal_hct:
        return  # ماكو مدى طبيعي لـHCT محدد بعمر هذا المريض -- ما نقدر نحسب

    corrected_value = round(retic_value * (hct_value / normal_hct), 1)
    note = ("ملاحظة: النتيجة المصححة (Corrected Retic count) أقل من العدّ الأصلي "
            "(Reticulocyte count) — راجع القيم المُدخلة.") if corrected_value < retic_value else None

    existing = db.execute(
        "SELECT id, value_numeric, value_text, flag FROM results WHERE order_test_id=? AND test_parameter_id=?",
        (ot["id"], corrected_param["id"]),
    ).fetchone()
    if existing:
        if existing["value_numeric"] != corrected_value:
            db.execute(
                "INSERT INTO result_history (result_id, order_test_id, test_parameter_id, "
                "prev_value_numeric, prev_value_text, prev_flag, changed_by, changed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (existing["id"], ot["id"], corrected_param["id"], existing["value_numeric"],
                 existing["value_text"], existing["flag"], user_id, now),
            )
        db.execute(
            "UPDATE results SET value_numeric=?, value_text=NULL, flag='Normal', note=?, "
            "entered_by=?, entered_at=? WHERE id=?",
            (corrected_value, note, user_id, now, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, "
            "flag, note, entered_by, entered_at) VALUES (?, ?, ?, NULL, 'Normal', ?, ?, ?)",
            (ot["id"], corrected_param["id"], corrected_value, note, user_id, now),
        )


@app.route("/workbench/result/<int:order_test_id>", methods=["GET", "POST"])
@login_required
def result_entry(order_test_id):
    db = get_db()
    ot = db.execute(
        "SELECT ot.*, td.name as test_name, td.code as test_code, "
        "p.id as patient_id, p.full_name as patient_name, p.gender, p.age, p.age_unit, "
        "v.id as visit_id, v.registration_number "
        "FROM order_tests ot JOIN test_definitions td ON td.id=ot.test_definition_id "
        "JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id "
        "JOIN patients p ON p.id=v.patient_id WHERE ot.id=?",
        (order_test_id,),
    ).fetchone()
    if not ot:
        return "Not found", 404

    parameters = db.execute(
        "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (ot["test_definition_id"],)
    ).fetchall()

    if request.method == "POST":
        if ot["status"] in ("Completed", "Verified"):
            ok, err = _check_completed_result_gate(db, request.form)
            if not ok:
                flash(err)
                return redirect(url_for("result_entry", order_test_id=order_test_id))
        gate_person = (request.form.get("gate_person_name") or "").strip()
        save_order_test_results(db, ot, parameters, request.form, session["user_id"], patient_id=ot["patient_id"])
        # التحليل المعتمد (Verified) يبقى معتمَد بعد التعديل — الحقول صارت
        # قابلة للتعديل دائمًا حتى بعد الاعتماد (بطلب المستخدم)، وكل تعديل
        # يبقى مسجّل بجدول result_history (القيمة القديمة + مين عدّلها ووقتها)
        # حتى لو ما تغيّرت حالة الاعتماد ظاهريًا.
        if ot["status"] != "Verified":
            db.execute("UPDATE order_tests SET status='Completed' WHERE id=?", (order_test_id,))
        db.commit()
        _maybe_auto_whatsapp_send(db, ot["visit_id"])
        _maybe_archive_visit_pdf(db, ot["visit_id"])
        log_action("EnterResult", "order_test", order_test_id, f"gate_person={gate_person}" if gate_person else None)
        flash("Results saved.")
        return redirect(url_for("orders_list"))

    results = db.execute(
        "SELECT r.*, tp.name as param_name FROM results r "
        "JOIN test_parameters tp ON tp.id=r.test_parameter_id WHERE order_test_id=?",
        (order_test_id,),
    ).fetchall()
    results_by_param = {r["test_parameter_id"]: r for r in results}

    ranges = {}
    suggestions_map = {}
    history_map = {}
    for p in parameters:
        r = find_reference_range(db, p["id"], ot["gender"], ot["age"], ot["age_unit"],
                                  patient_id=ot["patient_id"], analyzer=ot["analyzer"] if "analyzer" in ot.keys() else None)
        ranges[p["id"]] = r
        sugg = db.execute("SELECT content FROM suggestions WHERE test_parameter_id=?", (p["id"],)).fetchall()
        suggestions_map[p["id"]] = [s["content"] for s in sugg]
        last_hist = db.execute(
            "SELECT * FROM result_history WHERE order_test_id=? AND test_parameter_id=? "
            "ORDER BY id DESC LIMIT 1", (order_test_id, p["id"]),
        ).fetchone()
        history_map[p["id"]] = last_hist

    return render_template("workbench/result_entry.html", ot=ot, parameters=parameters,
                            results_by_param=results_by_param, ranges=ranges,
                            suggestions_map=suggestions_map, history_map=history_map,
                            patient_hct=get_visit_hct(db, ot["visit_id"]))


# شاشة إدخال النتائج المُجمّعة لكل تحاليل الزيارة معًا: تُظهر كل تحليل طُلب
# لهذا المريض كمستطيل (بطاقة) منفصل بنفس صفوفه/حقوله المعتادة، وزر "حفظ"
# واحد يحفظ كل ما تمت تعبئته دفعة واحدة. فور الحفظ تصبح النتائج متاحة مباشرة
# بريبورت كل تحليل (زر طباعة أمام كل بطاقة)، مع بقاء إمكانية التعديل والحفظ
# مجددًا بنفس الصفحة قبل الطباعة الفعلية.
def get_ordered_parameters(db, ot):
    """يرجّع بارامترات order_test هذا — كلها إذا طُلب التحليل كامل
    (السلوك الافتراضي)، أو بس البارامترات المحدَّدة فعليًا لو استُخدم سهم
    "اختيار بارامترات معيّنة" بشاشة زيارة جديدة (راجع
    order_tests.selected_param_ids بـdatabase.py). تُستخدم بشاشة إدخال
    النتائج (عرض + حفظ) حتى ما تظهر/تُطلب قيم لبارامترات المريض ماطلبها
    أصلاً."""
    all_params = db.execute(
        "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id",
        (ot["test_definition_id"],),
    ).fetchall()
    selected_raw = ot["selected_param_ids"] if "selected_param_ids" in ot.keys() else None
    if not selected_raw:
        return all_params
    try:
        selected_ids = {int(x) for x in selected_raw.split(",") if x.strip()}
    except ValueError:
        return all_params
    filtered = [p for p in all_params if p["id"] in selected_ids]
    return filtered or all_params


@app.route("/front-desk/visits/<int:visit_id>/results", methods=["GET", "POST"])
@login_required
def visit_results_entry(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name as patient_name, p.gender, p.age, p.age_unit, p.phone "
        "FROM visits v JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404

    order_tests = db.execute(
        "SELECT ot.*, td.name as test_name, td.code as test_code, td.department as test_department, "
        "p.id as patient_id, p.gender as gender, p.age as age, p.age_unit as age_unit "
        "FROM order_tests ot JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id JOIN visits v2 ON v2.id = o.visit_id "
        "JOIN patients p ON p.id = v2.patient_id "
        "WHERE o.visit_id=? ORDER BY ot.id",
        (visit_id,),
    ).fetchall()
    if not order_tests:
        flash("لا توجد تحاليل مطلوبة بهذي الزيارة.")
        return redirect(url_for("results_list"))

    # ترتيب ثابت لعرض/طباعة/إدخال التحاليل — بغض النظر عن ترتيب طلبها الفعلي
    # بهذي الزيارة (ot.id الافتراضي). الأدمن يحدد الترتيب المطلوب من
    # Management → الإعدادات → "ترتيب التحاليل بشاشة إدخال النتائج" (اسم
    # التحليل بالضبط كما يظهر بالشاشة، مثلاً "HbA1c (BioChemstry)"، سطر لكل
    # تحليل). أي تحليل غير مذكور هناك يُرتَّب افتراضيًا حسب أولوية القسم
    # (DEPARTMENT_PRIORITY_KEYWORDS: كيمياء ← فايروسات ← هرمونات ← فيتامينات
    # ← تخثر ← أمراض الدم)، وبينهم حسب ترتيبهم الأصلي (ot.id) — فلو المريض
    # ماله بعض الأقسام تلقائيًا تنتخطى وتنطبع/تنعرض بس الأقسام الموجودة فعلاً
    # بنفس التسلسل المطلوب.
    order_pref_raw = get_setting(db, "results_entry_test_order", "")
    order_pref = [ln.strip() for ln in order_pref_raw.splitlines() if ln.strip()]
    if order_pref:
        rank = {name: i for i, name in enumerate(order_pref)}
        order_tests = sorted(
            order_tests,
            key=lambda row: (
                rank.get(row["test_name"], len(order_pref)),
                department_priority_rank(row["test_department"]),
                row["id"],
            ),
        )
    else:
        order_tests = sorted(
            order_tests,
            key=lambda row: (department_priority_rank(row["test_department"]), row["id"]),
        )

    if request.method == "POST":
        # نفس حماية النتيجة المكتملة (المطلوب 2)، لكن هنا مرة وحدة لكل
        # الطلب بدل كل تحليل لحاله -- إذا أي تحليل بهذي الزيارة مكتمل أصلاً،
        # نطلب كلمة المرور مرة وحدة قبل ما نحفظ أي شي من الدفعة كاملة
        # (all-or-nothing، أبسط وأأمن من فحص جزئي لكل بطاقة على حدة).
        if any(ot["status"] in ("Completed", "Verified") for ot in order_tests):
            ok, err = _check_completed_result_gate(db, request.form)
            if not ok:
                flash(err)
                return redirect(url_for("visit_results_entry", visit_id=visit_id))
        gate_person = (request.form.get("gate_person_name") or "").strip()
        any_saved = False
        for ot in order_tests:
            # التحاليل المعتمدة (Verified) صارت قابلة للتعديل دائمًا هيه
            # بعد، وتبقى معتمَدة بعد الحفظ (ما تحتاج فتح/إلغاء اعتماد أولًا)
            # — كل تعديل يبقى مسجّل بجدول result_history (القيمة القديمة +
            # مين عدّلها ووقتها) بغض النظر عن حالة الاعتماد.
            parameters = get_ordered_parameters(db, ot)
            touched = save_order_test_results(
                db, ot, parameters, request.form, session["user_id"], field_prefix=f"ot{ot['id']}_",
                patient_id=ot["patient_id"],
            )
            if touched:
                any_saved = True
                if ot["status"] != "Verified":
                    db.execute("UPDATE order_tests SET status='Completed' WHERE id=?", (ot["id"],))
        db.commit()
        if any_saved:
            _maybe_auto_whatsapp_send(db, visit_id)
            _maybe_archive_visit_pdf(db, visit_id)
            log_action("EnterResultsBulk", "visit", visit_id, f"gate_person={gate_person}" if gate_person else None)
            flash("تم حفظ النتائج.")
        else:
            flash("لم تُدخل أي قيمة جديدة.")
        return redirect(url_for("visit_results_entry", visit_id=visit_id))

    boxes = []
    for ot in order_tests:
        parameters = get_ordered_parameters(db, ot)
        results = db.execute(
            "SELECT r.*, tp.name as param_name FROM results r "
            "JOIN test_parameters tp ON tp.id=r.test_parameter_id WHERE order_test_id=?",
            (ot["id"],),
        ).fetchall()
        results_by_param = {r["test_parameter_id"]: r for r in results}
        ranges = {}
        suggestions_map = {}
        history_map = {}
        for p in parameters:
            ranges[p["id"]] = find_reference_range(
                db, p["id"], visit["gender"], visit["age"], visit["age_unit"],
                patient_id=visit["patient_id"],
                analyzer=ot["analyzer"] if "analyzer" in ot.keys() else None,
            )
            sugg = db.execute("SELECT content FROM suggestions WHERE test_parameter_id=?", (p["id"],)).fetchall()
            suggestions_map[p["id"]] = [s["content"] for s in sugg]
            history_map[p["id"]] = db.execute(
                "SELECT * FROM result_history WHERE order_test_id=? AND test_parameter_id=? "
                "ORDER BY id DESC LIMIT 1",
                (ot["id"], p["id"]),
            ).fetchone()
        boxes.append({
            "ot": ot, "parameters": parameters, "results_by_param": results_by_param,
            "ranges": ranges, "suggestions_map": suggestions_map, "history_map": history_map,
        })

    return render_template("front_desk/visit_results_entry.html", visit=visit, boxes=boxes,
                            patient_hct=get_visit_hct(db, visit_id),
                            patient_hct_normal=get_normal_hct(db, visit["gender"], visit["age"], visit["age_unit"]),
                            # هل كل تحاليل هذي الزيارة مكتملة/معتمدة؟ — يُستخدم لإظهار
                            # زر "إرسال عبر واتساب" لكل نتائج الزيارة دفعة وحدة بجانب
                            # زر إدخال النتائج (راجع partials/whatsapp_send_button.html).
                            all_completed=all(ot["status"] in ("Completed", "Verified") for ot in order_tests))


# ------------------------------------------------------------------------
# "اللوحة المجمّعة" — تجمع كل التحاليل "البسيطة" لنفس الزيارة (أي تحليل
# ماله تقرير مخصص كبير بـ REPORT_TEMPLATE_MAP، يعني كل شي غير CBC/Blood
# Film/WBC Differential/Fluid exam/Coagulation) بورقة A4 وحدة، مرتّبة
# حسب القسم (Department) اللي حدده الأدمن لكل تحليل بكتالوج التحاليل —
# مثلاً كل تحاليل قسم "Biochemical Test" تحت عنوان وحد، وتحتها "Virology
# screen"، وتحتها "Hormones"، وتحتها "Vitamins"، وهكذا لأي قسم إضافي،
# بنفس ترويسة الشعار والأطباء المشتركة (reports/base_report.html) بدون
# أي تكرار لها. تحليل بدون أي نتيجة مُدخلة بعد يُستبعد من اللوحة تلقائيًا
# حتى ما تطلع أسطر فاضية.
# ------------------------------------------------------------------------

# عناوين أعمدة اللوحة المجمّعة تختلف حسب اسم القسم — قسم Biochemistry تحديداً
# يستخدم تسميات مختلفة ("Laboratory Test Results" / "Conventional Units")
# عن بقية الأقسام ("Test Name" / "Normal Range") بنفس التقرير، مطابقةً
# لتصميم الورقة الأصلية. المطابقة بالاحتواء (case-insensitive) حتى تشتغل
# حتى لو الأدمن كتب اسم القسم بصيغة مختلفة شوي بكتالوج التحاليل (مثلاً
# "Biochemistry" أو "Biochemistry Tests" أو "biochemistry panel").
def _panel_column_labels(department_name):
    d = (department_name or "").strip().lower()
    if "biochem" in d:
        return {"name_header": "Laboratory Test Results", "range_header": "Conventional Units"}
    return {"name_header": "Test Name", "range_header": "Normal Range"}


@app.route("/front-desk/visits/<int:visit_id>/print/combined-panel")
@login_required
def print_combined_panel(visit_id):
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.full_name as patient_name, p.age, p.age_unit, p.gender, "
        "d.full_name as referring_doctor_name, rc.name as referral_center_name "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN doctors d ON d.id = v.doctor_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return "Not found", 404

    order_tests = db.execute(
        "SELECT ot.*, td.code as test_code, td.name as test_name, td.department as department, "
        "td.report_group as report_group, td.done_by_note as done_by_note "
        "FROM order_tests ot JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "WHERE o.visit_id=? AND ot.status IN ('Completed', 'Verified') "
        "ORDER BY COALESCE(NULLIF(TRIM(td.report_group), ''), td.department), td.name",
        (visit_id,),
    ).fetchall()

    # سطر/أسطر "Done by ..." (المطلوب 7) — كل تحليل داخل هذي اللوحة المجمّعة
    # ممكن يكون له done_by_note مختلف (أجهزة مختلفة لكل تحليل)، فنجمع كل
    # القيم غير الفاضية بدون تكرار، بنفس ترتيب ظهور تحاليلها بالتقرير.
    done_by_notes = []
    for _ot in order_tests:
        note = (_ot["done_by_note"] or "").strip() if "done_by_note" in _ot.keys() else ""
        if note and note not in done_by_notes:
            done_by_notes.append(note)

    # التحاليل القديمة (من زيارات سابقة) اللي وافق الموظف صراحة على دمج
    # نتائجها بهذي الزيارة تحديداً — راجع visit_previous_merges. مبوّبة
    # حسب test_definition_id لتسهيل مطابقتها مع تحاليل نفس النوع بالزيارة
    # الحالية (تُعرض كصف "Previous" جنبها)، أو كصف مستقل لو ما تكرر طلب
    # نفس التحليل بهذي الزيارة (راجع الحلقة بعد الحلقة الرئيسية أدناه).
    merged_previous = get_visit_previous_merges(db, visit_id)
    merged_by_test_def = {}
    for m in merged_previous:
        merged_by_test_def.setdefault(m["test_definition_id"], []).append(m)
    current_test_def_ids = {ot["test_definition_id"] for ot in order_tests if ot["test_code"] not in REPORT_TEMPLATE_MAP}

    groups_by_dept = {}
    dept_order = []
    for ot in order_tests:
        if ot["test_code"] in REPORT_TEMPLATE_MAP:
            continue  # لهذا التحليل تقريره الكبير الخاص، ما يدخل باللوحة المجمّعة
        params = db.execute(
            "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (ot["test_definition_id"],)
        ).fetchall()
        if not params:
            continue
        results = db.execute(
            "SELECT r.*, tp.name as pname FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE order_test_id=?",
            (ot["id"],),
        ).fetchall()
        results_by_name = {r["pname"]: r for r in results}
        multi_param = len(params) > 1
        rows = []
        for p in params:
            r = results_by_name.get(p["name"])
            if r is None:
                continue
            value = r["value_text"] if r["value_text"] not in (None, "") else r["value_numeric"]
            if value in (None, ""):
                continue
            rng = find_reference_range(db, p["id"], visit["gender"], visit["age"], visit["age_unit"],
                                        patient_id=visit["patient_id"],
                                        analyzer=ot["analyzer"] if "analyzer" in ot.keys() else None)
            # المدى الطبيعي بعمود واحد مدمج (بدون Low/High منفصلة) — نفضّل
            # range_text الجاهز لو موجود (يغطي حالات نصية زي "Non-Reactive
            # (< 1.0)")، وإلا نبنيه يدويًا من low/high الرقميين لو موجودين.
            if rng and rng["range_text"]:
                range_display = rng["range_text"]
            elif rng and rng["low"] is not None and rng["high"] is not None:
                range_display = f"{rng['low']} - {rng['high']}"
            elif rng and rng["low"] is not None:
                range_display = f"≥ {rng['low']}"
            elif rng and rng["high"] is not None:
                range_display = f"≤ {rng['high']}"
            else:
                range_display = ""
            # مستويات نص حر متعدد الأسطر (المطلوب 4ب) — نفس منطق custom_rows
            # بالضبط: لو range_text موجود يُفكّ لعدة مستويات (Label: value لكل
            # سطر)، وإلا سطر واحد بلا تسمية من range_display الجاهزة أعلاه.
            if rng and rng["range_text"]:
                range_tiers = parse_range_tiers(rng["range_text"])
            elif range_display:
                range_tiers = [{"label": None, "value": range_display}]
            else:
                range_tiers = []
            # الوحدة الثانية (unit2/unit2_factor) — سطر ثاني أصغر تحت
            # النتيجة والوحدة والمدى الطبيعي (زي S. Creatinine بالصورة:
            # mg/dL فوق وµmol/L تحت) — تُحسب فقط للنتائج الرقمية.
            value2 = unit2 = range2_display = None
            if p["unit2"] and p["unit2_factor"] not in (None, "", 0):
                try:
                    factor = float(p["unit2_factor"])
                    if r["value_numeric"] is not None:
                        value2 = round(float(r["value_numeric"]) * factor, 2)
                    unit2 = p["unit2"]
                    if rng and rng["low"] is not None and rng["high"] is not None:
                        range2_display = f"{round(rng['low'] * factor, 2)} - {round(rng['high'] * factor, 2)}"
                except (TypeError, ValueError):
                    value2 = unit2 = range2_display = None
            display_name = resolve_label(p) if multi_param else ot["test_name"]
            # صف "Previous" — يظهر بس لو الموظف وافق صراحة على دمج نتيجة
            # هذا التحليل بالضبط (نفس test_definition_id) من زيارة سابقة،
            # ولنفس اسم الباراميتر تحديداً (يدعم التحاليل متعددة
            # الباراميترات بدون خلط قيم باراميترات مختلفة مع بعض).
            previous_display = None
            for m in merged_by_test_def.get(ot["test_definition_id"], []):
                prev_val = m["results"].get(p["name"])
                if prev_val not in (None, ""):
                    previous_display = f"{display_name}: {prev_val} ({m['date_display']})"
                    break
            rows.append({
                "name": display_name,
                "result": value,
                "unit": p["unit"] or "",
                "range_display": range_display,
                "range_tiers": range_tiers,
                "flag": r["flag"] if "flag" in r.keys() else None,
                "value_align": resolve_value_align(p) if multi_param else None,
                "value2": value2,
                "unit2": unit2,
                "range2_display": range2_display,
                "previous_display": previous_display,
                # لون مخصص + فاصل صفحة اختياريان — الأولوية دائماً للباراميتر
                # المفرد (test_parameters.panel_color/panel_page_break، يُضبط
                # من "مصمم التقارير" لكل باراميتر لحاله)؛ لو غير مضبوط له
                # تحديداً، يرجع لإعداد التحليل كامل (test_definitions) كسلوك
                # احتياطي قديم — هذا يسمح بتلوين باراميتر وحدة بس (زي NRBC)
                # داخل تحليل متعدد الباراميترات (زي Blood film) بدون ما
                # يلوّن باقي باراميتراته.
                "color": p["panel_color"] or ot["panel_color"] or None,
                "_own_page_break": bool(p["panel_page_break"]),
            })
        if not rows:
            continue
        # فاصل الصفحة: كل صف يحمل فاصله المفرد (لو مضبوط لباراميتره تحديداً)،
        # وفاصل التحليل كامل (لو مفعّل) يُطبَّق فقط على أول صف من صفوفه.
        for row in rows:
            if row.pop("_own_page_break", False):
                row["page_break_before"] = True
        if ot["panel_page_break"]:
            rows[0]["page_break_before"] = True
        # الأولوية دائماً لاسم "الريبورت المجمّع" المخصص (report_group) إذا
        # الأدمن حدده لهذا التحليل من كتالوج التحاليل — وإلا نرجع لاسم
        # القسم (department) القديم كما كان الوضع قبل هذي الميزة.
        dept = (ot["report_group"] or "").strip() or ot["department"] or "Other"
        if dept not in groups_by_dept:
            groups_by_dept[dept] = []
            dept_order.append(dept)
        groups_by_dept[dept].extend(rows)

    # تحاليل قديمة موافَق على دمجها بس ما تكرر طلب نفس نوعها بهذي الزيارة
    # الجديدة إطلاقاً — تُضاف كصفوف "Previous" مستقلة (بدون نتيجة حالية
    # مقابلة) بنفس مجموعة قسمها، بدل ما تُفقَد لأن ما فيه صف حالي تُرفَق
    # جنبه.
    for test_def_id, merges in merged_by_test_def.items():
        if test_def_id in current_test_def_ids:
            continue
        td_row = db.execute(
            "SELECT department, report_group FROM test_definitions WHERE id=?", (test_def_id,)
        ).fetchone()
        if not td_row:
            continue
        old_params = db.execute(
            "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (test_def_id,)
        ).fetchall()
        multi_param_prev = len(old_params) > 1
        dept = (td_row["report_group"] or "").strip() or td_row["department"] or "Other"
        for m in merges:
            prev_rows = []
            for p in old_params:
                val = m["results"].get(p["name"])
                if val in (None, ""):
                    continue
                pname = p["name"] if multi_param_prev else m["test_name"]
                prev_rows.append({
                    "name": pname, "result": None, "unit": "", "range_display": "",
                    "range_tiers": [], "flag": None,
                    "value2": None, "unit2": None, "range2_display": None, "color": None,
                    "previous_display": f"{pname}: {val} ({m['date_display']})",
                })
            if prev_rows:
                if dept not in groups_by_dept:
                    groups_by_dept[dept] = []
                    dept_order.append(dept)
                groups_by_dept[dept].extend(prev_rows)

    # ترتيب طباعة أقسام اللوحة المجمّعة — افتراضيًا أبجدي (كما هو بالاستعلام
    # فوق)؛ لو الأدمن حدد ترتيبًا مخصصًا من الإعدادات (combined_panel_group_order)
    # نقدّم الأقسام المذكورة هناك بنفس ترتيبها، وأي قسم غير مذكور يبقى بعدها
    # بترتيبه الأبجدي الأصلي دون أي تغيير.
    group_order_raw = get_setting(db, "combined_panel_group_order", "")
    preferred_order = [ln.strip() for ln in group_order_raw.splitlines() if ln.strip()]
    if preferred_order:
        remaining = [d for d in dept_order if d not in preferred_order]
        dept_order = [d for d in preferred_order if d in dept_order] + remaining

    panel_groups = [
        {"department": d, "rows": groups_by_dept[d], **_panel_column_labels(d)}
        for d in dept_order
    ]

    logo_path = get_setting(db, "logo_path", "")
    logo_url = url_for("static", filename=logo_path) if logo_path else None
    from_other_lab = bool(visit["referral_center_id"]) and visit["referral_center_name"] not in (None, "", "Walk-in")

    try:
        dt = datetime.fromisoformat(visit["created_at"])
        visit_date = f"{dt.day}/{dt.month}/{dt.year}"
    except (TypeError, ValueError):
        visit_date = visit["created_at"] or ""

    age_display = format_age_display(visit["age"], visit["age_unit"])

    auto_flag_color_enabled, show_result_flag, flag_color_map = get_report_flag_settings(db)
    # تباعد الصفوف باللوحة المجمّعة (المطلوب 8) — الصفحة تجمع أكثر من
    # تحليل قد يكون لكل واحد إعداد row_spacing مختلف، فنستخدم أول قيمة
    # مضبوطة فعليًا (غير فاضية) بترتيب ظهور التحاليل بالصفحة كقيمة موحّدة
    # للصفحة كلها؛ ما فيه أي تحليل مضبوط له شي = يبقى التباعد الافتراضي
    # القديم تمامًا (بدون أي تغيير).
    _panel_row_spacing_raw = None
    for _ot in order_tests:
        _td_rs = db.execute(
            "SELECT row_spacing FROM test_definitions WHERE id=?", (_ot["test_definition_id"],)
        ).fetchone()
        if _td_rs and _td_rs["row_spacing"]:
            _panel_row_spacing_raw = _td_rs["row_spacing"]
            break
    return render_template(
        "reports/combined_panel.html",
        panel_groups=panel_groups, logo_url=logo_url, from_other_lab=from_other_lab,
        visit_date=visit_date, sex=visit["gender"] or "", age=age_display,
        patient_name=visit["patient_name"], patient_id=visit["registration_number"],
        referring_doctor_name=visit["referring_doctor_name"] or "",
        show_exam_signature=False,
        auto_flag_color_enabled=auto_flag_color_enabled, show_result_flag=show_result_flag, AUTO_FLAG_COLORS=flag_color_map,
        row_spacing_px=row_spacing_px(_panel_row_spacing_raw),
        done_by_notes=done_by_notes,
        # مكتبة الأختام/التواقيع + أي ختم مُلصق فعلاً فوق هذا التقرير الموحّد
        # حاليًا (راجع partials/stamp_picker.html لطريقة استخدامها بالقالب).
        stamp_target_type="visit", stamp_target_id=visit_id,
        digital_stamps=get_digital_stamps(db),
        stamp_placements=get_stamp_placements(db, "visit", visit_id),
    )


@app.route("/reports/print/<int:order_test_id>")
@login_required
def print_report(order_test_id):
    try:
        return _print_report_impl(order_test_id)
    except Exception:
        # تشخيص مؤقت: بدل صفحة "Internal Server Error" الفاضية اللي يعرضها
        # فلاسك بوضع الإنتاج (production)، نعرض هنا نص الخطأ الكامل
        # (Traceback) بالضبط مثل وضع debug، ونسجله كمان بملف نصي بجذر
        # البرنامج (error_log.txt) — حتى لو ما انتبه المستخدم يصوّر الشاشة
        # بنفس اللحظة، يكدر يفتح الملف بعدين ويرسله. احذف هذا الـ try/except
        # (رجّع فقط الجسم الأصلي لـ print_report) بعد ما تنحل المشكلة نهائيًا،
        # لأنه مو مناسب يبقى دائمًا مفعّل بنسخة تشتغل عند الزبون (يفضح تفاصيل
        # داخلية تقنية للمستخدم لو صار خطأ مستقبلي غير متوقع).
        import traceback
        tb_text = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(__file__), "error_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(datetime.now().isoformat(timespec="seconds") + f"  order_test_id={order_test_id}\n")
                f.write(tb_text)
        except Exception:
            pass
        return (
            "<h1>خطأ أثناء طباعة التقرير — order_test_id="
            + str(order_test_id)
            + "</h1><p>صوّر هذا النص كامل وأرسله:</p>"
            + "<pre style='direction:ltr; text-align:left; white-space:pre-wrap; "
            + "background:#f5f5f5; border:1px solid #ccc; padding:12px;'>"
            + escape(tb_text)
            + "</pre>"
        ), 500


def _print_report_impl(order_test_id):
    db = get_db()
    ot = db.execute(
        "SELECT ot.*, td.code as test_code, td.name as test_name, td.department as test_department, "
        "td.is_examining_test as is_examining_test, td.enable_stamp_widget as enable_stamp_widget, "
        "td.done_by_note as done_by_note, "
        "p.id as patient_id, p.full_name as patient_name, p.gender, p.age, p.age_unit, "
        "v.id as visit_id, v.created_at as visit_created_at, v.registration_number, "
        "v.doctor_id, v.referral_center_id, "
        "d.full_name as referring_doctor_name, rc.name as referral_center_name "
        "FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN doctors d ON d.id = v.doctor_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id "
        "WHERE ot.id = ?",
        (order_test_id,),
    ).fetchone()
    if not ot:
        return "Not found", 404

    template_name = REPORT_TEMPLATE_MAP.get(ot["test_code"])

    sibling_ot = None
    if ot["test_code"] in BF_RETIC_LINK:
        sibling_code = BF_RETIC_LINK[ot["test_code"]]
        sibling_ot = db.execute(
            "SELECT ot2.*, td2.code as test_code FROM order_tests ot2 "
            "JOIN test_definitions td2 ON td2.id = ot2.test_definition_id "
            "WHERE ot2.order_id = ? AND td2.code = ?",
            (ot["order_id"], sibling_code),
        ).fetchone()
        if sibling_ot:
            template_name = REPORT_TEMPLATE_MAP["BF"]

    custom_template = None
    if not template_name:
        # report_style='generic_exam': تحليل بُني بالكامل من صفحة المعاينة
        # نفسها (سحب أقسام/باراميترات) بدل قالب HTML مكتوب يدويًا — راجع
        # /management/report-designer/<id>/start-generic-exam أدناه.
        td_row = db.execute(
            "SELECT report_style FROM test_definitions WHERE id=?", (ot["test_definition_id"],)
        ).fetchone()
        if td_row and td_row["report_style"] == "generic_exam":
            template_name = "reports/generic_exam.html"
    if not template_name:
        custom_template = get_report_template(db, ot["test_definition_id"])
        if not custom_template:
            if session.get("role") == "admin":
                flash("لا يوجد تصميم طباعة لهذا التحليل بعد. صممه من: الإدارة ← مصمم التقارير.")
                return redirect(url_for("report_designer", test_definition_id=ot["test_definition_id"]))
            flash("No printable report layout is defined for this test yet.")
            return redirect(url_for("orders_list"))
        _ot_dept_row = db.execute(
            "SELECT department, report_style FROM test_definitions WHERE id=?", (ot["test_definition_id"],)
        ).fetchone()
        if _ot_dept_row and uses_order_style_report(_ot_dept_row["department"], _ot_dept_row["report_style"]):
            template_name = "reports/custom_v2.html"
        else:
            template_name = "reports/custom.html"

    # When Blood Film and Retic Count are both ordered for this visit, pull
    # parameters/results from BOTH order_tests so the one combined report
    # has everything — regardless of which of the two fields (Retic count,
    # Corrected Retic count) happen to live under which test definition.
    test_def_ids = [ot["test_definition_id"]]
    order_test_ids = [order_test_id]
    if sibling_ot:
        test_def_ids.append(sibling_ot["test_definition_id"])
        order_test_ids.append(sibling_ot["id"])

    parameters = []
    seen_param_names = set()
    for tdid in test_def_ids:
        for p in db.execute("SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (tdid,)).fetchall():
            if p["name"] not in seen_param_names:
                parameters.append(p)
                seen_param_names.add(p["name"])

    # قاموس اسم -> صف test_parameters (المطلوب 9ب/11) — يستخدمه custom_rows
    # وcbc_groups أدناه لجلب display_label/value_align لكل باراميتر بدون
    # إعادة الاستعلام لكل صف لحاله.
    params_by_name_row = {p["name"]: p for p in parameters}
    _td_row_spacing = db.execute(
        "SELECT row_spacing FROM test_definitions WHERE id=?", (ot["test_definition_id"],)
    ).fetchone()
    row_spacing_px_value = row_spacing_px(_td_row_spacing["row_spacing"] if _td_row_spacing else None)

    results = []
    for otid in order_test_ids:
        results.extend(db.execute(
            "SELECT r.*, tp.name as param_name FROM results r "
            "JOIN test_parameters tp ON tp.id = r.test_parameter_id WHERE order_test_id=?",
            (otid,),
        ).fetchall())
    results_by_name = {r["param_name"]: r for r in results}

    # وحدة كل باراميتر (اسم → وحدة) — يحتاجه بعض القوالب المخصّصة الجاهزة
    # (مثل blood_film.html) مباشرة كمتغيّر Jinja اسمه units.get('...')،
    # عكس params/ranges اللي تُبنى وتُستخدم فقط داخل مسارات CBC/custom
    # أدناه. يُبنى هنا مرة وحدة ويُمرَّر دائمًا لكل template_name بلا استثناء،
    # حتى لا يتكرر نفس الخطأ (UndefinedError: 'units' is undefined) لأي
    # قالب جاهز آخر يتوقع نفس المتغيّر مستقبلاً.
    units = {p["name"]: (p["unit"] or "") for p in parameters}

    params = {}
    ranges = {}
    # notes: ملاحظة نصية اختيارية محفوظة على صف النتيجة نفسها (عمود
    # results.note) -- تُستخدم حاليًا فقط لملاحظة "النتيجة المصححة أقل من
    # العدّ الأصلي" بتحليل Retic Count (راجع _apply_retic_correction)، لكنها
    # عامة لأي باراميتر مستقبلاً. القالب يعرضها كنص عادي بـeditable-label
    # حتى يقدر المستخدم يحذفها من معاينة الطباعة بنفس طريقة تعديل أي نص آخر
    # بالتقرير، بدون أي زر/ميزة جديدة.
    notes = {}
    for p in parameters:
        r = results_by_name.get(p["name"])
        if r is not None:
            value = r["value_text"] if r["value_text"] not in (None, "") else r["value_numeric"]
        else:
            value = None
        params[p["name"]] = "" if value is None else value
        notes[p["name"]] = (r["note"] if (r is not None and "note" in r.keys()) else None) or ""
        ranges[p["name"]] = find_reference_range(db, p["id"], ot["gender"], ot["age"], ot["age_unit"],
                                                  patient_id=ot["patient_id"],
                                                  analyzer=ot["analyzer"] if "analyzer" in ot.keys() else None)

    logo_path = get_setting(db, "logo_path", "")
    logo_url = url_for("static", filename=logo_path) if logo_path else None

    # Only show the "received from another lab" note when the visit was
    # actually referred in via a referral center, not a plain walk-in.
    from_other_lab = bool(ot["referral_center_id"]) and ot["referral_center_name"] not in (None, "", "Walk-in")

    font_size = 14 if ot["test_code"] == "CBC" else 16
    # مربع "توقيع وختم الدكتور الفاحص" كان مُلغى بكل التقارير (فراغ فاضي
    # بانتظار ختم/توقيع حقيقي يُلصق يدويًا على الورقة المطبوعة). الآن رجع
    # كصورة ختم/توقيع رقمية فعلية تُختار من مكتبة الأختام وتُسحب لموضعها —
    # راجع digital_stamps/stamp_placements أدناه وpartials/stamp_picker.html.
    show_exam_signature = ot["test_code"] in EXAM_SIGNATURE_TEST_CODES or bool(ot["is_examining_test"])

    try:
        dt = datetime.fromisoformat(ot["visit_created_at"])
        visit_date = f"{dt.day}/{dt.month}/{dt.year}"
    except (TypeError, ValueError):
        visit_date = ot["visit_created_at"] or ""

    # زيارة سابقة لنفس الشخص (تطابق كامل بالاسم + العمر) — تُعرض بالتقرير
    # (تاريخها + قيم باراميتراتها) فقط إذا وافق الموظف صراحة على دمجها
    # لحظة تسجيل هذي الزيارة (بنك تنبيه الزيارة السابقة بشاشة "زيارة
    # جديدة")، راجع visit_previous_merges — لا يوجد أي عرض تلقائي بعد
    # اليوم بغض النظر عن قسم التحليل. ?show_prev=0 يبقى يقدر يخفيها لحظة
    # الطباعة حتى لو انوافَق عليها، لكن ?show_prev=1 ما يقدر يظهرها من
    # غير موافقة أصلاً (مافيه بيانات تُعرض أصلاً بهاي الحالة).
    merged_previous = get_visit_previous_merges(db, ot["visit_id"])
    matched_merge = next(
        (m for m in merged_previous if m["test_definition_id"] == ot["test_definition_id"]), None,
    )
    show_prev_values = matched_merge is not None
    show_prev_override = request.args.get("show_prev")
    if show_prev_override == "0":
        show_prev_values = False
    previous_visit_date = matched_merge["date_display"] if matched_merge else None
    previous_values = matched_merge["results"] if matched_merge else {}

    cbc_groups = None
    if ot["test_code"] == "CBC":
        units_by_name = {p["name"]: p["unit"] for p in parameters}
        highlight_by_name = {p["name"]: bool(p["highlight"]) for p in parameters}
        cbc_groups = []
        for group in CBC_ROW_GROUPS:
            rows = []
            for name in group:
                rng = ranges.get(name)
                res_row = results_by_name.get(name)
                rows.append({
                    "name": resolve_label(params_by_name_row.get(name)),
                    "result": params.get(name, ""),
                    "unit": units_by_name.get(name, ""),
                    "low": rng["low"] if rng else "",
                    "high": rng["high"] if rng else "",
                    "highlight": highlight_by_name.get(name, False),
                    "previous": previous_values.get(name, "") if show_prev_values else "",
                    "flag": res_row["flag"] if res_row else None,
                    "value_align": resolve_value_align(params_by_name_row.get(name)),
                })
            cbc_groups.append(rows)

    custom_rows = None
    custom_heading = None
    custom_heading_align = "center"
    custom_rows_align = "right"
    if custom_template:
        units_by_name = {p["name"]: p["unit"] for p in parameters}
        unit2_by_name = {p["name"]: p["unit2"] for p in parameters}
        unit2_factor_by_name = {p["name"]: p["unit2_factor"] for p in parameters}
        custom_heading = custom_template["heading"] or ot["test_name"]
        custom_heading_align = custom_template["heading_align"] or "center"
        custom_rows_align = custom_template["rows_align"] or "right"
        row_defs = json.loads(custom_template["rows_json"] or "[]")
        custom_rows = []
        for rd in row_defs:
            pname = rd.get("param_name", "")
            rng = ranges.get(pname)
            normal_range = ""
            if rng:
                if rng["range_text"]:
                    normal_range = rng["range_text"]
                elif rng["low"] is not None and rng["high"] is not None:
                    normal_range = f"{rng['low']} - {rng['high']}"
                elif rng["low"] is not None:
                    normal_range = f"> {rng['low']}"
                elif rng["high"] is not None:
                    normal_range = f"< {rng['high']}"
            result_val = params.get(pname, "")
            res_row = results_by_name.get(pname)
            flag_val = res_row["flag"] if res_row else None

            # حقل "This test done by ... (FDA Approved)" (source_note) أُلغي
            # عرضه نهائيًا بالتقرير المطبوع بناءً على الطلب — يبقى العمود
            # موجود بجدول reference_ranges (ما يُحذف) لكن لا يُقرأ ولا يُمرَّر
            # للقالب أبداً بعد الآن، فلا يظهر إطلاقًا مهما كانت قيمته بقاعدة
            # البيانات.

            # مستويات Normal Range المفصّلة (زي Triglycerides بالنموذج
            # المرجعي) — من range_text لو موجود، وإلا من normal_range
            # الجاهزة (سطر واحد بلا تسمية، زي أغلب التحاليل العادية).
            if rng and rng["range_text"]:
                range_tiers = parse_range_tiers(rng["range_text"])
            elif normal_range:
                range_tiers = [{"label": None, "value": normal_range}]
            else:
                range_tiers = []

            # مدى الوحدة الثانية (unit2) — يُحسب تلقائيًا بنفس معامل تحويل
            # النتيجة (unit2_factor) على low/high، فقط لمدى بسيط (سطر واحد
            # رقمي بلا مستويات)؛ لا ينطبق على مدى متدرّج (range_tiers متعدد).
            normal_range2 = None
            if rng and not (rng["range_text"] and len(range_tiers) > 1) and rng["low"] is not None and rng["high"] is not None:
                factor = unit2_factor_by_name.get(pname)
                low2 = format_unit2_value(rng["low"], factor)
                high2 = format_unit2_value(rng["high"], factor)
                if low2 is not None and high2 is not None:
                    normal_range2 = f"{low2} - {high2}"

            custom_rows.append({
                "label": resolve_label(params_by_name_row.get(pname), rd.get("label")),
                "result": result_val,
                "unit": units_by_name.get(pname, ""),
                "normal_range": normal_range,
                "range_tiers": range_tiers,
                "normal_range2": normal_range2,
                "previous": previous_values.get(pname, "") if show_prev_values else "",
                "result2": format_unit2_value(result_val, unit2_factor_by_name.get(pname)),
                "unit2": unit2_by_name.get(pname) or "",
                # حرية تحريك موضع الحقول لكل صف على حدة (يُضبط من مصمم
                # التقرير مستقبلاً، يُقرأ من rows_json): name_side='right'
                # ينقل اسم التحليل فيزيائيًا لعمود القيمة بدل عمود الاسم،
                # range_position='below' يرجع المدى الطبيعي لسطر مستقل تحت
                # اسم التحليل بدل عمود محاذي لعمود النتيجة (الافتراضي).
                "name_side": rd.get("name_side") or "left",
                "range_position": rd.get("range_position") or "inline",
                "name_align": rd.get("name_align"),
                "color": rd.get("color"),
                "value_align": resolve_value_align(params_by_name_row.get(pname)),
                "flag": flag_val,
                "page_break_before": rd.get("page_break_before", False),
            })

    age_display = format_age_display(ot["age"], ot["age_unit"])

    # ترويسة متكرّرة تلقائيًا بأعلى كل صفحة إضافية عند الطباعة (نفس الشعار،
    # أسماء الأطباء، الدكتور المرسل، اسم المريض، التاريخ...) — فقط لتقارير
    # الكيمياء/الهرمونات/الفيتامينات/الدلائل الورمية/التخثر/الفايروسات (اللي
    # تُطبع كبطاقات وقد تطول لأكثر من صفحة)، وليس لتحاليل أمراض الدم إطلاقًا
    # (CBC وغيره من التقارير الجاهزة أبدًا ما يُمرَّر لها هذا المتغيّر، فتبقى
    # بسلوكها القديم تمامًا). راجع base_report.html لآلية التكرار الفعلية.
    repeat_header_on_print = department_shows_previous_values(ot["test_department"])

    _pt_en_row = db.execute(
        "SELECT full_name_en FROM patients WHERE id=?", (ot["patient_id"],)
    ).fetchone()
    patient_name_en_value = (_pt_en_row["full_name_en"] or "") if _pt_en_row else ""

    # تخصيص مظهر التقرير (سحب باراميتر، لون/خط/حجم، إزاحة صفحة...) —
    # يُمزَج مستوى التحليل (كل المرضى) مع استثناء هذا المريض بالذات لو
    # موجود. report_layout_has_patient_override يتحكم بإظهار زر "إرجاع
    # لتصميم افتراضي" بالقالب (يظهر فقط لو فيه استثناء فعلي لهذا المريض).
    report_layout, report_layout_has_patient_override = get_report_layout(
        db, ot["test_definition_id"], order_test_id
    )
    # ملاحظة: تُمرَّر "parameters" هنا (قائمة صفوف test_parameters الخام) —
    # وليس "params" (dict بصيغة name→value المبني أعلاه بسطر 3710 للقوالب
    # القديمة CBC/custom). كان بالخطأ يُمرَّر params هنا، فـ Python يتكرّر
    # على مفاتيح الـ dict (نصوص) بدل صفوف Row، مما يسبب TypeError فوري لأي
    # تحليل — هذا الفرق هو سبب انهيار كل طباعة (CBC وGUE/GSE/SFA سوا).
    macro_params, micro_params = _build_exam_sections(ot["test_code"], parameters, report_layout)

    auto_flag_color_enabled, show_result_flag, flag_color_map = get_report_flag_settings(db)
    return render_template(
        template_name,
        ot=ot, params=params, ranges=ranges, units=units, notes=notes, cbc_groups=cbc_groups,
        custom_rows=custom_rows, custom_heading=custom_heading,
        custom_heading_align=custom_heading_align, custom_rows_align=custom_rows_align,
        show_prev_values=show_prev_values, previous_visit_date=previous_visit_date,
        previous_values=previous_values, repeat_header_on_print=repeat_header_on_print,
        logo_url=logo_url, from_other_lab=from_other_lab, font_size=font_size,
        show_exam_signature=show_exam_signature,
        # enable_stamp_widget: يتحكم فقط بصندوق "إضافة ختم / توقيع" التفاعلي
        # (stamp_picker.html) — منفصل تماماً عن show_exam_signature أعلاه
        # (صندوق التوقيع الثابت الخاص بالفحوصات). الافتراضي 0 لأي تحليل ما
        # فُعِّل له صراحةً من مصمم التقارير.
        enable_stamp_widget=bool(ot["enable_stamp_widget"]) if "enable_stamp_widget" in ot.keys() else False,
        test_definition_id=ot["test_definition_id"],
        stamp_target_type="order_test", stamp_target_id=order_test_id,
        digital_stamps=get_digital_stamps(db),
        stamp_placements=get_stamp_placements(db, "order_test", order_test_id),
        visit_date=visit_date, sex=ot["gender"] or "", age=age_display,
        patient_name=ot["patient_name"], patient_id=ot["registration_number"],
        referring_doctor_name=ot["referring_doctor_name"] or "",
        sample_no=ot["barcode"] if "barcode" in ot.keys() else "",
        sample_time=(ot["collected_at"] or ot["accessioned_at"] or "") if "collected_at" in ot.keys() else "",
        number_of=get_patient_number_of_day(db, order_test_id),
        patient_name_en=patient_name_en_value,
        # order_test_id / results_by_name / param_notes / report_comment:
        # مطلوبة لقوالب فحوصات exam_report_shared.html (GUE/GSE/SFA وأي
        # تحليل مستقبلي بنفس النمط) — تُمرَّر دائمًا بلا استثناء (نفس منطق
        # units أعلاه) حتى لا تتكرر مشكلة NameError/UndefinedError.
        order_test_id=order_test_id,
        results_by_name=results_by_name,
        param_notes={name: r["note"] for name, r in results_by_name.items() if r["note"]},
        report_layout=report_layout,
        report_layout_has_patient_override=report_layout_has_patient_override,
        macro_params=macro_params,
        micro_params=micro_params,
        auto_flag_color_enabled=auto_flag_color_enabled, show_result_flag=show_result_flag, AUTO_FLAG_COLORS=flag_color_map,
        row_spacing_px=row_spacing_px_value,
        done_by_note=(ot["done_by_note"] or "") if "done_by_note" in ot.keys() else "",
        # params_list: نفس "parameters" (قائمة صفوف test_parameters الخام)
        # بس باسم متاح مباشرة للقالب — قوالب الفحص (urine_exam.html وغيرها)
        # تستدعي shared.render_report_body(..., params_list, ...) بالضبط
        # بهذا الاسم (مو "params" — هذاك محجوز لصيغة dict القديمة name→value
        # اللي تستخدمها cbc.html/custom.html، وتمرير القائمة تحت نفس الاسم
        # كان يكسر عرض GUE/GSE/SFA بالكامل: كل صف يطلع فاضي بلا اسم/قيمة
        # لأن render_report_body يتكرر على مفاتيح الـ dict بدل صفوف Row).
        params_list=parameters,
    )



# ---------------------------------------------------------------- exam reports --
# نقطتا API لقوالب الفحص الجديدة (GUE/GSE/SFA — reports/urine_exam.html
# وغيرها، عبر editor_script() بـ exam_report_shared.html): ملاحظة عامة أسفل
# التقرير كامل، وملاحظة قصيرة أمام باراميتر واحد بالذات. مفصولتان تمامًا
# (جدولان مختلفان) حتى تُحفظ كل وحدة بشكل مستقل دون التأثير على الثانية.
@app.route("/order-tests/<int:order_test_id>/report-comment", methods=["POST"])
@login_required
def order_test_report_comment(order_test_id):
    # الميزة أُلغيت نهائيًا (المطلوب 1) — العمود report_comment يبقى بقاعدة
    # البيانات بدون استخدام، لكن هذا الراوت ما يعود يحفظ فيه أي شي بعد الآن.
    return jsonify({"ok": False, "error": "This feature has been removed."}), 410


@app.route("/order-tests/<int:order_test_id>/param-note", methods=["POST"])
@login_required
def order_test_param_note(order_test_id):
    db = get_db()
    order_test = db.execute("SELECT id FROM order_tests WHERE id=?", (order_test_id,)).fetchone()
    if not order_test:
        return jsonify({"error": "Not found"}), 404
    try:
        test_parameter_id = int(request.form.get("test_parameter_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "بيانات غير صالحة"}), 400
    note = request.form.get("note", "")
    existing = db.execute(
        "SELECT id FROM results WHERE order_test_id=? AND test_parameter_id=?",
        (order_test_id, test_parameter_id),
    ).fetchone()
    if existing:
        db.execute("UPDATE results SET note=? WHERE id=?", (note, existing["id"]))
    else:
        db.execute(
            "INSERT INTO results (order_test_id, test_parameter_id, note) VALUES (?, ?, ?)",
            (order_test_id, test_parameter_id, note),
        )
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------- report layout --
# نظام تخصيص مظهر التقرير (سحب باراميتر، لون/خط/حجم، إزاحة صفحة، إخفاء/
# تسمية عرض مخصصة) — راجع editor_script + applyReportLayout بـ
# exam_report_shared.html. "scope" دائمًا واحدة من: "test" (scope_id =
# test_definition_id، يطبّق على كل مريض عنده هذا التحليل) أو "order_test"
# (scope_id = order_test_id، استثناء خاص بمريض واحد بالذات، يتفوّق على
# scope="test" لو موجود ولا يأثر على أي مريض ثاني).
VALID_LAYOUT_SCOPES = ("test", "order_test")


@app.route("/api/reports/layout/<int:test_definition_id>", methods=["GET"])
@login_required
def api_report_layout_get(test_definition_id):
    db = get_db()
    order_test_id = request.args.get("order_test_id", type=int)
    test_layout = get_raw_layout(db, "test", test_definition_id)
    patient_layout = None
    merged = test_layout
    has_patient_override = False
    if order_test_id:
        merged, has_patient_override = get_report_layout(db, test_definition_id, order_test_id)
        if has_patient_override:
            patient_layout = get_raw_layout(db, "order_test", order_test_id)
    return jsonify({
        "test_layout": test_layout,
        "patient_layout": patient_layout,
        "merged": merged,
        "has_patient_override": has_patient_override,
    })


@app.route("/api/reports/layout", methods=["POST"])
@login_required
def api_report_layout_save():
    db = get_db()
    body = request.get_json(silent=True) or {}
    scope = body.get("scope")
    scope_id = body.get("scope_id")
    layout = body.get("layout")
    if scope not in VALID_LAYOUT_SCOPES:
        return jsonify({"error": "scope غير صحيح"}), 400
    try:
        scope_id = int(scope_id)
    except (TypeError, ValueError):
        return jsonify({"error": "scope_id غير صالح"}), 400
    if not isinstance(layout, dict):
        return jsonify({"error": "layout غير صالح"}), 400
    save_report_layout(db, scope, scope_id, layout, user_id=session.get("user_id"))
    log_action("SaveReportLayout", scope, scope_id)
    return jsonify({"ok": True})


@app.route("/api/reports/layout/reset", methods=["POST"])
@login_required
def api_report_layout_reset():
    db = get_db()
    body = request.get_json(silent=True) or {}
    scope = body.get("scope")
    scope_id = body.get("scope_id")
    if scope not in VALID_LAYOUT_SCOPES:
        return jsonify({"error": "scope غير صحيح"}), 400
    try:
        scope_id = int(scope_id)
    except (TypeError, ValueError):
        return jsonify({"error": "scope_id غير صالح"}), 400
    reset_report_layout(db, scope, scope_id)
    log_action("ResetReportLayout", scope, scope_id)
    return jsonify({"ok": True})


# ============== إدارة دكاترة الترويسة من نفس صفحة معاينة الطباعة ==============
# نسخة JSON خفيفة من نفس شاشة (الإدارة ← الإعدادات ← إدارة قائمة الدكاترة
# examining_doctors_manage أعلاه) — تفتح كنافذة منبثقة فوق أي معاينة تقرير
# بدل الاضطرار للخروج من المعاينة والذهاب للإعدادات. تستخدم نفس دوال
# database.py حرفيًا (get/add/update/delete_examining_doctor*) فالقائمتان
# يبقيان متطابقتين ومتزامنتين دائمًا.
@app.route("/api/examining-doctors", methods=["GET"])
@roles_required("admin")
def api_examining_doctors_list():
    db = get_db()
    rows = get_examining_doctors_full(db)
    return jsonify({"doctors": [dict(r) for r in rows]})


@app.route("/api/examining-doctors", methods=["POST"])
@roles_required("admin")
def api_examining_doctors_add():
    db = get_db()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الدكتور مطلوب"}), 400
    font_size = body.get("font_size")
    try:
        font_size = max(8, min(30, int(font_size))) if font_size not in (None, "") else None
    except (TypeError, ValueError):
        font_size = None
    add_examining_doctor_full(
        db, name, body.get("title") or "الدكتور", body.get("degree_ar") or "", body.get("degree_en") or "",
        bool(body.get("show_on_letterhead", True)), font_size,
    )
    log_action("AddExaminingDoctor", "examining_doctors_list", None, name)
    return jsonify({"ok": True, "doctors": [dict(r) for r in get_examining_doctors_full(db)]})


@app.route("/api/examining-doctors/<int:doctor_id>", methods=["POST"])
@roles_required("admin")
def api_examining_doctors_update(doctor_id):
    db = get_db()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الدكتور مطلوب"}), 400
    font_size = body.get("font_size")
    try:
        font_size = max(8, min(30, int(font_size))) if font_size not in (None, "") else None
    except (TypeError, ValueError):
        font_size = None
    update_examining_doctor(
        db, doctor_id, name, body.get("title") or "الدكتور", body.get("degree_ar") or "", body.get("degree_en") or "",
        bool(body.get("show_on_letterhead", True)), font_size,
    )
    log_action("UpdateExaminingDoctor", "examining_doctors_list", doctor_id, name)
    return jsonify({"ok": True, "doctors": [dict(r) for r in get_examining_doctors_full(db)]})


@app.route("/api/examining-doctors/<int:doctor_id>/delete", methods=["POST"])
@roles_required("admin")
def api_examining_doctors_delete(doctor_id):
    db = get_db()
    delete_examining_doctor(db, doctor_id)
    log_action("DeleteExaminingDoctor", "examining_doctors_list", doctor_id)
    return jsonify({"ok": True, "doctors": [dict(r) for r in get_examining_doctors_full(db)]})


# ============== إضافة باراميتر جديد مباشرة من صفحة معاينة التقرير ==============
# يستدعيه زر "+ إضافة باراميتر جديد لهذا القسم" (add_param_row بـ
# exam_report_shared.html) — بديل حقيقي عن رسالة placeholder السابقة.
# ينشئ صف test_parameters فعلي (اسم فقط، بلا وحدة/مدى طبيعي — تُضاف لاحقًا
# من كتالوج التحاليل لو احتاجها الأدمن)؛ ينزل تلقائيًا بقسم "Other Results"
# بأي تقرير فحص لهذا التحليل لحد ما يُسحب لمكانه الصحيح ويُحفظ التصميم.
@app.route("/api/test-parameters", methods=["POST"])
@roles_required("admin")
def api_add_test_parameter():
    db = get_db()
    body = request.get_json(silent=True) or {}
    try:
        test_definition_id = int(body.get("test_definition_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "بيانات غير صالحة"}), 400
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "اسم الباراميتر مطلوب"}), 400
    td = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_definition_id,)).fetchone()
    if not td:
        return jsonify({"error": "التحليل غير موجود"}), 404
    existing = db.execute(
        "SELECT id FROM test_parameters WHERE test_definition_id=? AND name=?", (test_definition_id, name)
    ).fetchone()
    if existing:
        return jsonify({"error": "فيه باراميتر بنفس هذا الاسم أصلاً لهذا التحليل"}), 400
    cur = db.execute(
        "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?, ?, '', 'Text')",
        (test_definition_id, name),
    )
    db.commit()
    log_action("AddTestParameter", "test_parameters", cur.lastrowid, name)
    return jsonify({"ok": True, "id": cur.lastrowid, "name": name})


# ============== تحديد/تعديل سعر باراميتر مفرد ==============
# يُستخدم فقط لما موظف الاستقبال يطلب بارامترات معيّنة بس من تحليل متعدد
# الباراميترات (سهم ▾ بشاشة "زيارة جديدة" — راجع شرح كامل عند
# order_tests.selected_param_ids بـdatabase.py). لو الباراميتر ما عنده
# سعر بعد، الموظف يكتبه أول مرة من نفس شاشة الطلب وينحفظ هنا دائمًا
# للطلبات الجاية. @login_required بدل admin عمداً — هذا إجراء تشغيلي
# اعتيادي وقت استقبال المريض، مو إعداد إداري.
@app.route("/api/test-parameters/<int:param_id>/set-price", methods=["POST"])
@login_required
def api_set_test_parameter_price(param_id):
    db = get_db()
    param = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not param:
        return jsonify({"ok": False, "error": "الباراميتر غير موجود"}), 404
    body = request.get_json(silent=True) or request.form
    try:
        price = float(body.get("price"))
        if price < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "السعر يجب أن يكون رقمًا صحيحًا"}), 400
    db.execute("UPDATE test_parameters SET price=? WHERE id=?", (price, param_id))
    db.commit()
    log_action("SetParameterPrice", "test_parameters", param_id, str(price))
    return jsonify({"ok": True, "price": price})


@app.route("/api/test-parameters/<int:param_id>/rename", methods=["POST"])
@login_required
def api_rename_test_parameter(param_id):
    """يعيد تسمية باراميتر تابع لتحليل — يُستخدم بالقلم ✏️ الجديد بلوحة
    اختيار البارامترات بشاشة "زيارة جديدة" (سهم ▾)، للسرعة بدون فتح صفحة
    Reference Range. @login_required بدل admin عمداً لنفس سبب set-price."""
    db = get_db()
    param = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not param:
        return {"ok": False, "error": "الباراميتر غير موجود"}, 404
    body = request.get_json(silent=True) or request.form
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return {"ok": False, "error": "الاسم لا يمكن أن يكون فارغًا"}, 400
    db.execute("UPDATE test_parameters SET name=? WHERE id=?", (new_name, param_id))
    db.commit()
    log_action("RenameParameter", "test_parameters", param_id, new_name)
    return {"ok": True, "name": new_name}


@app.route("/api/test-definitions/<int:test_definition_id>/parameters")
@login_required
def api_test_definition_parameters(test_definition_id):
    """يرجّع بارامترات تحليل معيّن (id/name/price) — يغذّي سهم ▾ بشاشة
    "زيارة جديدة" لاختيار بارامترات معيّنة بس من داخل تحليل متعدد
    الباراميترات بدل طلبه كامل (راجع order_tests.selected_param_ids)."""
    db = get_db()
    params = db.execute(
        "SELECT id, name, price FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id",
        (test_definition_id,),
    ).fetchall()
    return jsonify([dict(p) for p in params])


# ============== حذف باراميتر نهائيًا مباشرة من صفحة معاينة التقرير ==============
# يستدعيه زر ❌ (examDeleteParam بـexam_report_shared.html) — حذف حقيقي من
# test_parameters، مختلف تمامًا عن 🗑️/👁️ (إخفاء/إظهار فقط، ما يمس البيانات).
# محمي عمداً: يرفض الحذف لو فيه أي نتيجة محفوظة سابقًا لهذا الباراميتر (أي
# مريض/زيارة) — حتى ما نفقد تأريخ نتائج حقيقية بالغلط، ونقترح الإخفاء
# كبديل آمن بهذي الحالة. لا يحتاج تنظيف report_layout يدويًا بعدها: exam_row
# أصلاً ما يطبع إلا الأسماء الموجودة فعليًا بـtest_parameters (راجع
# `{% if name in params_by_name %}` بـrender_report_body)، فبمجرد الحذف
# يختفي الصف تلقائيًا من كل تقرير مستقبلي لهذا التحليل.
@app.route("/api/test-parameters/<int:param_id>", methods=["DELETE"])
@roles_required("admin")
def api_delete_test_parameter(param_id):
    db = get_db()
    p = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not p:
        return jsonify({"error": "الباراميتر غير موجود"}), 404
    used = db.execute(
        "SELECT COUNT(*) as c FROM results WHERE test_parameter_id=?", (param_id,)
    ).fetchone()["c"]
    if used:
        return jsonify({
            "error": f"عنده {used} نتيجة محفوظة سابقًا (لمرضى/زيارات مختلفة) — "
                     f"حذفه يفقد تأريخ هذي النتائج نهائيًا. استخدم زر 🗑️ (إخفاء) بدل الحذف.",
        }), 400
    db.execute("DELETE FROM reference_ranges WHERE test_parameter_id=?", (param_id,))
    db.execute("DELETE FROM test_parameters WHERE id=?", (param_id,))
    db.commit()
    log_action("DeleteTestParameter", "test_parameters", param_id, p["name"])
    return jsonify({"ok": True})


def _whatsapp_flush_pdf_dir():
    d = os.path.join(app.static_folder, "whatsapp_pdfs")
    os.makedirs(d, exist_ok=True)
    return d


def _open_whatsapp_with_pdf(phone, pdf_path, country_code):
    """يفتح محادثة واتساب مع رقم المريض مباشرة (تطبيق سطح المكتب المثبّت
    أصلاً على هذا الجهاز، عبر رابط whatsapp://)، ويفتح مجلد الملف ومحدِّد
    عليه بمستكشف الملفات — حتى يقدر المستخدم يسحب ملف الـPDF ويرفقه
    بنفسه بضغطة وحدة، بدل الاعتماد على أتمتة Selenium الهشة (اللي كانت
    تحتاج Chrome منفصل، وتسبب أقفال ملفات، وتوقف البرنامج بالكامل).
    يرجّع (opened_whatsapp: bool, opened_folder: bool)."""
    import re as _re
    digits = _re.sub(r"\D", "", phone or "")
    if not digits:
        return False, False
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = country_code + digits[1:]
    elif not digits.startswith(country_code):
        digits = country_code + digits

    opened_wa = False
    try:
        os.startfile(f"whatsapp://send?phone={digits}")
        opened_wa = True
    except OSError:
        try:
            webbrowser.open(f"https://wa.me/{digits}")
            opened_wa = True
        except Exception:
            opened_wa = False

    opened_folder = False
    try:
        subprocess.run(["explorer", "/select,", os.path.normpath(pdf_path)])
        opened_folder = True
    except Exception:
        opened_folder = False

    return opened_wa, opened_folder


def _safe_pdf_name_part(text):
    """ينظّف نص (اسم مريض/تحليل) حتى يصلح كجزء من اسم ملف PDF بويندوز —
    يشيل الأحرف الممنوعة (\\ / : * ? " < > |) بس، ويحافظ على باقي النص
    (بما فيه المسافات والعربي) زي ما هو، حتى يبقى اسم المريض مقروء
    بالظبط متل ما يظهر بالتقرير المطبوع، لتسهيل البحث بين ملفات الـPDF."""
    return re.sub(r'[\\/:*?"<>|]+', " ", (text or "").strip()).strip() or "ملف"


def _whatsapp_generate_and_queue(db, visit_row, patient_id, patient_name, phone,
                                  label, html_content, order_test_id=None):
    """يولّد PDF من الـHTML الجاهز (نفس صفحة الطباعة)، يسجّل صف بطابور
    whatsapp_sends، ثم يفتح واتساب على رقم المريض ومجلد الملف جنب بعض —
    الإرسال الفعلي خطوة يدوية بسيطة (سحب وإفلات) بدل إرسال آلي عبر متصفح
    منفصل يتحكم فيه Selenium، تفاديًا لكل مشاكل القفل والكراش السابقة."""
    import pdf_export

    now = datetime.now().isoformat(timespec="seconds")
    # اسم الملف يبدأ باسم المريض (مثل ما يظهر بالتقرير بالضبط) بدل رقم
    # الزيارة، حتى يقدر المستخدم يميّز فوراً بأي ملف بمجلد واتساب وهو
    # يدور عن نتيجة مريض معيّن، بدل أرقام زيارات ما تعني له شي بالنظرة.
    pdf_path = pdf_export.make_temp_pdf_path(_safe_pdf_name_part(patient_name))

    # توليد PDF نفسه كان بدون أي حماية — أي خطأ يصير أثناء التحويل (خط
    # ناقص، مسار شعار كسران، أي عطل بمكتبة التحويل) كان يطيح الطلب كامل
    # بصفحة 500 بيضاء بدون أي رسالة توضح شنو صار. الآن أي فشل هنا يُسجَّل
    # كصف "failed" بنفس الطابور بدل ما يكسر الصفحة بالكامل.
    try:
        pdf_export.html_to_pdf(html_content, request.url_root, pdf_path)
    except Exception as exc:
        db.execute(
            "INSERT INTO whatsapp_sends (visit_id, order_test_id, patient_id, patient_name, "
            "phone, label, pdf_path, status, attempts, error, requested_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', 1, ?, ?, ?)",
            (visit_row["id"], order_test_id, patient_id, patient_name, phone, label,
             pdf_path, f"فشل توليد PDF: {exc}", session.get("user_id"), now),
        )
        db.commit()
        log_action("WhatsAppSend", "order_test", order_test_id or visit_row["id"], f"PDF generation failed: {exc}")
        return False, f"فشل توليد ملف PDF: {exc}"

    opened_wa, opened_folder = _open_whatsapp_with_pdf(
        phone, pdf_path, get_setting(db, "whatsapp_country_code", "964")
    )

    # status='opened' (مو 'sent') لأننا فعلياً ما نتحقق برمجيًا إن الملف
    # انرسل فعلاً — هذا فتح واتساب + المجلد بس، الضغطة الأخيرة (سحب
    # الملف وإرسال) يسويها المستخدم بنفسه.
    status = "opened" if opened_wa else "failed"
    error = None if opened_wa else "تعذّر فتح تطبيق واتساب — تأكد إنه مثبّت على هذا الجهاز."
    db.execute(
        "INSERT INTO whatsapp_sends (visit_id, order_test_id, patient_id, patient_name, "
        "phone, label, pdf_path, status, attempts, error, requested_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (visit_row["id"], order_test_id, patient_id, patient_name, phone, label,
         pdf_path, status, error, session.get("user_id"), now),
    )
    db.commit()

    if opened_wa:
        return True, None
    return False, error


def _maybe_auto_whatsapp_send(db, visit_id):
    """إرسال تلقائي عبر واتساب لكل نتائج الزيارة دفعة واحدة (بملف PDF واحد،
    نفس أسلوب زر 'إرسال كل النتائج' اليدوي) — بس إذا تحققت الشروط الثلاثة:
    (1) رقم هاتف المريض مسجّل بملفه، (2) كل تحليل مطلوب بهذي الزيارة صار
    Completed أو Verified (ولا تحليل واحد لسا ناقص نتيجة)، و(3) ما سبق
    إرسال (تلقائي أو يدوي) لكل نتائج هذي الزيارة مجموعة من قبل — تفاديًا
    لتكرار الإرسال في كل مرة تُعدَّل فيها نتيجة بعد اكتمال الزيارة.
    تُستدعى بعد أي حفظ نتيجة (مفردة من result_entry، أو مُجمّعة من
    visit_results_entry). أي خطأ بتوليد الـPDF أو الإرسال لا يوقف حفظ
    النتائج أبدًا — يُسجَّل بطابور واتساب كـ pending/failed مثل أي محاولة
    إرسال يدوية عادية، وتلتقطه المهمة الخلفية أو زر 'إعادة المحاولة' لاحقًا."""
    visit = db.execute(
        "SELECT v.*, p.id as patient_id, p.full_name, p.phone FROM visits v "
        "JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit or not (visit["phone"] or "").strip():
        return False

    statuses = [row["status"] for row in db.execute(
        "SELECT ot.status FROM order_tests ot JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
        (visit_id,),
    ).fetchall()]
    if not statuses or any(s not in ("Completed", "Verified") for s in statuses):
        return False  # لسا فيه تحليل ناقص نتيجة — ما نرسل شي بعد

    already = db.execute(
        "SELECT id FROM whatsapp_sends WHERE visit_id=? AND order_test_id IS NULL "
        "AND status IN ('pending', 'sent', 'opened')",
        (visit_id,),
    ).fetchone()
    if already:
        return False  # سبق إرسال/طابور كل نتائج هذي الزيارة مجموعة من قبل

    try:
        html_content = _build_combined_designed_reports_html(visit_id)
    except Exception:
        return False
    if not html_content:
        return False

    ok, error = _whatsapp_generate_and_queue(
        db, visit, visit["patient_id"], visit["full_name"], visit["phone"],
        "كل نتائج الزيارة (إرسال تلقائي)", html_content, order_test_id=None,
    )
    log_action("WhatsAppAutoSend", "visit", visit_id, "OK" if ok else f"queued: {error}")
    if ok:
        flash("📱 النتائج مكتملة — تم إرسالها تلقائيًا عبر واتساب للمريض.")
    else:
        flash(f"📱 النتائج مكتملة لكن تعذّر الإرسال الفوري — انضافت لطابور واتساب وسترسل تلقائيًا عند توفر الإنترنت. ({error})")
    return True


def _get_pdf_archive_dir(db):
    """مجلد أرشفة الـPDF الدائم كما ظبطه المدير من Management → Settings
    (settings.pdf_archive_dir). يرجّع None إذا لسا فاضي (غير مُعد بعد) —
    وبهذي الحالة الأرشفة التلقائية تُتجاهل بصمت بدل ما تكسر حفظ النتائج."""
    d = (get_setting(db, "pdf_archive_dir", "") or "").strip()
    if not d:
        return None
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def _maybe_archive_visit_pdf(db, visit_id):
    """يحفظ نسخة PDF دائمة (موحّدة لكل نتائج الزيارة) بمجلد الأرشيف الثابت،
    بس إذا: (1) المدير ظبط مجلد أرشفة من الإعدادات، و(2) كل تحليل مطلوب
    بهذي الزيارة صار Completed أو Verified. تُستدعى من نفس نقطتي حفظ
    النتائج اللي تستدعي _maybe_auto_whatsapp_send (مفردة ومُجمّعة)، وتُعيد
    توليد/استبدال نفس الملف (upsert بـ visit_id) في كل مرة — حتى يبقى
    الملف المؤرشف مطابقًا دائمًا لآخر تعديل على النتائج، حتى لو تم تعديلها
    بعد الاكتمال. أي خطأ بالتوليد لا يوقف حفظ النتائج أبدًا."""
    archive_dir = _get_pdf_archive_dir(db)
    if not archive_dir:
        return False

    visit = db.execute(
        "SELECT v.*, p.id as patient_id, p.full_name, p.registration_number as _unused, "
        "d.full_name as referring_doctor_name, rc.name as referral_center_name "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN doctors d ON d.id = v.doctor_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id "
        "WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return False

    statuses = [row["status"] for row in db.execute(
        "SELECT ot.status FROM order_tests ot JOIN orders o ON o.id = ot.order_id WHERE o.visit_id=?",
        (visit_id,),
    ).fetchall()]
    if not statuses or any(s not in ("Completed", "Verified") for s in statuses):
        return False  # لسا فيه تحليل ناقص نتيجة — ما نؤرشف بعد

    try:
        html_content = _build_combined_designed_reports_html(visit_id)
    except Exception:
        return False
    if not html_content:
        return False

    import pdf_export
    try:
        # اسم ملف واضح للبحث اليدوي بمجلد الأرشيف نفسه من خارج البرنامج:
        # رقم_التسجيل - اسم المريض - تاريخ الزيارة.pdf (كل رمز غير آمن
        # بالاسم يُستبدل بشرطة سفلية).
        safe_name = secure_filename(visit["full_name"] or "patient") or "patient"
        try:
            dt = datetime.fromisoformat(visit["created_at"])
            date_part = dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            date_part = datetime.now().strftime("%Y-%m-%d")
        filename = f"{visit['registration_number']}_{safe_name}_{date_part}.pdf"
        pdf_path = os.path.join(archive_dir, filename)
        pdf_export.html_to_pdf(html_content, request.url_root, pdf_path)
    except Exception:
        return False

    save_saved_report(
        db, visit_id, visit["patient_id"], visit["full_name"], visit["registration_number"],
        pdf_path, referring_doctor_name=visit["referring_doctor_name"],
        referral_center_name=visit["referral_center_name"],
    )
    return True


def _whatsapp_generate_and_queue_multi(db, visit_row, patient_id, patient_name, phone, items):
    """نفس _whatsapp_generate_and_queue فوق، بس لعدة تحاليل كملفات PDF
    منفصلة دفعة وحدة (بدل ملف مجمّع واحد) — items: قائمة عناصر بشكل
    (label, html_content, order_test_id). يولّد كل الملفات بنفس المجلد،
    يسجّل صف طابور لكل واحد منها، ثم يفتح واتساب مرة وحدة + يفتح نفس
    المجلد (بدون تحديد ملف معيّن، خلافاً عن opened_folder المفرد) حتى
    يقدر المستخدم يحدد كل الملفات مرة وحدة (Ctrl+A أو تحديد متعدد)
    ويسحبها كلها سوا لمحادثة واتساب بضغطة وحدة."""
    import pdf_export

    now = datetime.now().isoformat(timespec="seconds")
    generated_paths = []
    for label, html_content, order_test_id in items:
        # كل ملف بالوضع "منفصل" اسمه "اسم المريض - اسم التحليل"، حتى لو
        # فتحت المجلد ولقيت عدة ملفات لنفس الزيارة تعرف فوراً أي ملف
        # لأي تحليل بدون ما تفتحه.
        prefix = f"{_safe_pdf_name_part(patient_name)} - {_safe_pdf_name_part(label)}"
        pdf_path = pdf_export.make_temp_pdf_path(prefix)
        try:
            pdf_export.html_to_pdf(html_content, request.url_root, pdf_path)
        except Exception as exc:
            db.execute(
                "INSERT INTO whatsapp_sends (visit_id, order_test_id, patient_id, patient_name, "
                "phone, label, pdf_path, status, attempts, error, requested_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', 1, ?, ?, ?)",
                (visit_row["id"], order_test_id, patient_id, patient_name, phone, label,
                 pdf_path, f"فشل توليد PDF: {exc}", session.get("user_id"), now),
            )
            continue
        generated_paths.append((pdf_path, label, order_test_id))

    if not generated_paths:
        db.commit()
        return False, "تعذّر توليد أي ملف PDF لأي تحليل."

    # نفتح واتساب مرة وحدة بس (مو لكل ملف)، ونفتح مجلد الملفات (بدون
    # تحديد ملف معيّن — عكس _open_whatsapp_with_pdf المفرد اللي يحدد ملف
    # واحد بعينه) حتى يقدر المستخدم يحدد كل الملفات المولَّدة الجديدة
    # مرة وحدة ويسحبها سوا.
    import re as _re
    digits = _re.sub(r"\D", "", phone or "")
    country_code = get_setting(db, "whatsapp_country_code", "964")
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = country_code + digits[1:]
    elif digits and not digits.startswith(country_code):
        digits = country_code + digits

    opened_wa = False
    if digits:
        try:
            os.startfile(f"whatsapp://send?phone={digits}")
            opened_wa = True
        except OSError:
            try:
                webbrowser.open(f"https://wa.me/{digits}")
                opened_wa = True
            except Exception:
                opened_wa = False

    try:
        folder = os.path.dirname(os.path.normpath(generated_paths[0][0]))
        subprocess.run(["explorer", folder])
    except Exception:
        pass

    status = "opened" if opened_wa else "failed"
    error = None if opened_wa else "تعذّر فتح تطبيق واتساب — تأكد إنه مثبّت على هذا الجهاز."
    for pdf_path, label, order_test_id in generated_paths:
        db.execute(
            "INSERT INTO whatsapp_sends (visit_id, order_test_id, patient_id, patient_name, "
            "phone, label, pdf_path, status, attempts, error, requested_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (visit_row["id"], order_test_id, patient_id, patient_name, phone, label,
             pdf_path, status, error, session.get("user_id"), now),
        )
    db.commit()

    if opened_wa:
        return True, f"جهّزنا {len(generated_paths)} ملف PDF منفصل وفتحنا واتساب + مجلد الملفات — حدد كل الملفات (Ctrl+A) واسحبها سوا للمحادثة."
    return False, error

def _do_whatsapp_send_visit(visit_id, mode):
    """المنطق الفعلي لإرسال كل نتائج الزيارة عبر واتساب — mode='combined'
    (ملف PDF واحد مجمّع، الافتراضي القديم) أو 'separate' (ملف PDF مستقل
    لكل تحليل مكتمل). يرجّع (ok, message)."""
    db = get_db()
    visit = db.execute(
        "SELECT v.*, p.id as patient_id, p.full_name, p.phone FROM visits v "
        "JOIN patients p ON p.id = v.patient_id WHERE v.id=?",
        (visit_id,),
    ).fetchone()
    if not visit:
        return False, "الزيارة غير موجودة."
    if not visit["phone"]:
        return False, "لا يوجد رقم هاتف مسجّل لهذا المريض — أضِفه من ملف المريض أولًا."

    if mode == "separate":
        order_tests = db.execute(
            "SELECT ot.id, td.code as test_code, td.name as test_name "
            "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
            "JOIN test_definitions td ON td.id = ot.test_definition_id "
            "WHERE o.visit_id=? AND ot.status IN ('Completed', 'Verified') ORDER BY ot.id",
            (visit_id,),
        ).fetchall()
        seen_codes = set()
        items = []
        for ot in order_tests:
            code = ot["test_code"]
            if code in BF_RETIC_LINK and BF_RETIC_LINK[code] in seen_codes:
                continue
            seen_codes.add(code)
            report_html = print_report(ot["id"])
            if not isinstance(report_html, str):
                continue
            items.append((ot["test_name"], report_html, ot["id"]))
        if not items:
            return False, "لا توجد نتائج مكتملة بهذي الزيارة لإرسالها بعد."
        ok, error = _whatsapp_generate_and_queue_multi(
            db, visit, visit["patient_id"], visit["full_name"], visit["phone"], items,
        )
        log_action("WhatsAppSend", "visit", visit_id, "opened" if ok else f"failed: {error}")
        return ok, error

    html_content = _build_combined_designed_reports_html(visit_id)
    if not html_content:
        return False, "لا توجد نتائج مكتملة بهذي الزيارة لإرسالها بعد."

    ok, error = _whatsapp_generate_and_queue(
        db, visit, visit["patient_id"], visit["full_name"], visit["phone"],
        "كل نتائج الزيارة", html_content, order_test_id=None,
    )
    log_action("WhatsAppSend", "visit", visit_id, "opened" if ok else f"failed: {error}")
    if ok:
        return True, "📎 جهّزنا ملف PDF واحد بكل نتائج الزيارة وفتحنا واتساب — اسحب الملف من نافذة المجلد وأرفقه بالمحادثة."
    return False, error


def _do_whatsapp_send_result(order_test_id):
    """المنطق الفعلي لإرسال نتيجة تحليل واحد عبر واتساب — يرجّع (ok, message,
    visit_id أو None). تُستخدم من مسارين: الرابط الكلاسيكي (فورم + flash +
    redirect) للاستخدام خارج أي iframe، والـAPI JSON (fetch من جوّه مودال
    'طباعة كل النتائج المكتملة') بدون أي تنقّل/إعادة تحميل."""
    db = get_db()
    ot = db.execute(
        "SELECT ot.*, td.name as test_name, v.id as visit_id, "
        "p.id as patient_id, p.full_name as patient_name, p.phone "
        "FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id "
        "JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id "
        "JOIN patients p ON p.id = v.patient_id WHERE ot.id=?",
        (order_test_id,),
    ).fetchone()
    if not ot:
        return False, "النتيجة غير موجودة.", None
    if not ot["phone"]:
        return False, "لا يوجد رقم هاتف مسجّل لهذا المريض — أضِفه من ملف المريض أولًا.", ot["visit_id"]

    html_content = print_report(order_test_id)
    if not isinstance(html_content, str):
        return False, "لا يوجد تصميم طباعة لهذا التحليل بعد.", ot["visit_id"]

    ok, error = _whatsapp_generate_and_queue(
        db, ot, ot["patient_id"], ot["patient_name"], ot["phone"],
        ot["test_name"], html_content, order_test_id=order_test_id,
    )
    log_action("WhatsAppSend", "order_test", order_test_id, "opened" if ok else f"failed: {error}")
    if ok:
        return True, f"📎 جهّزنا ملف PDF لنتيجة {ot['test_name']} وفتحنا واتساب — اسحب الملف من نافذة المجلد وأرفقه بالمحادثة.", ot["visit_id"]
    return False, error, ot["visit_id"]


@app.route("/whatsapp/send-result/<int:order_test_id>", methods=["POST"])
@login_required
def whatsapp_send_result(order_test_id):
    """إرسال نتيجة تحليل واحد محدّد (مو كل نتائج الزيارة) عبر واتساب —
    نفس زر '🖨 طباعة التقرير' لكن يولّد PDF ويرسله بدل ما يفتحه بالمتصفح.
    (فورم كلاسيكي: flash + redirect — للاستخدام خارج أي iframe)."""
    ok, message, visit_id = _do_whatsapp_send_result(order_test_id)
    flash(message if ok else f"❌ {message}")
    return redirect(url_for("visit_results_entry", visit_id=visit_id) if visit_id else url_for("results_list"))


@app.route("/whatsapp/api/send-result/<int:order_test_id>", methods=["POST"])
@login_required
def whatsapp_api_send_result(order_test_id):
    """نفس whatsapp_send_result فوق بالضبط، بس يرجّع JSON بدل flash+redirect —
    يُستخدم بزر 📱 المفرد جوّه مودال 'طباعة كل النتائج المكتملة' (iframe)
    عبر fetch()، حتى ما يحتاج أي تنقّل/إعادة تحميل يكسر المودال."""
    ok, message, _visit_id = _do_whatsapp_send_result(order_test_id)
    return jsonify({"ok": ok, "message": message})


@app.route("/whatsapp/send-visit/<int:visit_id>", methods=["POST"])
@login_required
def whatsapp_send_visit(visit_id):
    """إرسال كل نتائج الزيارة عبر واتساب — mode بحقل الفورم: 'combined'
    (الافتراضي، ملف PDF واحد مجمّع) أو 'separate' (ملف PDF مستقل لكل
    تحليل). فورم كلاسيكي: flash + redirect — للاستخدام خارج أي iframe."""
    mode = request.form.get("mode", "combined")
    ok, message = _do_whatsapp_send_visit(visit_id, mode)
    flash(message if ok else f"❌ {message}")
    return redirect(url_for("visit_results_entry", visit_id=visit_id))


@app.route("/whatsapp/api/send-visit/<int:visit_id>", methods=["POST"])
@login_required
def whatsapp_api_send_visit(visit_id):
    """نفس whatsapp_send_visit فوق بالضبط، بس يرجّع JSON بدل flash+redirect —
    يُستخدم بأزرار 📱 'إرسال الكل' جوّه مودال 'طباعة كل النتائج المكتملة'
    (iframe) عبر fetch()."""
    mode = request.form.get("mode", "combined")
    ok, message = _do_whatsapp_send_visit(visit_id, mode)
    return jsonify({"ok": ok, "message": message})


@app.route("/reports/archive")
@login_required
def pdf_archive():
    """بحث سريع بأرشيف الـPDF الدائم (باسم المريض أو رقم التسجيل)، من داخل
    البرنامج مباشرة — بدل ما يفتّش المستخدم يدويًا بمجلد الأرشيف بالحاسبة."""
    db = get_db()
    q = request.args.get("q", "").strip()
    archive_dir = _get_pdf_archive_dir(db)
    rows = search_saved_reports(db, q) if archive_dir else []
    return render_template("pdf_archive.html", rows=rows, q=q, archive_configured=bool(archive_dir))


@app.route("/reports/archive/<int:visit_id>/open")
@login_required
def pdf_archive_open(visit_id):
    """يفتح/يحمّل نسخة الأرشيف الدائمة مباشرة (نفس ملف مجلد الأرشفة بالضبط،
    وليس توليدًا جديدًا) — لو الملف انمسح يدويًا من مجلد الأرشيف من خارج
    البرنامج (نقل/حذف)، نرجّع رسالة واضحة بدل خطأ سيرفر غامض."""
    db = get_db()
    row = get_saved_report(db, visit_id)
    if not row or not row["pdf_path"] or not os.path.exists(row["pdf_path"]):
        flash("الملف غير موجود بمجلد الأرشيف — يمكن انحذف أو انقل يدويًا من خارج البرنامج.")
        return redirect(url_for("pdf_archive"))
    return send_file(row["pdf_path"], as_attachment=False,
                      download_name=os.path.basename(row["pdf_path"]))


@app.route("/whatsapp/queue")
@roles_required("supervisor")
def whatsapp_queue():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM whatsapp_sends ORDER BY id DESC LIMIT 200"
    ).fetchall()
    return render_template("whatsapp_queue.html", rows=rows)


@app.route("/whatsapp/queue/<int:send_id>/retry", methods=["POST"])
@roles_required("supervisor")
def whatsapp_retry(send_id):
    db = get_db()
    row = db.execute("SELECT * FROM whatsapp_sends WHERE id=?", (send_id,)).fetchone()
    if not row:
        flash("العنصر غير موجود.")
        return redirect(url_for("whatsapp_queue"))
    opened_wa, _ = _open_whatsapp_with_pdf(
        row["phone"], row["pdf_path"], get_setting(db, "whatsapp_country_code", "964")
    )
    if opened_wa:
        db.execute(
            "UPDATE whatsapp_sends SET status='opened', sent_at=?, attempts=attempts+1, error=NULL WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), send_id),
        )
        db.commit()
        flash("📎 فتحنا واتساب ومجلد الملف من جديد — أرفقه وأرسله يدويًا.")
    else:
        db.execute(
            "UPDATE whatsapp_sends SET status='failed', error=?, attempts=attempts+1 WHERE id=?",
            ("تعذّر فتح تطبيق واتساب — تأكد إنه مثبّت على هذا الجهاز.", send_id),
        )
        db.commit()
        flash("❌ تعذّر فتح تطبيق واتساب.")
    return redirect(url_for("whatsapp_queue"))


def whatsapp_background_worker():
    """كانت هذي المهمة تحاول تفتح Chrome بالخلفية كل 3 دقائق لإعادة إرسال
    أي عنصر فاشل عبر Selenium — بدون علم المستخدم، وهذا سبب رئيسي محتمل
    لتراكم نوافذ Chrome عالقة وأقفال ملفات (بما فيها مشاكل التثبيت اللي
    واجهناها). بما إن الإرسال صار خطوة يدوية بالكامل (فتح واتساب + سحب
    الملف من المستخدم نفسه)، ما فيه داعي لإعادة محاولة تلقائية بالخلفية
    إطلاقاً — المستخدم يعيد المحاولة بنفسه من "طابور واتساب" وقت ما يريد.
    خليت الدالة موجودة بس بدون أي فعل، تفاديًا لأي خطأ لو استدعاها كود
    ثاني بالمشروع."""
    return


@app.route("/workbench/verify/<int:order_test_id>", methods=["POST"])
@roles_required("supervisor")
def verify_result(order_test_id):
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("UPDATE results SET verified_by=?, verified_at=? WHERE order_test_id=?",
               (session["user_id"], now, order_test_id))
    db.execute("UPDATE order_tests SET status='Verified' WHERE id=?", (order_test_id,))
    db.commit()
    log_action("Verify", "order_test", order_test_id)
    flash("Result verified & approved.")
    next_visit_id = request.form.get("next_visit_id")
    if next_visit_id:
        return redirect(url_for("visit_results_entry", visit_id=next_visit_id))
    return redirect(url_for("orders_list"))


@app.route("/workbench/unverify/<int:order_test_id>", methods=["POST"])
@roles_required("supervisor")
def unverify_result(order_test_id):
    # Reopens a previously verified/released result for correction. Never
    # silent: it clears verified_by/verified_at (so it visibly shows as
    # un-verified again everywhere, including on any printed report) and
    # writes an audit log entry with who reopened it and why, then sends
    # the person straight back into the edit form. Re-verification is
    # required again afterward — nothing about a corrected result skips the
    # normal approval step.
    db = get_db()
    reason = request.form.get("reason", "").strip()
    db.execute("UPDATE results SET verified_by=NULL, verified_at=NULL WHERE order_test_id=?", (order_test_id,))
    db.execute("UPDATE order_tests SET status='Completed' WHERE id=?", (order_test_id,))
    db.commit()
    log_action("Unverify", "order_test", order_test_id, reason or "(no reason given)")
    flash("Result reopened for editing — re-verification will be required after saving.")
    next_visit_id = request.form.get("next_visit_id")
    if next_visit_id:
        return redirect(url_for("visit_results_entry", visit_id=next_visit_id))
    return redirect(url_for("result_entry", order_test_id=order_test_id))



# ---------------------------------------------------------------- billing --
@app.route("/billing/rates", methods=["GET", "POST"])
@roles_required("admin", "accountant")
def rates():
    db = get_db()
    if request.method == "POST":
        if request.form.get("add_test_form") is not None:
            # فورم إضافة تحليل جديد لسريع من نفس صفحة Rates (زر إضافة/حذف
            # المطلوب هنا) -- بديل مختصر عن الذهاب لصفحة Test Catalog، يضيف
            # code/name/department/price فقط بدون باراميترات (تُضاف لاحقًا
            # من Test Catalog لو احتاج التحليل نتائج مفصّلة).
            code = request.form.get("new_code", "").strip()
            name = request.form.get("new_name", "").strip()
            department = request.form.get("new_department", "").strip()
            price = float(request.form.get("new_price") or 0)
            if not code or not name:
                flash("الكود والاسم مطلوبان لإضافة تحليل جديد.")
            else:
                try:
                    db.execute(
                        "INSERT INTO test_definitions (code, name, department, price) VALUES (?, ?, ?, ?)",
                        (code, name, department, price),
                    )
                    db.commit()
                    log_action("AddTest", "test_definitions", 0, f"{code}:{name}")
                    flash(f'تمت إضافة "{name}" لكتالوج الأسعار.')
                except Exception:
                    flash("تعذّر الإضافة -- على الأغلب هذا الكود مستخدم أصلاً لتحليل آخر.")
            return redirect(url_for("rates"))

        if request.form.get("update_department_form") is not None:
            test_id = request.form.get("test_id")
            department = request.form.get("department", "").strip()
            db.execute("UPDATE test_definitions SET department=? WHERE id=?", (department, test_id))
            db.commit()
            flash("Department updated.")
            return redirect(url_for("rates"))

        test_id = request.form.get("test_id")
        price = float(request.form.get("price") or 0)
        db.execute("UPDATE test_definitions SET price=? WHERE id=?", (price, test_id))
        db.commit()
        flash("Price updated.")
        return redirect(url_for("rates"))
    tests = db.execute("SELECT * FROM test_definitions ORDER BY department, name").fetchall()
    return render_template("billing/rates.html", tests=tests)


@app.route("/billing/rates/<int:test_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_rate_test(test_id):
    """يمسح تحليل كامل من الكتالوج (زر حذف بصفحة Rates) — بس لو ما فيه أي
    طلب سابق (order_tests) مرتبط فيه، حتى ما ننكسر تقارير/فواتير قديمة.
    لو مستخدم فعلاً بزيارة قديمة، نعطّله بدل مسحه (is_active=0) ونوضح
    السبب بدل رفض صامت."""
    db = get_db()
    test = db.execute("SELECT id, name FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not test:
        flash("هذا التحليل غير موجود أصلاً.")
        return redirect(url_for("rates"))
    used = db.execute("SELECT COUNT(*) as c FROM order_tests WHERE test_definition_id=?", (test_id,)).fetchone()["c"]
    if used:
        db.execute("UPDATE test_definitions SET is_active=0 WHERE id=?", (test_id,))
        db.commit()
        flash(f"\"{test['name']}\" مستخدم بـ{used} طلب سابق فما يُمسح نهائيًا — تم تعطيله بدل ذلك (ما يظهر بقوائم الطلب الجديدة).")
    else:
        db.execute("DELETE FROM test_parameters WHERE test_definition_id=?", (test_id,))
        db.execute("DELETE FROM reference_ranges WHERE test_parameter_id IN "
                   "(SELECT id FROM test_parameters WHERE test_definition_id=?)", (test_id,))
        db.execute("DELETE FROM test_definitions WHERE id=?", (test_id,))
        db.commit()
        flash(f"تم حذف \"{test['name']}\" نهائيًا.")
    log_action("DeleteOrDeactivateTest", "test_definitions", test_id, "")
    return redirect(url_for("rates"))


@app.route("/billing/invoices")
@login_required
def invoices_list():
    db = get_db()
    rows = db.execute(
        "SELECT i.id, i.total_amount, i.discount_amount, i.paid_amount, i.status, i.created_at, i.is_locked, "
        "p.full_name as patient_name, v.registration_number, v.id as visit_id "
        "FROM invoices i JOIN visits v ON v.id = i.visit_id JOIN patients p ON p.id = v.patient_id "
        "ORDER BY i.id DESC LIMIT 200"
    ).fetchall()
    return render_template("billing/invoices.html", rows=rows)


@app.route("/billing/invoices/<int:invoice_id>/toggle-lock", methods=["POST"])
@roles_required("admin", "accountant")
def toggle_invoice_lock(invoice_id):
    db = get_db()
    inv = db.execute("SELECT is_locked FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    new_val = 0 if inv["is_locked"] else 1
    db.execute("UPDATE invoices SET is_locked=? WHERE id=?", (new_val, invoice_id))
    db.commit()
    log_action("ToggleLock", "invoice", invoice_id, str(new_val))
    flash("Invoice locked." if new_val else "Invoice reopened.")
    return redirect(url_for("invoices_list"))


@app.route("/billing/invoices/<int:invoice_id>/discount", methods=["POST"])
@roles_required("admin", "accountant")
def apply_discount(invoice_id):
    db = get_db()
    inv = db.execute("SELECT is_locked FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if inv and inv["is_locked"]:
        flash("Invoice is locked. Reopen it first to make changes.")
        return redirect(url_for("invoices_list"))
    amount = float(request.form.get("discount_amount") or 0)
    db.execute("UPDATE invoices SET discount_amount=? WHERE id=?", (amount, invoice_id))
    db.commit()
    log_action("Discount", "invoice", invoice_id, f"amount={amount}")
    flash("Discount applied.")
    return redirect(url_for("invoices_list"))



@app.route("/billing/registers")
@login_required
def registers():
    db = get_db()
    rows = db.execute(
        "SELECT u.full_name as user, "
        "COALESCE(SUM(pay.amount),0) as payments, "
        "COALESCE((SELECT SUM(discount_amount) FROM invoices WHERE created_by=u.id),0) as discounts "
        "FROM users u LEFT JOIN payments pay ON pay.user_id = u.id "
        "GROUP BY u.id ORDER BY payments DESC"
    ).fetchall()
    return render_template("billing/registers.html", rows=rows)


@app.route("/billing/pay/<int:visit_id>", methods=["POST"])
@login_required
def pay_invoice(visit_id):
    db = get_db()
    amount = float(request.form.get("amount") or 0)
    invoice = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if invoice:
        now = datetime.now().isoformat(timespec="seconds")
        db.execute("INSERT INTO payments (invoice_id, amount, method, user_id, paid_at) "
                   "VALUES (?, ?, 'Cash', ?, ?)", (invoice["id"], amount, session["user_id"], now))
        new_paid = invoice["paid_amount"] + amount
        status = "Paid" if new_paid >= invoice["total_amount"] else "Partial"
        db.execute("UPDATE invoices SET paid_amount=?, status=? WHERE id=?",
                   (new_paid, status, invoice["id"]))
        db.commit()
        log_action("Payment", "invoice", invoice["id"], f"amount={amount}")
        flash("Payment recorded.")
    return redirect(url_for("visits_list"))


# ------------------------------------------------------- master definitions
@app.route("/master/packages", methods=["GET", "POST"])
@roles_required("supervisor")
def packages_list():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip()
        test_ids = request.form.getlist("tests")
        cur = db.execute("INSERT INTO packages (name, code) VALUES (?, ?)", (name, code))
        pkg_id = cur.lastrowid
        for tid in test_ids:
            db.execute("INSERT INTO package_tests (package_id, test_definition_id) VALUES (?, ?)", (pkg_id, tid))
        db.commit()
        flash("Package created.")
        return redirect(url_for("packages_list"))

    packages = db.execute("SELECT * FROM packages ORDER BY name").fetchall()
    pkg_tests = {}
    for pkg in packages:
        tests = db.execute(
            "SELECT td.name FROM package_tests pt JOIN test_definitions td ON td.id = pt.test_definition_id "
            "WHERE pt.package_id=?", (pkg["id"],),
        ).fetchall()
        pkg_tests[pkg["id"]] = [t["name"] for t in tests]
    all_tests = db.execute("SELECT * FROM test_definitions WHERE is_active=1 ORDER BY name").fetchall()
    return render_template("master/packages.html", packages=packages, pkg_tests=pkg_tests, all_tests=all_tests)


@app.route("/master/parameters/<int:param_id>/rename", methods=["POST"])
@roles_required("supervisor")
def rename_test_parameter(param_id):
    """يعدّل اسم الـParameter نفسه بكتالوج التحاليل (وليس فقط أي اقتراح
    مرتبط فيه) -- من نفس صفحة Suggestions (المطلوب 5/9). تنبيه: لو هذا
    الباراميتر يُستخدم داخل قالب تقرير جاهز (مثل CBC أو Retic Count) بالاسم
    القديم صراحةً (params.get('الاسم القديم') بملف الـtemplate)، تغيير
    الاسم هنا بيخلّي هذا السطر يختفي من ذاك التقرير لحد ما يتحدّث القالب
    بالاسم الجديد يدويًا -- آمن تمامًا فقط للباراميترات العامة (قسم
    Other Results) اللي ما مربوطة بقالب مخصّص."""
    db = get_db()
    new_name = (request.form.get("new_name") or "").strip()
    if not new_name:
        flash("اسم الـParameter لا يمكن أن يكون فارغًا.")
        return redirect(url_for("suggestions_list"))
    row = db.execute("SELECT id FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not row:
        flash("هذا الـParameter غير موجود.")
        return redirect(url_for("suggestions_list"))
    db.execute("UPDATE test_parameters SET name=? WHERE id=?", (new_name, param_id))
    db.commit()
    log_action("RenameParameter", "test_parameters", param_id, new_name)
    flash("تم تعديل اسم الـParameter.")
    return redirect(url_for("suggestions_list"))


@app.route("/master/tests/<int:test_definition_id>/rename", methods=["POST"])
@roles_required("supervisor")
def rename_test_definition_name(test_definition_id):
    """يعدّل اسم التحليل (Test) نفسه بكتالوج التحاليل -- من نفس صفحة
    Suggestions (المطلوب 5/9). يغيّر الاسم بكل مكان يستخدمه (شاشات الإدخال،
    الفواتير، التقارير...) لأنه نفس صف test_definitions.name المستخدم
    بكل الاستعلامات، وليس نسخة منفصلة خاصة بهذي الصفحة."""
    db = get_db()
    new_name = (request.form.get("new_name") or "").strip()
    if not new_name:
        flash("اسم التحليل لا يمكن أن يكون فارغًا.")
        return redirect(url_for("suggestions_list"))
    row = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_definition_id,)).fetchone()
    if not row:
        flash("هذا التحليل غير موجود.")
        return redirect(url_for("suggestions_list"))
    db.execute("UPDATE test_definitions SET name=? WHERE id=?", (new_name, test_definition_id))
    db.commit()
    log_action("RenameTest", "test_definitions", test_definition_id, new_name)
    flash("تم تعديل اسم التحليل.")
    return redirect(url_for("suggestions_list"))


@app.route("/master/suggestions", methods=["GET", "POST"])
@roles_required("supervisor")
def suggestions_list():
    db = get_db()
    if request.method == "POST":
        param_id = request.form.get("test_parameter_id")
        content = request.form.get("content", "").strip()
        if content:
            db.execute("INSERT INTO suggestions (test_parameter_id, content) VALUES (?, ?)", (param_id, content))
            db.commit()
            flash("Suggestion added.")
        return redirect(url_for("suggestions_list"))

    rows = db.execute(
        "SELECT s.id, s.content, s.test_parameter_id, tp.name as param_name, td.name as test_name, "
        "td.id as test_definition_id FROM suggestions s "
        "JOIN test_parameters tp ON tp.id = s.test_parameter_id "
        "JOIN test_definitions td ON td.id = tp.test_definition_id ORDER BY td.name LIMIT 200"
    ).fetchall()
    parameters = db.execute(
        "SELECT tp.id, tp.name, td.name as test_name, td.id as test_definition_id FROM test_parameters tp "
        "JOIN test_definitions td ON td.id = tp.test_definition_id ORDER BY td.name"
    ).fetchall()
    return render_template("master/suggestions.html", rows=rows, parameters=parameters)


@app.route("/master/suggestions/<int:suggestion_id>/update", methods=["POST"])
@roles_required("supervisor")
def update_suggestion(suggestion_id):
    """يعدّل اقتراح موجود — الباراميتر المرتبط فيه و/أو نصّه — من نفس
    صفحة Suggestions (زر ✏️ لكل صف)."""
    db = get_db()
    row = db.execute("SELECT id FROM suggestions WHERE id=?", (suggestion_id,)).fetchone()
    if not row:
        flash("هذا الاقتراح غير موجود.")
        return redirect(url_for("suggestions_list"))
    param_id = request.form.get("test_parameter_id")
    content = request.form.get("content", "").strip()
    if not content:
        flash("نص الاقتراح لا يمكن أن يكون فارغًا.")
        return redirect(url_for("suggestions_list"))
    db.execute(
        "UPDATE suggestions SET test_parameter_id=?, content=? WHERE id=?",
        (param_id, content, suggestion_id),
    )
    db.commit()
    flash("تم تعديل الاقتراح.")
    return redirect(url_for("suggestions_list"))


@app.route("/master/suggestions/<int:suggestion_id>/delete", methods=["POST"])
@roles_required("supervisor")
def delete_suggestion(suggestion_id):
    db = get_db()
    db.execute("DELETE FROM suggestions WHERE id=?", (suggestion_id,))
    db.commit()
    flash("تم حذف الاقتراح.")
    return redirect(url_for("suggestions_list"))



@app.route("/master/mapcodes/bulk_add_test", methods=["POST"])
@roles_required("supervisor")
def mapcodes_bulk_add_test():
    """يضيف مرة وحدة سطر Mapcode لكل عناصر تحليل معيّن دفعة وحدة (مثلاً كل
    الـ 21 عنصر بتحليل CBC) بدل ما تضيفهم واحد واحد يدوياً من القائمة.
    الكود الافتراضي المكتوب بـ machine_code هو اسم العنصر نفسه كبداية —
    لازم بعدها تراجعه وتصححه بالكود الحقيقي اللي يرسله جهازك بالذات (شوف
    صفحة Host Interface بعد أول عينة تجريبية). العناصر النصية (Text، مثل
    Comment أو Conclusion) تُستثنى لأنه الأجهزة لا ترسل نصوص حرة عادةً،
    وأي عنصر عنده Mapcode موجود مسبقاً يُتخطّى حتى ما يتكرر."""
    db = get_db()
    test_definition_id = request.form.get("test_definition_id")
    machine_name = request.form.get("bulk_machine_name", "").strip()
    params = db.execute(
        "SELECT id, name FROM test_parameters WHERE test_definition_id=? AND result_type='Numeric' ORDER BY id",
        (test_definition_id,),
    ).fetchall()
    added = 0
    skipped = 0
    for p in params:
        exists = db.execute(
            "SELECT 1 FROM mapcodes WHERE test_parameter_id=? LIMIT 1", (p["id"],)
        ).fetchone()
        if exists:
            skipped += 1
            continue
        db.execute(
            "INSERT INTO mapcodes (test_parameter_id, machine_name, machine_code, send_enabled, receive_enabled) "
            "VALUES (?, ?, ?, 1, 1)",
            (p["id"], machine_name, p["name"]),
        )
        added += 1
    db.commit()
    flash(f"تمت إضافة {added} عنصر — راجع وصحّح الأكواد بالأكواد الحقيقية من جهازك. ({skipped} كانوا موجودين مسبقاً وتُخطّوا)" if added or skipped else "هذا التحليل ما عنده عناصر رقمية.")
    return redirect(url_for("mapcodes_list"))


@app.route("/master/mapcodes", methods=["GET", "POST"])
@roles_required("supervisor")
def mapcodes_list():
    db = get_db()
    if request.method == "POST":
        param_id = request.form.get("test_parameter_id")
        machine_name = request.form.get("machine_name", "").strip()
        machine_code = request.form.get("machine_code", "").strip()
        send_enabled = 1 if request.form.get("send_enabled") else 0
        receive_enabled = 1 if request.form.get("receive_enabled") else 0
        db.execute(
            "INSERT INTO mapcodes (test_parameter_id, machine_name, machine_code, send_enabled, receive_enabled) "
            "VALUES (?, ?, ?, ?, ?)",
            (param_id, machine_name, machine_code, send_enabled, receive_enabled),
        )
        db.commit()
        flash("Mapcode added.")
        return redirect(url_for("mapcodes_list"))

    rows = db.execute(
        "SELECT m.*, tp.name as param_name, td.name as test_name FROM mapcodes m "
        "JOIN test_parameters tp ON tp.id = m.test_parameter_id "
        "JOIN test_definitions td ON td.id = tp.test_definition_id ORDER BY td.name LIMIT 200"
    ).fetchall()
    parameters = db.execute(
        "SELECT tp.id, tp.name, td.name as test_name FROM test_parameters tp "
        "JOIN test_definitions td ON td.id = tp.test_definition_id ORDER BY td.name"
    ).fetchall()
    tests = db.execute(
        "SELECT id, name FROM test_definitions ORDER BY name"
    ).fetchall()
    return render_template("master/mapcodes.html", rows=rows, parameters=parameters, tests=tests)


@app.route("/master/mapcodes/<int:mapcode_id>/edit", methods=["POST"])
@roles_required("supervisor")
def update_mapcode(mapcode_id):
    db = get_db()
    machine_name = request.form.get("machine_name", "").strip()
    machine_code = request.form.get("machine_code", "").strip()
    send_enabled = 1 if request.form.get("send_enabled") else 0
    receive_enabled = 1 if request.form.get("receive_enabled") else 0
    db.execute(
        "UPDATE mapcodes SET machine_name=?, machine_code=?, send_enabled=?, receive_enabled=? WHERE id=?",
        (machine_name, machine_code, send_enabled, receive_enabled, mapcode_id),
    )
    db.commit()
    flash(t(session.get("lang", "en"), "mapcode_updated"))
    return redirect(url_for("mapcodes_list"))


@app.route("/master/mapcodes/<int:mapcode_id>/delete", methods=["POST"])
@roles_required("supervisor")
def delete_mapcode(mapcode_id):
    db = get_db()
    db.execute("DELETE FROM mapcodes WHERE id=?", (mapcode_id,))
    db.commit()
    flash(t(session.get("lang", "en"), "mapcode_deleted"))
    return redirect(url_for("mapcodes_list"))


@app.route("/master/host-interface", methods=["GET", "POST"])
@designer_required
def host_interface():
    db = get_db()
    if request.method == "POST":
        enabled = "1" if request.form.get("enabled") else "0"
        ip = request.form.get("ip", "0.0.0.0").strip() or "0.0.0.0"
        port = request.form.get("port", "5000").strip() or "5000"
        set_setting(db, "host_listener_enabled", enabled)
        set_setting(db, "host_listener_ip", ip)
        set_setting(db, "host_listener_port", port)
        db.commit()
        flash(t(session.get("lang", "en"), "host_settings_saved"))
        return redirect(url_for("host_interface"))

    enabled = get_setting(db, "host_listener_enabled", "0") == "1"
    ip = get_setting(db, "host_listener_ip", "0.0.0.0")
    port = get_setting(db, "host_listener_port", "5000")
    logs = db.execute(
        "SELECT * FROM host_interface_log ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return render_template("master/host_interface.html", enabled=enabled, ip=ip, port=port, logs=logs)


@app.route("/master/host-interface/clear-log", methods=["POST"])
@designer_required
def clear_host_interface_log():
    db = get_db()
    db.execute("DELETE FROM host_interface_log")
    db.commit()
    return redirect(url_for("host_interface"))


@app.route("/master/quick-add-items", methods=["GET", "POST"])
@roles_required("supervisor")
def quick_add_items():
    db = get_db()
    if request.method == "POST":
        test_id = request.form.get("test_definition_id")
        exists = db.execute("SELECT id FROM quick_add_items WHERE test_definition_id=?", (test_id,)).fetchone()
        if not exists:
            db.execute("INSERT INTO quick_add_items (test_definition_id) VALUES (?)", (test_id,))
            db.commit()
            flash("Added to Quick Add.")
        return redirect(url_for("quick_add_items"))

    rows = db.execute(
        "SELECT q.id, td.name as test_name, td.department FROM quick_add_items q "
        "JOIN test_definitions td ON td.id = q.test_definition_id WHERE q.is_active=1 ORDER BY q.display_order"
    ).fetchall()
    all_tests = db.execute("SELECT * FROM test_definitions WHERE is_active=1 ORDER BY name").fetchall()
    return render_template("master/quick_add_items.html", rows=rows, all_tests=all_tests)


@app.route("/master/quick-add-items/<int:item_id>/remove", methods=["POST"])
@roles_required("supervisor")
def quick_add_item_remove(item_id):
    db = get_db()
    db.execute("UPDATE quick_add_items SET is_active=0 WHERE id=?", (item_id,))
    db.commit()
    flash("Removed from Quick Add.")
    return redirect(url_for("quick_add_items"))



@app.route("/master/reference-ranges", methods=["GET", "POST"])
@roles_required("supervisor")
def reference_ranges():
    db = get_db()
    if request.method == "POST":
        param_id = request.form.get("test_parameter_id")
        gender = request.form.get("gender") or "Both"
        age_from = request.form.get("age_from") or 0
        age_from_unit = request.form.get("age_from_unit") or "Years"
        age_to = request.form.get("age_to") or 120
        age_to_unit = request.form.get("age_to_unit") or "Years"
        low = request.form.get("low") or None
        high = request.form.get("high") or None
        range_text = request.form.get("range_text") or None
        # scope_type="patient" (المطلوب 5): patient_id يقفل هذي النسبة على
        # مريض واحد بالذات (حالة خاصة/علاج) — تتفوّق تلقائيًا على أي نسبة
        # عامة لنفس الباراميتر (راجع find_reference_range بـdatabase.py).
        # range_label اختياري، عرض فقط (مثلاً "مرضى الكورتيزون").
        scope_type = request.form.get("scope_type") or "all"
        patient_id = request.form.get("patient_id") or None if scope_type == "patient" else None
        range_label = request.form.get("range_label") or None
        # analyzer (المطلوب 6): اسم جهاز حر — فاضي يعني نسبة عامة بغض النظر
        # عن الجهاز.
        analyzer = request.form.get("analyzer") or None
        db.execute(
            "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit, "
            "low, high, range_text, patient_id, range_label, analyzer) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (param_id, gender, age_from, age_from_unit, age_to, age_to_unit, low, high, range_text,
             patient_id, range_label, analyzer),
        )
        db.commit()
        flash("Reference range added.")
        return redirect(url_for("reference_ranges"))

    ranges = db.execute(
        "SELECT rr.*, tp.name as param_name, td.name as test_name, p.full_name as patient_name "
        "FROM reference_ranges rr "
        "JOIN test_parameters tp ON tp.id = rr.test_parameter_id "
        "JOIN test_definitions td ON td.id = tp.test_definition_id "
        "LEFT JOIN patients p ON p.id = rr.patient_id "
        "ORDER BY td.name LIMIT 200"
    ).fetchall()
    parameters = db.execute(
        "SELECT tp.id, tp.name, tp.highlight, tp.unit, tp.unit2, tp.unit2_factor, td.name as test_name "
        "FROM test_parameters tp "
        "JOIN test_definitions td ON td.id = tp.test_definition_id ORDER BY td.name"
    ).fetchall()
    # تجميع الصفوف حسب الباراميتر — كل باراميتر يطلع كارد لحاله، وكل تيير
    # (حالة/طور فسيولوجي) داخل range_text يطلع صف عرض مستقل قابل للتحرير
    # لحاله عبر tier-save، بدل جدول مسطّح وحدة لكل الفحوصات مع بعض.
    param_meta = {p["id"]: p for p in parameters}
    groups_by_param = {}
    order = []
    for r in ranges:
        pid = r["test_parameter_id"]
        if pid not in groups_by_param:
            meta = param_meta.get(pid)
            groups_by_param[pid] = {
                "id": pid, "name": r["param_name"], "test_name": r["test_name"],
                "unit": meta["unit"] if meta else "", "highlight": meta["highlight"] if meta else 0,
                "unit2": meta["unit2"] if meta else "", "unit2_factor": meta["unit2_factor"] if meta else "",
                "rows": [],
            }
            order.append(pid)
        for tier in reference_range_tiers(r):
            groups_by_param[pid]["rows"].append({
                "range_id": r["id"], "gender": r["gender"],
                "age_from": r["age_from"], "age_from_unit": r["age_from_unit"],
                "age_to": r["age_to"], "age_to_unit": r["age_to_unit"],
                "label": tier["label"], "low": tier["low"], "high": tier["high"], "raw": tier["raw"],
                "patient_id": r["patient_id"], "patient_name": r["patient_name"],
                "range_label": r["range_label"], "analyzer": r["analyzer"],
            })
    parameter_groups = [groups_by_param[pid] for pid in order]
    all_test_definitions = db.execute(
        "SELECT id, name, department FROM test_definitions WHERE is_active=1 ORDER BY name"
    ).fetchall()
    return render_template("master/reference_ranges.html", parameter_groups=parameter_groups,
                            parameters=parameters, known_analyzers=get_known_analyzers(db),
                            known_units=get_known_units(db), all_test_definitions=all_test_definitions)


@app.route("/master/reference-ranges/tier-save", methods=["POST"])
@roles_required("supervisor")
def save_reference_range_tier():
    """يحفظ حالة/طور واحد (تيير) من كارد باراميتر بصفحة Reference Ranges —
    إمّا يعدّل تيير موجود (original_label يحدّد أيّه)، يضيف تيير جديد لصف
    جنس/فئة عمرية موجود أصلاً بدل ما يسوي صف مكرر، أو يسوي صف جديد كليًا لو
    ما فيه صف مطابق أصلاً."""
    db = get_db()
    range_id = request.form.get("range_id") or None
    test_parameter_id = request.form.get("test_parameter_id")
    original_label = request.form.get("original_label") or ""
    gender = request.form.get("gender") or "Both"
    age_from = request.form.get("age_from") or 0
    age_from_unit = request.form.get("age_from_unit") or "Years"
    age_to = request.form.get("age_to") or 120
    age_to_unit = request.form.get("age_to_unit") or "Years"
    label = (request.form.get("label") or "").strip() or None
    low_raw = request.form.get("low")
    high_raw = request.form.get("high")
    low = float(low_raw) if low_raw not in (None, "") else None
    high = float(high_raw) if high_raw not in (None, "") else None
    raw_text = (request.form.get("raw_text") or "").strip() or None
    if raw_text:
        low = high = None
    scope_type = request.form.get("scope_type") or "all"
    patient_id = (request.form.get("patient_id") or None) if scope_type == "patient" else None
    range_label = request.form.get("range_label") or None
    analyzer = request.form.get("analyzer") or None

    row = db.execute("SELECT * FROM reference_ranges WHERE id=?", (range_id,)).fetchone() if range_id else None
    if not row:
        row = db.execute(
            "SELECT * FROM reference_ranges WHERE test_parameter_id=? AND gender=? AND age_from=? "
            "AND age_from_unit=? AND age_to=? AND age_to_unit=? AND patient_id IS ?",
            (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit, patient_id),
        ).fetchone()

    tiers = reference_range_tiers(row) if row else []
    new_tier = {"label": label, "low": low, "high": high, "raw": raw_text}
    for i, tier in enumerate(tiers):
        if (tier["label"] or "") == original_label:
            tiers[i] = new_tier
            break
    else:
        tiers.append(new_tier)

    range_text, base_low, base_high = serialize_range_tiers(tiers)

    if row:
        db.execute(
            "UPDATE reference_ranges SET gender=?, age_from=?, age_from_unit=?, age_to=?, age_to_unit=?, "
            "low=?, high=?, range_text=?, patient_id=?, range_label=?, analyzer=? WHERE id=?",
            (gender, age_from, age_from_unit, age_to, age_to_unit, base_low, base_high, range_text,
             patient_id, range_label, analyzer, row["id"]),
        )
    else:
        db.execute(
            "INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit, "
            "low, high, range_text, patient_id, range_label, analyzer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit, base_low, base_high,
             range_text, patient_id, range_label, analyzer),
        )
    db.commit()
    flash("تم حفظ النسبة الطبيعية.")
    return redirect(url_for("reference_ranges"))


@app.route("/master/reference-ranges/tier-delete", methods=["POST"])
@roles_required("supervisor")
def delete_reference_range_tier():
    """يحذف حالة/طور واحد بس من صف — لو كان آخر تيير بالصف، يحذف الصف كله
    (نفس /master/reference-ranges/<id>/delete القديم) بدل ما يخلّي صف فاضي."""
    db = get_db()
    range_id = request.form.get("range_id")
    label = request.form.get("label") or ""
    row = db.execute("SELECT * FROM reference_ranges WHERE id=?", (range_id,)).fetchone()
    if row:
        remaining = [t for t in reference_range_tiers(row) if (t["label"] or "") != label]
        if not remaining:
            db.execute("DELETE FROM reference_ranges WHERE id=?", (range_id,))
        else:
            range_text, base_low, base_high = serialize_range_tiers(remaining)
            db.execute("UPDATE reference_ranges SET low=?, high=?, range_text=? WHERE id=?",
                       (base_low, base_high, range_text, range_id))
        db.commit()
    flash("تم الحذف.")
    return redirect(url_for("reference_ranges"))


@app.route("/master/reference-ranges/<int:range_id>/edit", methods=["POST"])
@roles_required("supervisor")
def update_reference_range(range_id):
    db = get_db()
    gender = request.form.get("gender") or "Both"
    age_from = request.form.get("age_from") or 0
    age_from_unit = request.form.get("age_from_unit") or "Years"
    age_to = request.form.get("age_to") or 120
    age_to_unit = request.form.get("age_to_unit") or "Years"
    low = request.form.get("low") or None
    high = request.form.get("high") or None
    range_text = request.form.get("range_text") or None
    scope_type = request.form.get("scope_type") or "all"
    patient_id = request.form.get("patient_id") or None if scope_type == "patient" else None
    range_label = request.form.get("range_label") or None
    analyzer = request.form.get("analyzer") or None
    db.execute(
        "UPDATE reference_ranges SET gender=?, age_from=?, age_from_unit=?, age_to=?, age_to_unit=?, low=?, high=?, "
        "range_text=?, patient_id=?, range_label=?, analyzer=? WHERE id=?",
        (gender, age_from, age_from_unit, age_to, age_to_unit, low, high, range_text,
         patient_id, range_label, analyzer, range_id),
    )
    db.commit()
    flash(t(session.get("lang", "en"), "range_updated"))
    return redirect(url_for("reference_ranges"))


@app.route("/master/reference-ranges/<int:range_id>/delete", methods=["POST"])
@roles_required("supervisor")
def delete_reference_range(range_id):
    db = get_db()
    db.execute("DELETE FROM reference_ranges WHERE id=?", (range_id,))
    db.commit()
    flash(t(session.get("lang", "en"), "range_deleted"))
    return redirect(url_for("reference_ranges"))


@app.route("/master/test-catalog/<int:test_id>/rename", methods=["POST"])
@roles_required("supervisor")
def rename_test_definition(test_id):
    """يعيد تسمية تحليل موجود — يُستخدم بالقلم ✏️ الجديد جنب كل تحليل
    بشاشة "زيارة جديدة" (تعديل سريع من نفس الصفحة، بدون فتح كتالوج
    التحاليل). لا يغيّر أي بارامتر تابع لهذا التحليل، فقط اسم التحليل
    نفسه (test_definitions.name)."""
    db = get_db()
    body = request.get_json(silent=True) or request.form
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return {"ok": False, "error": "الاسم لا يمكن أن يكون فارغًا"}, 400
    row = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "التحليل غير موجود"}, 404
    db.execute("UPDATE test_definitions SET name=? WHERE id=?", (new_name, test_id))
    db.commit()
    log_action("RenameTest", "test_definitions", test_id, new_name)
    return {"ok": True, "name": new_name}


@app.route("/master/test-catalog/<int:test_id>/price", methods=["POST"])
@roles_required("supervisor")
def update_test_price(test_id):
    db = get_db()
    try:
        price = float(request.form.get("price") or request.json.get("price"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid price"}, 400
    db.execute("UPDATE test_definitions SET price=? WHERE id=?", (price, test_id))
    db.commit()
    return {"ok": True, "price": price}


@app.route("/master/test-catalog/<int:test_id>/toggle-examining", methods=["POST"])
@roles_required("supervisor")
def toggle_examining_test(test_id):
    db = get_db()
    row = db.execute("SELECT is_examining_test FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not row:
        return {"ok": False}, 404
    new_val = 0 if row["is_examining_test"] else 1
    db.execute("UPDATE test_definitions SET is_examining_test=? WHERE id=?", (new_val, test_id))
    db.commit()
    return {"ok": True, "is_examining_test": new_val}


# اسم "الريبورت المجمّع" (report_group) اللي يظهر عنوانًا فرعيًا للوحة
# الطباعة المجمّعة (print_combined_panel) — فاضي يرجّع التحليل يعتمد على
# اسم القسم (department) العام كالمعتاد بدل عنوان مخصص.
@app.route("/master/test-catalog/<int:test_id>/report-group", methods=["POST"])
@roles_required("supervisor")
def update_test_report_group(test_id):
    db = get_db()
    value = (request.form.get("report_group") or "").strip()
    row = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not row:
        return {"ok": False}, 404
    db.execute("UPDATE test_definitions SET report_group=? WHERE id=?", (value, test_id))
    db.commit()
    return {"ok": True, "report_group": value}


@app.route("/master/test-catalog/<int:test_id>/field", methods=["POST"])
@roles_required("supervisor")
def update_test_field(test_id):
    """تعديل مباشر لعمود code/name/department/sample_type من نفس صفحة
    كتالوج التحاليل — قائمة بيضاء صارمة بالأعمدة المسموحة (allowed_fields)
    حتى ما يقدر أي طلب يعدّل عمود ثاني غير مقصود بهذا المسار."""
    db = get_db()
    field = (request.form.get("field") or "").strip()
    value = (request.form.get("value") or "").strip()
    allowed_fields = {"code", "name", "department", "sample_type"}
    if field not in allowed_fields:
        return {"ok": False, "error": "حقل غير مسموح بتعديله من هنا"}, 400
    row = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "التحليل غير موجود"}, 404
    if field in ("code", "name") and not value:
        return {"ok": False, "error": "هذا الحقل لا يمكن أن يكون فارغًا"}, 400
    try:
        db.execute(f"UPDATE test_definitions SET {field}=? WHERE id=?", (value, test_id))
        db.commit()
    except Exception as e:
        # الأرجح تعارض قيد UNIQUE على code (كود مستخدم أصلاً لتحليل آخر).
        return {"ok": False, "error": "تعذّر الحفظ — على الأغلب هذا الكود مستخدم أصلاً لتحليل آخر"}, 400
    log_action("UpdateTestField", "test_definitions", test_id, f"{field}={value}")
    return {"ok": True, "field": field, "value": value}


@app.route("/master/test-parameters/<int:param_id>/toggle-highlight", methods=["POST"])
@roles_required("supervisor")
def toggle_parameter_highlight(param_id):
    # Yellow-shading a result on the printed report is a manual, per-parameter
    # choice the admin makes here — nothing is highlighted automatically.
    db = get_db()
    row = db.execute("SELECT highlight FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not row:
        return {"ok": False}, 404
    new_val = 0 if row["highlight"] else 1
    db.execute("UPDATE test_parameters SET highlight=? WHERE id=?", (new_val, param_id))
    db.commit()
    return {"ok": True, "highlight": new_val}


# ------------------------------------------------------------------------
# أداة "تعديل وحدة القياس" — تسمح للمشرف/الأدمن يغيّر وحدة أي معيار
# (test_parameter) مباشرة (مثل NRBC، أو أي معيار يحتاج تغيير وحدته لاحقًا)
# دون لمس قاعدة البيانات يدويًا. لو التغيير يمثّل تحويل قياس فعلي (مو مجرد
# إعادة تسمية)، تقدر تعطيها معامل تحويل (factor) واتجاه (ضرب/قسمة) فتتحول
# كل المدايات المرجعية (reference_ranges) المرتبطة بهذا المعيار تلقائيًا
# بنفس المعامل والاتجاه، حتى تبقى متوافقة مع الوحدة الجديدة. لإعادة تسمية
# بدون أي تغيير بالأرقام (مثل NRBC من "100/wbc" إلى "/100WBC")، اترك
# المعامل = 1.
# ------------------------------------------------------------------------
@app.route("/master/unit-converter", methods=["GET"])
@roles_required("supervisor")
def unit_converter():
    db = get_db()
    # شيلنا فلتر "result_type = 'Numeric'" — أي باراميتر بأي تحليل يظهر
    # هنا الحين، مو بس الرقمية، حتى تقدر تعدّل وحدة أي شي بالبرنامج من
    # نفس هذي الصفحة.
    parameters = db.execute(
        "SELECT tp.id, tp.name, tp.unit, tp.unit2, tp.unit2_factor, td.name as test_name, td.department "
        "FROM test_parameters tp JOIN test_definitions td ON td.id = tp.test_definition_id "
        "ORDER BY td.department, td.name, tp.name"
    ).fetchall()
    return render_template("master/unit_converter.html", parameters=parameters)


# ------------------------------------------------------------------------
# تعديل مباشر وبسيط للوحدة — تكتب النص وتضغط حفظ وخلاص، بدون أي معامل
# تحويل أو اتجاه (بعكس "تغيير/تحويل الوحدة الأساسية" تحت، اللي مصمم
# لعملية تحويل رقمية فعلية تلمس المديات المرجعية معها). هذا الخيار
# للحالة الشائعة: بس تبي تغيّر/تصلّح نص الوحدة نفسه (مثال: NRBC من
# "100/wbc" إلى "/100wbc") بدون لمس أي رقم ثاني إطلاقاً.
# ------------------------------------------------------------------------
@app.route("/master/unit-converter/<int:param_id>/set-unit", methods=["POST"])
@roles_required("supervisor")
def unit_converter_set_unit(param_id):
    db = get_db()
    param = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not param:
        if request.form.get("ajax"):
            return {"ok": False, "error": "المعيار غير موجود."}, 404
        flash("المعيار غير موجود.")
        return redirect(url_for("unit_converter"))
    new_unit = request.form.get("unit", "").strip()
    db.execute("UPDATE test_parameters SET unit=? WHERE id=?", (new_unit, param_id))
    db.commit()
    # ajax=1: يُرسَل فقط من محرّر الوحدة المصغّر بصفحة النسب الطبيعية
    # (reference_ranges.html) — يرجّع JSON بدل صفحة كاملة، بدون أي تأثير
    # على استخدام صفحة "تعديل الوحدات" الأصلية (نموذج عادي، بلا ajax=1).
    if request.form.get("ajax"):
        return {"ok": True, "unit": new_unit}
    flash(f"تم تحديث وحدة {param['name']} إلى \"{new_unit}\"." if new_unit else f"تم إفراغ وحدة {param['name']}.")
    return redirect(url_for("unit_converter"))


# ------------------------------------------------------------------------
# الوحدة الثانية الدائمة لعرض النتيجة بوحدتين بنفس الوقت وقت الطباعة
# (مثلاً mg/dL و mmol/L لنفس الباراميتر) — بخلاف "تحويل الوحدة" أعلاه اللي
# يغيّر الوحدة الأساسية مرة وحدة ويحوّل المديات المرجعية معها، هذا الإعداد
# دائم ولا يلمس الوحدة الأساسية ولا المديات المرجعية إطلاقًا: فقط يضيف قيمة
# محسوبة تلقائيًا (value2 = value1 × factor) تُطبع جنب النتيجة الأصلية.
# اترك حقل "الوحدة الثانية" فاضي لإلغاء/تعطيل الوحدة الثانية لهذا الباراميتر.
# ------------------------------------------------------------------------
@app.route("/master/unit-converter/<int:param_id>/set-dual-unit", methods=["POST"])
@roles_required("supervisor")
def unit_converter_set_dual(param_id):
    db = get_db()
    param = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    is_ajax = bool(request.form.get("ajax"))
    if not param:
        if is_ajax:
            return {"ok": False, "error": "المعيار غير موجود."}, 404
        flash("المعيار غير موجود.")
        return redirect(url_for("unit_converter"))

    unit2 = (request.form.get("unit2") or "").strip()
    if not unit2:
        db.execute("UPDATE test_parameters SET unit2=NULL, unit2_factor=NULL WHERE id=?", (param_id,))
        db.commit()
        log_action("SetDualUnit", "test_parameter", param_id, "cleared")
        if is_ajax:
            return {"ok": True, "unit2": None, "unit2_factor": None}
        flash(f"تم إلغاء الوحدة الثانية لـ \"{param['name']}\".")
        return redirect(url_for("unit_converter"))

    factor_raw = (request.form.get("unit2_factor") or "").strip()
    try:
        factor = float(factor_raw)
        if factor <= 0:
            raise ValueError
    except ValueError:
        if is_ajax:
            return {"ok": False, "error": "معامل التحويل يجب أن يكون رقمًا أكبر من صفر."}, 400
        flash("معامل التحويل للوحدة الثانية يجب أن يكون رقمًا أكبر من صفر.")
        return redirect(url_for("unit_converter"))

    db.execute("UPDATE test_parameters SET unit2=?, unit2_factor=? WHERE id=?", (unit2, factor, param_id))
    db.commit()
    log_action("SetDualUnit", "test_parameter", param_id, f"{param['unit']} -> {unit2} (x{factor})")
    if is_ajax:
        return {"ok": True, "unit2": unit2, "unit2_factor": factor}
    flash(f"تم حفظ الوحدة الثانية لـ \"{param['name']}\": {unit2} (يُحسب تلقائيًا = القيمة × {factor}).")
    return redirect(url_for("unit_converter"))


@app.route("/master/unit-converter/<int:param_id>/apply", methods=["POST"])
@roles_required("supervisor")
def unit_converter_apply(param_id):
    db = get_db()
    param = db.execute("SELECT * FROM test_parameters WHERE id=?", (param_id,)).fetchone()
    if not param:
        flash("المعيار غير موجود.")
        return redirect(url_for("unit_converter"))

    new_unit = (request.form.get("new_unit") or "").strip()
    direction = request.form.get("direction", "multiply")
    try:
        factor = float(request.form.get("factor") or 1)
    except ValueError:
        factor = 1.0
    if factor <= 0:
        flash("معامل التحويل يجب أن يكون رقمًا أكبر من صفر.")
        return redirect(url_for("unit_converter"))

    old_unit = param["unit"]
    ranges = db.execute("SELECT id, low, high FROM reference_ranges WHERE test_parameter_id=?", (param_id,)).fetchall()
    for r in ranges:
        new_low = r["low"]
        new_high = r["high"]
        if direction == "divide":
            if new_low is not None:
                new_low = new_low / factor
            if new_high is not None:
                new_high = new_high / factor
        else:
            if new_low is not None:
                new_low = new_low * factor
            if new_high is not None:
                new_high = new_high * factor
        db.execute("UPDATE reference_ranges SET low=?, high=? WHERE id=?", (new_low, new_high, r["id"]))

    if new_unit:
        db.execute("UPDATE test_parameters SET unit=? WHERE id=?", (new_unit, param_id))

    db.commit()
    log_action(
        "UnitConvert", "test_parameter", param_id,
        f"{old_unit!r} -> {new_unit!r} ({direction} x{factor}, {len(ranges)} ranges updated)",
    )
    flash(f"تم تحديث وحدة \"{param['name']}\" وتحويل {len(ranges)} مدى مرجعي.")
    return redirect(url_for("unit_converter"))



# تصنيف تلقائي لحقل "الريبورت المجمّع" (report_group) — يطابق اسم كل
# تحليل مع كلمات مفتاحية شائعة تحدد أي من المجاميع الثابتة الخمس ينتمي
# لها، حتى تصير كل تحاليل "سكر/دهون/سكر تراكمي/وظائف كلى/وظائف كبد/
# كالسيوم/مغنيسيوم/إلكترولايت" تحت "Biochemistry Tests" مجتمعة، وهكذا
# لبقية المجاميع — بدل ما الأدمن يدخل كل تحليل لحاله يدويًا. لا تلمس أي
# تحليل مصنّف يدويًا من قبل (report_group غير فاضي) إطلاقًا، حتى لا تلغي
# أي تخصيص سابق.
FIXED_REPORT_GROUPS = [
    "Biochemistry Tests", "Hormones Tests", "Vitamins Tests",
    "Virology Screening", "Tumor Marker",
]

_REPORT_GROUP_KEYWORDS = [
    ("Tumor Marker", [
        "cea", "afp", "psa", "ca125", "ca 125", "ca19-9", "ca 19-9", "ca15-3",
        "ca 15-3", "beta-hcg", "b-hcg", "tumor marker", "tumour marker",
    ]),
    ("Virology Screening", [
        "hbsag", "hbsab", "anti-hbs", "anti-hcv", "hcv", "hiv", "hbcab",
        "rubella", "toxoplasma", "cmv", "ebv", "vdrl", "tpha", "hepatitis",
        "measles", "mumps", "varicella", "widal", "brucella",
    ]),
    ("Vitamins Tests", ["vitamin", "folate", "folic acid", "b12"]),
    ("Hormones Tests", [
        "tsh", " t3", " t4", "ft3", "ft4", "fsh", " lh", "prolactin",
        "cortisol", "testosterone", "estrogen", "estradiol", "progesterone",
        "insulin", "pth", "parathyroid", "growth hormone", " gh ", "acth", "dhea",
    ]),
    ("Biochemistry Tests", [
        "fbs", "glucose", "sugar", "rbs", "hba1c", "glycated", "lipid",
        "cholesterol", "triglyceride", "hdl", "ldl", "vldl", "urea",
        "creatinine", "uric acid", "bun", "kidney", "renal", " alt", " ast",
        " alp", "sgot", "sgpt", "bilirubin", "albumin", "total protein",
        "liver", "ggt", "calcium", "magnesium", "phosphorus", "phosphate",
        "sodium", "potassium", "chloride", "electrolyte", "amylase",
        "lipase", "ferritin", "tibc", "crp", "esr", "ldh",
    ]),
]


def _guess_report_group(test_name):
    name = f" {(test_name or '').strip().lower()} "
    for group, keywords in _REPORT_GROUP_KEYWORDS:
        for kw in keywords:
            if kw in name:
                return group
    return None


@app.route("/master/test-catalog/auto-assign-report-groups", methods=["POST"])
@roles_required("supervisor")
def auto_assign_report_groups():
    """يعبّي report_group تلقائيًا لكل تحليل ماله تصنيف بعد (لا يلمس أي
    تحليل مصنّف يدويًا من قبل) بمطابقة اسمه مع الكلمات المفتاحية فوق.
    يرجّع JSON بعدد التحاليل المصنَّفة، وأسماء أي تحاليل ما انطابقت مع أي
    كلمة (تحتاج تصنيف يدوي من الأدمن)."""
    db = get_db()
    tests = db.execute(
        "SELECT id, name FROM test_definitions WHERE report_group IS NULL OR TRIM(report_group)=''"
    ).fetchall()
    updated = 0
    unmatched = []
    for t in tests:
        group = _guess_report_group(t["name"])
        if group:
            db.execute("UPDATE test_definitions SET report_group=? WHERE id=?", (group, t["id"]))
            updated += 1
        else:
            unmatched.append(t["name"])
    db.commit()
    return jsonify({"ok": True, "updated": updated, "unmatched": unmatched})


@app.route("/master/test-catalog", methods=["GET", "POST"])
@roles_required("supervisor")
def test_catalog():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        department = request.form.get("department", "").strip()
        report_group = request.form.get("report_group", "").strip()
        sample_type = request.form.get("sample_type", "").strip()
        price = float(request.form.get("price") or 0)
        is_examining_test = 1 if request.form.get("is_examining_test") else 0
        params_raw = request.form.get("parameters", "").strip()

        cur = db.execute(
            "INSERT INTO test_definitions (code, name, department, report_group, sample_type, price, is_examining_test) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, department, report_group, sample_type, price, is_examining_test),
        )
        test_id = cur.lastrowid
        for chunk in params_raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "unit:" in chunk:
                pname, unit = chunk.split("unit:")
                pname, unit = pname.strip(), unit.strip()
            else:
                pname, unit = chunk, ""
            db.execute(
                "INSERT INTO test_parameters (test_definition_id, name, unit, result_type) "
                "VALUES (?, ?, ?, 'Numeric')",
                (test_id, pname, unit),
            )
        db.commit()
        flash("Test added to catalog.")
        return redirect(url_for("test_catalog"))

    tests = db.execute("SELECT * FROM test_definitions ORDER BY department, name").fetchall()
    # أسماء "الريبورت المجمّع" المستخدمة أصلاً بأي تحليل — تُعرض كاقتراحات
    # بحقل الإدخال (datalist) حتى يعيد الأدمن استخدام نفس الاسم بالضبط بدل
    # ما يكتبه بصيغة مختلفة شوي فينفصل عن مجموعته بالخطأ (مثلاً "Viral
    # study" مرة و"Viral Study" مرة ثانية تصيران مجموعتين منفصلتين).
    report_groups = sorted(set(FIXED_REPORT_GROUPS) | {
        row["report_group"].strip() for row in tests if row["report_group"] and row["report_group"].strip()
    })
    return render_template("master/test_catalog.html", tests=tests, report_groups=report_groups)


# ------------------------------------------------------------ parameter order
# ترتيب باراميترات أي تحليل (بشاشة إدخال النتائج وبالتقرير المطبوع) —
# صفحة مستقلة عامة لأي تحليل (مو خاصة بس بتحاليل الـdifferential)، لأن
# ترتيب الباراميترات بقاعدة البيانات بيّن (test_parameters.sort_order)
# وما كان فيه شاشة تتحكم فيه سابقًا — كانت تعتمد على ترتيب id (الإدخال).
@app.route("/master/parameter-order", methods=["GET", "POST"])
@roles_required("supervisor")
def parameter_order():
    db = get_db()
    if request.method == "POST":
        test_id = request.form.get("test_id")
        param_ids = request.form.getlist("param_id")
        orders = request.form.getlist("order")
        for pid, order in zip(param_ids, orders):
            try:
                order_val = int(order)
            except (TypeError, ValueError):
                order_val = 0
            db.execute("UPDATE test_parameters SET sort_order=? WHERE id=?", (order_val, pid))
        db.commit()
        flash("تم حفظ ترتيب الباراميترات.")
        return redirect(url_for("parameter_order", test_id=test_id))

    tests = db.execute(
        "SELECT DISTINCT td.id, td.name, td.code FROM test_definitions td "
        "JOIN test_parameters tp ON tp.test_definition_id = td.id "
        "ORDER BY td.name"
    ).fetchall()

    selected_id = request.args.get("test_id", type=int)
    if not selected_id and tests:
        selected_id = tests[0]["id"]

    parameters = []
    if selected_id:
        parameters = db.execute(
            "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id",
            (selected_id,),
        ).fetchall()

    return render_template("master/parameter_order.html", tests=tests, parameters=parameters, selected_id=selected_id)


def unique_test_code(db, name):
    """يولّد رمزًا فريدًا للتحليل من اسمه الإنكليزي عند الإضافة السريعة من
    قسم الطلبات (بدون الحاجة لإدخال رمز يدويًا)."""
    base = re.sub(r"[^A-Za-z0-9]+", "", name).upper()[:12] or "TEST"
    code = base
    n = 1
    while db.execute("SELECT 1 FROM test_definitions WHERE code=?", (code,)).fetchone():
        n += 1
        code = f"{base}{n}"
    return code


# إضافة/تعديل/إخفاء تحليل بسرعة من داخل نفس نافذة "قسم الطلبات" بشاشتي
# "زيارة جديدة" و"تعديل الزيارة" — دون مغادرة الصفحة أو فقدان بيانات الزيارة
# التي بدأ المستخدم بتعبئتها (لهذا الاستجابة JSON وليس إعادة توجيه صفحة).
@app.route("/api/tests/quick-add", methods=["POST"])
@roles_required("supervisor")
def api_quick_add_test():
    db = get_db()
    name = (request.form.get("name") or "").strip()
    department = (request.form.get("department") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    code = unique_test_code(db, name)
    cur = db.execute(
        "INSERT INTO test_definitions (code, name, department, sample_type, price, is_active, is_examining_test) "
        "VALUES (?, ?, ?, '', 0, 1, 0)",
        (code, name, department),
    )
    db.commit()
    log_action("QuickAddTest", "test_definition", cur.lastrowid, name)
    return jsonify({"id": cur.lastrowid, "name": name, "department": department, "code": code})

@app.route("/api/tests/quick-add-with-price", methods=["POST"])
@login_required
def api_quick_add_test_with_price():
    """يسمح لأي مستخدم مسجّل دخول (مو بس admin/supervisor) بإضافة تحليل غير
    موجود بالقائمة مباشرة أثناء إنشاء زيارة جديدة، مع تحديد سعره فورًا —
    يبقى هذا التحليل محفوظًا بالكتالوج بشكل دائم لأي زيارة قادمة. لو التحليل
    موجود مسبقًا بنفس الاسم، نرجع بياناته الحالية بدل ما ننشئ نسخة مكررة."""
    db = get_db()
    name = (request.form.get("name") or "").strip()
    try:
        price = float(request.form.get("price") or 0)
    except ValueError:
        price = 0
    if not name:
        return jsonify({"error": "اسم التحليل مطلوب"}), 400
    if price < 0:
        return jsonify({"error": "السعر يجب أن يكون رقمًا موجبًا"}), 400
    existing = db.execute(
        "SELECT id, price FROM test_definitions WHERE LOWER(TRIM(name))=LOWER(TRIM(?))", (name,)
    ).fetchone()
    if existing:
        return jsonify({"id": existing["id"], "name": name, "price": existing["price"], "existed": True})
    code = unique_test_code(db, name)
    cur = db.execute(
        "INSERT INTO test_definitions (code, name, department, sample_type, price, is_active, is_examining_test) "
        "VALUES (?, ?, '', '', ?, 1, 0)",
        (code, name, price),
    )
    db.commit()
    log_action("QuickAddTestWithPrice", "test_definition", cur.lastrowid, f"{name} ({price})")
    return jsonify({"id": cur.lastrowid, "name": name, "price": price, "existed": False})

# إضافة تحليل غير موجود بالقائمة مباشرة من قسم "الطلبات" بشاشة "زيارة
# جديدة" — متاحة لأي مستخدم مسجّل دخول (وليس فقط admin/supervisor مثل
# نافذة "إدارة التحاليل" وراوت /api/tests/quick-add أعلاه)، لأن موظف
# الاستقبال هو من يواجه هذا الموقف يوميًا (مريض طلب تحليل غير مُدرج بعد).
# يُطلب السعر إجباريًا هنا (بعكس /api/tests/quick-add اللي يحفظه 0 مؤقتًا
# بانتظار أن يعدّله المدير لاحقًا من كتالوج التحاليل) حتى يدخل التحليل
# فورًا بجدول الفاتورة/المجموع بسعره الصحيح دون انتظار أحد.
@app.route("/api/tests/quick-add-priced", methods=["POST"])
@login_required
def api_quick_add_test_priced():
    db = get_db()
    name = (request.form.get("name") or "").strip()
    price_raw = (request.form.get("price") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    try:
        price = float(price_raw)
        if price < 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "السعر يجب أن يكون رقمًا (0 أو أكثر)"}), 400
    code = unique_test_code(db, name)
    cur = db.execute(
        "INSERT INTO test_definitions (code, name, department, sample_type, price, is_active, is_examining_test) "
        "VALUES (?, ?, '', '', ?, 1, 0)",
        (code, name, price),
    )
    db.commit()
    log_action("QuickAddTestPriced", "test_definition", cur.lastrowid, f"{name} ({price})")
    return jsonify({"id": cur.lastrowid, "name": name, "price": price, "code": code})


# إضافة اسم طبيب فاحص جديد بسرعة من نفس شاشة "زيارة جديدة" (القائمتين
# "دكتور المختبر الفاحص" و"الدكتور الفاحص") — يُحفظ بنفس قائمة الإعدادات
# التي يديرها المدير من Management → Settings، فيظهر لاحقًا هناك أيضًا.
@app.route("/api/examining-doctors/quick-add", methods=["POST"])
@login_required
def api_quick_add_examining_doctor():
    db = get_db()
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    add_examining_doctor(db, name)
    log_action("QuickAddExaminingDoctor", "settings", 0, name)
    return jsonify({"name": name})


@app.route("/api/tests/<int:test_id>/quick-edit", methods=["POST"])
@roles_required("supervisor")
def api_quick_edit_test(test_id):
    db = get_db()
    name = (request.form.get("name") or "").strip()
    department = (request.form.get("department") or "").strip()
    if not name:
        return jsonify({"error": "الاسم مطلوب"}), 400
    test = db.execute("SELECT id FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not test:
        return jsonify({"error": "not found"}), 404
    db.execute("UPDATE test_definitions SET name=?, department=? WHERE id=?", (name, department, test_id))
    db.commit()
    log_action("QuickEditTest", "test_definition", test_id, name)
    return jsonify({"id": test_id, "name": name, "department": department})


@app.route("/api/tests/<int:test_id>/quick-hide", methods=["POST"])
@roles_required("supervisor")
def api_quick_hide_test(test_id):
    db = get_db()
    test = db.execute("SELECT id, is_active FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not test:
        return jsonify({"error": "not found"}), 404
    new_val = 0 if test["is_active"] else 1
    db.execute("UPDATE test_definitions SET is_active=? WHERE id=?", (new_val, test_id))
    db.commit()
    log_action("QuickToggleTestActive", "test_definition", test_id, str(new_val))
    return jsonify({"id": test_id, "is_active": new_val})


@app.route("/api/tests/active-list")
@roles_required("supervisor")
def api_tests_active_list():
    db = get_db()
    tests = db.execute(
        "SELECT id, name, department, is_active FROM test_definitions WHERE is_active=1 ORDER BY department, name"
    ).fetchall()
    return jsonify([dict(t) for t in tests])



# --------------------------------------------------------------- management
@app.route("/management/settings", methods=["GET", "POST"])
@roles_required("admin")
def app_settings():
    db = get_db()
    if request.method == "POST":
        name_en = request.form.get("app_name", "").strip()
        name_ar = request.form.get("app_name_ar", "").strip()
        if name_en:
            set_setting(db, "app_name", name_en)
        if name_ar:
            set_setting(db, "app_name_ar", name_ar)

        lab_address_raw = request.form.get("lab_address", "").strip()
        if lab_address_raw:
            set_setting(db, "lab_address", lab_address_raw)
        lab_phone_raw = request.form.get("lab_phone", "").strip()
        if lab_phone_raw:
            set_setting(db, "lab_phone", lab_phone_raw)

        file = request.files.get("logo")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext in ALLOWED_LOGO_EXT:
                filename = secure_filename(f"logo.{ext}")
                # remove any previously uploaded logo with a different extension
                for old_ext in ALLOWED_LOGO_EXT:
                    old_path = os.path.join(UPLOAD_DIR, f"logo.{old_ext}")
                    if os.path.exists(old_path):
                        os.remove(old_path)
                file.save(os.path.join(UPLOAD_DIR, filename))
                set_setting(db, "logo_path", f"uploads/{filename}")
            else:
                flash("Unsupported logo file type. Use PNG, JPG, GIF, SVG or WEBP.")

        # خلفية شاشة الترحيب (dashboard) — نفس منطق رفع الشعار أعلاه بالضبط:
        # نحذف أي نسخة قديمة (بأي امتداد) ثم نحفظ الجديدة باسم ثابت
        # dashboard-bg.<ext> حتى يبقى مسار واحد معروف. زر "إزالة الصورة"
        # منفصل (checkbox/hidden باسم remove_dashboard_bg) يمسحها بدون رفع بديل.
        if request.form.get("remove_dashboard_bg") == "1":
            old_bg_path = get_setting(db, "dashboard_bg_path", "")
            if old_bg_path:
                old_bg_full = os.path.join(UPLOAD_DIR, os.path.basename(old_bg_path))
                if os.path.exists(old_bg_full):
                    os.remove(old_bg_full)
            set_setting(db, "dashboard_bg_path", "")
        else:
            bg_file = request.files.get("dashboard_bg")
            if bg_file and bg_file.filename:
                bg_ext = bg_file.filename.rsplit(".", 1)[-1].lower() if "." in bg_file.filename else ""
                if bg_ext in ALLOWED_DASHBOARD_BG_EXT:
                    bg_filename = secure_filename(f"dashboard-bg.{bg_ext}")
                    for old_ext in ALLOWED_DASHBOARD_BG_EXT:
                        old_bg = os.path.join(UPLOAD_DIR, f"dashboard-bg.{old_ext}")
                        if os.path.exists(old_bg):
                            os.remove(old_bg)
                    bg_file.save(os.path.join(UPLOAD_DIR, bg_filename))
                    set_setting(db, "dashboard_bg_path", f"uploads/{bg_filename}")
                else:
                    flash("صيغة صورة غير مدعومة لخلفية شاشة الترحيب. استخدم PNG أو JPG أو WEBP.")

        # خصائص خلفية شاشة الترحيب (تعتيم/ضبابية الطبقة فوق الصورة أو
        # التدرّج) — قابلة للتحكم الكامل من هنا بدل قيمتين ثابتتين
        # بالكود (كانت .62 وblur(2px))، بنفس أسلوب report_row_pad
        # وبقية إعدادات التخصيص أعلاه. تُحقن عالمياً بـinject_globals
        # وتُستخدم مباشرة بـdashboard.html.
        bg_opacity = request.form.get("dashboard_bg_overlay_opacity", "").strip()
        if bg_opacity:
            try:
                bg_opacity_val = max(0, min(100, int(bg_opacity)))
                set_setting(db, "dashboard_bg_overlay_opacity", str(bg_opacity_val))
            except ValueError:
                pass
        bg_blur = request.form.get("dashboard_bg_blur", "").strip()
        if bg_blur:
            try:
                bg_blur_val = max(0, min(20, int(bg_blur)))
                set_setting(db, "dashboard_bg_blur", str(bg_blur_val))
            except ValueError:
                pass
        # موضع الصورة (top/center/bottom) -- أعدتها هنا (كانت موجودة قبل)
        # لحد ما يتأكد المستخدم إذا يريدها يبقى أو يشيلها نهائيًا.
        bg_position_raw = request.form.get("dashboard_bg_position", "").strip()
        if bg_position_raw in ("top", "center", "bottom"):
            set_setting(db, "dashboard_bg_position", bg_position_raw)

        # ألوان الواجهة العامة (المطلوب: تغيير ألوان الخلفية بكل صفحات
        # البرنامج، مو بس شاشة الترحيب) -- نفس أسلوب باقي إعدادات
        # التخصيص، فحص بسيط على صيغة hex صحيحة (#RRGGBB) قبل الحفظ.
        primary_color_raw = request.form.get("theme_primary_color", "").strip()
        if primary_color_raw and _HEX_COLOR_RE.match(primary_color_raw):
            set_setting(db, "theme_primary_color", primary_color_raw)
        page_bg_raw = request.form.get("theme_page_bg_color", "").strip()
        if page_bg_raw and _HEX_COLOR_RE.match(page_bg_raw):
            set_setting(db, "theme_page_bg_color", page_bg_raw)

        # ملاحظة: إدارة أسماء وشهادات دكاترة الفحص انتقلت لشاشة مستقلة
        # (management/examining_doctors.html عبر الرابط بهذي الصفحة) — ما عاد
        # فيها فورم هنا.

        # ارتفاع/عرض خلايا جدول نتائج التقرير — رقم صحيح بين 2 و30 بكسل فقط،
        # أي قيمة غير صالحة تُتجاهل ويبقى المحفوظ سابقًا كما هو.
        row_pad_raw = request.form.get("report_row_pad", "").strip()
        if row_pad_raw:
            try:
                row_pad = max(2, min(30, int(row_pad_raw)))
                set_setting(db, "report_row_pad", str(row_pad))
            except ValueError:
                pass
        col_pad_raw = request.form.get("report_col_pad", "").strip()
        if col_pad_raw:
            try:
                col_pad = max(2, min(40, int(col_pad_raw)))
                set_setting(db, "report_col_pad", str(col_pad))
            except ValueError:
                pass

        pi_gap_raw = request.form.get("patient_info_top_gap", "").strip()
        if pi_gap_raw:
            try:
                pi_gap = max(0, min(60, int(pi_gap_raw)))
                set_setting(db, "patient_info_top_gap", str(pi_gap))
            except ValueError:
                pass
        pi_label_w_raw = request.form.get("patient_info_label_width", "").strip()
        if pi_label_w_raw:
            try:
                pi_label_w = max(60, min(220, int(pi_label_w_raw)))
                set_setting(db, "patient_info_label_width", str(pi_label_w))
            except ValueError:
                pass
        pi_row_gap_raw = request.form.get("patient_info_row_gap", "").strip()
        if pi_row_gap_raw:
            try:
                pi_row_gap = max(0, min(30, int(pi_row_gap_raw)))
                set_setting(db, "patient_info_row_gap", str(pi_row_gap))
            except ValueError:
                pass
        pi_col_gap_raw = request.form.get("patient_info_col_gap", "").strip()
        if pi_col_gap_raw:
            try:
                pi_col_gap = max(0, min(150, int(pi_col_gap_raw)))
                set_setting(db, "patient_info_col_gap", str(pi_col_gap))
            except ValueError:
                pass
        underline_style_raw = request.form.get("report_underline_style")
        if underline_style_raw in ("solid", "dashed", "none"):
            set_setting(db, "report_underline_style", underline_style_raw)

        wa_code = request.form.get("whatsapp_country_code", "").strip()
        if wa_code:
            set_setting(db, "whatsapp_country_code", "".join(ch for ch in wa_code if ch.isdigit()))

        # حجم ونوع خط أسماء/شهادات الدكاترة بترويسة كل تقرير مطبوع (base_report.html)
        # — إعداد عام واحد ينطبق على الجميع دفعة وحدة، مو لكل شخص لحاله.
        lh_size_raw = request.form.get("letterhead_font_size", "").strip()
        if lh_size_raw:
            try:
                lh_size = max(8, min(30, int(lh_size_raw)))
                set_setting(db, "letterhead_font_size", str(lh_size))
            except ValueError:
                pass
        lh_family_raw = request.form.get("letterhead_font_family", "").strip()
        if lh_family_raw:
            set_setting(db, "letterhead_font_family", lh_family_raw)

        # موضع الشعار (يمين الافتراضي/وسط/يسار) وحجمه (عرضه بالبكسل) —
        # إعدادان عامان جديدان، نفس أسلوب باقي إعدادات التقرير.
        logo_pos_raw = request.form.get("logo_position", "").strip()
        if logo_pos_raw in ("right", "center", "left"):
            set_setting(db, "logo_position", logo_pos_raw)
        logo_width_raw = request.form.get("logo_width", "").strip()
        if logo_width_raw:
            try:
                logo_width = max(30, min(300, int(logo_width_raw)))
                set_setting(db, "logo_width", str(logo_width))
            except ValueError:
                pass

        # ترتيب أقسام اللوحة المجمّعة — سطر واحد لكل اسم قسم/ريبورت مجمّع
        # (report_group أو department)، بنفس الترتيب اللي يريده الأدمن
        # بالطباعة. حقل نصي فاضي بالكامل = رجوع للترتيب الأبجدي الافتراضي.
        panel_group_order_raw = request.form.get("combined_panel_group_order")
        if panel_group_order_raw is not None:
            set_setting(db, "combined_panel_group_order", panel_group_order_raw.strip())

        # ترتيب ثابت للتحاليل بشاشة "إدخال النتائج" (Results Entry) — سطر
        # لكل اسم تحليل بالضبط كما يظهر بالشاشة (مثلاً "HbA1c (BioChemstry)")،
        # بنفس الترتيب اللي يريده الأدمن، ثابت دائماً بغض النظر عن ترتيب
        # طلب التحاليل الفعلي بكل زيارة. فاضي بالكامل = رجوع لترتيب الطلب
        # الأصلي (ot.id) كالسابق.
        results_order_raw = request.form.get("results_entry_test_order")
        if results_order_raw is not None:
            set_setting(db, "results_entry_test_order", results_order_raw.strip())
        analyzers_raw = request.form.get("known_analyzers")
        if analyzers_raw is not None:
            set_setting(db, "known_analyzers", analyzers_raw.strip())
        # تصحيحات ترجمة الأسماء العربية للإنكليزي (المطلوب: ترجمة دقيقة —
        # القاموس الجاهز بالكود يغطي أسماء شائعة، وهذا الحقل يخلي المختبر
        # يصحّح أي اسم يطلع غلط بنفسه دون انتظار تحديث بالكود. سطر لكل
        # اسم بصيغة "عربي=إنكليزي"، مثال: سمر=Samar
        name_translit_raw = request.form.get("name_translit_overrides")
        if name_translit_raw is not None:
            set_setting(db, "name_translit_overrides", name_translit_raw.strip())
        # حجم خط اسم التحليل وحجم خط النتيجة بجدول/بطاقات النتائج بكل
        # التقارير المطبوعة — إعدادان عامان منفصلان عن بعض (وعن حجم خط
        # ترويسة الدكاترة letterhead_font_size أعلاه)، دفعة وحدة لكل
        # التقارير. أي قيمة غير صالحة تُتجاهل ويبقى المحفوظ سابقًا كما هو.
        tn_size_raw = request.form.get("test_name_font_size", "").strip()
        if tn_size_raw:
            try:
                tn_size = max(8, min(30, int(tn_size_raw)))
                set_setting(db, "test_name_font_size", str(tn_size))
            except ValueError:
                pass
        rv_size_raw = request.form.get("result_value_font_size", "").strip()
        if rv_size_raw:
            try:
                rv_size = max(8, min(30, int(rv_size_raw)))
                set_setting(db, "result_value_font_size", str(rv_size))
            except ValueError:
                pass

        # مجلد أرشفة الـPDF الدائم (نقطة #8) — يُضبط مرة وحدة هنا وقت
        # التنصيب/الإعداد الأولي، ويُعاد استخدامه تلقائيًا بعدها لكل زيارة
        # تكتمل نتائجها. لا نتحقق من وجوده هنا (os.makedirs لاحقًا وقت
        # الأرشفة الفعلية يكفي) حتى يقدر المدير يكتب مسار جهاز آخر بالشبكة.
        archive_dir_raw = request.form.get("pdf_archive_dir", "").strip()
        if archive_dir_raw:
            set_setting(db, "pdf_archive_dir", archive_dir_raw)

        # ألوان رموز الـ Conclusion (نجمة/أسهم/استفهام/تعجب) — كل رمز إله
        # حقل <input type=color> باسم marker_color_<key> بشاشة الإعدادات.
        # نحفظ فقط الألوان اللي وصلت وبصيغة hex صحيحة؛ أي حقل فاضي أو غير
        # صالح يبقى على قيمته المحفوظة سابقًا (أو الافتراضي إذا ما انحفظ شي).
        marker_colors = {}
        raw_existing = get_setting(db, "conclusion_marker_colors", "")
        if raw_existing:
            try:
                marker_colors = json.loads(raw_existing)
            except (ValueError, TypeError):
                marker_colors = {}
        for m in CONCLUSION_MARKERS:
            val = request.form.get("marker_color_" + m["key"], "").strip()
            if val and _HEX_COLOR_RE.match(val):
                marker_colors[m["key"]] = val
        if marker_colors:
            set_setting(db, "conclusion_marker_colors", json.dumps(marker_colors))

        # تلوين/أعلام النتائج (المطلوب 2 و3) — نفس مشكلة أي checkbox بفورم
        # منفصل عن باقي كروت الإعدادات: checkbox غير محدد ما يظهر إطلاقًا
        # بالفورم، فما نقدر نميّز "هذا الكرت انحفظ والخيار متروك فارغ" عن
        # "فورم كرت ثاني انحفظ وهذا الحقل أصلاً مو منه". لذلك نعتمد على
        # حقل hidden مميّز (flag_settings_form) موجود فقط بفورم هذا الكرت
        # تحديداً بـsettings.html — لا نلمس هذا الإعداد أبداً إلا لو
        # الفورم المُرسَل فعلاً هو فورم هذا الكرت.
        if request.form.get("flag_settings_form") is not None:
            set_setting(db, "auto_flag_color_enabled", "1" if request.form.get("auto_flag_color_enabled") else "0")
            set_setting(db, "show_result_flag", "1" if request.form.get("show_result_flag") else "0")
            flag_high = request.form.get("flag_color_high", "").strip()
            if flag_high and _HEX_COLOR_RE.match(flag_high):
                set_setting(db, "flag_color_high", flag_high)
            flag_low = request.form.get("flag_color_low", "").strip()
            if flag_low and _HEX_COLOR_RE.match(flag_low):
                set_setting(db, "flag_color_low", flag_low)

        # ------------------------------------------------------------
        # بطاقة "تحليل مجاني" — محمية بيوزر/باسوورد تعديل مخصص ومنفصل عن
        # كل نظام يوزرات البرنامج العادي. أول مرة (ما فيه يوزر/باسوورد
        # تعديل محفوظ بعد) نقبل أي يوزر/باسوورد جديدين يُكتبان بحقلي
        # "يوزر جديد/باسوورد جديد" كبذرة أولى؛ بعدها أي تعديل (حتى تغيير
        # اليوزر/الباسوورد نفسه) يحتاج تأكيد اليوزر/الباسوورد الحاليين أولاً.
        # ------------------------------------------------------------
        if request.form.get("fee_waiver_form") is not None:
            gate_user_input = request.form.get("gate_username", "").strip()
            gate_pass_input = request.form.get("gate_password", "")
            stored_gate_user = get_setting(db, "fee_waiver_gate_username", "")
            stored_gate_hash = get_setting(db, "fee_waiver_gate_password_hash", "")

            gate_ok = False
            if not stored_gate_user and not stored_gate_hash:
                new_gate_user_first = request.form.get("new_gate_username", "").strip()
                new_gate_pass_first = request.form.get("new_gate_password", "")
                if new_gate_user_first and new_gate_pass_first:
                    set_setting(db, "fee_waiver_gate_username", new_gate_user_first)
                    set_setting(db, "fee_waiver_gate_password_hash", hash_password(new_gate_pass_first))
                    gate_ok = True
                    flash("تم إنشاء يوزر/باسوورد التعديل الخاص بميزة \"تحليل مجاني\" لأول مرة.")
                else:
                    flash("لأول ضبط لهذه الميزة: اكتب يوزر وباسوورد جديدين بحقلي \"تغيير يوزر/باسوورد هذا التعديل\" بالأسفل.")
            elif gate_user_input and gate_user_input == stored_gate_user and hash_password(gate_pass_input) == stored_gate_hash:
                gate_ok = True
            else:
                flash("يوزر أو باسوورد التعديل غير صحيح — لم يتم حفظ أي تغيير على بطاقة \"تحليل مجاني\".")

            if gate_ok:
                waiver_name = request.form.get("waiver_authorized_name", "").strip()
                if waiver_name:
                    set_setting(db, "fee_waiver_authorized_name", waiver_name)
                waiver_pass = request.form.get("waiver_password", "")
                if waiver_pass:
                    set_setting(db, "fee_waiver_password_hash", hash_password(waiver_pass))
                new_gate_user = request.form.get("new_gate_username", "").strip()
                new_gate_pass = request.form.get("new_gate_password", "")
                if new_gate_user and new_gate_pass and (stored_gate_user or stored_gate_hash):
                    set_setting(db, "fee_waiver_gate_username", new_gate_user)
                    set_setting(db, "fee_waiver_gate_password_hash", hash_password(new_gate_pass))
                    flash("تم تغيير يوزر/باسوورد التعديل الخاص بميزة \"تحليل مجاني\".")
                db.commit()
                log_action("UpdateFeeWaiverSettings", "settings", 0)
                flash("تم حفظ إعدادات \"تحليل مجاني\".")
            return redirect(url_for("app_settings"))

        # ------------------------------------------------------------
        # كلمات مرور واجهتي "استقبال" و"مختبر" (المطلوب 3) -- كل وحدة
        # مستقلة، تُسأل بس وقت الدخول/تبديل الواجهة لتلك القيمة تحديدًا.
        # ترك الحقل فاضي = ما يغيّر كلمة المرور الحالية (يبقى نفس الشي
        # -- خله فاضي كل مرة إذا ما تريد تغييرها).
        # ------------------------------------------------------------
        if request.form.get("interface_passwords_form") is not None:
            recep_pass = request.form.get("interface_reception_password", "")
            if recep_pass:
                set_setting(db, "interface_reception_password_hash", hash_password(recep_pass))
            lab_pass = request.form.get("interface_lab_password", "")
            if lab_pass:
                set_setting(db, "interface_lab_password_hash", hash_password(lab_pass))
            db.commit()
            log_action("UpdateInterfacePasswords", "settings", 0)
            flash("تم حفظ كلمات مرور الواجهات.")
            return redirect(url_for("app_settings"))

        # ------------------------------------------------------------
        # الشاشة الرئيسية (المطلوب: العنوان + صور الخيارات الثلاث + لوني
        # التدرّج). نفس أسلوب رفع صورة خلفية شاشة الترحيب أعلاه بالضبط،
        # لكن لكل صورة من الثلاث خزّانها الخاص (landing_<key>_image_path)
        # حتى ما تتداخل ببعضها. حقل فاضي = يبقى نفس الشي الحالي.
        # ------------------------------------------------------------
        if request.form.get("landing_page_form") is not None:
            landing_title_raw = request.form.get("landing_title", "").strip()
            if landing_title_raw:
                set_setting(db, "landing_title", landing_title_raw)
            for gkey in ("landing_gradient_color1", "landing_gradient_color2"):
                gval = request.form.get(gkey, "").strip()
                if gval and _HEX_COLOR_RE.match(gval):
                    set_setting(db, gkey, gval)
            for img_key in ("reception", "lab", "together"):
                setting_key = f"landing_{img_key}_image_path"
                if request.form.get(f"remove_landing_{img_key}_image") == "1":
                    old_path = get_setting(db, setting_key, "")
                    if old_path:
                        old_full = os.path.join(UPLOAD_DIR, os.path.basename(old_path))
                        if os.path.exists(old_full):
                            os.remove(old_full)
                    set_setting(db, setting_key, "")
                    continue
                img_file = request.files.get(f"landing_{img_key}_image")
                if img_file and img_file.filename:
                    img_ext = img_file.filename.rsplit(".", 1)[-1].lower() if "." in img_file.filename else ""
                    if img_ext in ALLOWED_DASHBOARD_BG_EXT:
                        img_filename = secure_filename(f"landing-{img_key}.{img_ext}")
                        for old_ext in ALLOWED_DASHBOARD_BG_EXT:
                            old_img = os.path.join(UPLOAD_DIR, f"landing-{img_key}.{old_ext}")
                            if os.path.exists(old_img):
                                os.remove(old_img)
                        img_file.save(os.path.join(UPLOAD_DIR, img_filename))
                        set_setting(db, setting_key, f"uploads/{img_filename}")
                    else:
                        flash(f"صيغة صورة غير مدعومة لبطاقة {img_key}. استخدم PNG أو JPG أو WEBP.")
            db.commit()
            log_action("UpdateLandingPage", "settings", 0)
            flash("تم حفظ إعدادات الشاشة الرئيسية.")
            return redirect(url_for("app_settings"))

        db.commit()
        log_action("UpdateSettings", "settings", 0)
        flash("Settings saved.")
        return redirect(url_for("app_settings"))

    current = {
        "app_name": get_setting(db, "app_name", ""),
        "app_name_ar": get_setting(db, "app_name_ar", ""),
        "lab_address": get_setting(db, "lab_address", ""),
        "lab_phone": get_setting(db, "lab_phone", ""),
        "logo_path": get_setting(db, "logo_path", ""),
        "dashboard_bg_path": get_setting(db, "dashboard_bg_path", ""),
        "dashboard_bg_overlay_opacity": get_setting(db, "dashboard_bg_overlay_opacity", "62"),
        "theme_primary_color": get_setting(db, "theme_primary_color", "#205072"),
        "theme_page_bg_color": get_setting(db, "theme_page_bg_color", "#F3F6F8"),
        "landing_title": get_setting(db, "landing_title", "نظام الإدارة المتكامل"),
        "landing_gradient_color1": get_setting(db, "landing_gradient_color1", "#0f172a"),
        "landing_gradient_color2": get_setting(db, "landing_gradient_color2", "#205072"),
        "landing_reception_image_path": get_setting(db, "landing_reception_image_path", ""),
        "landing_lab_image_path": get_setting(db, "landing_lab_image_path", ""),
        "landing_together_image_path": get_setting(db, "landing_together_image_path", ""),
        "dashboard_bg_blur": get_setting(db, "dashboard_bg_blur", "2"),
        "dashboard_bg_position": get_setting(db, "dashboard_bg_position", "center"),
        "report_row_pad": get_setting(db, "report_row_pad", "5"),
        "patient_info_top_gap": get_setting(db, "patient_info_top_gap", "4"),
        "patient_info_label_width": get_setting(db, "patient_info_label_width", "108"),
        "patient_info_row_gap": get_setting(db, "patient_info_row_gap", "3"),
        "patient_info_col_gap": get_setting(db, "patient_info_col_gap", "36"),
        "report_underline_style": get_setting(db, "report_underline_style", "solid"),
        "report_col_pad": get_setting(db, "report_col_pad", "12"),
        "whatsapp_country_code": get_setting(db, "whatsapp_country_code", "964"),
        "pdf_archive_dir": get_setting(db, "pdf_archive_dir", ""),
        "letterhead_font_size": get_setting(db, "letterhead_font_size", "14"),
        "letterhead_font_family": get_setting(db, "letterhead_font_family", "Segoe UI, Tahoma, Arial, sans-serif"),
        "test_name_font_size": get_setting(db, "test_name_font_size", "16"),
        "result_value_font_size": get_setting(db, "result_value_font_size", "16"),
        "logo_position": get_setting(db, "logo_position", "right"),
        "logo_width": get_setting(db, "logo_width", "100"),
        "combined_panel_group_order": get_setting(db, "combined_panel_group_order", ""),
        "name_translit_overrides": get_setting(db, "name_translit_overrides", ""),
        "results_entry_test_order": get_setting(db, "results_entry_test_order", ""),
        "known_analyzers": get_setting(db, "known_analyzers", ""),
        "auto_flag_color_enabled": get_setting(db, "auto_flag_color_enabled", "0"),
        "show_result_flag": get_setting(db, "show_result_flag", "0"),
        "flag_color_high": get_setting(db, "flag_color_high", "#D40000"),
        "flag_color_low": get_setting(db, "flag_color_low", "#B58900"),
        "fee_waiver_authorized_name": get_setting(db, "fee_waiver_authorized_name", ""),
    }
    marker_colors_by_char = get_conclusion_marker_colors(db)
    conclusion_markers = [
        {**m, "color": marker_colors_by_char[m["char"]]} for m in CONCLUSION_MARKERS
    ]
    return render_template(
        "management/settings.html", current=current, conclusion_markers=conclusion_markers
    )


# ------------------------------------------------------------------------
# تبديل "التحديث التلقائي" بضغطة وحدة من شريط الأعلى (بجانب اسم المستخدم) —
# متاح لدخول الأدمن العادي، بعكس /designer/update/toggle اللي يحتاج جلسة
# "مصمم" منفصلة. الاثنين يكتبان لنفس المفتاح (auto_update_enabled) بجدول
# الإعدادات، فتفعيل/تعطيل أي وحدة منهم ينعكس على الثاني وعلى auto_updater
# نفسه فورًا. يرجّع المستخدم لنفس الصفحة اللي كان فيها (request.referrer).
# ------------------------------------------------------------------------
# ============================================================================
# نظام النسخ الاحتياطي / الاستعادة (Backup / Restore) على USB أو CD
# ============================================================================
# فكرة العمل: قاعدة بيانات البرنامج بالكامل عبارة عن ملف واحد (lis.db).
# "تصدير نسخة احتياطية" ينسخ هذا الملف بأمان (عبر sqlite backup API، حتى
# لو فيه استخدام لحظي) ويحزمه مع صفحة بحث بسيطة تعمل بدون تنصيب البرنامج
# (search_offline.html) داخل ملف ZIP واحد يُنزَّل من المتصفح -- والمستخدم
# نفسه يحفظه بعدها بمكان تخزينه (USB / قرص) ويقدر يحرقه على CD إذا يريد.
# "استيراد نسخة احتياطية" يرفع نفس ملف الـZIP ويستبدل قاعدة البيانات
# الحالية بعد أخذ نسخة احتياطية تلقائية من القديمة أولاً (تحسّبًا لأي خطأ).
#
# 🔒 حماية إضافية مطلوبة صراحة: العملية بالكامل (تصدير أو استيراد) لازم
# تمر عبر يوزر/باسوورد خاصين بهذا الغرض فقط (backup_gate_username /
# backup_gate_password_hash) -- منفصلين تمامًا عن يوزر دخولك العادي وعن
# يوزر ميزة "تحليل مجاني" -- بنفس أسلوب "أول مرة تُترك فاضية تُنشأ تلقائيًا،
# وبعدها أي تغيير يحتاج تأكيد اليوزر/الباسوورد الحاليين" المتّبع بكل أنظمة
# الحماية الحساسة بهذا البرنامج.
# ============================================================================

def _check_backup_gate(db, username, password):
    """يتحقق من يوزر/باسوورد النسخ الاحتياطي الخاصين. يرجّع (ok: bool,
    first_time: bool) -- لو ما فيه يوزر/باسوورد محفوظ بعد (أول استخدام)،
    يعتبرها "غير جاهزة" (ok=False) لكن يعلّم first_time=True حتى تظهر
    رسالة توجّه المستخدم لصفحة الإعدادات يضبطها أول مرة."""
    stored_user = get_setting(db, "backup_gate_username", "")
    stored_hash = get_setting(db, "backup_gate_password_hash", "")
    if not stored_user and not stored_hash:
        return False, True
    ok = bool(username) and username == stored_user and hash_password(password or "") == stored_hash
    return ok, False


@app.route("/management/backup", methods=["GET"])
@roles_required("admin")
def backup_center():
    db = get_db()
    gate_ready = bool(get_setting(db, "backup_gate_username", ""))
    return render_template(
        "management/backup.html",
        gate_ready=gate_ready,
        hardware_id=license_manager.get_hardware_id(),
        last_backup_at=get_setting(db, "last_backup_at", ""),
    )


@app.route("/management/backup/set-gate", methods=["POST"])
@roles_required("admin")
def backup_set_gate():
    # نفس منطق بطاقة "تحليل مجاني" بالإعدادات: أول مرة تُترك الحقول فاضية
    # (ما فيه يوزر/باسوورد محفوظ) يُقبل أي يوزر/باسوورد جديدين كبذرة أولى؛
    # بعدها أي تغيير يحتاج تأكيد اليوزر/الباسوورد الحاليين أولاً.
    db = get_db()
    stored_user = get_setting(db, "backup_gate_username", "")
    stored_hash = get_setting(db, "backup_gate_password_hash", "")
    current_user_input = request.form.get("current_username", "").strip()
    current_pass_input = request.form.get("current_password", "")
    new_user = request.form.get("new_username", "").strip()
    new_pass = request.form.get("new_password", "")

    if not stored_user and not stored_hash:
        if new_user and new_pass:
            set_setting(db, "backup_gate_username", new_user)
            set_setting(db, "backup_gate_password_hash", hash_password(new_pass))
            db.commit()
            log_action("SetBackupGate", "settings", 0)
            flash("تم إنشاء يوزر/باسوورد النسخ الاحتياطي لأول مرة.")
        else:
            flash("اكتب يوزر وباسوورد جديدين لإنشاء صلاحية النسخ الاحتياطي أول مرة.")
    elif current_user_input == stored_user and hash_password(current_pass_input) == stored_hash:
        if new_user and new_pass:
            set_setting(db, "backup_gate_username", new_user)
            set_setting(db, "backup_gate_password_hash", hash_password(new_pass))
            db.commit()
            log_action("ChangeBackupGate", "settings", 0)
            flash("تم تغيير يوزر/باسوورد النسخ الاحتياطي.")
        else:
            flash("اكتب يوزر وباسوورد جديدين بحقلي \"يوزر/باسوورد جديد\" لتغييرهما.")
    else:
        flash("يوزر أو باسوورد النسخ الاحتياطي الحالي غير صحيح -- لم يتم أي تغيير.")
    return redirect(url_for("backup_center"))


def _build_offline_export(db):
    """يبني كل مكونات البحث والتفاصيل الكاملة بدون تنصيب أو ترخيص:
    1) صفحة فهرس (search_offline.html) للبحث باسم المريض/رقم التسجيل/التاريخ.
    2) ملف HTML مستقل لكل زيارة فيها تحليل مكتمل واحد على الأقل، بنفس
       التصميم الحقيقي حرفيًا لتقرير المريض (نفس الدالة المستخدمة أصلاً
       لتوليد ملف PDF الموحّد للأرشفة/واتساب: _build_combined_designed_reports_html) —
       فتحه من نفس الـUSB أو الـCD بأي متصفح يعرض كل الأرقام والقيم
       المرجعية بالضبط متل لو طُبع من داخل البرنامج، بدون أي اتصال أو
       تنصيب. الزيارات اللي ما فيها أي تحليل مكتمل بعد تظهر بالفهرس بس
       بدون رابط تقرير (لأنه ما فيه نتيجة جاهزة أصلاً تُطبع).
    يرجّع (index_html: str, report_files: dict[اسم الملف -> محتوى HTML])."""
    rows = db.execute(
        "SELECT v.id, v.registration_number, p.full_name, v.gender, v.age, v.age_unit, "
        "v.created_at, d.full_name as doctor_name, v.examining_doctor "
        "FROM visits v "
        "JOIN patients p ON p.id = v.patient_id "
        "LEFT JOIN doctors d ON d.id = v.doctor_id "
        "ORDER BY v.created_at DESC"
    ).fetchall()
    records = []
    report_files = {}
    for v in rows:
        tests = db.execute(
            "SELECT td.name, ot.status, ot.fee_waived FROM order_tests ot "
            "JOIN test_definitions td ON td.id = ot.test_definition_id "
            "JOIN orders o ON o.id = ot.order_id "
            "WHERE o.visit_id=? AND (ot.hidden_from_log IS NULL OR ot.hidden_from_log=0)",
            (v["id"],),
        ).fetchall()
        report_file = None
        try:
            combined_html = _build_combined_designed_reports_html(v["id"])
        except Exception:
            # ما نوقّف التصدير كامل بسبب تقرير وحيد فشل توليده -- نتجاهله
            # ونكمّل الباقي (نفس أسلوب _build_combined_designed_reports_html
            # نفسها مع كل تحليل).
            combined_html = None
        if combined_html:
            safe_name = secure_filename(str(v["registration_number"] or v["id"])) or f"visit_{v['id']}"
            filename = f"{safe_name}.html"
            if filename in report_files:
                filename = f"{safe_name}_{v['id']}.html"
            report_files[filename] = combined_html
            report_file = f"reports/{filename}"
        records.append({
            "reg": v["registration_number"],
            "name": v["full_name"],
            "gender": v["gender"],
            "age": f"{v['age'] or ''} {v['age_unit'] or ''}".strip(),
            "date": v["created_at"],
            "referring_doctor": v["doctor_name"] or "",
            "examining_doctor": v["examining_doctor"] or "",
            "tests": [
                {"name": t["name"], "status": t["status"], "free": bool(t["fee_waived"])}
                for t in tests
            ],
            "report_file": report_file,
        })
    data_json = json.dumps(records, ensure_ascii=False)
    html = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<title>بحث نسخة احتياطية -- سجل المرضى</title>
<style>
body{font-family:Tahoma,Arial,sans-serif;background:#f3f6f8;margin:0;padding:20px;}
h1{color:#205072;font-size:18px;}
input{padding:8px;width:100%;max-width:420px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px;}
table{width:100%;border-collapse:collapse;background:#fff;margin-top:14px;}
th,td{border:1px solid #e2e8f0;padding:6px 10px;font-size:13px;text-align:right;}
th{background:#205072;color:#fff;}
.muted{color:#64748b;font-size:12px;}
.free{color:#0f766e;font-weight:bold;}
a.report-link{background:#205072;color:#fff;text-decoration:none;padding:4px 10px;border-radius:5px;font-size:12px;white-space:nowrap;}
span.no-report{color:#94a3b8;font-size:12px;}
</style></head><body>
<h1>🔎 بحث كامل بالنسخة الاحتياطية (بدون تنصيب أو ترخيص)</h1>
<p class="muted">اضغط "عرض التقرير الكامل" لأي مريض عنده نتيجة جاهزة لعرض كل الأرقام والقيم المرجعية بنفس تصميم التقرير المطبوع بالضبط -- كل هذا يفتح من نفس الملفات المحلية بدون أي اتصال انترنت.</p>
<input id="q" type="text" placeholder="اكتب اسم المريض أو رقم التسجيل أو التاريخ...">
<table id="tbl"><thead><tr><th>رقم التسجيل</th><th>الاسم</th><th>الجنس</th><th>العمر</th><th>التاريخ</th><th>التحاليل</th><th>التقرير</th></tr></thead>
<tbody></tbody></table>
<script>
const DATA = __DATA_JSON__;
const tbody = document.querySelector('#tbl tbody');
function render(list) {
  tbody.innerHTML = '';
  list.slice(0, 300).forEach(function(r) {
    const testsStr = r.tests.map(function(t){ return t.name + (t.free ? ' (مجاني)' : ''); }).join('، ');
    const reportCell = r.report_file
      ? '<a class="report-link" target="_blank" href="' + r.report_file + '">📄 عرض التقرير الكامل</a>'
      : '<span class="no-report">لا توجد نتيجة جاهزة بعد</span>';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + r.reg + '</td><td>' + r.name + '</td><td>' + r.gender + '</td><td>' + r.age +
      '</td><td>' + r.date + '</td><td>' + testsStr + '</td><td>' + reportCell + '</td>';
    tbody.appendChild(tr);
  });
}
document.getElementById('q').addEventListener('input', function(e) {
  const q = e.target.value.trim().toLowerCase();
  if (!q) { render(DATA); return; }
  render(DATA.filter(function(r) {
    return (r.reg + ' ' + r.name + ' ' + r.date).toLowerCase().indexOf(q) !== -1;
  }));
});
render(DATA);
</script>
</body></html>"""
    return html.replace("__DATA_JSON__", data_json), report_files


@app.route("/management/backup/export", methods=["POST"])
@roles_required("admin")
def backup_export():
    db = get_db()
    ok, first_time = _check_backup_gate(db, request.form.get("username", "").strip(), request.form.get("password", ""))
    if first_time:
        flash("لازم تضبط يوزر/باسوورد النسخ الاحتياطي أولاً من نفس هذه الصفحة.")
        return redirect(url_for("backup_center"))
    if not ok:
        flash("يوزر أو باسوورد النسخ الاحتياطي غير صحيح -- لم يتم تصدير أي شيء.")
        return redirect(url_for("backup_center"))

    from database import DB_PATH
    # نسخ آمن لملف قاعدة البيانات عبر sqlite backup API (يتعامل صح حتى لو
    # فيه اتصال ثاني يستخدم الملف بنفس اللحظة، بعكس نسخ الملف مباشرة).
    tmp_dir = tempfile.mkdtemp(prefix="lis_backup_")
    db_copy_path = os.path.join(tmp_dir, "lis.db")
    src_conn = sqlite3.connect(DB_PATH)
    dst_conn = sqlite3.connect(db_copy_path)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()

    offline_html, report_files = _build_offline_export(db)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "hardware_id": license_manager.get_hardware_id(),
        "app": get_setting(db, "app_name", "LIS"),
        "reports_included": len(report_files),
    }

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_copy_path, "lis.db")
        zf.writestr("search_offline.html", offline_html)
        zf.writestr("backup_info.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        # كل زيارة عندها نتيجة مكتملة تحصل على ملف تقرير كامل مستقل بنفس
        # التصميم الحقيقي بالضبط -- راجع _build_offline_export أعلاه.
        for filename, content in report_files.items():
            zf.writestr(f"reports/{filename}", content)
    zip_buf.seek(0)
    shutil.rmtree(tmp_dir, ignore_errors=True)

    set_setting(db, "last_backup_at", manifest["created_at"])
    db.commit()
    log_action("ExportBackup", "settings", 0, f"by={request.form.get('username','').strip()}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(zip_buf, mimetype="application/zip", as_attachment=True,
                      download_name=f"lis_backup_{stamp}.zip")


@app.route("/management/backup/import", methods=["POST"])
@roles_required("admin")
def backup_import():
    db = get_db()
    ok, first_time = _check_backup_gate(db, request.form.get("username", "").strip(), request.form.get("password", ""))
    if first_time:
        flash("لازم تضبط يوزر/باسوورد النسخ الاحتياطي أولاً من نفس هذه الصفحة.")
        return redirect(url_for("backup_center"))
    if not ok:
        flash("يوزر أو باسوورد النسخ الاحتياطي غير صحيح -- لم يتم استيراد أي شيء.")
        return redirect(url_for("backup_center"))

    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        flash("اختر ملف النسخة الاحتياطية (ZIP) أولاً.")
        return redirect(url_for("backup_center"))

    from database import DB_PATH
    tmp_dir = tempfile.mkdtemp(prefix="lis_restore_")
    zip_path = os.path.join(tmp_dir, "upload.zip")
    uploaded.save(zip_path)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if "lis.db" not in zf.namelist():
                flash("هذا الملف ليس نسخة احتياطية صالحة (ما فيه lis.db بداخله).")
                return redirect(url_for("backup_center"))
            zf.extract("lis.db", tmp_dir)
    except zipfile.BadZipFile:
        flash("تعذّر فتح الملف -- تأكد إنه ملف ZIP صالح من نفس البرنامج.")
        return redirect(url_for("backup_center"))

    extracted_db = os.path.join(tmp_dir, "lis.db")
    # تحقق سلامة قبل الاستبدال -- ما نستبدل قاعدة بيانات تالفة أو ملف مو حتى sqlite
    try:
        check_conn = sqlite3.connect(extracted_db)
        result = check_conn.execute("PRAGMA integrity_check").fetchone()
        check_conn.close()
        if not result or result[0] != "ok":
            flash("ملف قاعدة البيانات بالنسخة الاحتياطية غير سليم -- تم إلغاء الاستيراد.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return redirect(url_for("backup_center"))
    except Exception:
        flash("تعذّر التحقق من ملف قاعدة البيانات -- تم إلغاء الاستيراد.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return redirect(url_for("backup_center"))

    # نسخة احتياطية تلقائية من القاعدة الحالية قبل الاستبدال -- تحسبًا لأي غلط
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_copy = os.path.join(os.path.dirname(DB_PATH), f"lis_before_restore_{stamp}.db")
    shutil.copy2(DB_PATH, safety_copy)

    shutil.copy2(extracted_db, DB_PATH)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    log_action("ImportBackup", "settings", 0, f"by={request.form.get('username','').strip()}")
    flash("تم استيراد النسخة الاحتياطية بنجاح. أعد تشغيل البرنامج الآن حتى تظهر البيانات المستوردة بشكل صحيح "
          f"(نسخة القاعدة القديمة محفوظة احتياطًا باسم lis_before_restore_{stamp}.db بجانب البرنامج).")
    return redirect(url_for("backup_center"))



@roles_required("admin")
def toggle_auto_update():
    db = get_db()
    currently_on = get_setting(db, "auto_update_enabled", "1") == "1"
    set_setting(db, "auto_update_enabled", "0" if currently_on else "1")
    db.commit()
    log_action("ToggleAutoUpdate", "settings", 0, "off" if currently_on else "on")
    db.close()
    flash("تم إيقاف التحديث التلقائي." if currently_on else "تم تفعيل التحديث التلقائي.")
    return redirect(request.referrer or url_for("dashboard"))


# ------------------------------------------------------------------------
# إدارة قائمة (دكتور المختبر الفاحص) — اسم/لقب/شهادة عربي/شهادة انكليزي
# وترتيب يدوي (فوق/تحت)، بالإضافة لمفتاح "إظهار بترويسة التقرير" لكل واحد
# منهم. مفتوحة من بطاقة "دكتور المختبر الفاحص" بصفحة الإعدادات. الأسماء
# نفسها تبقى تُستخدم كنص بجداول أخرى (أجور الفحص، الزيارات) فتغيير الاسم
# هنا لا يحدّث تلقائيًا سجلات قديمة محفوظة بالاسم السابق.
# ------------------------------------------------------------------------
@app.route("/management/examining-doctors", methods=["GET"])
@roles_required("admin")
def examining_doctors_manage():
    db = get_db()
    doctors = get_examining_doctors_full(db)
    return render_template("management/examining_doctors.html", doctors=doctors)


@app.route("/management/examining-doctors/add", methods=["POST"])
@roles_required("admin")
def examining_doctor_add():
    db = get_db()
    name = request.form.get("name", "").strip()
    if not name:
        flash("اسم الدكتور مطلوب.")
        return redirect(url_for("examining_doctors_manage"))
    title = request.form.get("title", "الدكتور").strip()
    degree_ar = request.form.get("degree_ar", "").strip() or None
    degree_en = request.form.get("degree_en", "").strip() or None
    show_on_letterhead = bool(request.form.get("show_on_letterhead"))
    # حجم خط مخصص لهذا الدكتور تحديداً بالترويسة (اختياري) — يتجاوز الحجم
    # العام letterhead_font_size من الإعدادات لو تُرك فاضي يرث العام كالمعتاد.
    font_size_raw = request.form.get("font_size", "").strip()
    font_size = None
    if font_size_raw:
        try:
            font_size = max(8, min(30, int(font_size_raw)))
        except ValueError:
            font_size = None
    add_examining_doctor_full(db, name, title, degree_ar, degree_en, show_on_letterhead, font_size)
    log_action("AddExaminingDoctor", "examining_doctor", 0, name)
    flash(f"تمت إضافة \"{name}\".")
    return redirect(url_for("examining_doctors_manage"))


@app.route("/management/examining-doctors/<int:doctor_id>/update", methods=["POST"])
@roles_required("admin")
def examining_doctor_update(doctor_id):
    db = get_db()
    name = request.form.get("name", "").strip()
    if not name:
        flash("اسم الدكتور مطلوب.")
        return redirect(url_for("examining_doctors_manage"))
    title = request.form.get("title", "الدكتور").strip()
    degree_ar = request.form.get("degree_ar", "").strip() or None
    degree_en = request.form.get("degree_en", "").strip() or None
    show_on_letterhead = bool(request.form.get("show_on_letterhead"))
    font_size_raw = request.form.get("font_size", "").strip()
    font_size = None
    if font_size_raw:
        try:
            font_size = max(8, min(30, int(font_size_raw)))
        except ValueError:
            font_size = None
    update_examining_doctor(db, doctor_id, name, title, degree_ar, degree_en, show_on_letterhead, font_size)
    log_action("UpdateExaminingDoctor", "examining_doctor", doctor_id, name)
    flash(f"تم حفظ تعديلات \"{name}\".")
    return redirect(url_for("examining_doctors_manage"))


@app.route("/management/examining-doctors/<int:doctor_id>/delete", methods=["POST"])
@roles_required("admin")
def examining_doctor_delete(doctor_id):
    db = get_db()
    delete_examining_doctor(db, doctor_id)
    log_action("DeleteExaminingDoctor", "examining_doctor", doctor_id)
    flash("تم الحذف.")
    return redirect(url_for("examining_doctors_manage"))


@app.route("/management/examining-doctors/<int:doctor_id>/move", methods=["POST"])
@roles_required("admin")
def examining_doctor_move(doctor_id):
    db = get_db()
    direction = request.form.get("direction", "")
    if direction in ("up", "down"):
        move_examining_doctor(db, doctor_id, direction)
    return redirect(url_for("examining_doctors_manage"))


# ------------------------------------------------------------------------
# مكتبة الأختام والتواقيع الرقمية — أيقونة/صفحة إدارة واحدة تسمح بإضافة أي
# عدد من الأختام (ختم المختبر نفسه + ختم/توقيع كل دكتور فاحص على حدة، لأن
# كل واحد منهم مختلف عن الثاني) بدون أي حصر. كل صورة تُحفظ دائمًا بخلفية
# بيضاء صلبة (راجع _save_stamp_image_on_white_bg) حتى تظهر واضحة وكأنها
# ختم/توقيع حقيقي فوق التقرير المطبوع، وليست "نشازًا". من نفس الشاشة يقدر
# المدير يربط أي ختم باسم دكتور فاحص محدد من القائمة (اختياري) — هذا الربط
# بس اقتراح تلقائي لاحقًا، ولا يمنع اختيار أي ختم آخر يدويًا عند إتمام
# التقرير (راجع stamp_placement_* أدناه لآلية الإلصاق الفعلي فوق تقرير
# معيّن مع إمكانية سحبه لأي موضع).
# ------------------------------------------------------------------------
@app.route("/management/stamps", methods=["GET"])
@roles_required("admin")
def stamps_manage():
    db = get_db()
    stamps = get_digital_stamps(db, active_only=False)
    doctors = get_examining_doctors_full(db)
    return render_template("management/stamps.html", stamps=stamps, doctors=doctors)


@app.route("/management/stamps/add", methods=["POST"])
@roles_required("admin")
def stamp_add():
    db = get_db()
    label = (request.form.get("label") or "").strip()
    kind = request.form.get("kind") or "stamp"
    if kind not in ("stamp", "signature", "stamp_signature"):
        kind = "stamp"
    linked_doctor_raw = request.form.get("linked_examining_doctor_id") or ""
    linked_doctor_id = int(linked_doctor_raw) if linked_doctor_raw.isdigit() else None
    file = request.files.get("image")

    if not label:
        flash("اسم/تسمية الختم أو التوقيع مطلوبة (مثلاً: ختم د. خليل حمود).")
        return redirect(url_for("stamps_manage"))
    if not file or not file.filename:
        flash("لازم ترفع صورة الختم أو التوقيع.")
        return redirect(url_for("stamps_manage"))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_STAMP_EXT:
        flash("صيغة الصورة غير مدعومة — استخدم PNG أو JPG أو WEBP.")
        return redirect(url_for("stamps_manage"))

    # نحجز id أولاً بصف مؤقت (اسم ملف فاضي) حتى نقدر نسمّي ملف الصورة
    # stamp_<id>.png بنفس رقم الصف مباشرة، ثم نحدّثه بعد حفظ الصورة فعليًا.
    new_id = add_digital_stamp(db, label, kind, image_filename="", 
                                linked_examining_doctor_id=linked_doctor_id,
                                created_by=session.get("user_id"))
    try:
        filename = _save_stamp_image_on_white_bg(file, new_id)
    except Exception:
        delete_digital_stamp(db, new_id)
        flash("تعذّر معالجة الصورة المرفوعة — تأكد إنها صورة صالحة، وإن مكتبة Pillow مثبّتة على الجهاز (pip install Pillow).")
        return redirect(url_for("stamps_manage"))
    db.execute("UPDATE digital_stamps SET image_filename=? WHERE id=?", (filename, new_id))
    db.commit()
    log_action("AddDigitalStamp", "digital_stamp", new_id, label)
    flash(f"تمت إضافة \"{label}\" لمكتبة الأختام والتواقيع.")
    return redirect(url_for("stamps_manage"))


@app.route("/management/stamps/<int:stamp_id>/update", methods=["POST"])
@roles_required("admin")
def stamp_update(stamp_id):
    db = get_db()
    label = (request.form.get("label") or "").strip()
    kind = request.form.get("kind") or "stamp"
    if kind not in ("stamp", "signature", "stamp_signature"):
        kind = "stamp"
    linked_doctor_raw = request.form.get("linked_examining_doctor_id") or ""
    linked_doctor_id = int(linked_doctor_raw) if linked_doctor_raw.isdigit() else None
    is_active = bool(request.form.get("is_active"))
    if not label:
        flash("اسم/تسمية الختم أو التوقيع مطلوبة.")
        return redirect(url_for("stamps_manage"))
    update_digital_stamp(db, stamp_id, label, kind, linked_doctor_id, is_active)
    log_action("UpdateDigitalStamp", "digital_stamp", stamp_id, label)
    flash(f"تم حفظ تعديلات \"{label}\".")
    return redirect(url_for("stamps_manage"))


@app.route("/management/stamps/<int:stamp_id>/delete", methods=["POST"])
@roles_required("admin")
def stamp_delete(stamp_id):
    db = get_db()
    stamp = get_digital_stamp(db, stamp_id)
    if stamp:
        delete_digital_stamp(db, stamp_id)
        try:
            os.remove(os.path.join(STAMPS_UPLOAD_DIR, stamp["image_filename"]))
        except OSError:
            pass
        log_action("DeleteDigitalStamp", "digital_stamp", stamp_id, stamp["label"])
    flash("تم الحذف.")
    return redirect(url_for("stamps_manage"))


# API خفيف يرجّع قائمة الأختام/التواقيع الفعّالة (JSON) — يُستخدم بالقائمة
# المنسدلة "إضافة ختم/توقيع" بشاشة إتمام/طباعة أي تقرير (راجع
# partials/stamp_picker.html).
@app.route("/api/stamps/list")
@login_required
def api_stamps_list():
    db = get_db()
    kind = request.args.get("kind") or None
    stamps = get_digital_stamps(db, kind=kind, active_only=True)
    return jsonify([{
        "id": s["id"],
        "label": s["label"],
        "kind": s["kind"],
        "doctor_name": s["doctor_name"],
        "default_width": s["default_width"],
        "image_url": url_for("static", filename=f"uploads/stamps/{s['image_filename']}"),
    } for s in stamps])


# إلصاق/تحريك ختم فوق تقرير معيّن (target_type: 'visit' لتقرير موحّد لكل
# نتائج الزيارة، أو 'order_test' لتحليل مفرد) — تُستدعى بـfetch من جافاسكربت
# كل ما المستخدم يفلت الختم بمكان جديد بعد سحبه (drag&drop)، فتتحدّث فقط
# بدل ما تتكرر (راجع upsert_stamp_placement بقاعدة البيانات).
@app.route("/api/reports/<target_type>/<int:target_id>/stamps", methods=["GET"])
@login_required
def api_report_stamps_get(target_type, target_id):
    if target_type not in ("visit", "order_test"):
        return jsonify({"error": "target_type غير صحيح"}), 400
    db = get_db()
    placements = get_stamp_placements(db, target_type, target_id)
    return jsonify([{
        "placement_id": p["id"],
        "stamp_id": p["stamp_id"],
        "label": p["label"],
        "pos_x": p["pos_x"],
        "pos_y": p["pos_y"],
        "width": p["width"] or p["default_width"],
        "image_url": url_for("static", filename=f"uploads/stamps/{p['image_filename']}"),
    } for p in placements])


@app.route("/api/reports/<target_type>/<int:target_id>/stamps", methods=["POST"])
@login_required
def api_report_stamps_place(target_type, target_id):
    if target_type not in ("visit", "order_test"):
        return jsonify({"error": "target_type غير صحيح"}), 400
    db = get_db()
    try:
        stamp_id = int(request.form.get("stamp_id"))
        pos_x = float(request.form.get("pos_x", 40))
        pos_y = float(request.form.get("pos_y", 40))
        width_raw = request.form.get("width")
        width = float(width_raw) if width_raw else None
    except (TypeError, ValueError):
        return jsonify({"error": "بيانات غير صالحة"}), 400
    placement_id = upsert_stamp_placement(db, target_type, target_id, stamp_id, pos_x, pos_y,
                                           width, placed_by=session.get("user_id"))
    log_action("PlaceStamp", target_type, target_id, f"stamp_id={stamp_id}")
    return jsonify({"ok": True, "placement_id": placement_id})


@app.route("/api/reports/stamps/<int:placement_id>/remove", methods=["POST"])
@login_required
def api_report_stamps_remove(placement_id):
    db = get_db()
    remove_stamp_placement(db, placement_id)
    log_action("RemoveStamp", "stamp_placement", placement_id)
    return jsonify({"ok": True})


def _parse_docx_rows(file_storage, parameters):
    """Read an admin-uploaded Word (.docx) reference report and pull out an
    ordered list of {"param_name", "label"} rows by matching each line/cell
    of text in the document against this test's existing parameter names.
    Returns (rows, matched_count, total_lines_found)."""
    try:
        import docx  # python-docx
    except ImportError:
        return None, 0, 0

    document = docx.Document(file_storage)
    param_by_lower = {p["name"].strip().lower(): p["name"] for p in parameters}

    def match_param(text):
        low = text.strip().lower()
        low = low.rstrip(":.").strip()
        if not low:
            return None
        if low in param_by_lower:
            return param_by_lower[low]
        for pname_low, pname in param_by_lower.items():
            if pname_low and (pname_low in low or low in pname_low):
                return pname
        return None

    raw_lines = []
    for table in document.tables:
        for trow in table.rows:
            cells = [c.text.strip() for c in trow.cells if c.text.strip()]
            if cells:
                raw_lines.append(cells[0])
    if not raw_lines:
        for para in document.paragraphs:
            text = para.text.strip()
            if text:
                raw_lines.append(text)

    rows = []
    matched = 0
    seen = set()
    for line in raw_lines:
        pname = match_param(line)
        if pname and pname in seen:
            continue
        if pname:
            seen.add(pname)
            matched += 1
        rows.append({"param_name": pname or "", "label": line})
    return rows, matched, len(raw_lines)


@app.route("/management/report-designer", methods=["GET", "POST"])
@roles_required("admin")
def report_designer():
    db = get_db()
    hardcoded_codes = set(REPORT_TEMPLATE_MAP.keys())

    if request.method == "POST":
        test_id = request.form.get("test_definition_id")
        test = db.execute("SELECT * FROM test_definitions WHERE id=?", (test_id,)).fetchone()
        if not test:
            flash("التحليل غير موجود.")
            return redirect(url_for("report_designer"))

        parameters = db.execute(
            "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (test_id,)
        ).fetchall()
        mode = request.form.get("mode", "manual")
        source_docx_name = None
        existing_tpl = get_report_template(db, test_id)
        heading_align = request.form.get("heading_align") or (existing_tpl["heading_align"] if existing_tpl else None) or "center"
        rows_align = request.form.get("rows_align") or (existing_tpl["rows_align"] if existing_tpl else None) or "right"

        if mode == "stamp":
            # تفعيل/تعطيل صندوق "إضافة ختم / توقيع" التفاعلي لهذا التحليل —
            # عام لكل أنواع التقارير (جاهزة أو مخصصة)، منفصل تمامًا عن تصميم
            # الجدول نفسه. معطّل افتراضيًا (0) بكل التحاليل القديمة والجديدة.
            enable_stamp_widget = 1 if request.form.get("enable_stamp_widget") else 0
            db.execute("UPDATE test_definitions SET enable_stamp_widget=? WHERE id=?", (enable_stamp_widget, test_id))
            db.commit()
            log_action("UpdateStampWidgetSetting", "test_definition", int(test_id), str(enable_stamp_widget))
            flash("تم حفظ إعداد صندوق الختم/التوقيع.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        if mode == "done_by":
            # سطر "Done by ..." الاختياري لهذا التحليل تحديداً (المطلوب 7) —
            # فاضي = لا يظهر أبداً بـ.footer-block أي تقرير لهذا التحليل.
            done_by_note = request.form.get("done_by_note", "").strip() or None
            db.execute("UPDATE test_definitions SET done_by_note=? WHERE id=?", (done_by_note, test_id))
            db.commit()
            log_action("UpdateDoneByNote", "test_definition", int(test_id), done_by_note or "")
            flash("تم حفظ سطر Done by.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        if mode == "spacing":
            # المسافة بين صفوف الباراميترات (المطلوب 8) — تنطبق على exam
            # rows وcustom cards وCBC وcombined panel لنفس هذا التحليل.
            # فاضي = رجوع للتباعد الافتراضي القديم (بدون أي تغيير). راجع
            # row_spacing_px أعلى الملف لكيفية تفسير القيمة المحفوظة.
            spacing_choice = request.form.get("row_spacing_preset", "").strip()
            spacing_custom = request.form.get("row_spacing_custom", "").strip()
            row_spacing_value = spacing_custom if spacing_choice == "custom" and spacing_custom else (spacing_choice or None)
            db.execute("UPDATE test_definitions SET row_spacing=? WHERE id=?", (row_spacing_value, test_id))
            db.commit()
            log_action("UpdateRowSpacing", "test_definition", int(test_id), row_spacing_value or "")
            flash("تم حفظ إعداد التباعد بين الصفوف.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        if mode == "param_overrides":
            # تسمية عرض بديلة + محاذاة رقم النتيجة لكل باراميتر (المطلوب 9ب
            # و11) — فورم واحد يرسل صفوف كل باراميترات هذا التحليل سوا
            # (label_<param_id> و align_<param_id>). فاضي/"" = رجوع للاسم
            # الأصلي أو المحاذاة الافتراضية القديمة (بدون أي تغيير).
            for p in parameters:
                label_val = request.form.get(f"label_{p['id']}", "").strip() or None
                align_val = request.form.get(f"align_{p['id']}", "").strip() or None
                if align_val not in ("near_name", "center", "near_unit"):
                    align_val = None
                db.execute(
                    "UPDATE test_parameters SET display_label=?, value_align=? WHERE id=?",
                    (label_val, align_val, p["id"]),
                )
            db.commit()
            log_action("UpdateParamOverrides", "test_definition", int(test_id), "")
            flash("تم حفظ تسميات ومحاذاة الباراميترات.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        if mode == "docx":
            file = request.files.get("docx_file")
            if not file or not file.filename:
                flash("لم تختر ملف Word.")
                return redirect(url_for("report_designer", test_definition_id=test_id))
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in ALLOWED_DOCX_EXT:
                flash("صيغة الملف يجب أن تكون .docx")
                return redirect(url_for("report_designer", test_definition_id=test_id))
            rows, matched, total = _parse_docx_rows(file, parameters)
            if rows is None:
                flash("مكتبة قراءة ملفات Word (python-docx) غير مثبتة بعد. شغّل تشغيل البرنامج.vbs مرة واحدة وأنت متصل بالإنترنت ليتم تثبيتها تلقائيًا، ثم أعد المحاولة.")
                return redirect(url_for("report_designer", test_definition_id=test_id))
            if not rows:
                flash("لم أجد أي صفوف أو نصوص داخل ملف Word هذا.")
                return redirect(url_for("report_designer", test_definition_id=test_id))
            rows_json = json.dumps(rows, ensure_ascii=False)
            source_docx_name = secure_filename(file.filename)
            save_report_template(db, test_id, test["name"], rows_json, source_docx_name, session["user_id"],
                                  heading_align=heading_align, rows_align=rows_align)
            log_action("SaveReportTemplate", "test_definition", int(test_id), f"docx:{source_docx_name}")
            flash(f"تم استيراد التصميم من Word: {matched} من {total} سطر تم ربطها تلقائيًا بنتائج التحليل. "
                  f"الشعار وترويسة الأطباء وذيل الصفحة ستُضاف تلقائيًا عند الطباعة — راجع الصفوف غير المرتبطة (إن وجدت) وعدّلها يدويًا أدناه.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        if mode == "panel":
            # إعدادات "اللوحة المجمّعة" — مستويان: (أ) التحليل كامل، تنطبق
            # على كل باراميتراته كسلوك احتياطي؛ (ب) كل باراميتر لحاله
            # (panel_color_<pid>/panel_page_break_<pid>) تكتسح مستوى التحليل
            # لنفس الباراميتر لو ضُبطت — تسمح بتلوين/فصل باراميتر وحدة بس
            # (زي NRBC) داخل تحليل متعدد الباراميترات دون التأثير على الباقي.
            panel_color = request.form.get("panel_color", "").strip()
            enable_panel_color = bool(request.form.get("enable_panel_color"))
            panel_color_val = panel_color if (enable_panel_color and panel_color and _HEX_COLOR_RE.match(panel_color)) else None
            panel_page_break = 1 if request.form.get("panel_page_break") else 0
            db.execute(
                "UPDATE test_definitions SET panel_color=?, panel_page_break=? WHERE id=?",
                (panel_color_val, panel_page_break, test_id),
            )
            for p in parameters:
                pid = p["id"]
                p_color = request.form.get(f"param_panel_color_{pid}", "").strip()
                p_enable = bool(request.form.get(f"enable_param_panel_color_{pid}"))
                p_color_val = p_color if (p_enable and p_color and _HEX_COLOR_RE.match(p_color)) else None
                p_page_break = 1 if request.form.get(f"param_panel_page_break_{pid}") else 0
                db.execute(
                    "UPDATE test_parameters SET panel_color=?, panel_page_break=? WHERE id=?",
                    (p_color_val, p_page_break, pid),
                )
            db.commit()
            log_action("UpdatePanelSettings", "test_definition", int(test_id), "panel")
            flash("تم حفظ إعدادات اللوحة المجمّعة.")
            return redirect(url_for("report_designer", test_definition_id=test_id))

        # mode == manual: rebuild the row order from the submitted list of
        # parameter ids (checked + reordered by the admin in the form).
        heading = request.form.get("heading", "").strip() or test["name"]
        ordered_param_ids = request.form.getlist("param_order")
        rows = []
        params_by_id = {str(p["id"]): p for p in parameters}
        for pid in ordered_param_ids:
            p = params_by_id.get(pid)
            if p:
                row = {"param_name": p["name"], "label": p["name"]}
                # حرية تحريك الحقول لكل صف — تُقرأ فقط لو مصمم التقرير
                # (report_designer.html) يرسلها فعليًا كحقول name_side_<id>/
                # range_position_<id> (زر أو قائمة اختيار جنب كل صف)؛ إذا ما
                # أُرسلت (كل الحالات الحالية) تبقى القيم الافتراضية كما هي
                # ولا يتغيّر أي تصميم محفوظ سابقًا.
                name_side = request.form.get(f"name_side_{pid}")
                if name_side in ("left", "right"):
                    row["name_side"] = name_side
                range_position = request.form.get(f"range_position_{pid}")
                if range_position in ("inline", "below"):
                    row["range_position"] = range_position
                # لون مخصص لهذا التحليل (اسمه ونتيجته) — اختياري، فاضي يعني
                # يبقى باللون الافتراضي بكل التقرير. وفاصل صفحة: لو مفعّل،
                # هذا التحليل يبدأ دائمًا بأعلى صفحة جديدة عند الطباعة (يُقرأ
                # بـ custom.html كـ page-break-before قبل بطاقة هذا الصف).
                row_color = request.form.get(f"row_color_{pid}", "").strip()
                if request.form.get(f"enable_color_{pid}") and row_color and _HEX_COLOR_RE.match(row_color):
                    row["color"] = row_color
                if request.form.get(f"page_break_{pid}"):
                    row["page_break_before"] = True
                rows.append(row)
        if not rows:
            flash("اختر باراميتر واحد على الأقل لتصميم التقرير.")
            return redirect(url_for("report_designer", test_definition_id=test_id))
        rows_json = json.dumps(rows, ensure_ascii=False)
        # unit_column ثابتة 1 دائمًا الآن (المطلوب: عمود نتيجة وعمود وحدة
        # مستقلّين بكل تقرير، بلا استثناء) — عمود report_templates.unit_column
        # نفسه يبقى بقاعدة البيانات (بدون DROP) لعدم فقدان بيانات قديمة، بس
        # ما عاد يُقرأ من فورم ولا يُقرأ شرطيًا بالقوالب (custom.html صارت
        # تطبع بهذا التخطيط دائمًا بغض النظر عن قيمته).
        save_report_template(db, test_id, heading, rows_json, None, session["user_id"],
                              heading_align=heading_align, rows_align=rows_align, unit_column=1)
        log_action("SaveReportTemplate", "test_definition", int(test_id), "manual")
        flash("تم حفظ تصميم التقرير. الشعار سيُضاف تلقائيًا عند الطباعة.")
        return redirect(url_for("report_designer", test_definition_id=test_id))

    all_tests = db.execute(
        "SELECT * FROM test_definitions WHERE is_active=1 ORDER BY department, name"
    ).fetchall()
    tests_status = []
    for test in all_tests:
        has_builtin = test["code"] in hardcoded_codes
        custom = get_report_template(db, test["id"])
        tests_status.append({
            "test": test,
            "has_builtin": has_builtin,
            "has_custom": bool(custom),
            "needs_design": not has_builtin and not custom,
        })

    selected_id = request.args.get("test_definition_id", type=int)
    selected_test = None
    selected_parameters = []
    selected_template = None
    selected_rows_by_param = {}
    if selected_id:
        selected_test = db.execute("SELECT * FROM test_definitions WHERE id=?", (selected_id,)).fetchone()
        if selected_test:
            selected_parameters = db.execute(
                "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (selected_id,)
            ).fetchall()
            selected_template = get_report_template(db, selected_id)
            if selected_template:
                for r in json.loads(selected_template["rows_json"] or "[]"):
                    selected_rows_by_param[r.get("param_name", "")] = r

    # ترتيب عرض الباراميترات بشاشة التصميم يدويًا: لو فيه تصميم محفوظ سابقًا،
    # نعرضهم بنفس ترتيب rows_json المحفوظ (نفس ترتيب الطباعة فعليًا) أولاً،
    # وأي باراميتر جديد أُضيف للتحليل لاحقًا (بعد آخر حفظ) يُلحق بالنهاية غير
    # مؤشر عليه — هذا يخلي "إضافة تحليل/باراميتر جديد لاحقًا" يظهر تلقائيًا
    # هنا جاهز للتأشير عليه دون أي خطوة إضافية. بدون تصميم سابق، الترتيب
    # الافتراضي هو ترتيب الإدخال بقاعدة البيانات كالمعتاد.
    ordered_selected_params = list(selected_parameters)
    if selected_template:
        params_by_name = {p["name"]: p for p in selected_parameters}
        saved_order = [r.get("param_name", "") for r in json.loads(selected_template["rows_json"] or "[]")]
        seen = set()
        ordered = []
        for name in saved_order:
            p = params_by_name.get(name)
            if p and name not in seen:
                ordered.append(p)
                seen.add(name)
        for p in selected_parameters:
            if p["name"] not in seen:
                ordered.append(p)
                seen.add(p["name"])
        ordered_selected_params = ordered

    return render_template(
        "management/report_designer.html",
        tests_status=tests_status, selected_test=selected_test,
        selected_parameters=ordered_selected_params, selected_template=selected_template,
        selected_rows_by_param=selected_rows_by_param,
    )


@app.route("/management/report-designer/preview/<int:test_definition_id>")
@roles_required("admin")
def preview_report_design(test_definition_id):
    try:
        return _preview_report_design_impl(test_definition_id)
    except Exception:
        import traceback
        tb_text = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(__file__), "error_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(datetime.now().isoformat(timespec="seconds") + f"  preview test_definition_id={test_definition_id}\n")
                f.write(tb_text)
        except Exception:
            pass
        return (
            "<h1>خطأ أثناء معاينة التصميم — test_definition_id="
            + str(test_definition_id)
            + "</h1><p>صوّر هذا النص كامل وأرسله:</p>"
            + "<pre style='direction:ltr; text-align:left; white-space:pre-wrap; "
            + "background:#f5f5f5; border:1px solid #ccc; padding:12px;'>"
            + escape(tb_text)
            + "</pre>"
        ), 500


def _preview_report_design_impl(test_definition_id):
    # Renders the exact same report template print_report() uses, but with
    # clearly-labeled sample data instead of a real order/patient — so the
    # admin can actually SEE a built-in or custom design (logo, headings,
    # row layout) from the report-designer page without needing to create a
    # real visit/result first. Reads test_definitions/test_parameters only;
    # never touches patient, visit, or result data.
    db = get_db()
    test = db.execute("SELECT * FROM test_definitions WHERE id=?", (test_definition_id,)).fetchone()
    if not test:
        return "Not found", 404

    template_name = REPORT_TEMPLATE_MAP.get(test["code"])
    custom_template = None
    if not template_name and test["report_style"] == "generic_exam":
        template_name = "reports/generic_exam.html"
    if not template_name:
        custom_template = get_report_template(db, test_definition_id)
        if not custom_template:
            flash("لا يوجد تصميم لهذا التحليل بعد لتتم معاينته. صممه أولاً بالأسفل.")
            return redirect(url_for("report_designer", test_definition_id=test_definition_id))
        if uses_order_style_report(test["department"], test["report_style"]):
            template_name = "reports/custom_v2.html"
        else:
            template_name = "reports/custom.html"

    parameters = db.execute(
        "SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (test_definition_id,)
    ).fetchall()
    units_by_name = {p["name"]: p["unit"] for p in parameters}
    highlight_by_name = {p["name"]: bool(p["highlight"]) for p in parameters}
    params_by_name_row = {p["name"]: p for p in parameters}
    row_spacing_px_value = row_spacing_px(test["row_spacing"] if "row_spacing" in test.keys() else None)
    # show_prev_values يبقى False دائمًا بالمعاينة (بلا استثناء) — هذي معاينة
    # تصميم بدون مريض حقيقي، فمافيه "نتيجة سابقة" فعلية أصلاً لأي تحليل. كان
    # يُحسب سابقًا من department_shows_previous_values(department) فقط، فيطلع
    # "Previous Result — X: — mg/dL" فاضي بكل تحليل قسمه يدعم النتيجة
    # السابقة، حتى لو ما فيه مريض إطلاقًا. النتيجة السابقة الحقيقية تُحسب
    # وتُعرض فقط بالطباعة الفعلية (_print_report_impl) لما تكون موجودة
    # وموثّقة لنفس المريض تحديداً.
    show_prev_values = False
    logo_path = get_setting(db, "logo_path", "")
    logo_url = url_for("static", filename=logo_path) if logo_path else None

    cbc_groups = None
    if test["code"] == "CBC":
        cbc_groups = []
        for group in CBC_ROW_GROUPS:
            rows = [{"name": resolve_label(params_by_name_row.get(name)), "result": "—", "unit": units_by_name.get(name, ""),
                     "low": "", "high": "", "highlight": highlight_by_name.get(name, False),
                     "previous": "—" if show_prev_values else "", "flag": None,
                     "value_align": resolve_value_align(params_by_name_row.get(name))}
                    for name in group]
            cbc_groups.append(rows)

    custom_rows = None
    custom_heading = None
    custom_heading_align = "center"
    custom_rows_align = "right"
    if custom_template:
        custom_heading = custom_template["heading"] or test["name"]
        custom_heading_align = custom_template["heading_align"] or "center"
        custom_rows_align = custom_template["rows_align"] or "right"
        row_defs = json.loads(custom_template["rows_json"] or "[]")
        custom_rows = [{
            "label": resolve_label(params_by_name_row.get(rd.get("param_name", "")), rd.get("label")),
            "result": "—", "unit": units_by_name.get(rd.get("param_name", ""), ""),
            "normal_range": "—", "range_tiers": [{"label": None, "value": "—"}],
            "normal_range2": None, "result2": None, "unit2": "",
            "previous": "—" if show_prev_values else "",
            "name_side": rd.get("name_side") or "left",
            "range_position": rd.get("range_position") or "inline",
            "name_align": rd.get("name_align"),
            "color": rd.get("color"),
            "value_align": resolve_value_align(params_by_name_row.get(rd.get("param_name", ""))),
            "flag": None,
            "page_break_before": rd.get("page_break_before", False),
        } for rd in row_defs]

    params = {p["name"]: "—" for p in parameters}

    # نفس منطق _print_report_impl بالضبط (راجع التعليق هناك) — القوالب
    # الجاهزة الحديثة (GUE/GSE/SFA وأي قالب مستقبلي بنفس نمط
    # exam_report_shared.html) تتوقع هذي المتغيرات دائمًا، وهذي المعاينة
    # كانت ما تمررها إطلاقًا فتنهار بـ UndefinedError فورًا. بما إنها معاينة
    # بلا مريض/طلب حقيقي، القيم فاضية/رمزية بدل بيانات فعلية — عدا
    # report_layout اللي نجيبها فعليًا (مستوى التحليل فقط، order_test_id=0
    # ما يطابق أي استثناء مريض حقيقي) حتى يشوف الأدمن نفس التخصيص المحفوظ.
    report_layout, report_layout_has_patient_override = get_report_layout(db, test_definition_id, 0)
    macro_params, micro_params = _build_exam_sections(test["code"], parameters, report_layout)

    auto_flag_color_enabled, show_result_flag, flag_color_map = get_report_flag_settings(db)
    return render_template(
        template_name,
        ot={"test_name": test["name"], "test_code": test["code"]}, params=params, ranges={}, units=units_by_name, cbc_groups=cbc_groups,
        custom_rows=custom_rows, custom_heading=custom_heading,
        custom_heading_align=custom_heading_align, custom_rows_align=custom_rows_align,
        show_prev_values=show_prev_values, previous_visit_date=None, previous_values={},
        repeat_header_on_print=department_shows_previous_values(test["department"]),
        logo_url=logo_url, from_other_lab=False, font_size=14 if test["code"] == "CBC" else 16,
        show_exam_signature=False,
        # نفس تفعيل/تعطيل صندوق الختم المحفوظ فعليًا لهذا التحليل، حتى تشوف
        # بالمعاينة بالضبط نفس اللي رح يطلع بالطباعة الحقيقية.
        enable_stamp_widget=bool(test["enable_stamp_widget"]) if "enable_stamp_widget" in test.keys() else False,
        stamp_target_type="test_definition", stamp_target_id=test_definition_id,
        digital_stamps=[], stamp_placements=[],
        visit_date=f"{datetime.now().day}/{datetime.now().month}/{datetime.now().year}", sex="—", age="—",
        patient_name="اسم المريض — معاينة تصميم فقط", patient_id="0000",
        referring_doctor_name="—", is_design_preview=True, preview_test_id=test_definition_id,
        test_definition_id=test_definition_id,
        sample_no="—", sample_time="—", number_of="—", patient_name_en="",
        order_test_id=0, results_by_name={}, param_notes={},
        auto_flag_color_enabled=auto_flag_color_enabled, show_result_flag=show_result_flag, AUTO_FLAG_COLORS=flag_color_map,
        row_spacing_px=row_spacing_px_value,
        done_by_note=(test["done_by_note"] or "") if "done_by_note" in test.keys() else "",
        report_layout=report_layout, report_layout_has_patient_override=report_layout_has_patient_override,
        macro_params=macro_params, micro_params=micro_params,
        params_list=parameters,
    )


@app.route("/management/report-designer/<int:test_definition_id>/start-generic-exam", methods=["GET", "POST"])
@roles_required("admin")
def start_generic_exam_report(test_definition_id):
    """يفعّل مسار reports/generic_exam.html لهذا التحليل بدل مسار "مصمم
    التقارير" العام — يبني تقرير فحص كامل (أقسام Macroscopic/Microscopic
    قابلة للتسمية، وباراميترات تُسحب بينها) من نفس صفحة معاينة الطباعة،
    بدون كتابة أي قالب HTML يدوي. لصق زر/رابط لهذا المسار بصفحة "مصمم
    التقارير" (management/report_designer.html) يفعّله لأي تحليل تختاره:
      <a href="/management/report-designer/{{ test.id }}/start-generic-exam">
        🧪 ابدأ تصميم فحص من الصفر (Macroscopic/Microscopic)
      </a>
    """
    db = get_db()
    test = db.execute("SELECT id, name, code FROM test_definitions WHERE id=?", (test_definition_id,)).fetchone()
    if not test:
        flash("التحليل غير موجود.")
        return redirect(url_for("report_designer"))
    db.execute("UPDATE test_definitions SET report_style='generic_exam' WHERE id=?", (test_definition_id,))
    db.commit()
    log_action("StartGenericExamReport", "test_definition", test_definition_id, test["name"])
    flash(
        f"تم تفعيل تصميم فحص من الصفر لـ \"{test['name']}\" ({test['code']}). "
        "اطبع أي نتيجة لهذا التحليل الآن (Results/Orders) — يطلع بقسم واحد "
        "افتراضي (Other Results) فيه كل الباراميترات، وتقدر تسمّي الأقسام "
        "وتسحب الباراميترات بينها وتلوّنها من زر ✏️ تعديل التصميم بأعلى المعاينة."
    )
    return redirect(url_for("report_designer", test_definition_id=test_definition_id))


@app.route("/master/test-catalog/<int:test_id>/report-header-style", methods=["POST"])
@roles_required("supervisor")
def set_test_report_header_style(test_id):
    """يفرض/يلغي التصميم الجديد (جدول Conventional/SI Units) لتحليل معيّن
    يدويًا، بغض النظر عن اسم قسمه (Department) — يُستخدم فقط لو الكشف
    التلقائي (uses_order_style_report أعلى الملف) ما انطبق صح على تحليل
    معيّن. value يوصل 'custom_v2' (فرض التفعيل) أو 'classic' (فرض
    الإلغاء) أو فاضي (رجوع للكشف التلقائي حسب القسم)."""
    db = get_db()
    test = db.execute("SELECT id, name FROM test_definitions WHERE id=?", (test_id,)).fetchone()
    if not test:
        return {"ok": False, "error": "التحليل غير موجود"}, 404
    value = (request.form.get("value") or "").strip()
    if value not in ("custom_v2", "classic", ""):
        return {"ok": False, "error": "قيمة غير صالحة"}, 400
    db.execute("UPDATE test_definitions SET report_style=? WHERE id=?", (value or None, test_id))
    db.commit()
    log_action("SetReportHeaderStyle", "test_definition", test_id, value or "auto")
    return {"ok": True, "value": value}


if __name__ == "__main__":
    init_db()
    astm_host.start_listener_if_enabled()

    import threading
    threading.Thread(target=whatsapp_background_worker, daemon=True).start()
    # يحمّل توكن قراءة GitHub من الإعدادات المحلية (settings.github_read_token)
    # إلى الذاكرة قبل تشغيل خيط التحديث — التوكن نفسه ما يُكتب أبداً بكود
    # auto_updater.py حتى ما يترفع مع git push ويُلغى تلقائياً من GitHub
    # (راجع الشرح المفصّل بأعلى auto_updater.py).
    _startup_db = get_db()
    auto_updater.load_token_from_db(_startup_db)
    _startup_db.close()
    # خيط فحص التحديث التلقائي — يشتغل دائماً بالخلفية، لكن ما يتحقق فعلياً
    # من GitHub إلا إذا كان هذا الجهاز "مربوط بالإنترنت" من لوحة المصمم
    # (settings.auto_update_enabled = 1). راجع auto_updater.py.
    threading.Thread(target=auto_updater.background_loop, args=(get_db,), daemon=True).start()

    app.run(host="0.0.0.0", port=9090, debug=False, threaded=True)
