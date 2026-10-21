# -*- coding: utf-8 -*-
r"""
apply_patch_v74.py - أرشيف PDF: زر "فتح" يفتح التقرير دائمًا (PDF أو صفحة جاهزة للطباعة) بدل الرجوع برسالة "الملف غير موجود".
  1) لو ملف الأرشيف غير موجود وتعذّر توليده -> يفتح نفس التقرير (اللوحة المجمّعة) مباشرة بنافذة مستقلة، مع زر طباعة / حفظ كـPDF.
  2) سبب فشل توليد الـPDF يتسجّل بـ error_log.txt (بدل ما يختفي بصمت) حتى نعرف السبب بالضبط.
شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v74.py        (نسخة احتياطية app.py.bak_v74، ويوقف لو app.py مختلف)
وانسخ templates\pdf_archive.html (زر فتح بنافذة مستقلة).
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")

HELPERS = r'''def _v74_log_exc(msg):
    """يكتب سبب الفشل + traceback بـ error_log.txt (بدل ما نبلعه بصمت)."""
    try:
        import traceback as _tb
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_log.txt"), "a", encoding="utf-8") as _f:
            _f.write("\n[%s] %s\n%s\n" % (datetime.now().isoformat(timespec="seconds"), msg, _tb.format_exc()))
    except Exception:
        pass


def _v74_printable_html(html_content):
    """لما يتعذّر توليد PDF: نعرض التقرير نفسه مع شريط (لا يُطبع) فيه زر طباعة / حفظ كـPDF."""
    if not isinstance(html_content, str) or "</body>" not in html_content:
        return html_content
    bar = ('<style>@media print{#lisV74Bar{display:none!important}}</style>'
           '<div id="lisV74Bar" style="position:fixed;top:8px;left:8px;z-index:99999;background:#fff;border:1px solid #94A3B8;'
           'border-radius:10px;padding:6px 12px;font:13px Tahoma,Arial,sans-serif;direction:rtl;box-shadow:0 3px 12px rgba(0,0,0,.25);">'
           '<button onclick="window.print()" style="background:#205072;color:#fff;border:0;border-radius:7px;padding:6px 14px;'
           'font:700 13px Tahoma;cursor:pointer;">🖨 طباعة / حفظ كـ PDF</button>'
           '<span style="color:#64748B;margin-inline-start:8px;">(بنافذة الطباعة اختر الوجهة: Save as PDF)</span></div>')
    return html_content.replace("</body>", bar + "</body>", 1)


def _serve_pdf_or_html(html_content, prefix):'''

S_OLD = 'def _serve_pdf_or_html(html_content, prefix):'
R_OLD = '''    except Exception:
        pass
    return html_content


@app.route("/reports/pdf/test/<int:order_test_id>")'''
R_NEW = '''    except Exception:
        _v74_log_exc("pdf_export failed (_serve_pdf_or_html)")
    return _v74_printable_html(html_content)


@app.route("/reports/pdf/test/<int:order_test_id>")'''

M_OLD = '''    except Exception:
        return False

    save_saved_report(
        db, visit_id, visit["patient_id"], visit["full_name"], visit["registration_number"],'''
M_NEW = '''    except Exception:
        _v74_log_exc("PDF archive generation failed for visit %s" % visit_id)
        return False

    save_saved_report(
        db, visit_id, visit["patient_id"], visit["full_name"], visit["registration_number"],'''

O_OLD = '''        flash("الملف غير موجود بمجلد الأرشيف — يمكن انحذف أو انقل يدويًا من خارج البرنامج.")
        return redirect(url_for("pdf_archive"))'''
O_NEW = '''        # v74: تعذّر توليد/إيجاد الملف المؤرشف — نفتح التقرير نفسه (PDF أو صفحة جاهزة للطباعة) بدل الرجوع للأرشيف برسالة
        return redirect(url_for("report_pdf_visit", visit_id=visit_id))'''

V_OLD = '''    html_content = _build_combined_designed_reports_html(visit_id)
    _restore_printed_at(db, snap)
    if not html_content:'''
V_NEW = '''    html_content = None
    try:   # نفس "اللوحة المجمّعة" المصممة اللي تنطبع (مثل الأرشفة v72)، وإلا المولّد القديم
        session.setdefault("interface", "both")
        _h74 = print_combined_panel(visit_id)
        html_content = _h74 if isinstance(_h74, str) and len(_h74) > 500 else None
    except Exception:
        _v74_log_exc("print_combined_panel failed (report_pdf_visit)")
    if not html_content:
        html_content = _build_combined_designed_reports_html(visit_id)
    _restore_printed_at(db, snap)
    if not html_content:'''


def main():
    s = open(P, encoding="utf-8").read()
    if "_v74_log_exc" in s:
        sys.exit("Already patched - nothing to do.")
    for n, a in (("S", S_OLD), ("R", R_OLD), ("M", M_OLD), ("O", O_OLD), ("V", V_OLD)):
        c = s.count(a)
        if c != 1:
            sys.exit("STOPPED: anchor %s found %d times (expected 1). app.py differs from what this patch expects - nothing changed." % (n, c))
    new = s.replace(S_OLD, HELPERS).replace(R_OLD, R_NEW).replace(M_OLD, M_NEW).replace(O_OLD, O_NEW).replace(V_OLD, V_NEW)
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v74")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: app.py patched (backup app.py.bak_v74). Copy templates\\pdf_archive.html too, then restart the program.")


if __name__ == "__main__":
    main()
