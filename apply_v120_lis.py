# -*- coding: utf-8 -*-
"""
apply_v120_lis.py - يربط lis_client_config.py بالـLIS (بلوك واحد بعد ledger_sync.install).
داخل مجلد الـLIS:   py apply_v120_lis.py      (نسخة app.py.bak_v120؛ تشغيله مرتين آمن)
"""
import io, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(HERE, "app.py"); MARK = "v120: client_config"
def main():
    if not os.path.exists(P) or not os.path.exists(os.path.join(HERE, "lis_client_config.py")):
        sys.exit("شغّل الملف من مجلد الـLIS (فيه app.py) بعد نسخ lis_client_config.py إليه.")
    s = io.open(P, encoding="utf-8", newline="").read()
    if MARK in s:
        print("مطبّق مسبقاً."); return
    nl = "\r\n" if "\r\n" in s else "\n"; lines = s.split(nl)
    idx = [i for i, l in enumerate(lines) if "ledger_sync.install(app, dict(" in l]
    if len(idx) != 1:
        sys.exit("توقفت: سطر ledger_sync.install غير موجود/مكرر (%d). أرسل لي app.py." % len(idx))
    ind = re.match(r"\s*", lines[idx[0]]).group(0)
    block = [ind + "try:   # " + MARK,
             ind + "    import lis_client_config",
             ind + "    lis_client_config.install(app, dict(get_db=get_db, get_setting=get_setting, set_setting=set_setting, login_required=login_required, log_action=log_action))",
             ind + "except Exception as _e120:",
             ind + "    print('lis_client_config not loaded:', _e120)"]
    lines[idx[0] + 1:idx[0] + 1] = block
    new = nl.join(lines); compile(new, "app.py", "exec")
    shutil.copy2(P, P + ".bak_v120"); io.open(P, "w", encoding="utf-8", newline="").write(new)
    print("تم: ربط تهيئة العميل (app.py.bak_v120). أعد تشغيل البرنامج ثم افتح  /management/client-config")
if __name__ == "__main__":
    main()
