"""
نظام ترخيص البرنامج (Offline License System)
=================================================
يعمل بالكامل بدون انترنت. آلية العمل:

1. عند أول تشغيل للبرنامج على أي جهاز، يُفعَّل تلقائياً وضع تجريبي (Trial)
   مدته 3 أيام، مربوط بمعرّف الجهاز (Hardware ID) المحسوب من رقم اللوحة
   الأم/القرص الصلب (وليس من الـ IP، لأن الـ IP يتغيّر). الـ IP يُسجَّل فقط
   لغرض المعلومة/المتابعة.

2. عند انتهاء الفترة التجريبية، أو عند نقل البرنامج لجهاز آخر (Hardware ID
   يختلف عن المسجَّل)، يتوقف البرنامج عن العمل ويعرض للمستخدم معرّف جهازه
   ويطلب منه إرساله للمصمم (مثلاً عبر واتساب).

3. المصمم يدخل لوحة "إعدادات المصمم" الخاصة به داخل نفس البرنامج (محمية
   باسم مستخدم/كلمة مرور لا يعرفها غيره)، يدخل معرّف جهاز العميل، ويولّد
   كود تفعيل موقّع رقمياً (HMAC) خاص بذلك الجهاز فقط ولا يعمل على أي جهاز
   غيره، مع تاريخ صلاحية يحدده المصمم (تجريبي/مدة معينة/دائم).

4. المصمم يرسل للعميل اسم مستخدم + الكود عبر واتساب. عند إدخالهما في شاشة
   "تفعيل الترخيص" يتحقق البرنامج من التوقيع محلياً (بدون أي اتصال انترنت)
   ويقارنه بمعرّف الجهاز الحالي.

⚠️ مهم جداً للمصمم: غيّر قيمة SECRET_KEY أدناه إلى نص سرّي من اختيارك قبل
تسليم البرنامج لأي عميل، ولا تشاركه مع أحد إطلاقاً — هو الأساس الذي تُبنى
عليه كل أكواد التفعيل. لو سُرّب هذا المفتاح يصبح بإمكان أي شخص توليد أكواد
تفعيل بنفسه.
"""
import base64
import hashlib
import hmac
import os
import platform
import socket
import subprocess
from datetime import date, datetime, timedelta

from database import hash_password

# 🔒 غيّرها أنت (المصمم) قبل توزيع البرنامج على أي عميل — سرّية بالكامل
SECRET_KEY = "gcJhWIdS2qxTiTBFtXx4ePi8nwJc3OajQCLVapusbu1iccWI"

TRIAL_DAYS = 3


# ------------------------------------------------------------ hardware id --
def _raw_machine_fingerprint():
    system = platform.system()
    parts = []
    try:
        if system == "Windows":
            out = subprocess.check_output(
                "wmic csproduct get uuid", shell=True,
                stderr=subprocess.DEVNULL, timeout=5,
            ).decode(errors="ignore")
            lines = [ln.strip() for ln in out.splitlines() if ln.strip() and "UUID" not in ln.upper()]
            if lines:
                parts.append(lines[0])
            out2 = subprocess.check_output(
                "wmic diskdrive get serialnumber", shell=True,
                stderr=subprocess.DEVNULL, timeout=5,
            ).decode(errors="ignore")
            lines2 = [ln.strip() for ln in out2.splitlines() if ln.strip() and "SERIAL" not in ln.upper()]
            if lines2:
                parts.append(lines2[0])
        elif system == "Linux":
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(p):
                    with open(p) as f:
                        parts.append(f.read().strip())
                    break
        elif system == "Darwin":
            out = subprocess.check_output(
                "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID",
                shell=True, stderr=subprocess.DEVNULL, timeout=5,
            ).decode(errors="ignore")
            parts.append(out.strip())
    except Exception:
        pass
    # يبقى موجود دائماً كخيار احتياطي حتى لو فشلت كل الطرق أعلاه
    import uuid as _uuid
    parts.append(str(_uuid.getnode()))
    return "|".join(parts)


def get_hardware_id():
    """معرّف ثابت للجهاز، لا يتغيّر إلا إذا تغيّر الجهاز فعلياً (لوحة أم/قرص)."""
    raw = _raw_machine_fingerprint()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    short = digest[:16]
    return "-".join(short[i:i + 4] for i in range(0, 16, 4))


