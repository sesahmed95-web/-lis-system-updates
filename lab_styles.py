# -*- coding: utf-8 -*-
"""
نظام ستايلات التقارير بتبويبات (v16).

- كتالوج ستايلات لكل «عائلة» تقرير: CBC / Blood film+Retic / BMA / BM Biopsy (جديدة)،
  + التخثر وGUE/GSE/SFA وأسلوب جدول النتائج (موجودة أصلاً — نفس مخزنها القديم، فما ينكسر شي).
- كل ستايل «بطاقة» توضع بتبويب؛ تقدر تنقلها لتبويب ثاني، تضيف تبويبات، تنسخ ستايل وتعدّل ألوانه/خطه/نصوصه.
- الاعتماد (اختيار الستايل) عام: يطبّق على كل الزيارات الحالية والقادمة لذلك التحليل.
- القوالب تقرأ الستايل عبر الدالة report_style('cbc'|'bf'|'bma'|'bmb') (Jinja global).
الإعدادات (جدول settings): rs_active_<family> · rs_tabs · rs_custom · rs_opts
"""
import json
import re
import time

from flask import request, render_template, redirect, url_for, flash, jsonify

FAMILIES = {
    # family: (عنوان، كود التحليل للمعاينة، تبويب افتراضي)
    "cbc": ("CBC — صورة الدم الكاملة", "CBC", "heme"),
    "bf": ("Blood film / Retic count", "BF", "heme"),
    "bma": ("BMA — شفط نقي العظم", "BMA", "heme"),
    "bmb": ("BM Biopsy — خزعة نقي العظم", "BMBIOPSY", "heme"),
    "culture": ("Culture & Sensitivity / Vitek", "CULTURE", "micro"),
    "hbe": ("Hb / Protein Electrophoresis", "HBE", "heme"),
    "coag": ("التخثر", "COAG", "coag"),
    "exam": ("GUE / GSE / SFA", "GUE", "urine"),
    "result": ("جدول النتائج (كيمياء/هرمونات/فيتامينات/فايروسات…)", None, "chem"),
}
NEW_FAMILIES = ("cbc", "bf", "bma", "bmb", "culture", "hbe")          # عائلات تقبل النسخ والتعديل الكامل
EXTERNAL = ("coag", "exam", "result")               # مخزنها القديم محفوظ كما هو

# حقول التعديل لكل ستايل: (مفتاح, عنوان, نوع, افتراضي)
_C = "color"
OPT_SPECS = {
    "cbc:classic": [],
    "cbc:lab_table": [
        ("line", "لون الخطوط", _C, "#000000"), ("section", "لون عنوان القسم (Hematology)", _C, "#1D4ED8"),
        ("abn", "لون القيم غير الطبيعية", _C, "#C00000"), ("font", "حجم الخط (px)", "num", 14),
        ("range_note", "نص بجانب Reference Range", "text", "according to age"),
        ("prev_title", "عنوان عمود النتيجة السابقة", "text", "Previous Result"),
        ("show_unit", "إظهار الوحدات", "bool", 1), ("show_prev", "عمود النتيجة السابقة (زيارة واحدة + تاريخها)", "bool", 1),
        ("show_all", "إظهار كل بارامترات CBC الموجودة (حتى غير المرتبة بالمجموعات)", "bool", 1),
        ("hide", "صفوف مخفية (أسماؤها مفصولة بفاصلة) — أو اضغط ✕ على الصف بالمعاينة", "list", []),
    ],
    "cbc:lab_plain": [
        ("line", "لون الخطوط", _C, "#000000"), ("section", "لون عنوان القسم (Hematology)", _C, "#1D4ED8"),
        ("abn", "لون القيم غير الطبيعية", _C, "#C00000"), ("font", "حجم الخط (px)", "num", 14),
        ("range_note", "نص بجانب Reference Range", "text", "according to age"),
        ("show_unit", "إظهار الوحدات", "bool", 1),
        ("show_all", "إظهار كل بارامترات CBC الموجودة (حتى غير المرتبة بالمجموعات)", "bool", 1),
        ("hide", "صفوف مخفية (أسماؤها مفصولة بفاصلة) — أو اضغط ✕ على الصف بالمعاينة", "list", []),
    ],
    "bf:classic": [],
    "bf:boxed": [
        ("border", "لون الإطار", _C, "#222222"), ("label_bg", "خلفية العناوين", _C, "#EEF4FB"),
        ("concl_bg", "خلفية Conclusion", _C, "#DCE9F7"), ("font", "حجم الخط (px)", "num", 15),
        ("show_cbc", "ملء WBC / Hb / Platelet / HCT تلقائياً من CBC نفس الزيارة (بالتقرير وبشاشة الإدخال) — إلغاء التأشير = ما تنملأ", "bool", 1),
        ("autofit", "ضغط الخط تلقائيًا لتبقى النتيجة بصفحة واحدة (لو RBC/WBC/Platelet طويلة)", "bool", 1),
        ("hide", "صفوف مخفية (أسماؤها مفصولة بفاصلة) — أو اضغط ✕ على الصف بالمعاينة", "list", []),
        ("extra", "باراميترات مضافة (الاسم|الوحدة|L أو R) — أو استخدم ➕ بالمعاينة", "list", []),
        ("shift", "إزاحة العناوين يمين/يسار (الاسم|بكسل) — أو استخدم ◀ ▶ بالمعاينة", "list", []),
    ],
    "bma:classic": [],
    "bma:blue": [
        ("head_bg", "لون أشرطة العناوين", _C, "#B8D0EC"), ("border", "لون الإطار", _C, "#1F3A7A"),
        ("font", "حجم الخط (px)", "num", 15), ("bullet", "رمز النقطة", "text", "•"),
        ("no_label", "عنوان رقم العينة", "text", "BM aspirate No.:"),
    ],
    "culture:classic": [],
    "culture:vitek": [
        ("line", "لون الخطوط", _C, "#000000"), ("head_bg", "خلفية عناوين الأعمدة", _C, "#FFFFFF"),
        ("title", "عنوان الجدول", "text", "Susceptibility Information"), ("font", "حجم الخط (px)", "num", 14),
        ("show_mic", "إظهار عمود MIC", "bool", 1), ("two_cols", "عمودان من المضادات (مثل التقرير الأصلي)", "bool", 1),
        ("show_status", "إظهار Status: Final", "bool", 1), ("show_header", "إظهار Selected Organism / Source / Collected", "bool", 1),
        ("footer", "تعليق ثابت بآخر التقرير (اختياري)", "text", ""),
    ],
    "hbe:classic": [],
    "hbe:image": [
        ("img_h", "أقصى ارتفاع للصورة (mm)", "num", 165), ("img_w", "عرض الصورة (% من عرض الورقة)", "num", 100),
        ("all_images", "طباعة كل الصور المرفوعة (بدل آخر صورة فقط)", "bool", 0),
        ("show_dev", "إظهار سطر الجهاز/المريض فوق الصورة", "bool", 1),
        ("title", "عنوان التقرير (فاضي = اسم التحليل)", "text", ""),
        ("com_font", "حجم خط Comments (px)", "num", 16),
    ],
    "bmb:classic": [],
    "bmb:blue": [
        ("head_bg", "لون أشرطة العناوين", _C, "#B8D0EC"), ("border", "لون الإطار", _C, "#1F3A7A"),
        ("font", "حجم الخط (px)", "num", 15), ("bullet", "رمز النقطة", "text", "■"),
        ("no_label", "عنوان رقم العينة", "text", "BM biopsy No.:"),
    ],
}

