# -*- coding: utf-8 -*-
r"""
apply_patch_v66.py - يضيف المتغير lab_name_ar لقوالب التقارير حتى عنوان التقرير المطبوع ياخذ اسم مختبر العميل من قاعدته
(قبلها كان الاسم مكتوب حرفيًا بالقالب base_report.html، فيطلع اسم مختبرك عند كل العملاء).
شغّله مرة واحدة من مجلد البرنامج:  python tools\apply_patch_v66.py     (نسخة احتياطية app.py.bak_v66، ويوقف لو app.py مختلف)
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")
A1 = '    logo_position = get_setting(db, "logo_position", "right")\n'
A2 = "                logo_position=logo_position,\n"
def main():
    s = open(P, encoding="utf-8").read()
    if "# v66-lab-name-ctx" in s:
        sys.exit("Already patched - nothing to do.")
    for n, a in (("A1", A1), ("A2", A2)):
        if s.count(a) != 1:
            sys.exit("STOPPED: anchor %s found %d times (expected 1). Nothing changed." % (n, s.count(a)))
    new = s.replace(A1, A1 + '    lab_name_ar = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "")  # v66-lab-name-ctx\n') \
           .replace(A2, A2 + "                lab_name_ar=lab_name_ar,\n")
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v66")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: patched (backup app.py.bak_v66). Restart the program.")
if __name__ == "__main__":
    main()
