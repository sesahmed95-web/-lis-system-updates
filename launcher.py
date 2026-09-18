"""
launcher.py
-----------
هذا الملف بديل عن تشغيل "python app.py" يدويًا من التيرمنال. وظيفته:
1. يشغّل سيرفر Flask (نفس app.py) بالخلفية بدون ما يفتح نافذة تيرمنال سوداء.
2. ينتظر لين السيرفر يصير جاهز فعليًا (بدل انتظار وقت ثابت قد يفشل أو يبطّئ).
3. يفتح نافذة "شبيهة ببرنامج مستقل" (بدون شريط عنوان متصفح ولا تبويبات)
   تشير إلى البرنامج المحلي -- هذا هو نفس الشكل الظاهر بالصور اللي رفعتها،
   ويشتغل بأي حاسبة فيها Edge (موجود افتراضيًا بكل ويندوز 10/11) حتى لو ما
   فيها Chrome.

هذا هو الملف اللي تعطيه لـ PyInstaller (مو app.py مباشرة) عشان الناتج
النهائي يكون تجربة "افتح البرنامج واشتغل" بضغطة وحدة، بدون تيرمنال ولا
أوامر يدوية.

الاستخدام أثناء التطوير عندك (بدون تغليف):
    python launcher.py

أمر التغليف بـPyInstaller (يشغّل من نفس مجلد البرنامج بجهاز ويندوز):
    pyinstaller --onefile --noconsole --name "SpecializedHematologistLab" ^
        --add-data "templates;templates" ^
        --add-data "static;static" ^
        --icon "app_icon.ico" ^
        launcher.py

ملاحظات مهمة:
- --noconsole يمنع ظهور نافذة تيرمنال سوداء بالخلفية.
- --add-data يضمن نسخ مجلدي templates وstatic داخل الـexe (PyInstaller
  ما يكتشفهم تلقائيًا لأنهم يُحمَّلون بـrender_template/url_for وقت
  التشغيل، مو باستيراد Python مباشر).
- إذا عندك ملفات ثانية يستخدمها البرنامج (مثل الشعار الافتراضي بمجلد
  static، أو ملف lis.db فارغ لأول تشغيل)، أضفها بنفس أسلوب --add-data.
- شغّل هذا الأمر بجهاز ويندوز (مو من هذا المحادثة) لأن PyInstaller يبني
  ملف .exe يشتغل بنفس نظام التشغيل اللي بنيته فيه بالضبط.
"""

import os
import sys
import time
import threading
import socket
import webbrowser
import subprocess

PORT = 9090
URL = f"http://127.0.0.1:{PORT}"

# عنوان النافذة والأيقونة يظهران من <title> بصفحات البرنامج نفسها ومن
# ملف app_icon.ico اللي تمرره لـPyInstaller بـ--icon أعلاه -- ما يحتاجون
# ضبط هنا.


def _port_is_open(port, host="127.0.0.1", timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_server(port, max_wait_seconds=20):
    """ينتظر لين Flask يصير جاهز فعليًا (بدل time.sleep(2) ثابت اللي قد
    يفشل بجهاز بطيء أو يبطّئ بجهاز سريع)."""
    started = time.time()
    while time.time() - started < max_wait_seconds:
        if _port_is_open(port):
            return True
        time.sleep(0.2)
    return False


def _start_flask_server():
    # يستورد app.py نفسه ويشغّله بنفس الخيط -- هذا يفترض إن app.py
    # يحتوي "if __name__ == '__main__': ... app.run(...)"، فنستدعي
    # app.run() مباشرة هنا بدل تشغيل app.py كملف مستقل، حتى يشتغل صح
    # جوّا ملف exe واحد بدون الحاجة لعملية Python ثانية منفصلة.
    import app as flask_app_module  # يفترض وجود app.py بنفس المجلد
    flask_app_module.init_db()
    flask_app_module.app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def _open_app_window():
    """يفتح نافذة "شبيهة ببرنامج مستقل" (بدون شريط عنوان/تبويبات متصفح)
    تشير للبرنامج المحلي -- بالترتيب: Edge (موجود افتراضيًا بكل ويندوز)
    ثم Chrome لو موجود، وإذا ما فيه أي منهم يفتح بالمتصفح الافتراضي
    العادي (تجربة أقل احترافية بس البرنامج يبقى شغّال)."""
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in edge_paths + chrome_paths:
        if os.path.exists(exe):
            subprocess.Popen([exe, f"--app={URL}"])
            return
    # لا Edge ولا Chrome بمساراتهم الافتراضية -- افتح بالمتصفح الافتراضي
    # (تجربة عادية بشريط عنوان، بس البرنامج يبقى شغّال ومتاح).
    webbrowser.open(URL)


def main():
    server_thread = threading.Thread(target=_start_flask_server, daemon=True)
    server_thread.start()

    if _wait_for_server(PORT):
        _open_app_window()
    else:
        # السيرفر ما جاهز بعد 20 ثانية -- افتح المتصفح برضو، المتصفح نفسه
        # يعيد المحاولة لو الصفحة أول مرة تطلع خطأ اتصال.
        _open_app_window()

    # يبقي العملية شغّالة (السيرفر بخيط داخلي) لين المستخدم يسكّر النافذة
    # يدويًا من مدير المهام لو احتاج -- بالتطبيق الفعلي الأفضل نربط هذا
    # بمراقبة نافذة المتصفح وإغلاق العملية تلقائيًا لما يسكّرها المستخدم؛
    # هذا تحسين ممكن نضيفه لاحقًا لو احتجته.
    server_thread.join()


if __name__ == "__main__":
    main()