# الكتالوج الأساسي: key -> (family, id, عنوان, وصف)
BASE_STYLES = [
    ("cbc", "classic", "الكلاسيكي (الحالي)", "الجدول الحالي: Test / result / units / Normal Range"),
    ("cbc", "lab_table", "جدول المختبر (Investigation / Result / Previous)",
     "حسب الصورة: ترويسة بخطوط، Hematology، أرقام غير طبيعية بالأحمر، ونتيجة زيارة سابقة واحدة بتاريخها تحت الجدول"),
    ("cbc", "lab_plain", "جدول المختبر بدون نتيجة سابقة",
     "نفس ستايل جدول المختبر (Investigation / Result / Reference Range) لكن بدون عمود النتيجة السابقة ولا تاريخ الزيارة السابقة"),
    ("bf", "classic", "الكلاسيكي (الحالي)", "جدول الديفرنشل + RBC/WBC/Platelets + Conclusion"),
    ("bf", "boxed", "جدول مؤطّر (CBC + Differential + Retic)",
     "حسب الصورة: جدول بإطار واحد يجمع قيم CBC والديفرنشل والريتك وحقول الوصف والخلاصة"),
    ("bma", "classic", "الكلاسيكي (الحالي)", "إطار واحد: Cellularity … Conclusion"),
    ("bma", "blue", "أشرطة زرقاء (BM aspirate)", "حسب الصورة: شريط رقم العينة + شريط العنوان + قائمة نقاط + شريط Conclusion"),
    ("culture", "classic", "الكلاسيكي (الحالي)", "جدول Sensitive / Intermediate / Resistant لكل بكتيريا"),
    ("culture", "vitek", "Vitek — Susceptibility Information", "حسب الصورة: Selected Organism + Source، وجدول Antimicrobial / MIC / Interpretation بعمودين، وStatus: Final"),
    ("hbe", "classic", "الكلاسيكي (الحالي) — منحنى معاد الرسم + جدول", "يطبع المنحنى والجدول بعد قراءة القمم (📎 ← 🧬 Hb Curve)، أو جدول الباراميترات"),
    ("hbe", "image", "صورة الجهاز مباشرة + Comments", "يطبع صورة الورقة/الشاشة المرفوعة من إدخال النتائج (بعد القص) بدون الحاجة لقراءة القمم، وتحتها Comments"),
    ("bmb", "classic", "الكلاسيكي (الحالي)", "Clinical notes + Conclusion"),
    ("bmb", "blue", "أشرطة زرقاء (BM biopsy)", "حسب الصورة: شريط رقم الخزعة + شريط العنوان + نقاط مربعة + Conclusion"),
    ("coag", "table", "جدول النتائج (مثل الكيمياء)", "يتبع أسلوب جدول النتائج العام"),
    ("coag", "1", "تصميم 1 — الكلاسيكي", ""), ("coag", "2", "تصميم 2", ""), ("coag", "3", "تصميم 3", ""), ("coag", "4", "تصميم 4", ""),
    ("exam", "1", "تصميم 1 — الكلاسيكي", ""), ("exam", "2", "تصميم 2 — جدول رسمي", ""),
    ("exam", "3", "تصميم 3 — إطار", ""), ("exam", "4", "تصميم 4 — إكلينيكي ملوّن", ""),
    ("exam", "5", "تصميم 5 — Macro/Micro (حسب الصورة)", "عناوين Macroscopic / Microscopic بخط تحتها، الاسم : النتيجة، والمدى الطبيعي على اليمين (مثل 0-2 /HPF)"),
    ("exam", "6", "تصميم 6 — جدول بخطوط فاصلة", "نفس ترتيب تصميم 5 لكن بصفوف مفصولة بخطوط رفيعة وعناوين بشريط خفيف"),
    ("result", "a1", "Style A — Labels Set 1", ""), ("result", "a2", "Style A — Labels Set 2", ""),
    ("result", "b_grid", "Style B — Matching Image 1", ""), ("result", "b_compact", "Style B — Compact", ""),
    ("result", "r1", "Style R1 — شريط ملوّن + المدى تحت الاسم", ""), ("result", "r2", "Style R2 — أعمدة كلاسيكية", ""),
    ("result", "r3", "Style R3 — مدمج بشرائط أقسام", ""),
]
BASE = {f"{f}:{i}": {"family": f, "id": i, "title": t, "desc": d} for f, i, t, d in BASE_STYLES}

