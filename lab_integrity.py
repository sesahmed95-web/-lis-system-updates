# -*- coding: utf-8 -*-
"""
فحص سلامة التقارير + إرجاع باراميترات CBC القياسية + نسخ احتياطي تلقائي.

- كل العمليات «إضافة فقط»: لا تحذف باراميتر ولا نتيجة ولا تغيّر قيمة مريض.
- إرجاع الاسم القديم (rename) يحافظ على نفس id الباراميتر، فتبقى كل النتائج السابقة مربوطة به.
"""
import os
import re
import sqlite3
import time

# الباراميترات القياسية لـCBC (نفس أسماء الجهاز/المعادلات: MCH وMCHC تُحسب من HGB وRBC وHCT)
CBC_STD = [
    ("WBCs", "X10^9/L", "Numeric", 4.0, 10.0),
    ("Ly", "%", "Numeric", 20, 40), ("MO", "%", "Numeric", 2.0, 10.0),
    ("NE", "%", "Numeric", 40, 80), ("EO", "%", "Numeric", 1.0, 6.0), ("BA", "%", "Numeric", 0.0, 2.0),
    ("LY#", "X10^9/uL", "Numeric", 1.0, 3.0), ("MO#", "X10^9/uL", "Numeric", 0.2, 1.0),
    ("NE#", "X10^9/uL", "Numeric", 2.0, 7.0), ("EO#", "X10^9/uL", "Numeric", 0.02, 0.5),
    ("BA#", "X10^9/uL", "Numeric", 0.01, 0.02),
    ("RBC", "X10^12/uL", "Numeric", 4.5, 5.5), ("HGB", "g/dl", "Numeric", 13.0, 17.0),
    ("HCT", "%", "Numeric", 40.0, 50.0), ("MCV", "fL", "Numeric", 83.0, 101),
    ("MCH", "pg", "Numeric", 27.0, 32.0), ("MCHC", "g/dL", "Numeric", 31.5, 34.5),
    ("RDW", "%", "Numeric", 11.6, 14.0), ("RDW-SD", "fL", "Numeric", 39.0, 46),
    ("PLT", "X10^9/uL", "Numeric", 150, 400), ("MPV", "fL", "Numeric", 7.0, 10.0),
    ("Comment", "", "Text", None, None),
]

# أسماء بديلة شائعة (كتالوج جاهز/تعديل يدوي) → الاسم القياسي
_ALIASES = {
    "white blood cells (wbc)": "WBCs", "wbc": "WBCs", "wbcs": "WBCs",
    "lymphocytes %": "Ly", "lymphocytes": "Ly", "lym%": "Ly", "lym": "Ly", "ly%": "Ly",
    "monocytes %": "MO", "monocytes": "MO", "mon%": "MO", "mo%": "MO",
    "neutrophils %": "NE", "neutrophils": "NE", "neu%": "NE", "ne%": "NE", "gran%": "NE",
    "eosinophils %": "EO", "eosinophils": "EO", "eos%": "EO", "eo%": "EO",
    "basophils %": "BA", "basophils": "BA", "bas%": "BA", "ba%": "BA",
    "lymphocytes #": "LY#", "lym#": "LY#", "ly#": "LY#",
    "monocytes #": "MO#", "mon#": "MO#", "mo#": "MO#",
    "neutrophils #": "NE#", "neu#": "NE#", "ne#": "NE#", "gran#": "NE#",
    "eosinophils #": "EO#", "eos#": "EO#", "eo#": "EO#",
    "basophils #": "BA#", "bas#": "BA#", "ba#": "BA#",
    "red blood cells (rbc)": "RBC", "rbc": "RBC",
    "hemoglobin (hgb)": "HGB", "hemoglobin": "HGB", "hgb": "HGB", "hb": "HGB",
    "hematocrit (hct)": "HCT", "hematocrit": "HCT", "hct": "HCT",
    "mean corpuscular volume (mcv)": "MCV", "mcv": "MCV",
    "mean corpuscular hemoglobin (mch)": "MCH", "mch": "MCH",
    "mean corpuscular hemoglobin concentration (mchc)": "MCHC", "mchc": "MCHC",
    "red cell distribution width (rdw-cv)": "RDW", "rdw-cv": "RDW", "rdw": "RDW",
    "red cell distribution width (rdw-sd)": "RDW-SD", "rdw-sd": "RDW-SD",
    "platelets (plt)": "PLT", "platelets": "PLT", "plt": "PLT",
    "mean platelet volume (mpv)": "MPV", "mpv": "MPV",
}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _cbc_id(db):
    r = db.execute("SELECT id FROM test_definitions WHERE code='CBC'").fetchone()
    return r["id"] if r else None