def get_local_ip():
    """للمعلومة والتوثيق فقط — لا يُستخدم كأساس للقفل لأنه يتغيّر."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "0.0.0.0"


# --------------------------------------------------------- activation codes --
def _b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:12].upper()


def generate_activation_code(hardware_id, expiry_date, is_trial=False):
    """expiry_date: نص 'YYYY-MM-DD' أو None (دائم). يعيد كود نصي يُرسَل للعميل.
    is_trial: يُطبَع داخل الكود نفسه (وليس فقط في سجل المصمم) حتى يقدر جهاز
    العميل يميّز التجريبي عن أي ترخيص آخر له نفس عدد الأيام، بدون اعتماد
    على أي شيء غير الكود نفسه."""
    hardware_id = hardware_id.strip().upper()
    exp_str = expiry_date or "PERM"
    trial_flag = "T" if is_trial else "F"
    payload = f"{hardware_id}|{exp_str}|{trial_flag}"
    sig = _sign(payload)
    raw = f"{exp_str}|{trial_flag}|{sig}"
    flat = _b32(raw.encode())
    return "-".join(flat[i:i + 5] for i in range(0, len(flat), 5))


def verify_activation_code(hardware_id, code):
    """يتحقق من الكود محلياً بدون انترنت. يعيد (نجاح, تاريخ_الانتهاء_أو_None, تجريبي؟, رسالة_خطأ)."""
    hardware_id = hardware_id.strip().upper()
    try:
        flat = code.replace("-", "").replace(" ", "").upper()
        pad = "=" * (-len(flat) % 8)
        raw = base64.b32decode(flat + pad).decode("utf-8")
        exp_str, trial_flag, sig = raw.split("|", 2)
    except Exception:
        # يدعم أيضاً الأكواد القديمة (قبل إضافة علامة التجريبي) التي لا
        # تحتوي حقل trial_flag، حتى لا تنكسر أكواد صدرت سابقاً.
        try:
            flat = code.replace("-", "").replace(" ", "").upper()
            pad = "=" * (-len(flat) % 8)
            raw = base64.b32decode(flat + pad).decode("utf-8")
            exp_str, sig = raw.split("|", 1)
            trial_flag = "F"
            payload = f"{hardware_id}|{exp_str}"
            expected = _sign(payload)
            if not hmac.compare_digest(sig, expected):
                return False, None, False, "هذا الكود غير مطابق لهذا الجهاز — تأكد أن معرّف الجهاز المُرسَل للمصمم صحيح"
            expiry = None if exp_str == "PERM" else exp_str
            return True, expiry, False, None
        except Exception:
            return False, None, False, "كود التفعيل غير صالح — تأكد من نسخه كاملاً بدون أخطاء"

    payload = f"{hardware_id}|{exp_str}|{trial_flag}"
    expected = _sign(payload)
    if not hmac.compare_digest(sig, expected):
        return False, None, False, "هذا الكود غير مطابق لهذا الجهاز — تأكد أن معرّف الجهاز المُرسَل للمصمم صحيح"

    expiry = None if exp_str == "PERM" else exp_str
    return True, expiry, trial_flag == "T", None


# ------------------------------------------------------------ license state --
def ensure_license_row(db):
    row = db.execute("SELECT * FROM license_info WHERE id=1").fetchone()
    if row is None:
        hw = get_hardware_id()
        now = datetime.now()
        # لا يوجد أي تفعيل تلقائي بعد الآن — أول تشغيل يبقى "بانتظار التفعيل"
        # لحد ما المصمم يعطي المستخدم يوزر/كود (تجريبي أو غيره) لهذا الجهاز
        # بالتحديد. هذا يضمن ما أحد يشغّل البرنامج على أي جهاز بدون علم المصمم.
        db.execute(
            "INSERT INTO license_info "
            "(id, hardware_id, install_date, status, license_username, license_expiry, last_ip, last_checked) "
            "VALUES (1, ?, ?, 'pending', NULL, NULL, ?, ?)",
            (hw, now.isoformat(timespec="seconds"), get_local_ip(), now.isoformat(timespec="seconds")),
        )
        db.commit()
        row = db.execute("SELECT * FROM license_info WHERE id=1").fetchone()
    return row


def check_license(db):
    """يُستدعى قبل كل طلب تقريباً. يعيد dict فيه status من:
    pending / active / expired / hardware_mismatch / revoked
    (pending = جهاز جديد لسا ما انطاله أي كود تفعيل إطلاقاً، حتى لو تجريبي)
    (revoked = المصمم ألغى ترخيص هذا الجهاز عن بُعد — راجع mark_revoked)
    """
    row = ensure_license_row(db)
    current_hw = get_hardware_id()
    db.execute(
        "UPDATE license_info SET last_ip=?, last_checked=? WHERE id=1",
        (get_local_ip(), datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()

    if row["status"] == "revoked":
        return {
            "status": "revoked", "hardware_id": current_hw,
            "expiry": row["license_expiry"], "revoked_reason": row["revoked_reason"],
        }

    if row["status"] == "pending":
        return {"status": "pending", "hardware_id": current_hw, "expiry": None}

    if row["hardware_id"] != current_hw:
        return {
            "status": "hardware_mismatch",
            "hardware_id": current_hw,
            "stored_hardware_id": row["hardware_id"],
            "expiry": row["license_expiry"],
        }

    days_left = None
    if row["license_expiry"]:
        try:
            exp = date.fromisoformat(row["license_expiry"])
            days_left = (exp - date.today()).days
            if days_left < 0:
                return {
                    "status": "expired",
                    "hardware_id": current_hw,
                    "expiry": row["license_expiry"],
                    "days_left": days_left,
                    "is_trial": bool(row["is_trial"]),
                }
        except Exception:
            pass

    return {
        "status": row["status"],
        "hardware_id": current_hw,
        "expiry": row["license_expiry"],
        "license_username": row["license_username"],
        "days_left": days_left,
        "is_trial": bool(row["is_trial"]),
    }


def apply_activation(db, username, code):
    username = (username or "").strip()
    if not username:
        return False, "الرجاء إدخال اسم المستخدم الذي أعطاك إياه المصمم"
    hw = get_hardware_id()
    ok, expiry, is_trial, err = verify_activation_code(hw, code)
    if not ok:
        return False, err
    # تفعيل جديد ناجح يلغي أي حالة "ملغى عن بُعد" سابقة لهذا الجهاز — المصمم
    # هو نفسه من أصدر هذا الكود الجديد، فهو بذلك يعيد السماح للجهاز.
    db.execute(
        "UPDATE license_info SET status='active', license_username=?, license_expiry=?, "
        "hardware_id=?, last_checked=?, is_trial=?, revoked_reason=NULL WHERE id=1",
        (username, expiry, hw, datetime.now().isoformat(timespec="seconds"), 1 if is_trial else 0),
    )
    db.commit()
    return True, None


def mark_revoked(db, reason=None):
    """يُستدعى فقط من auto_updater.check_revocation عند لقاء معرّف جهاز هذا
    التنصيب داخل قائمة الإلغاء البعيدة على GitHub. يقفل البرنامج فوراً
    بنفس شاشة 'تفعيل الترخيص' لكن بحالة revoked وبسبب الإلغاء (إن وُجد)،
    ويتطلب كود تفعيل جديد من المصمم للاستمرار."""
    ensure_license_row(db)
    db.execute(
        "UPDATE license_info SET status='revoked', revoked_reason=? WHERE id=1",
        (reason or "",),
    )
    db.commit()


def log_issued_code(db, hardware_id, username, expiry, code):
    db.execute(
        "INSERT INTO license_issue_log (hardware_id, username, expiry, code, issued_at) VALUES (?,?,?,?,?)",
        (hardware_id.strip().upper(), username, expiry or "دائم", code, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


# --------------------------------------------------------------- designer --
def designer_exists(db):
    return db.execute("SELECT 1 FROM designer_account WHERE id=1").fetchone() is not None


def create_designer_account(db, username, password):
    db.execute(
        "INSERT INTO designer_account (id, username, password_hash) VALUES (1, ?, ?)",
        (username.strip(), hash_password(password)),
    )
    db.commit()


def verify_designer(db, username, password):
    row = db.execute("SELECT * FROM designer_account WHERE id=1").fetchone()
    if not row:
        return False
    return row["username"] == (username or "").strip() and row["password_hash"] == hash_password(password)


def change_designer_password(db, new_password):
    db.execute("UPDATE designer_account SET password_hash=? WHERE id=1", (hash_password(new_password),))
    db.commit()
