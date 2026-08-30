# -*- coding: utf-8 -*-
"""
إرسال ملف PDF لرقم واتساب معيّن عبر أتمتة WhatsApp Web (بدون أي اشتراك أو
API مدفوع) — بالاعتماد على جلسة واتساب مسجّلة دخول على متصفح Chrome يعمل
بالخلفية على نفس جهاز السيرفر.

⚠️ ملاحظات مهمة قبل الاستخدام الفعلي:
1) هذا أسلوب غير رسمي (WhatsApp ما يوفره كـAPI معتمد)، فهو مخالف تقنيًا
   لشروط استخدام واتساب، وفيه احتمال (بسيط لكنه موجود) لحظر الرقم المستخدم
   إذا صار إرسال بكميات كبيرة أو بشكل آلي جدًا. يُفضّل استخدام رقم واتساب
   مخصص للمختبر (مو الرقم الشخصي).
2) يحتاج جهاز السيرفر أن يكون عليه Google Chrome مثبّت + مكتبة selenium.
3) أول مرة فقط: تفتح نافذة Chrome وتُظهر QR Code، يُمسح ضوئيًا من نفس
   واتساب المختبر على الموبايل (مثل أي جهاز واتساب ويب عادي). الجلسة تُحفظ
   بمجلد whatsapp_profile/ بجانب البرنامج، فما يطلب QR مرة ثانية إلا إذا
   انتهت الجلسة أو تسجيل الخروج يدويًا.
4) لازم يبقى الإنترنت متوفر وقت الإرسال فقط — البرنامج نفسه يبقى محلي
   بالكامل، وواتساب هو الجزء الوحيد اللي يحتاج اتصال.

**تثبيت لمرة وحدة:**
    pip install selenium webdriver-manager
"""
import os
import time

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "whatsapp_profile")

_driver = None


def _profile_has_saved_session() -> bool:
    """يتحقق تقريبيًا (بدون فتح أي متصفح) إذا مجلد whatsapp_profile فيه
    أصلاً جلسة واتساب محفوظة من قبل — عبر التأكد من وجود ملفات التخزين
    المحلي اللي Chrome يحفظها بعد أول تسجيل دخول ناجح لأي موقع. نعتمد هذا
    الفحص السريع لقرار "نفتح نافذة ظاهرة للـQR" أو "نشتغل بالخلفية مباشرة".
    """
    marker = os.path.join(PROFILE_DIR, "Default", "Local Storage", "leveldb")
    try:
        return os.path.isdir(marker) and len(os.listdir(marker)) > 0
    except OSError:
        return False


def _get_driver():
    """يرجّع نفس نافذة Chrome المفتوحة أصلاً (جلسة واتساب واحدة تبقى شغالة
    طول ما البرنامج شغال)، أو يفتح وحدة جديدة أول مرة.

    بعد أول تسجيل دخول ناجح (الجلسة محفوظة بمجلد whatsapp_profile)، يشتغل
    Chrome بوضع خفي (headless) — بدون أي نافذة ظاهرة — لتقليل استهلاك
    الموارد أثناء عمل البرنامج العادي. أول مرة بس (قبل ما توجد جلسة محفوظة)
    تفتح نافذة ظاهرة حتى يمكن مسح رمز QR من الموبايل."""
    global _driver
    if _driver is not None:
        try:
            _driver.title  # يتأكد إن النافذة لسا مفتوحة
            return _driver
        except Exception:
            _driver = None

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException

    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--no-first-run")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-sync")
    opts.add_argument("--disable-translate")
    opts.add_argument("--disable-features=Translate,MediaRouter")
    opts.add_argument("--mute-audio")
    opts.add_argument("--log-level=3")

    if _profile_has_saved_session():
        # جلسة محفوظة أصلاً — نشتغل بالخلفية بالكامل، بدون نافذة ظاهرة ولا
        # استهلاك موارد إضافي (هذا يحل مشكلة "البرنامج صار ثقيل بالتنقل").
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1280,900")
    else:
        # أول مرة بس — تفتح نافذة ظاهرة (مصغّرة) حتى يمكن مسح رمز QR.
        opts.add_argument("--start-minimized")

    try:
        # webdriver-manager يحمّل وينزّل نسخة chromedriver مطابقة تلقائيًا
        # لنسخة Chrome المثبتة بالجهاز — يمنع أشهر سبب لخطأ
        # "chromedriver!GetHandleVerifier" (تعارض إصدار Chrome/chromedriver).
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        _driver = webdriver.Chrome(service=service, options=opts)
    except SessionNotCreatedException as exc:
        # السبب الأشهر لهذا الخطأ بالذات: نسخة ثانية من نفس البرنامج
        # (app.py) شغّالة بنفس الوقت، وكل وحدة منهم تحاول تفتح Chrome على
        # نفس مجلد whatsapp_profile بنفس اللحظة — يخلق تعارض قفل ملفات.
        raise WhatsAppSendError(
            "تعذّر فتح متصفح واتساب — على الأغلب لأن نسخة ثانية من البرنامج "
            "شغّالة بنفس الوقت بالخلفية (تعارض على مجلد whatsapp_profile). "
            "افتح Task Manager وتأكد ما فيه أكثر من عملية python.exe أو "
            "app.exe شغّالة، سكّرهم كلهم، وشغّل البرنامج مرة وحدة بس."
        ) from exc
    except WebDriverException as exc:
        raise WhatsAppSendError(f"تعذّر تشغيل متصفح واتساب: {exc}") from exc

    _driver.get("https://web.whatsapp.com")
    return _driver


