# -*- coding: utf-8 -*-
r"""
apply_patch_v76.py - اسم المختبر + الشعار + بوابة النتائج تنتقل مع الـSetup حتى لو العميل عنده قاعدة بيانات قديمة.
  1) tools\make_client_installer.py : يولّد portal_preset.json (اسم المختبر، هاتف، عنوان، بوابة النتائج، الشعار) من قاعدة العميل المنظّفة
     ويضمّه داخل الـSetup نفسه. عند أول تشغيل بعد التنصيب يتطبّق تلقائيًا (ولا يمس المرضى) — بدل ما تعتمد على قاعدة lis.db
     اللي الـSetup ما يستبدلها إذا العميل عنده واحدة.
  2) app.py : زر "QR المريض" لما بوابة النتائج غير مضبوطة: الاستقبال يشوف رسالة واضحة ويرجع لصفحته بدل ما يُرمى لصفحة الإعدادات
     (الممنوعة عنه) ويطلع "هذي الصفحة متاحة فقط لواجهة المختبر".
شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v76.py     (نسخ احتياطية .bak_v76، ويوقف لو أي ملف مختلف)
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
INS = os.path.join(ROOT, "tools", "make_client_installer.py")

# ---------------- make_client_installer.py ----------------
I_FUNC_ANCHOR = "def main():\n"
I_FUNC = r'''def _write_embedded_preset(bld):
    """يولّد portal_preset.json داخل مجلد البناء من إعدادات قاعدة العميل المنظّفة (اسم المختبر/الهاتف/العنوان/البوابة/الشعار)
    حتى ينتقل مع الـSetup ويتطبق عند أول تشغيل حتى لو العميل عنده lis.db قديمة (الـSetup ما يستبدل قاعدته)."""
    import base64, json, sqlite3
    keys = ("app_name", "app_name_ar", "lab_name", "lab_phone", "lab_address", "portal_enabled", "portal_mode", "portal_url",
            "portal_api_key", "portal_pdf_enabled", "portal_title")
    con = sqlite3.connect(os.path.join(bld, "lis.db"))
    try:
        rows = con.execute("SELECT key, value FROM settings WHERE key IN (%s) OR key='logo_path'" % ",".join("?" * len(keys)), keys).fetchall()
    finally:
        con.close()
    st = {k: v for k, v in rows if v not in (None, "")}
    logo_path = st.pop("logo_path", "")
    payload = {"settings": st}
    if logo_path:
        fp = os.path.join(bld, "static", logo_path.replace("/", os.sep))
        if os.path.isfile(fp) and os.path.getsize(fp) <= 3 * 1024 * 1024:
            raw = open(fp, "rb").read()
            payload["logo"] = {"filename": "logo_%d%s" % (len(raw), os.path.splitext(fp)[1] or ".png"), "b64": base64.b64encode(raw).decode("ascii")}
    if not st and "logo" not in payload:
        return None
    with open(os.path.join(bld, "portal_preset.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return sorted(st.keys()) + (["logo"] if "logo" in payload else [])


def main():
'''
I_USE_ANCHOR = '    open(os.path.join(bld, "installer_client.iss"), "w", encoding="utf-8-sig", newline="").write(iss)\n'
I_USE = '''    _emb = _write_embedded_preset(bld)
    if _emb:
        print("embedded portal_preset.json ->", ", ".join(_emb))
        _pl = 'Source: "portal_preset.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist'
        if _pl not in iss:
            iss = iss.replace("[Files]", "[Files]\\r\\n; v76: client's name/logo/portal travel with the Setup and apply on first start (even over an existing lis.db)\\r\\n" + _pl, 1)
''' + I_USE_ANCHOR

# ---------------- app.py ----------------
A_OLD = '''        flash("اضبط رابط بوابة النتائج أولاً من الإعدادات ← بوابة النتائج.")
        return redirect(url_for("app_settings"))'''
A_NEW = '''        if session.get("designer_id") or session.get("interface") in ("lab", "both"):
            flash("اضبط رابط بوابة النتائج أولاً من الإعدادات ← بوابة النتائج.")
            return redirect(url_for("app_settings"))
        # الاستقبال ما يدخل الإعدادات (ممنوعة عنه) فلا نرميه عليها: رسالة واضحة ونرجعه لصفحته
        flash("بوابة النتائج غير مضبوطة على هذا الجهاز بعد — أبلغ المسؤول/الدعم ليضبطها (QR المريض يحتاجها).")
        return redirect(request.referrer or url_for("dashboard"))'''


def _write(path, new):
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error in %s, nothing changed: %s" % (os.path.basename(path), e))
    os.remove(tmp)


def main():
    s_app = open(APP, encoding="utf-8").read()
    s_ins = open(INS, encoding="utf-8").read()
    todo = []
    if A_NEW in s_app:
        print("app.py: already patched")
    else:
        if s_app.count(A_OLD) != 1:
            sys.exit("STOPPED: app.py anchor found %d times (expected 1). Nothing changed." % s_app.count(A_OLD))
        todo.append((APP, s_app.replace(A_OLD, A_NEW)))
    if "_write_embedded_preset" in s_ins:
        print("make_client_installer.py: already patched")
    else:
        if s_ins.count(I_FUNC_ANCHOR) != 1 or s_ins.count(I_USE_ANCHOR) != 1:
            sys.exit("STOPPED: make_client_installer.py differs from what this patch expects. Nothing changed.")
        todo.append((INS, s_ins.replace(I_USE_ANCHOR, I_USE).replace(I_FUNC_ANCHOR, I_FUNC)))
    for path, new in todo:
        _write(path, new)
    for path, new in todo:
        shutil.copy2(path, path + ".bak_v76")
        open(path, "w", encoding="utf-8", newline="").write(new)
        print("OK patched:", os.path.relpath(path, ROOT), "(backup .bak_v76)")
    if not todo:
        print("Nothing to do.")


if __name__ == "__main__":
    main()