DEFAULT_TABS = [
    {"id": "coag", "name": "التخثر"},
    {"id": "chem", "name": "الكيمياء والتحاليل الرقمية"},
    {"id": "heme", "name": "أمراض الدم"},
    {"id": "urine", "name": "الإدرار والخروج والحيامن"},
    {"id": "micro", "name": "الزرع والحساسية (Culture / Vitek)"},
    {"id": "other", "name": "باقي الفحوصات"},
]

# ---------------------------------------------------------------- نماذج معاينة
SAMPLE_CBC = {  # name: (result, low, high, prev)
    "WBCs": ("8.76", 4, 11, "7.90"), "NE": ("51.2", 37, 72, "49.0"), "Ly": ("37.3", 25, 40, "38.5"), "MO": ("5.3", 2, 8, "5.1"),
    "BA": ("0.7", 0, 1, "0.6"), "EO": ("5.5", 0, 4, "4.2"), "NE#": ("4.49", 1.5, 7, "3.9"), "LY#": ("3.27", 1, 3.7, "3.0"),
    "MO#": ("0.46", 0.2, 0.8, "0.4"), "BA#": ("0.06", 0, 0.1, "0.05"), "EO#": ("0.48", 0, 0.4, "0.33"),
    "RBC": ("2.85", 3.8, 5.2, "3.1"), "HGB": ("8.1", 12, 15, "8.8"), "HCT": ("25.8", 35, 48, "27.0"), "MCV": ("90.5", 80, 94, "88.0"),
    "MCH": ("28.4", 26, 34, "28.0"), "MCHC": ("31.4", 31, 37, "31.5"), "RDW": ("22.7", 11, 16, "21.0"), "RDW-SD": ("72.1", 37, 54, "70.0"),
    "PLT": ("978", 150, 400, "910"), "MPV": ("11.0", 9, 13, "10.8"),
}
SAMPLE_BF = {"Neutrophils": "54", "Lymphocytes": "36", "Monocytes": "3", "Eosinophils": "6", "Basophils": "1",
             "RBC_desc": "Normochromic, anisocytosis with some macrocytes, oval, target and tear drop cells.",
             "WBC_desc": "Normal total and differential count, no immature cells seen.", "Platelets_desc": "Marked thrombocytosis.",
             "Conclusion": "Normochromic anemia + thrombocytosis."}
SAMPLE_BMA = {"Cellularity": "Hypercellular marrow fragments and trails.",
              "Megakaryocytes": "are seen in plentiful number of pleomorphic morphology (some large hyperlobated forms seen).",
              "Myelopoiesis": "is hyperactive with full maturation spectrum and mild dysplasia (hypolobated and abnormal lobation).",
              "Erythropoiesis": "is hyperactive with normoblastic and some megaloblastic maturation.",
              "Conclusion": "The overall picture is highly s/o MPN/MDS with ring sideroblast and thrombocytosis (MPN/MDS-RS-T).\nGenetic study is recommended please.\nBM biopsy will follow.",
              "Biopsy No": ""}
SAMPLE_BMB = {"Clinical notes": "A core of bone marrow trephine biopsy measuring about 1.6 cm consisting of soft tissue, trabecular bone, marrow tissue and sinusoidal hemorrhage.\nThe marrow is hypercellular with partially effaced architecture showing mixed haemopoietic elements with increased megakaryocytes number showing multiple clusters.",
              "Conclusion": "The overall picture is c/w MPN/MDS with ring sideroblasts and thrombocytosis.\nGenetic study is recommended."}