def is_logged_in(timeout=5) -> bool:
    """يتحقق إذا جلسة واتساب مسجّلة دخول أصلاً (بدون ما يفتح نافذة جديدة إذا
    غير ضروري)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = _get_driver()
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='pane-side']"))
        )
        return True
    except Exception:
        return False


def normalize_phone(phone: str, default_country_code: str = "964") -> str:
    """يحوّل رقم الهاتف المحلي (07XXXXXXXXX) لصيغة دولية بدون + أو أصفار
    بادئة، متل ما يطلبها رابط wa.me. default_country_code = العراق افتراضيًا،
    يُغيّر من ملف الإعدادات إذا المختبر ببلد ثاني."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = default_country_code + digits[1:]
    if not digits.startswith(default_country_code) and len(digits) <= 11:
        digits = default_country_code + digits.lstrip("0")
    return digits


class WhatsAppSendError(Exception):
    pass


def send_pdf(phone: str, pdf_path: str, caption: str = "", country_code: str = "964",
             wait_seconds: int = 40) -> None:
    """يرسل ملف PDF لرقم واتساب معيّن. يرمي WhatsAppSendError مع سبب واضح
    عند الفشل (لا اتصال إنترنت، رقم غير مسجّل بواتساب، الجلسة غير مسجّلة
    دخول...) حتى يسجّل الاستدعاء الفشل بطابور whatsapp_sends ويعيد المحاولة
    لاحقًا بدل ما يفشل البرنامج بالكامل."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    if not os.path.exists(pdf_path):
        raise WhatsAppSendError(f"ملف الـPDF غير موجود: {pdf_path}")

    phone_number = normalize_phone(phone, country_code)
    if not phone_number:
        raise WhatsAppSendError("رقم هاتف المريض غير صالح أو غير مسجّل.")

    driver = _get_driver()

    if not is_logged_in(timeout=8):
        raise WhatsAppSendError(
            "جلسة واتساب ويب غير مسجّلة دخول على السيرفر. افتح نافذة "
            "Chrome (whatsapp_profile) وامسح رمز QR مرة وحدة من موبايل "
            "المختبر."
        )

    driver.get(f"https://web.whatsapp.com/send?phone={phone_number}")

    try:
        # ينتظر ظهور مربّع كتابة الرسالة = يعني الرقم صحيح والمحادثة فتحت
        WebDriverWait(driver, wait_seconds).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[@contenteditable='true'][@data-tab]")
            )
        )
    except TimeoutException:
        # واتساب يعرض تنبيه "Phone number shared via url is invalid" إذا
        # الرقم مو مسجّل أصلاً بواتساب
        raise WhatsAppSendError(
            "تعذّر فتح محادثة مع هذا الرقم — تأكد إن رقم المريض صحيح "
            "ومسجّل بواتساب، أو إن الإنترنت متوفر."
        )

    # زر المرفقات (📎) ثم اختيار "مستند"
    try:
        attach_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[@title='Attach' or @title='إرفاق']"))
        )
        attach_btn.click()
        time.sleep(0.5)

        # حقل رفع الملف الخاص بـ"مستند" (input[type=file] مخفي بواجهة واتساب)
        file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
        doc_input = None
        for fi in file_inputs:
            accept = fi.get_attribute("accept") or ""
            if "pdf" in accept or accept == "" or "*" in accept:
                doc_input = fi
        if doc_input is None and file_inputs:
            doc_input = file_inputs[-1]
        if doc_input is None:
            raise WhatsAppSendError("تعذّر إيجاد زر رفع الملف بواجهة واتساب ويب (قد تكون الواجهة تغيّرت).")

        doc_input.send_keys(os.path.abspath(pdf_path))
        time.sleep(2)

        if caption:
            caption_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@contenteditable='true'][@data-tab]")
                )
            )
            caption_box.send_keys(caption)

        send_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='send']"))
        )
        send_btn.click()
        time.sleep(2)
    except WhatsAppSendError:
        raise
    except Exception as exc:
        # نقصر رسالة الخطأ الخام (أحيانًا ستاك تريس طويل جداً من chromedriver
        # نفسه) حتى تبقى قابلة للقراءة بطابور واتساب — النص الكامل يبقى
        # بسجلّات البرنامج لو احتجته لاحقًا بالتشخيص.
        msg = str(exc)
        if len(msg) > 400:
            msg = msg[:400] + "…"
        raise WhatsAppSendError(f"فشل إرسال الملف عبر واتساب ويب: {msg}")


def has_internet(timeout=3) -> bool:
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except OSError:
        return False
