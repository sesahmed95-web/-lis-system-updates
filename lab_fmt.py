# -*- coding: utf-8 -*-
"""
lab_fmt.py (v108) — تنسيق الخط/الحجم/اللون لتقارير النتائج من داخل التقرير نفسه.

النطاقات الثلاثة:
  all  : كل التقرير
  grp  : مجموعة (cbc / diff / morph / retic ...) — تُعرَّف بـ data-grp على صفوف الجدول
  p    : باراميتر واحد — يُطابَق باسمه (data-nm) بحروف صغيرة؛ يشمل الاسم + النتيجة + الوحدة، أو الاسم فقط (lbl=1)

التخزين: إعداد واحد بقاعدة LIS  report_fmt_v1  (JSON) — يسري على كل التقارير المفردة والمجمّعة.
الافتراضي: عناوين WBC Count / Differential Leucocyte Count / Blood film morphology بحجم 18 (اسم العنوان فقط).
"""
import json
import re
from markupsafe import Markup
from flask import request, jsonify

SETTING_KEY = "report_fmt_v1"
FONTS = {
    "Arial": "Arial, Helvetica, sans-serif",
    "Times New Roman": "'Times New Roman', Times, serif",
    "Tahoma": "Tahoma, Arial, sans-serif",
    "Segoe UI": "'Segoe UI', Tahoma, Arial, sans-serif",
    "Calibri": "Calibri, Arial, sans-serif",
    "Verdana": "Verdana, Geneva, sans-serif",
    "Georgia": "Georgia, serif",
    "Courier New": "'Courier New', monospace",
}
DEFAULT_P = {
    "wbc count": {"size": 18, "lbl": 1},
    "differential leucocyte count": {"size": 18, "lbl": 1},
    "blood film morphology": {"size": 18, "lbl": 1},
}
_KEY_OK = re.compile(r"^[\w .,'()/+\-%\u0600-\u06FF]{1,60}$")
_COLOR_OK = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_entry(d):
    """يرجع قاموساً نظيفاً (size/family/color/lbl) أو {} إن لم يبقَ شيء صالح."""
    out = {}
    try:
        sz = int(float(d.get("size"))) if d.get("size") not in (None, "") else None
    except (TypeError, ValueError):
        sz = None
    if sz is not None and 8 <= sz <= 40:
        out["size"] = sz
    fam = d.get("family")
    if fam in FONTS:
        out["family"] = fam
    col = d.get("color")
    if isinstance(col, str) and _COLOR_OK.match(col):
        out["color"] = col.lower()
    if out and d.get("lbl"):
        out["lbl"] = 1
    return out


def _load(db, get_setting):
    try:
        raw = get_setting(db, SETTING_KEY, "") or ""
        d = json.loads(raw) if raw else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def effective(db, get_setting):
    """الإعداد الفعلي = الافتراضي + المحفوظ (المحفوظ يغلب بالاسم)."""
    d = _load(db, get_setting)
    p = {k: dict(v) for k, v in DEFAULT_P.items()}
    for k, v in (d.get("p") or {}).items():
        if v:
            p[k] = v
        else:
            p.pop(k, None)         # {} = المستخدم ألغى الافتراضي لهذا الباراميتر
    return {"all": d.get("all") or {}, "grp": d.get("grp") or {}, "p": p}


def _decl(e):
    parts = []
    if e.get("size"):
        parts.append("font-size:%dpx !important" % int(e["size"]))
    if e.get("family") in FONTS:
        parts.append("font-family:%s !important" % FONTS[e["family"]])
    if e.get("color"):
        parts.append("color:%s !important" % e["color"])
    return ";".join(parts)


