# -*- coding: utf-8 -*-
"""
lis_wipe.py - تنفيذ «مسح كل سجلات المرضى» داخل الـLIS عندما يطلبه المدير من سجل المرضى (السحابة).
الخطوات (بالترتيب، وأي فشل يوقف التنفيذ ولا يحذف شيئاً):
  1) نسخة كاملة من قاعدة الـLIS إلى مجلد backups بجانب القاعدة   (before_wipe_YYYYmmdd_HHMMSS.db)
  2) حذف كل الزيارات بنفس دالة الحذف المعتمدة (طلبات/نتائج/فواتير/مدفوعات)، ثم المرضى الذين بلا زيارات
  3) إرسال wipe-ack للسحابة ليستأنف الرفع
لا يمسح: قائمة التحاليل، الأسعار، الأطباء الفاحصين، الإعدادات، المستخدمين.
أول تشغيل لا يمسح شيئاً من طلب قديم (يضبط المؤشر فقط).
"""
import os, sqlite3, threading, time

import ledger_sync as ls

_started = {"v": False}
_state = {"last": "", "err": "", "wiped": 0}
_CTX = {}


def _db_file(db):
    r = db.execute("PRAGMA database_list").fetchone()
    return r[2] if r and r[2] else ""


def backup_db(db):
    path = _db_file(db)
    if not path:
        raise RuntimeError("تعذّر تحديد ملف قاعدة البيانات للنسخ الاحتياطي")
    folder = os.path.join(os.path.dirname(path), "backups")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "before_wipe_%s.db" % time.strftime("%Y%m%d_%H%M%S"))
    dst = sqlite3.connect(out)
    try:
        db.backup(dst)
    finally:
        dst.close()
    if not os.path.exists(out) or os.path.getsize(out) < 1024:
        raise RuntimeError("النسخة الاحتياطية لم تُنشأ بشكل سليم")
    return out


def wipe_local(db, delete_visit):
    n = 0
    for v in db.execute("SELECT * FROM visits").fetchall():
        delete_visit(db, v)
        n += 1
    try:
        db.execute("DELETE FROM patient_followups WHERE patient_id NOT IN (SELECT patient_id FROM visits)")
    except Exception:
        pass
    db.execute("DELETE FROM patients WHERE id NOT IN (SELECT patient_id FROM visits)")
    db.commit()
    return n


def check_once():
    db = ls._db()
    c = ls.cfg(db)
    if not c["url"].startswith("https://") or not c["key"]:
        return "غير مضبوط"
    code, j = ls._request(c["url"] + "/api/lis/wipe", c["key"], None, 20)
    if code != 200 or not j.get("ok"):
        return "HTTP %s" % code
    at = int(j.get("wipeAt") or 0)
    raw = ls._get(db, "ledger_wipe_ack", "")
    if raw == "":                       # أول تشغيل: لا نمسح من طلب قديم
        ls._set(db, "ledger_wipe_ack", str(at))
        db.commit()
        return "جاهز"
    if at <= int(raw or 0):
        return "لا يوجد طلب مسح"
    dv = _CTX.get("delete_visit")
    if not dv:
        return "دالة الحذف غير متوفرة"
    with ls._lock:
        bk = backup_db(db)             # يرمي استثناء فلا يُحذف شيء
        n = wipe_local(db, dv)
        ls._set(db, "ledger_wipe_ack", str(at))
        ls._set(db, "names_choice_pending", "1")      # v112: يظهر شريط (استيراد أسماء / ابدأ فارغاً)
        db.commit()
    try:
        la = _CTX.get("log_action")
        if la:
            la("Delete", "all_patients", 0, "مسح كل السجلات (%d زيارة) — نسخة: %s" % (n, bk))
    except Exception:
        pass
    ls._request(c["url"] + "/api/lis/wipe-ack", c["key"], {"wipeAt": at}, 20)
    _state.update(wiped=n, last=time.strftime("%Y-%m-%d %H:%M:%S"), err="")
    return "تم مسح %d زيارة — نسخة: %s" % (n, bk)


def _loop():
    time.sleep(25)
    while True:
        try:
            _state["last_msg"] = check_once()
        except Exception as e:
            _state["err"] = ls._redact(e)
        time.sleep(45)


def install(ctx):
    _CTX.update(ctx or {})
    if not _started["v"]:
        _started["v"] = True
        threading.Thread(target=_loop, daemon=True, name="lis-wipe").start()
