# -*- coding: utf-8 -*-
"""
apply_v98.py - يرقّي سطور v97 في app.py إلى v98 (جدول الإحصائيات الجديد + المرضى من البرنامجين + حسابات الأطباء + الصرفيات).
التشغيل داخل مجلد app.py:   py apply_v98.py     (نسخة احتياطية app.py.bak_v98 أولاً؛ تشغيله مرتين لا يضر)
"""
import io, os, re, shutil, sys

BLOCK = '''# ===================== v98: تفاصيل الإحصائيات (lis_stats_plus.py) =====================
def _v98_make_pdf(html_content, name):
    import pdf_export
    p = pdf_export.make_temp_pdf_path(re.sub(r"[^\\w\\-]+", "_", name))
    _v86_html_to_pdf(html_content, request.url_root, p)
    return p


try:
    import lis_stats_plus as _v98_sp
    try:
        import lis_cloud_bridge as _v98_cb
        _v98_cloud = _v98_cb.make(get_db, get_setting)
    except Exception as _v98_ce:
        print("lis_cloud_bridge not loaded:", _v98_ce)
        _v98_cloud = None
    _v98_sp.install(app, dict(get_db=get_db, login_required=login_required, get_setting=get_setting, set_setting=set_setting,
                              make_pdf=_v98_make_pdf, open_wa=_open_whatsapp_with_pdf, cloud_logs=_v98_cloud))
except Exception as _v98_e:
    print("lis_stats_plus not loaded:", _v98_e)
# ===================== end v98 =====================
'''


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, "app.py")
    if not os.path.exists(p):
        sys.exit("ما لقيت app.py بهذا المجلد. شغّل الملف من مجلد البرنامج.")
    for need in ("lis_stats_plus.py", "lis_cloud_bridge.py"):
        if not os.path.exists(os.path.join(here, need)):
            sys.exit("انسخ %s لنفس المجلد أولاً." % need)
    s = io.open(p, encoding="utf-8").read()
    if "# ===================== v98:" in s:
        print("v98 موجود مسبقاً - ما تغيّر شي."); return
    pat = re.compile(r"# ===================== v97: .*?# ===================== end v97 =====================\n", re.S)
    if pat.search(s):
        s = pat.sub(lambda m: BLOCK, s, count=1)
    else:
        mark = "\nif __name__ == \"__main__\":"
        i = s.rfind(mark)
        if i < 0:
            sys.exit("ما قدرت أحدد مكان الإضافة بـ app.py - أرسل لي الملف.")
        s = s[:i] + "\n" + BLOCK + s[i:]
    shutil.copy2(p, p + ".bak_v98")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    compile(s, p, "exec")
    print("تم: ترقية الإحصائيات إلى v98 (النسخة القديمة: app.py.bak_v98)")


if __name__ == "__main__":
    main()