def build_css(fmt):
    css = []
    a = _decl(fmt.get("all") or {})
    if a:
        css.append("#rptResults, #rptResults td, #rptResults th, #rptResults p, #rptResults div, "
                   "#rptResults span:not(.rs-t), #rptResults b, #rptResults i, #rptResults u{%s}" % a)
    for g, e in (fmt.get("grp") or {}).items():
        d = _decl(e)
        if d and re.match(r"^[\w\-]{1,30}$", g):
            css.append('#rptResults tr[data-grp="%s"] td, #rptResults tr[data-grp="%s"] td *:not(sup){%s}' % (g, g, d))
    for k, e in (fmt.get("p") or {}).items():
        d = _decl(e)
        if not d or not _KEY_OK.match(k) or '"' in k or "\\" in k:
            continue
        s = '#rptResults tr td[data-nm="%s" i]' % k      # tr: يرفع الخصوصية فوق قاعدة المجموعة
        if e.get("lbl"):
            css.append("%s, %s *:not(sup){%s}" % (s, s, d))
        else:
            css.append("%s, %s *:not(sup), %s + td, %s + td *:not(sup), %s + td + td, %s + td + td *:not(sup){%s}" % (s, s, s, s, s, s, d))
    return "\n".join(css)


def register(app, get_db, get_setting, set_setting, roles_required, login_required=None, log_action=None):
    def _css():
        db = get_db()
        try:
            return Markup(build_css(effective(db, get_setting)))
        except Exception:
            return Markup("")
        finally:
            try:
                db.close()
            except Exception:
                pass

    app.jinja_env.globals["report_fmt_css"] = _css
    lg = login_required or (lambda f: f)

    @app.route("/api/report-fmt", methods=["GET"], endpoint="lab_fmt_get")
    @lg
    def lab_fmt_get():
        db = get_db()
        try:
            return jsonify(ok=True, fmt=effective(db, get_setting), fonts=list(FONTS.keys()))
        finally:
            db.close()

    @app.route("/api/report-fmt", methods=["POST"], endpoint="lab_fmt_set")
    @roles_required("admin")
    def lab_fmt_set():
        d = request.get_json(silent=True) or {}
        scope = d.get("scope")
        key = str(d.get("key") or "").strip().lower()
        db = get_db()
        try:
            cur = _load(db, get_setting)
            if d.get("reset_all"):
                cur = {}
            elif scope in ("all", "grp", "p"):
                if scope == "all":
                    e = _clean_entry(d)
                    if d.get("reset"):
                        cur.pop("all", None)
                    else:
                        cur["all"] = e
                else:
                    if not key or (scope == "grp" and not re.match(r"^[\w\-]{1,30}$", key)) or \
                       (scope == "p" and not _KEY_OK.match(key)):
                        return jsonify(ok=False, error="مفتاح غير صالح"), 400
                    bucket = cur.setdefault(scope, {})
                    if d.get("reset"):
                        if scope == "p" and key in DEFAULT_P:
                            bucket[key] = {}        # يلغي الافتراضي (حجم 18) لهذا العنوان
                        else:
                            bucket.pop(key, None)
                    else:
                        e = _clean_entry(d)
                        if not e:
                            return jsonify(ok=False, error="لم يُحدَّد حجم/خط/لون صالح"), 400
                        bucket[key] = e
            else:
                return jsonify(ok=False, error="نطاق غير معروف"), 400
            set_setting(db, SETTING_KEY, json.dumps(cur, ensure_ascii=False))
            db.commit()
            if log_action:
                try:
                    log_action("Update", "report_fmt", 0, "%s:%s" % (scope, key))
                except Exception:
                    pass
            return jsonify(ok=True, fmt=effective(db, get_setting))
        finally:
            db.close()

    @app.route("/api/report-units", methods=["GET"], endpoint="lab_fmt_units")
    @roles_required("admin")
    def lab_fmt_units():
        """كل باراميترات كل التحاليل مع وحداتها — لمحرّر الوحدات داخل صفحة المصمم."""
        db = get_db()
        try:
            rows = db.execute(
                "SELECT tp.id, tp.name, COALESCE(tp.unit,'') unit, td.code test_code, td.name test_name, "
                "COALESCE(td.department,'') department FROM test_parameters tp "
                "JOIN test_definitions td ON td.id = tp.test_definition_id "
                "ORDER BY td.department, td.name, tp.id").fetchall()
            return jsonify(ok=True, items=[{k: r[k] for k in ("id", "name", "unit", "test_code", "test_name", "department")} for r in rows])
        finally:
            db.close()