def register(app, get_db, get_setting, set_setting, roles_required, log_action=None):
    from database import get_result_layout, save_result_layout, RESULT_STYLES

    # ------------------------------------------------------------ تخزين
    def _json(db, key, default):
        try:
            v = json.loads(get_setting(db, key, "") or "")
            return v if isinstance(v, type(default)) else default
        except (TypeError, ValueError):
            return default

    def _customs(db):
        out = {}
        for k, v in _json(db, "rs_custom", {}).items():
            if isinstance(v, dict) and v.get("family") in NEW_FAMILIES and f"{v.get('family')}:{v.get('base')}" in BASE:
                out[k] = {"family": v["family"], "base": v["base"], "title": str(v.get("title") or "نسخة")[:60]}
        return out

    def _all_styles(db):
        """key -> dict(family, id(base id), title, desc, custom)"""
        cu = _customs(db)
        opts_all = _json(db, "rs_opts", {})
        out = {}
        for k, b in BASE.items():
            title = (opts_all.get(k) or {}).get("_title") or b["title"]
            out[k] = {**b, "key": k, "title": str(title)[:60], "custom": False}
        for k, c in cu.items():
            b = BASE[f"{c['family']}:{c['base']}"]
            out[k] = {"family": c["family"], "id": c["base"], "key": k, "title": c["title"], "desc": b["desc"], "custom": True}
        return out

    def _tabs(db, styles):
        tabs = _json(db, "rs_tabs", [])
        clean, seen = [], set()
        for t in tabs:
            if not isinstance(t, dict) or not t.get("id"):
                continue
            cards = [k for k in (t.get("cards") or []) if k in styles and k not in seen]
            seen.update(cards)
            clean.append({"id": str(t["id"])[:20], "name": str(t.get("name") or "تبويب")[:40], "cards": cards})
        if not clean:
            clean = [{**d, "cards": []} for d in DEFAULT_TABS]
        ids = {t["id"] for t in clean}
        for k, s in styles.items():            # أي ستايل غير موضوع بتبويب → تبويبه الافتراضي
            if k in seen:
                continue
            dt = FAMILIES[s["family"]][2]
            tgt = next((t for t in clean if t["id"] == dt), clean[0])
            tgt["cards"].append(k)
        _ = ids
        return clean

    def _save_tabs(db, tabs):
        set_setting(db, "rs_tabs", json.dumps([{"id": t["id"], "name": t["name"], "cards": t["cards"]} for t in tabs], ensure_ascii=False))

    def _opts_for(db, key, styles=None):
        styles = styles or _all_styles(db)
        s = styles.get(key)
        if not s:
            return {}
        spec = OPT_SPECS.get(f"{s['family']}:{s['id']}", [])
        saved = _json(db, "rs_opts", {}).get(key, {})
        out = {}
        for name, _label, typ, dflt in spec:
            v = saved.get(name, dflt)
            if typ == "list":
                v = [str(x) for x in v] if isinstance(v, list) else []
            out[name] = v
        return out

    def _active_key(db, family):
        if family == "coag":
            v = get_setting(db, "report_design_coag", "table")
            return f"coag:{v}" if f"coag:{v}" in BASE else "coag:table"
        if family == "exam":
            v = get_setting(db, "report_design_exam", "1")
            return f"exam:{v}" if f"exam:{v}" in BASE else "exam:1"
        if family == "result":
            return "result:" + get_result_layout(db)["style"]
        k = get_setting(db, f"rs_active_{family}", "") or f"{family}:classic"
        return k

    # ------------------------------------------------------------ Jinja: report_style
    def report_style(family):
        db = get_db()
        try:
            styles = _all_styles(db)
            key = None
            try:
                q = request.args.get("rs", "")
                if q in styles and styles[q]["family"] == family:
                    key = q
            except RuntimeError:
                pass
            if not key:
                key = _active_key(db, family)
            if key not in styles:
                key = f"{family}:classic" if f"{family}:classic" in styles else key
            s = styles.get(key) or {"id": "classic", "title": "", "family": family}
            return {"key": key, "id": s["id"], "title": s["title"], "opts": _opts_for(db, key, styles)}
        finally:
            db.close()

    def cbc_wants_extra():
        st = report_style("cbc")
        return st["id"] in ("lab_table", "lab_plain") and bool(st["opts"].get("show_all", 1))

    def rs_hide_prev_footer(ot):
        """سطر «زيارة سابقة بتاريخ» الافتراضي أسفل الصفحة يتكرر مع سطر ستايل جدول المختبر → نخفيه هناك."""
        try:
            code = ot["test_code"]
        except (KeyError, IndexError, TypeError):
            return False
        if code != "CBC":
            return False
        st = report_style("cbc")
        if st["id"] == "lab_plain":
            return True        # بدون نتيجة سابقة: لا يظهر حتى سطر «زيارة سابقة بتاريخ»
        return st["id"] == "lab_table" and bool(st["opts"].get("show_prev", 1))

    _CBC_NAMES = {"wbc": ["WBCs", "WBC", "WBC count", "WBC Count"], "hb": ["HGB", "Hb", "HB", "Hemoglobin"],
                  "plt": ["PLT", "Platelet count", "Platelets"], "hct": ["HCT", "PCV"]}

    def lab_cbc_vals(ot):
        """قيم CBC لنفس الزيارة (لجدول Blood film المؤطّر). بالمعاينة: قيم نموذجية."""
        try:
            visit_id = ot["visit_id"]
        except (KeyError, IndexError, TypeError):
            return {"wbc": "", "hb": "", "plt": "", "hct": ""}
        db = get_db()
        try:
            rows = db.execute(
                "SELECT tp.name AS n, r.value_text AS t, r.value_numeric AS v FROM order_tests ot2 "
                "JOIN orders o2 ON o2.id = ot2.order_id JOIN test_definitions td ON td.id = ot2.test_definition_id "
                "JOIN results r ON r.order_test_id = ot2.id JOIN test_parameters tp ON tp.id = r.test_parameter_id "
                "WHERE o2.visit_id = ? AND td.code = 'CBC'", (visit_id,)).fetchall()
        except Exception:
            return {}
        finally:
            db.close()
        by = {}
        for r in rows:
            v = r["t"] if r["t"] not in (None, "") else r["v"]
            if isinstance(v, float) and v == int(v):
                v = int(v)
            if v not in (None, ""):
                by[r["n"]] = v
        return {k: next((by[n] for n in names if n in by), "") for k, names in _CBC_NAMES.items()}

    def preview_fill(code, params, cbc_groups, row_groups):
        """معاينة الستايلات: هيكل التقرير فقط، كل الحقول فاضية (بلا أرقام نموذجية). ترجع (params, cbc_groups, prev_date)."""
        pdate = None
        params = {k: "" for k in params}
        if code == "CBC" and cbc_groups:
            pdate = "__ / __ / ____"      # حتى يظهر عمود النتيجة السابقة بالمعاينة
            for g in cbc_groups:
                for r in g:
                    r["result"], r["previous"], r["flag"] = "", "", None
        return params, cbc_groups, pdate

    app.jinja_env.globals.update(report_style=report_style, rs_hide_prev_footer=rs_hide_prev_footer, lab_cbc_vals=lab_cbc_vals)
    app.config["LAB_STYLES"] = {"cbc_wants_extra": cbc_wants_extra, "preview_fill": preview_fill, "report_style": report_style}

    # ------------------------------------------------------------ صفحة الإدارة
    def _preview_url(db, s):
        fam, sid = s["family"], s["id"]
        code = FAMILIES[fam][1]
        if fam == "result":
            return url_for("result_style_preview") + f"?style={sid}"
        row = db.execute("SELECT id FROM test_definitions WHERE code=?", (code,)).fetchone()
        if not row and fam == "hbe":
            row = db.execute("SELECT id FROM test_definitions WHERE UPPER(code) LIKE '%ELECTRO%' OR UPPER(name) LIKE '%ELECTRO%' ORDER BY id LIMIT 1").fetchone()
        if not row and fam == "culture":
            row = db.execute("SELECT id FROM test_definitions WHERE UPPER(code) LIKE '%CULTURE%' OR UPPER(name) LIKE '%CULTURE%' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return ""
        base = url_for("preview_report_design", test_definition_id=row["id"])
        if fam in ("coag", "exam"):
            return f"{base}?design={sid}"
        return f"{base}?rs={s['key']}"

    @app.route("/management/report-styles")
    @roles_required("admin")
    def report_styles_page():
        db = get_db()
        try:
            styles = _all_styles(db)
            tabs = _tabs(db, styles)
            active = {f: _active_key(db, f) for f in FAMILIES}
            opts_all = {k: _opts_for(db, k, styles) for k in styles}
            for k, s in styles.items():
                s["preview"] = _preview_url(db, s)
                s["spec"] = OPT_SPECS.get(f"{s['family']}:{s['id']}", [])
                s["active"] = active.get(s["family"]) == k
                s["editable"] = s["family"] in NEW_FAMILIES
            return render_template("management/report_styles.html", tabs=tabs, styles=styles, opts=opts_all,
                                   families=FAMILIES, cur_tab=request.args.get("tab", ""))
        finally:
            db.close()

    def _back(tab=""):
        return redirect(url_for("report_styles_page", tab=tab))

    @app.route("/management/report-styles/hide-row", methods=["POST"])
    @roles_required("admin")
    def report_styles_hide_row():
        """زر ✕ على صف بمعاينة الستايل: يخفيه (أو يرجّعه mode=show) لكل التقارير بهذا الستايل."""
        db = get_db()
        try:
            key, row = request.form.get("key", ""), (request.form.get("row") or "").strip()[:40]
            styles = _all_styles(db)
            s = styles.get(key)
            spec = OPT_SPECS.get(f"{s['family']}:{s['id']}", []) if s else []
            if not s or not row or not any(n == "hide" for n, _l, _t, _d in spec):
                return jsonify({"ok": False}), 400
            oa = _json(db, "rs_opts", {})
            cur = _opts_for(db, key, styles)
            hide = [x for x in cur.get("hide", []) if x != row]
            if request.form.get("mode") != "show":
                hide.append(row)
            oa[key] = {**oa.get(key, {}), "hide": hide[:60]}
            set_setting(db, "rs_opts", json.dumps(oa, ensure_ascii=False))
            db.commit()
            return jsonify({"ok": True, "hide": hide})
        finally:
            db.close()

    @app.route("/management/report-styles/extra-row", methods=["POST"])
    @roles_required("admin")
    def report_styles_extra_row():
        """إضافة/حذف باراميتر جديد بستايل (extra): الاسم|الوحدة|L/R."""
        db = get_db()
        try:
            key = request.form.get("key", "")
            name = (request.form.get("name") or "").replace("|", " ").strip()[:40]
            unit = (request.form.get("unit") or "").replace("|", " ").strip()[:15]
            side = "R" if request.form.get("side") == "R" else "L"
            styles = _all_styles(db)
            s = styles.get(key)
            spec = OPT_SPECS.get(f"{s['family']}:{s['id']}", []) if s else []
            if not s or not name or not any(n == "extra" for n, _l, _t, _d in spec):
                return jsonify({"ok": False}), 400
            oa = _json(db, "rs_opts", {})
            cur = _opts_for(db, key, styles)
            lst = [x for x in cur.get("extra", []) if x.split("|")[0] != name]
            if request.form.get("mode") != "remove":
                lst.append(f"{name}|{unit}|{side}")
            oa[key] = {**oa.get(key, {}), "extra": lst[:40]}
            set_setting(db, "rs_opts", json.dumps(oa, ensure_ascii=False))
            db.commit()
            return jsonify({"ok": True, "extra": lst})
        finally:
            db.close()

    @app.route("/management/report-styles/shift-row", methods=["POST"])
    @roles_required("admin")
    def report_styles_shift_row():
        """أزرار ◀ ▶ على عنوان/باراميتر بمعاينة الستايل: يحرّكه يمين/يسار (dx بالبكسل)."""
        db = get_db()
        try:
            key, row = request.form.get("key", ""), (request.form.get("row") or "").strip()[:40]
            try:
                dx = int(request.form.get("dx", "0"))
            except ValueError:
                dx = 0
            styles = _all_styles(db)
            s = styles.get(key)
            spec = OPT_SPECS.get(f"{s['family']}:{s['id']}", []) if s else []
            if not s or not row or "|" in row or not any(n == "shift" for n, _l, _t, _d in spec):
                return jsonify({"ok": False}), 400
            oa = _json(db, "rs_opts", {})
            cur = _opts_for(db, key, styles)
            m = {}
            for it in cur.get("shift", []):
                a, _, b = it.rpartition("|")
                try:
                    m[a] = int(b)
                except ValueError:
                    pass
            m[row] = max(-400, min(400, m.get(row, 0) + dx))
            if m[row] == 0:
                del m[row]
            lst = [f"{a}|{b}" for a, b in m.items()][:60]
            oa[key] = {**oa.get(key, {}), "shift": lst}
            set_setting(db, "rs_opts", json.dumps(oa, ensure_ascii=False))
            db.commit()
            return jsonify({"ok": True, "shift": lst})
        finally:
            db.close()

    @app.route("/management/report-styles/act", methods=["POST"])
    @roles_required("admin")
    def report_styles_act():
        db = get_db()
        f = request.form
        act, key, tab = f.get("act", ""), f.get("key", ""), f.get("tab", "")
        if f.get("reset"):
            act = "reset_opts"
        try:
            styles = _all_styles(db)
            tabs = _tabs(db, styles)
            msg = ""
            if act == "activate" and key in styles:
                fam, sid = styles[key]["family"], styles[key]["id"]
                if fam == "coag":
                    set_setting(db, "report_design_coag", sid)
                elif fam == "exam":
                    set_setting(db, "report_design_exam", sid)
                elif fam == "result":
                    cfg = get_result_layout(db)
                    if sid in RESULT_STYLES:
                        cfg["style"] = sid
                        save_result_layout(db, cfg)
                else:
                    set_setting(db, f"rs_active_{fam}", key)
                msg = f"تم اعتماد «{styles[key]['title']}» لكل الزيارات."
            elif act == "move" and key in styles:
                dest = f.get("dest", "")
                if any(t["id"] == dest for t in tabs):
                    for t in tabs:
                        if key in t["cards"]:
                            t["cards"].remove(key)
                    next(t for t in tabs if t["id"] == dest)["cards"].append(key)
                    _save_tabs(db, tabs)
                    tab = dest
                    msg = "تم نقل الستايل."
            elif act == "add_tab":
                name = (f.get("name") or "").strip()[:40]
                if name:
                    tid = "t" + str(int(time.time()))[-7:]
                    tabs.append({"id": tid, "name": name, "cards": []})
                    _save_tabs(db, tabs)
                    tab = tid
                    msg = "تمت إضافة التبويب."
            elif act == "rename_tab":
                name = (f.get("name") or "").strip()[:40]
                for t in tabs:
                    if t["id"] == tab and name:
                        t["name"] = name
                _save_tabs(db, tabs)
                msg = "تم تغيير الاسم."
            elif act == "del_tab":
                tgt = next((t for t in tabs if t["id"] == tab), None)
                if tgt and len(tabs) > 1:
                    rest = [t for t in tabs if t is not tgt]
                    rest[0]["cards"].extend(tgt["cards"])
                    _save_tabs(db, rest)
                    tab = rest[0]["id"]
                    msg = "حُذف التبويب ونُقلت ستايلاته للتبويب الأول."
            elif act == "clone" and key in styles and styles[key]["family"] in NEW_FAMILIES:
                cu = _json(db, "rs_custom", {})
                nk = f"{styles[key]['family']}:c{int(time.time())}"
                cu[nk] = {"family": styles[key]["family"], "base": styles[key]["id"], "title": styles[key]["title"] + " (نسخة)"}
                set_setting(db, "rs_custom", json.dumps(cu, ensure_ascii=False))
                oa = _json(db, "rs_opts", {})
                oa[nk] = dict(oa.get(key, {}))
                set_setting(db, "rs_opts", json.dumps(oa, ensure_ascii=False))
                for t in tabs:
                    if key in t["cards"]:
                        t["cards"].append(nk)
                        tab = t["id"]
                        break
                _save_tabs(db, tabs)
                msg = "تم نسخ الستايل — عدّل النسخة كما تريد."
            elif act == "delete" and key in _customs(db):
                cu = _json(db, "rs_custom", {})
                fam = cu.get(key, {}).get("family")
                cu.pop(key, None)
                set_setting(db, "rs_custom", json.dumps(cu, ensure_ascii=False))
                for t in tabs:
                    if key in t["cards"]:
                        t["cards"].remove(key)
                        tab = t["id"]
                _save_tabs(db, tabs)
                if fam and get_setting(db, f"rs_active_{fam}", "") == key:
                    set_setting(db, f"rs_active_{fam}", f"{fam}:classic")
                msg = "حُذفت النسخة."
            elif act in ("save_opts", "reset_opts") and key in styles and styles[key]["family"] in NEW_FAMILIES:
                s = styles[key]
                oa = _json(db, "rs_opts", {})
                if act == "reset_opts":
                    oa.pop(key, None)
                    msg = "رجعت الإعدادات الافتراضية."
                else:
                    new = {}
                    title = (f.get("_title") or "").strip()[:60]
                    if title and title != BASE.get(key, {}).get("title"):
                        if s["custom"]:
                            cu = _json(db, "rs_custom", {})
                            if key in cu:
                                cu[key]["title"] = title
                                set_setting(db, "rs_custom", json.dumps(cu, ensure_ascii=False))
                        else:
                            new["_title"] = title
                    for name, _l, typ, dflt in OPT_SPECS.get(f"{s['family']}:{s['id']}", []):
                        raw = f.get("o_" + name)
                        if typ == "bool":
                            new[name] = 1 if raw else 0
                        elif typ == "color":
                            new[name] = raw if raw and re.fullmatch(r"#[0-9A-Fa-f]{6}", raw) else dflt
                        elif typ == "list":
                            new[name] = [x.strip()[:40] for x in re.split(r"[,\n،]", raw or "") if x.strip()][:60]
                        elif typ == "num":
                            try:
                                new[name] = max(9, min(26, int(raw)))
                            except (TypeError, ValueError):
                                new[name] = dflt
                        else:
                            new[name] = (raw or "").strip()[:60]
                    oa[key] = new
                    msg = "تم حفظ التعديلات (تنطبق على كل الزيارات)."
                set_setting(db, "rs_opts", json.dumps(oa, ensure_ascii=False))
            db.commit()
            if msg:
                flash(msg)
            if log_action:
                try:
                    log_action("ReportStyles", "style", 0, f"{act}:{key or tab}")
                except Exception:
                    pass
        finally:
            db.close()
        nxt = f.get("next", "")
        if nxt.startswith("/management/") and "//" not in nxt:   # رجوع لصفحة المعاينة الداخلية بعد التثبيت
            return redirect(nxt)
        return _back(tab)

    # ------------------------------------------------------------ معاينة داخل البرنامج (بدون فتح المتصفح)
    @app.route("/management/report-styles/view")
    @roles_required("admin")
    def report_style_view():
        """معاينة كاملة داخل نفس البرنامج: زر رجوع + زر «تثبيت هذا الستايل» (يعتمده لكل الزيارات)."""
        db = get_db()
        try:
            styles = _all_styles(db)
            key = request.args.get("key", "")
            back = request.args.get("back", "") or url_for("report_styles_page")
            if not back.startswith("/") or back.startswith("//"):
                back = url_for("report_styles_page")
            if key not in styles:
                flash("الستايل غير موجود.")
                return redirect(back)
            s = styles[key]
            s["preview"] = _preview_url(db, s)
            active = _active_key(db, s["family"]) == key
            here = url_for("report_style_view", key=key, back=back)
            return render_template("management/report_style_view.html", s=s, family_title=FAMILIES[s["family"]][0],
                                   active=active, back=back, here=here)
        finally:
            db.close()

    @app.route("/management/report-designer/view/<int:test_id>")
    @roles_required("admin")
    def report_design_view(test_id):
        """معاينة تصميم تحليل معيّن داخل البرنامج مع زر رجوع."""
        back = request.args.get("back", "") or url_for("test_panel", test_id=test_id)
        if not back.startswith("/") or back.startswith("//"):
            back = url_for("test_panel", test_id=test_id)
        return render_template("management/report_style_view.html", s={"title": "معاينة التقرير", "desc": "", "key": "",
                               "preview": url_for("preview_report_design", test_definition_id=test_id)},
                               family_title="", active=False, back=back, here="", no_pin=True)

    # ------------------------------------------------------------ صفحة «الفحص» بتبويبات: التقرير / النسب الطبيعية / شكل التقرير
    _FAM_BY_CODE = {"CBC": "cbc", "BF": "bf", "BFRETIC": "bf", "BMA": "bma", "BMBIOPSY": "bmb", "COAG": "coag",
                    "GUE": "exam", "GSE": "exam", "SFA": "exam", "CULTURE": "culture"}

    def _log_path():
        import os
        return os.path.join(app.root_path, "error_log.txt")

    def _show_error(where, exc):
        import traceback, datetime
        from markupsafe import escape
        tb = traceback.format_exc()
        try:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write("\n[%s] %s — %s: %s\n%s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), where, type(exc).__name__, exc, tb))
        except Exception:
            pass
        tail = "\n".join(tb.strip().splitlines()[-14:])
        body = ("<html dir='rtl'><head><meta charset='utf-8'><title>خطأ</title></head><body style='font-family:Tahoma,Arial;margin:30px;max-width:900px'>"
                "<h2>⚠️ تعذّر فتح: %s</h2><p><b>سبب الخطأ:</b> <code dir='ltr'>%s: %s</code></p>"
                "<p>انسخ النص التالي (أو صوّر الشاشة) وأرسله للمبرمج — وانكتب أيضاً بملف error_log.txt:</p>"
                "<pre dir='ltr' style='background:#f1f5f9;padding:12px;border-radius:8px;overflow:auto;white-space:pre-wrap'>%s</pre>"
                "<p><a href='javascript:history.back()'>↩ رجوع</a> · <a href='/management/error-log'>📜 عرض سجل الأخطاء</a></p></body></html>"
                % (escape(where), escape(type(exc).__name__), escape(str(exc)), escape(tail)))
        return body, 500

    @app.route("/management/error-log")
    @roles_required("admin")
    def v28_error_log():
        """آخر أسطر error_log.txt داخل البرنامج (للتشخيص بدون البحث عن الملف)."""
        from markupsafe import escape
        try:
            with open(_log_path(), "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()[-150:]
            txt = "\n".join(lines) or "(السجل فاضي)"
        except FileNotFoundError:
            txt = "(ما في ملف error_log.txt بعد — ما صار أي خطأ مسجّل)"
        return ("<html dir='rtl'><head><meta charset='utf-8'><title>سجل الأخطاء</title></head><body style='font-family:Tahoma,Arial;margin:24px'>"
                "<h2>📜 آخر 150 سطر من error_log.txt</h2><p><a href='javascript:history.back()'>↩ رجوع</a></p>"
                "<pre dir='ltr' style='background:#f1f5f9;padding:12px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px'>%s</pre></body></html>" % escape(txt))

    @app.route("/management/test-panel/<int:test_id>")
    @roles_required("admin")
    def test_panel(test_id):
        try:
            return _test_panel_impl(test_id)
        except Exception as _e:       # v28: بدل صفحة 500 العامة، اعرض سبب الخطأ واكتبه بسجل الأخطاء
            return _show_error("صفحة الفحص (النسب الطبيعية / شكل التقرير)", _e)

    def _test_panel_impl(test_id):
        db = get_db()
        try:
            t = db.execute("SELECT td.*, COALESCE(sc.name, NULLIF(TRIM(td.department),''), 'Other') AS sec_label "
                           "FROM test_definitions td LEFT JOIN sections sc ON sc.id = td.section_id WHERE td.id=?",
                           (test_id,)).fetchone()
            if not t:
                flash("الفحص غير موجود.")
                return redirect(url_for("report_designer"))
            params = db.execute("SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (test_id,)).fetchall()
            rows = []
            for p in params:
                rr = db.execute("SELECT * FROM reference_ranges WHERE test_parameter_id=? ORDER BY id", (p["id"],)).fetchall()
                rows.append({"p": p, "ranges": rr})
            fam = _FAM_BY_CODE.get((t["code"] or "").upper(), "")
            if not fam and "electroph" in ((t["code"] or "") + " " + (t["name"] or "")).lower():
                fam = "hbe"
            styles = _all_styles(db)
            fam_styles = []
            if fam:
                act = _active_key(db, fam)
                for k, st in styles.items():
                    if st["family"] == fam:
                        pv = _preview_url(db, {**st, "key": k})
                        fam_styles.append({**st, "key": k, "active": k == act, "preview": pv})
            sections = db.execute("SELECT id, name FROM sections ORDER BY sort_order, id").fetchall()
            # v29: قالب test_panel.html يقرأ بيانات الفحص من المتغيّر t (t['id']...) بينما base.html يستخدم t('...') للترجمة.
            # نمرّر كائناً يجمع الاثنين: يُستدعى كدالة ترجمة ويُقرأ كصف بيانات، فيشتغل القالب الحالي بدون تعديله.
            _ctx = {}
            app.update_template_context(_ctx)
            _tr = _ctx.get("t")

            class _TRow:
                def __init__(self, row, fn): self._row, self._fn = row, fn
                def __call__(self, *a, **k): return self._fn(*a, **k) if self._fn else (a[0] if a else "")
                def __getitem__(self, k): return self._row[k]
                def __getattr__(self, k):
                    try: return self._row[k]
                    except (IndexError, KeyError): raise AttributeError(k)
                def __iter__(self): return iter(self._row)
                def keys(self): return self._row.keys()
                def get(self, k, d=None):
                    try: return self._row[k]
                    except (IndexError, KeyError): return d
                def __bool__(self): return True
            _tobj = _TRow(t, _tr)
            return render_template("management/test_panel.html", test=_tobj, t=_tobj, rows=rows, fam=fam,
                                   fam_title=FAMILIES[fam][0] if fam else "",
                                   fam_styles=fam_styles, sections=sections, tab=request.args.get("tab", "report"))
        finally:
            db.close()

    @app.route("/management/test-panel/<int:test_id>/save-ranges", methods=["POST"])
    @roles_required("admin")
    def test_panel_save_ranges(test_id):
        db = get_db()
        f = request.form
        try:
            ok = {r["id"] for r in db.execute("SELECT id FROM test_parameters WHERE test_definition_id=?", (test_id,)).fetchall()}

            def num(v):
                v = (v or "").strip().replace(",", ".")
                try:
                    return float(v) if v != "" else None
                except ValueError:
                    return None
            n = 0
            for key in f:
                if not key.startswith("rr_low_"):
                    continue
                rid = int(key[7:]) if key[7:].isdigit() else 0
                row = db.execute("SELECT test_parameter_id FROM reference_ranges WHERE id=?", (rid,)).fetchone()
                if not row or row["test_parameter_id"] not in ok:
                    continue
                db.execute("UPDATE reference_ranges SET low=?, high=?, range_text=? WHERE id=?",
                           (num(f.get("rr_low_%d" % rid)), num(f.get("rr_high_%d" % rid)), (f.get("rr_text_%d" % rid) or "").strip() or None, rid))
                n += 1
            for key in f:
                if key.startswith("unit_") and key[5:].isdigit() and int(key[5:]) in ok:
                    db.execute("UPDATE test_parameters SET unit=? WHERE id=?", ((f.get(key) or "").strip(), int(key[5:])))
            sec = f.get("section_id", type=int)
            if sec:
                sr = db.execute("SELECT id, name, dept_name FROM sections WHERE id=?", (sec,)).fetchone()
                if sr:
                    db.execute("UPDATE test_definitions SET section_id=?, department=? WHERE id=?",
                               (sr["id"], (sr["dept_name"] or "").strip() or sr["name"], test_id))
            db.commit()
            flash("تم حفظ النسب الطبيعية والوحدات للفحص (%d صف)." % n)
        finally:
            db.close()
        return redirect(url_for("test_panel", test_id=test_id, tab="ranges"))