def scan(db):
    """يرجّع قائمة مشاكل بسيطة: تحاليل مفعّلة بلا باراميترات، وCBC ناقص."""
    out = {"cbc": None, "empty_tests": [], "no_range": 0}
    cid = _cbc_id(db)
    if cid:
        names = {r["name"] for r in db.execute("SELECT name FROM test_parameters WHERE test_definition_id=?", (cid,))}
        missing = [s[0] for s in CBC_STD if s[0] not in names]
        out["cbc"] = {"id": cid, "have": len(names), "missing": missing}
    for r in db.execute(
            "SELECT td.id, td.code, td.name FROM test_definitions td WHERE COALESCE(td.is_active,1)=1 AND "
            "NOT EXISTS (SELECT 1 FROM test_parameters tp WHERE tp.test_definition_id=td.id) ORDER BY td.name"):
        out["empty_tests"].append({"id": r["id"], "code": r["code"], "name": r["name"]})
    return out


def repair_cbc(db):
    """يرجّع ما نقص من CBC: (1) يعيد تسمية البديل للاسم القياسي بنفس id (النتائج تبقى)،
    (2) يضيف الناقص بالوحدة والمدى، (3) يضيف المدى المرجعي فقط للباراميتر اللي ما عنده أي مدى.
    يرجّع {'renamed':[...], 'added':[...], 'ranges':n}"""
    res = {"renamed": [], "added": [], "ranges": 0}
    cid = _cbc_id(db)
    if not cid:
        cur = db.execute("INSERT INTO test_definitions (code, name, name_ar, department, sample_type, price) "
                         "VALUES ('CBC','CBC','تعداد دم شامل','Hematology','Blood-EDTA',0)")
        cid = cur.lastrowid
        res["added"].append("CBC (test)")
    rows = db.execute("SELECT id, name FROM test_parameters WHERE test_definition_id=? ORDER BY id", (cid,)).fetchall()
    have = {r["name"]: r["id"] for r in rows}
    # (1) أسماء بديلة → قياسية
    for r in rows:
        std = _ALIASES.get(_norm(r["name"]))
        if std and std != r["name"] and std not in have:
            db.execute("UPDATE test_parameters SET name=? WHERE id=?", (std, r["id"]))
            res["renamed"].append("%s → %s" % (r["name"], std))
            have.pop(r["name"], None)
            have[std] = r["id"]
    # (2)+(3) إضافة الناقص والمدى
    for name, unit, rtype, lo, hi in CBC_STD:
        pid = have.get(name)
        if not pid:
            pid = db.execute("INSERT INTO test_parameters (test_definition_id, name, unit, result_type) VALUES (?,?,?,?)",
                             (cid, name, unit, rtype)).lastrowid
            have[name] = pid
            res["added"].append(name)
        if lo is not None or hi is not None:
            n = db.execute("SELECT COUNT(*) c FROM reference_ranges WHERE test_parameter_id=?", (pid,)).fetchone()["c"]
            if not n:
                db.execute("INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_to, low, high) "
                           "VALUES (?, 'Both', 0, 120, ?, ?)", (pid, lo, hi))
                res["ranges"] += 1
    # ترتيب العرض بحسب الترتيب القياسي (لا يمس الباراميترات الأخرى)
    try:
        for i, (name, *_r) in enumerate(CBC_STD, 1):
            if name in have:
                db.execute("UPDATE test_parameters SET sort_order=? WHERE id=?", (i, have[name]))
    except Exception:
        pass
    db.commit()
    return res


def auto_backup(db_path, keep=10, min_interval_h=6):
    """نسخة احتياطية آمنة (sqlite backup API) بمجلد backups/ بجانب قاعدة البيانات، تُحفظ آخر `keep` نسخ.
    لا تُنشأ نسخة جديدة إن كانت آخر نسخة أحدث من min_interval_h ساعة. ترجّع مسار النسخة أو None."""
    try:
        if not os.path.isfile(db_path):
            return None
        d = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
        os.makedirs(d, exist_ok=True)
        files = sorted(f for f in os.listdir(d) if f.startswith("lis_auto_") and f.endswith(".db"))
        if files and time.time() - os.path.getmtime(os.path.join(d, files[-1])) < min_interval_h * 3600:
            return None
        dst = os.path.join(d, "lis_auto_%s.db" % time.strftime("%Y%m%d_%H%M%S"))
        src = sqlite3.connect(db_path)
        try:
            bk = sqlite3.connect(dst)
            src.backup(bk)
            bk.close()
        finally:
            src.close()
        files = sorted(f for f in os.listdir(d) if f.startswith("lis_auto_") and f.endswith(".db"))
        for old in files[:-keep]:
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass
        return dst
    except Exception:
        return None
