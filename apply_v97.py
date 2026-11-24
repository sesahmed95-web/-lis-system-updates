# -*- coding: utf-8 -*-
"""
apply_v97.py - يضيف سطور «تفاصيل الإحصائيات» لملف app.py الموجود عندك (بدون استبداله).
التشغيل داخل مجلد البرنامج (نفس مكان app.py):   py apply_v97.py
- يعمل نسخة احتياطية app.py.bak_v97 أولاً.
- لو التعديل موجود مسبقاً يقول ذلك ولا يكرره.
"""
import io, os, shutil, sys

BLOCK = '''
# ===================== v97: تفاصيل الإحصائيات (lis_stats_plus.py) =====================
# ضغط على أي تاريخ بالإحصائيات ← مرضى اليوم وتحاليلهم؛ مختبرات أرسلت لنا؛ تحاليل أرسلناها لمختبرات؛ PDF + واتساب.
def _v97_make_pdf(html_content, name):
    import pdf_export
    p = pdf_export.make_temp_pdf_path(re.sub(r"[^\\w\\-]+", "_", name))
    _v86_html_to_pdf(html_content, request.url_root, p)
    return p


try:
    import lis_stats_plus as _v97_sp
    _v97_sp.install(app, dict(get_db=get_db, login_required=login_required, get_setting=get_setting, set_setting=set_setting,
                              make_pdf=_v97_make_pdf, open_wa=_open_whatsapp_with_pdf))
except Exception as _v97_e:
    print("lis_stats_plus not loaded:", _v97_e)
# ===================== end v97 =====================
'''
ANCHOR = "# ===================== end v94 =====================\n"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, "app.py")
    if not os.path.exists(p):
        sys.exit("ما لقيت app.py بهذا المجلد. شغّل الملف من مجلد البرنامج.")
    if not os.path.exists(os.path.join(here, "lis_stats_plus.py")):
        sys.exit("انسخ lis_stats_plus.py لنفس المجلد أولاً.")
    s = io.open(p, encoding="utf-8").read()
    if "v97: " in s and "lis_stats_plus" in s:
        print("التعديل موجود مسبقاً - ما تغيّر شي."); return
    for need in ("_v86_html_to_pdf", "_open_whatsapp_with_pdf", "def login_required"):
        if need not in s:
            sys.exit("app.py عندك ما فيه %s - أرسل لي الملف حتى أطابقه." % need)
    if s.count(ANCHOR) == 1:
        s = s.replace(ANCHOR, ANCHOR + BLOCK, 1)
    else:                                   # ما لقينا علامة v94: نحطها قبل بداية تشغيل السيرفر
        mark = "\nif __name__ == \"__main__\":"
        i = s.rfind(mark)
        if i < 0:
            sys.exit("ما قدرت أحدد مكان الإضافة بـ app.py - أرسل لي الملف.")
        s = s[:i] + "\n" + BLOCK + s[i:]
    shutil.copy2(p, p + ".bak_v97")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    compile(s, p, "exec")
    print("تم: أضفت v97 إلى app.py (النسخة القديمة: app.py.bak_v97)")


if __name__ == "__main__":
    main()
