# -*- coding: utf-8 -*-
r"""
client_scrub.py - يحذف أسرارك وروابطك الخاصة من نسخة قاعدة البيانات المخصّصة للعميل، ويفحصها.

الاستعمال (على قاعدة العميل بعد التنظيف، قبل بناء الـSetup):
    py client_scrub.py  <مسار lis.db>            -> يحذف ثم يطبع ما حذفه
    py client_scrub.py  <مسار lis.db> --check    -> يفحص فقط (لا يغيّر شي)، ويرجع خطأ إذا بقي سر
خيارات:
    --keep-portal      (الافتراضي) يترك portal_url / portal_api_key (لأن المُنشئ يضع بوابة العميل الجديدة)
    --drop-portal      يحذفهما أيضًا
    --reset-gates      يحذف كلمات سر البوّابات (حذف/نسخ احتياطي/إعفاء/واجهات) ليحدّدها العميل
    --drop-ai          يحذف مفاتيح الذكاء الصناعي (ai_api_key, ai_vision_key)
المفاتيح تُقرأ من جدول settings فقط؛ لا تُمس بيانات المرضى ولا التحاليل ولا الأسعار ولا الأقسام.
"""
import os
import sqlite3
import sys

GITHUB = ["github_write_token", "github_read_token", "update_signing_key_path"]
LEDGER_LINK = ["ledger_key", "ledger_url", "ledger_enabled", "ledger_auto_import", "ledger_days_back"]
# متعلقة بمرضى/زيارات جهازك أنت، ولا معنى لها عند العميل
STALE_PREFIX = ["ledger_hash_", "ledger_ids_", "ledger_orig_v", "ledger_last_", "ledger_link_file_applied",
                "ledger_backfill_v1", "auto_update_last_", "auto_update_pending_banner", "portal_remote_synced"]
AI = ["ai_api_key", "ai_vision_key"]
GATES = ["backup_gate_password_hash", "delete_password_hash", "fee_waiver_gate_password_hash", "fee_waiver_password_hash",
         "fee_waiver_authorized_name", "interface_lab_password_hash", "interface_reception_password_hash"]
PORTAL = ["portal_url", "portal_api_key"]


def _targets(keep_portal=True, reset_gates=False, drop_ai=False):
    exact = set(GITHUB + LEDGER_LINK)
    if not keep_portal:
        exact |= set(PORTAL)
    if reset_gates:
        exact |= set(GATES)
    if drop_ai:
        exact |= set(AI)
    return exact


def find(db, keep_portal=True, reset_gates=False, drop_ai=False):
    exact = _targets(keep_portal, reset_gates, drop_ai)
    out = []
    for (k,) in db.execute("SELECT key FROM settings").fetchall():
        if k in exact or any(k.startswith(p) for p in STALE_PREFIX):
            out.append(k)
    return sorted(out)


def scrub(path, keep_portal=True, reset_gates=False, drop_ai=False, dry=False):
    db = sqlite3.connect(path)
    try:
        keys = find(db, keep_portal, reset_gates, drop_ai)
        if not dry:
            for k in keys:
                db.execute("DELETE FROM settings WHERE key=?", (k,))
            db.commit()
        return keys
    finally:
        db.close()

def leak_scan(src_db, folder, keep_keys=(), sensitive_re=None, min_len=8):
    """يقرأ قيم الأسرار من قاعدتك الأصلية (للقراءة فقط) ويفتش بكل ملف داخل folder. يرجّع قائمة (ملف <- مفتاح)."""
    import os, re
    sensitive_re = sensitive_re or re.compile(r"(token|secret|api_?key|password|passwd|whatsapp|smtp)", re.I)
    exact = _targets(False, True, True)
    db = sqlite3.connect("file:%s?mode=ro" % src_db.replace("\\", "/"), uri=True)
    try:
        rows = db.execute("SELECT key, value FROM settings").fetchall()
    finally:
        db.close()
    needles = {}
    for k, v in rows:
        v = (v or "").strip()
        if len(v) < min_len or k in keep_keys:
            continue
        if k in exact or sensitive_re.search(k) or any(k.startswith(p) for p in STALE_PREFIX):
            needles[k] = v.encode("utf-8")
    hits = []
    for dp, _, fns in os.walk(folder):
        for fn in fns:
            fp = os.path.join(dp, fn)
            try:
                data = open(fp, "rb").read()
            except OSError:
                continue
            for k, nd in needles.items():
                if nd in data:
                    hits.append("%s  <-  %s" % (os.path.relpath(fp, folder), k))
    return hits


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__); return 2
    path = argv[0]
    flags = set(argv[1:])
    kw = dict(keep_portal="--drop-portal" not in flags, reset_gates="--reset-gates" in flags, drop_ai="--drop-ai" in flags)
    if "--check" in flags:
        keys = scrub(path, dry=True, **kw)
        if keys:
            print("بقيت %d إعدادات خاصة بك داخل القاعدة:" % len(keys)); print("  " + "\n  ".join(keys)); return 1
        print("نظيفة: لا أسرار ولا روابط خاصة بك داخل القاعدة."); return 0
    keys = scrub(path, **kw)
    print("تم حذف %d إعداد:" % len(keys)); print("  " + ("\n  ".join(keys) if keys else "(لا شي)")); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
