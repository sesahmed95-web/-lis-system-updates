# -*- coding: utf-8 -*-
"""
v37 — «تعديل سريع للتقارير»: اختر القسم ثم التحليل، وعدّل أي باراميتر (الاسم المطبوع/الوحدة/المحاذاة/التظليل)
وأي نسبة طبيعية (أرقام أو كلمات أو رموز ≥ ≤ < > + - …) وعنوان التقرير المطبوع.
يُسجَّل من lab_styles.register تلقائياً (بدون تعديل app.py).
"""
import json
from flask import request, jsonify, render_template_string, url_for

ALIGN = ("", "near_name", "center", "near_unit")

PAGE = r"""{% extends "base.html" %}
{% block page_title %}تعديل سريع للتقارير{% endblock %}
{% block content %}
<style>
  .qe { max-width:1500px; margin:auto; }
  .qe .cols { display:grid; grid-template-columns:minmax(0,1.5fr) minmax(340px,1fr); gap:14px; align-items:start; }
  @media (max-width:1100px) { .qe .cols { grid-template-columns:1fr; } }
  .qe #rows { overflow-x:auto; min-width:0; }
  .qe .rr { max-width:420px; }
  .qe .pv { position:sticky; top:8px; background:#E2E8F0; padding:8px; border-radius:10px; }
  .qe .pv h4 { margin:0 0 6px; font-size:.9em; color:#334155; }
  .qe .sheet { background:#fff; width:100%; aspect-ratio:210/297; overflow:hidden; padding:4% 5%; box-sizing:border-box; font-family:Arial,sans-serif; font-size:11px; direction:ltr; box-shadow:0 1px 6px rgba(0,0,0,.2); position:relative; }
  .qe .sheet .t { text-align:center; font-weight:800; font-size:1.5em; text-decoration:underline; margin:4px 0 8px; }
  .qe .sheet .d { width:100%; line-height:1.5; margin:2px 0; }
  .qe .sheet table { width:100%; border-collapse:collapse; margin-top:6px; }
  .qe .sheet th { border-top:1.5px solid #000; border-bottom:1.5px solid #000; padding:3px; }
  .qe .sheet td { padding:2px 4px; text-align:center; }
  .qe .sheet td.n { text-align:left; font-weight:700; }
  .qe .sheet tr.cur td { background:#FEF9C3; }
  .qe .sheet .hl td { background:#FFF59D; }
  .qe select, .qe input[type=text], .qe input[type=number] { padding:6px 8px; border:1px solid #CBD5E1; border-radius:8px; font:inherit; }
  .qe .bar { display:flex; gap:10px; flex-wrap:wrap; align-items:end; margin:12px 0; }
  .qe .bar label { display:flex; flex-direction:column; font-size:.85em; color:#475569; gap:3px; }
  .qe table { width:100%; border-collapse:collapse; background:#fff; }
  .qe th { background:#F1F5F9; padding:7px; font-size:.85em; border:1px solid #E2E8F0; }
  .qe td { padding:5px; border:1px solid #E2E8F0; vertical-align:top; }
  .qe .rr { display:flex; gap:4px; flex-wrap:wrap; align-items:center; margin-bottom:4px; padding:4px; background:#F8FAFC; border-radius:8px; direction:ltr; }
  .qe .rr input[type=text] { min-width:150px; flex:1; }
  .qe .rr input[type=number] { width:80px; }
  .qe .rr .meta { font-size:.75em; color:#64748B; }
  .qe .btn2 { border:1px solid #CBD5E1; background:#fff; border-radius:8px; padding:5px 10px; cursor:pointer; font:inherit; }
  .qe .ok { color:#15803D; font-weight:700; }
  .qe .sym button { padding:1px 7px; border:1px solid #CBD5E1; background:#fff; border-radius:6px; cursor:pointer; }
</style>
<div class="qe">
  <h2>✎ تعديل سريع للتقارير</h2>
  <div class="muted">اختر القسم ثم التحليل. أي تعديل يُحفظ بزر «حفظ» جنب كل باراميتر ويظهر بالتقارير المطبوعة والمعاينة.</div>
  <div class="bar">
    <label>القسم<select id="dept"><option value="">— اختر —</option>{% for d in depts %}<option>{{ d }}</option>{% endfor %}</select></label>
    <label>التحليل<select id="test"><option value="">— اختر القسم أولاً —</option></select></label>
    <span id="msg" class="ok"></span>
  </div>
  <div id="titleBox" style="display:none;margin:8px 0;padding:10px;background:#EFF6FF;border-radius:10px;">
    <b>عنوان التقرير المطبوع:</b>
    <input type="text" id="ttl" style="min-width:320px" placeholder="مثال: Complete Blood Count (CBC)">
    <button class="btn2" id="ttlSave">حفظ العنوان</button>
    <button class="btn2" id="ttlReset">رجوع للافتراضي</button>
    <small class="muted">يبدّل العنوان الأعلى بالتقرير (للتقارير اللي تطبع عنواناً). فارغ = الافتراضي.</small>
  </div>
  <div id="descBox" style="display:none;margin:8px 0;padding:10px;background:#F0FDF4;border-radius:10px;">
    <b>وصف التحليل (حد أقصى 5 أسطر، كل سطر بعرض الورقة):</b>
    <textarea id="desc" rows="5" style="width:100%;padding:6px 8px;border:1px solid #CBD5E1;border-radius:8px;font:inherit;direction:ltr" placeholder="كل سطر = سطر مستقل بعرض ورقة A4"></textarea>
    <label>مكانه: <select id="descPos"><option value="top">تحت عنوان التقرير</option><option value="bottom">آخر التقرير (فوق التذييل)</option></select></label>
    <button class="btn2" id="descSave">حفظ الوصف</button>
    <small class="muted">فارغ = بدون وصف.</small>
  </div>
  <div class="cols"><div id="rows"></div>
  <div class="pv"><h4>👁 معاينة سريعة (تتحدث مباشرة قبل الحفظ)</h4><div class="sheet" id="sheet"></div></div></div>
</div>
<script>
var T = {{ tests|tojson }};
var $ = function (i) { return document.getElementById(i); };
function say(t) { $('msg').textContent = t; setTimeout(function () { $('msg').textContent = ''; }, 3500); }
function post(url, obj) { return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify(obj) }).then(function (r) { return r.json(); }); }
$('dept').onchange = function () {
  var s = $('test'); s.innerHTML = '<option value="">— اختر —</option>';
  T.filter(function (t) { return t.department === $('dept').value; }).forEach(function (t) { var o = document.createElement('option'); o.value = t.id; o.textContent = t.code + ' — ' + t.name; s.appendChild(o); });
  $('rows').innerHTML = ''; $('titleBox').style.display = 'none'; $('descBox').style.display = 'none'; $('sheet').innerHTML = '';
};
$('test').onchange = load;
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
function load() {
  var id = $('test').value; if (!id) { $('rows').innerHTML = ''; $('titleBox').style.display = 'none'; $('descBox').style.display = 'none'; $('sheet').innerHTML = ''; return; }
  fetch('{{ url_for("quickedit_data") }}?test=' + id, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
    $('titleBox').style.display = ''; $('descBox').style.display = ''; $('desc').value = d.desc || ''; $('descPos').value = d.desc_pos || 'top'; $('ttl').value = d.title || ''; $('ttl').dataset.dt = d.name; $('ttl').placeholder = d.name; $('ttl').dataset.code = d.code;
    var h = '<table><tr><th>الباراميتر</th><th>الاسم المطبوع</th><th>الوحدة</th><th>محاذاة النتيجة</th><th>تظليل</th><th>النسب الطبيعية</th></tr>';
    d.params.forEach(function (p) {
      h += '<tr data-p="' + p.id + '"><td><b>' + esc(p.name) + '</b><br><button class="btn2 save" style="margin-top:6px">💾 حفظ</button></td>' +
        '<td><input type="text" class="f-label" value="' + esc(p.display_label) + '" placeholder="' + esc(p.name) + '"></td>' +
        '<td><input type="text" class="f-unit" style="width:90px" value="' + esc(p.unit) + '"></td>' +
        '<td><select class="f-align"><option value="">افتراضي</option><option value="near_name"' + (p.value_align === 'near_name' ? ' selected' : '') + '>جنب الاسم</option><option value="center"' + (p.value_align === 'center' ? ' selected' : '') + '>وسط</option><option value="near_unit"' + (p.value_align === 'near_unit' ? ' selected' : '') + '>جنب الوحدة</option></select></td>' +
        '<td><input type="checkbox" class="f-hl"' + (p.highlight ? ' checked' : '') + '></td><td class="rngs">';
      p.ranges.forEach(function (r) { h += rr(r); });
      h += '<button class="btn2 addr">+ نسبة طبيعية</button></td></tr>';
    });
    $('rows').innerHTML = h + '</table>'; preview();
  });
}
function rr(r) {
  var meta = (r.gender || 'Both') + ' · ' + r.age_from + ' ' + (r.age_from_unit || '') + '–' + r.age_to + ' ' + (r.age_to_unit || '');
  return '<div class="rr" data-r="' + r.id + '"><span class="meta">' + esc(meta) + '</span>' +
    'low <input type="number" step="any" class="r-low" value="' + esc(r.low) + '"> high <input type="number" step="any" class="r-high" value="' + esc(r.high) + '">' +
    '<input type="text" class="r-text" value="' + esc(r.range_text) + '" placeholder="نص/رموز (يغلب على الأرقام)">' +
    '<span class="sym"><button type="button" data-s="≥">≥</button><button type="button" data-s="≤">≤</button><button type="button" data-s="&lt;">&lt;</button><button type="button" data-s="&gt;">&gt;</button><button type="button" data-s="–">–</button><button type="button" data-s="±">±</button></span>' +
    '<button type="button" class="btn2 delr" title="حذف هذه النسبة">🗑</button></div>';
}
document.addEventListener('click', function (e) {
  var b = e.target, tr = b.closest && b.closest('tr[data-p]');
  if (b.closest && b.closest('.sym') && b.dataset.s) { var inp = b.closest('.rr').querySelector('.r-text'); inp.value += b.dataset.s; inp.focus(); return; }
  if (!tr) return;
  var pid = tr.dataset.p;
  if (b.classList.contains('addr')) { post('{{ url_for("quickedit_range_add") }}', { param: pid }).then(function (j) { if (j.ok) { b.insertAdjacentHTML('beforebegin', rr(j.range)); } else say('تعذر'); }); }
  else if (b.classList.contains('delr')) { if (!confirm('حذف هذه النسبة الطبيعية؟')) return; var d = b.closest('.rr'); post('{{ url_for("quickedit_range_del") }}', { id: d.dataset.r }).then(function (j) { if (j.ok) d.remove(); }); }
  else if (b.classList.contains('save')) {
    var ranges = [].map.call(tr.querySelectorAll('.rr'), function (d) { return { id: d.dataset.r, low: d.querySelector('.r-low').value, high: d.querySelector('.r-high').value, text: d.querySelector('.r-text').value }; });
    post('{{ url_for("quickedit_save") }}', { param: pid, label: tr.querySelector('.f-label').value, unit: tr.querySelector('.f-unit').value, align: tr.querySelector('.f-align').value, highlight: tr.querySelector('.f-hl').checked, ranges: ranges })
      .then(function (j) { say(j.ok ? '✔ تم الحفظ' : 'تعذر الحفظ'); });
  }
});
function preview(cur) {
  var rows = document.querySelectorAll('tr[data-p]'); if (!rows.length) return;
  var ttl = $('ttl').value || $('ttl').dataset.dt || '';
  var lines = $('desc').value.split('\n').filter(function (x) { return x.trim(); }).slice(0, 5);
  var dh = lines.map(function (l) { return '<div class="d">' + esc(l) + '</div>'; }).join('');
  var tb = '';
  [].forEach.call(rows, function (tr) {
    var lab = tr.querySelector('.f-label').value || tr.querySelector('b').textContent;
    var rg = [].map.call(tr.querySelectorAll('.rr'), function (d) {
      var t = d.querySelector('.r-text').value.trim(), lo = d.querySelector('.r-low').value, hi = d.querySelector('.r-high').value;
      return esc(t || (lo !== '' && hi !== '' ? lo + ' - ' + hi : lo !== '' ? '> ' + lo : hi !== '' ? '< ' + hi : ''));
    }).join('<br>');
    tb += '<tr' + ' class="' + (tr.querySelector('.f-hl').checked ? 'hl ' : '') + (cur && cur === tr ? 'cur' : '') + '"' + '><td class="n">' + esc(lab) + '</td><td>12.3</td><td>' + esc(tr.querySelector('.f-unit').value) + '</td><td>' + rg + '</td></tr>';
  });
  var pos = $('descPos').value;
  $('sheet').innerHTML = '<div class="t">' + esc(ttl) + '</div>' + (pos === 'top' ? dh : '') +
    '<table><tr><th>Test</th><th>Result</th><th>Unit</th><th>Normal range</th></tr>' + tb + '</table>' + (pos === 'bottom' ? '<div style="margin-top:10px">' + dh + '</div>' : '');
}
document.addEventListener('input', function (e) { var tr = e.target.closest && e.target.closest('tr[data-p]'); if (tr || e.target.id === 'ttl' || e.target.id === 'desc') preview(tr); });
document.addEventListener('change', function (e) { if (e.target.id === 'descPos' || (e.target.closest && e.target.closest('tr[data-p]'))) preview(); });
$('descSave').onclick = function () { post('{{ url_for("quickedit_desc") }}', { code: $('ttl').dataset.code, text: $('desc').value, pos: $('descPos').value }).then(function (j) { say(j.ok ? '✔ تم حفظ الوصف' : 'تعذر'); }); };
$('ttlSave').onclick = function () { post('{{ url_for("quickedit_title") }}', { code: $('ttl').dataset.code, title: $('ttl').value }).then(function (j) { say(j.ok ? '✔ تم حفظ العنوان' : 'تعذر'); }); };
$('ttlReset').onclick = function () { $('ttl').value = ''; $('ttlSave').click(); };
</script>
{% endblock %}"""

BTN = ('<a href="%s" id="qeBtn" title="تعديل سريع: باراميترات + نسب طبيعية + عنوان التقرير" '
       'style="position:fixed;bottom:18px;left:18px;z-index:9999;background:#1D4ED8;color:#fff;padding:10px 16px;'
       'border-radius:30px;text-decoration:none;font-weight:700;box-shadow:0 4px 14px rgba(0,0,0,.25)">✎ تعديل سريع للتقارير</a>')


_SAMETAB = r"""<script id="labSameTab">
/* v39: أزرار «إدخال النتائج» تفتح بنفس النافذة/التبويب بدل تبويب متصفح جديد */
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a[target="_blank"]'); if (!a) return;
  var u; try { u = new URL(a.href, location.href); } catch (_) { return; }
  if (u.origin === location.origin && /\/front-desk\/visits\/\d+\/results\/?$|\/enter-results|\/quick-entry/.test(u.pathname)) a.setAttribute('target', '_self');
}, true);
var _wo = window.open;
window.open = function (url, name, feat) {
  try {
    var u = new URL(url, location.href);
    if (u.origin === location.origin && /\/front-desk\/visits\/\d+\/results\/?$|\/enter-results|\/quick-entry/.test(u.pathname)) { location.href = u.href; return window; }
  } catch (_) {}
  return _wo.apply(window, arguments);
};
</script>"""


def register(app, get_db, get_setting, set_setting, roles_required, log_action=None):
    from flask import g
    try:
        from flask import before_render_template
    except ImportError:  # pragma: no cover
        before_render_template = None

    def _titles(db):
        try:
            v = json.loads(get_setting(db, "rs_titles", "") or "")
            return v if isinstance(v, dict) else {}
        except (TypeError, ValueError):
            return {}

    def _descs(db):
        try:
            v = json.loads(get_setting(db, "rs_desc", "") or "")
            return v if isinstance(v, dict) else {}
        except (TypeError, ValueError):
            return {}

    def _num(v):
        v = ("" if v is None else str(v)).strip()
        try:
            return float(v) if v != "" else None
        except ValueError:
            return None

    @app.route("/management/report-quick-edit")
    @roles_required("admin")
    def quickedit_page():
        db = get_db()
        try:
            rows = db.execute("SELECT id, code, name, COALESCE(department,'') AS department FROM test_definitions "
                              "WHERE COALESCE(is_active,1)=1 ORDER BY department, code").fetchall()
            tests = [{"id": r["id"], "code": r["code"], "name": r["name"], "department": r["department"] or "—"} for r in rows]
            depts = sorted({t["department"] for t in tests})
            return render_template_string(PAGE, tests=tests, depts=depts)
        finally:
            db.close()

    @app.route("/management/report-quick-edit/data")
    @roles_required("admin")
    def quickedit_data():
        db = get_db()
        try:
            t = db.execute("SELECT id, code, name FROM test_definitions WHERE id=?", (request.args.get("test", type=int),)).fetchone()
            if not t:
                return jsonify({"params": []}), 404
            params = []
            for p in db.execute("SELECT * FROM test_parameters WHERE test_definition_id=? ORDER BY sort_order, id", (t["id"],)).fetchall():
                rr = [dict(r) for r in db.execute(
                    "SELECT id, gender, age_from, age_from_unit, age_to, age_to_unit, low, high, range_text FROM reference_ranges "
                    "WHERE test_parameter_id=? AND patient_id IS NULL ORDER BY id", (p["id"],)).fetchall()]
                params.append({"id": p["id"], "name": p["name"], "display_label": p["display_label"] or "", "unit": p["unit"] or "",
                               "value_align": p["value_align"] or "", "highlight": bool(p["highlight"]), "ranges": rr})
            dd = _descs(db).get(t["code"], {})
            return jsonify({"code": t["code"], "name": t["name"], "title": _titles(db).get(t["code"], ""), "desc": dd.get("text", ""), "desc_pos": dd.get("pos", "top"), "params": params})
        finally:
            db.close()

    @app.route("/management/report-quick-edit/save", methods=["POST"])
    @roles_required("admin")
    def quickedit_save():
        j = request.get_json(silent=True) or {}
        db = get_db()
        try:
            p = db.execute("SELECT id FROM test_parameters WHERE id=?", (j.get("param"),)).fetchone()
            if not p:
                return jsonify({"ok": False}), 404
            align = j.get("align") if j.get("align") in ALIGN else ""
            db.execute("UPDATE test_parameters SET display_label=?, unit=?, value_align=?, highlight=? WHERE id=?",
                       ((j.get("label") or "").strip()[:60] or None, (j.get("unit") or "").strip()[:30],
                        align or None, 1 if j.get("highlight") else 0, p["id"]))
            for r in j.get("ranges") or []:
                row = db.execute("SELECT id FROM reference_ranges WHERE id=? AND test_parameter_id=?", (r.get("id"), p["id"])).fetchone()
                if row:
                    db.execute("UPDATE reference_ranges SET low=?, high=?, range_text=? WHERE id=?",
                               (_num(r.get("low")), _num(r.get("high")), (r.get("text") or "").strip()[:500] or None, row["id"]))
            db.commit()
            if log_action:
                try:
                    log_action("QuickEdit", "param", p["id"], "تعديل سريع")
                except Exception:
                    pass
            return jsonify({"ok": True})
        finally:
            db.close()

    @app.route("/management/report-quick-edit/range-add", methods=["POST"])
    @roles_required("admin")
    def quickedit_range_add():
        j = request.get_json(silent=True) or {}
        db = get_db()
        try:
            p = db.execute("SELECT id FROM test_parameters WHERE id=?", (j.get("param"),)).fetchone()
            if not p:
                return jsonify({"ok": False}), 404
            cur = db.execute("INSERT INTO reference_ranges (test_parameter_id, gender, age_from, age_from_unit, age_to, age_to_unit) "
                             "VALUES (?, 'Both', 0, 'Years', 120, 'Years')", (p["id"],))
            db.commit()
            return jsonify({"ok": True, "range": {"id": cur.lastrowid, "gender": "Both", "age_from": 0, "age_from_unit": "Years",
                                                   "age_to": 120, "age_to_unit": "Years", "low": None, "high": None, "range_text": None}})
        finally:
            db.close()

    @app.route("/management/report-quick-edit/range-del", methods=["POST"])
    @roles_required("admin")
    def quickedit_range_del():
        j = request.get_json(silent=True) or {}
        db = get_db()
        try:
            db.execute("DELETE FROM reference_ranges WHERE id=? AND patient_id IS NULL", (j.get("id"),))
            db.commit()
            return jsonify({"ok": True})
        finally:
            db.close()

    @app.route("/management/report-quick-edit/desc", methods=["POST"])
    @roles_required("admin")
    def quickedit_desc():
        j = request.get_json(silent=True) or {}
        code = (j.get("code") or "").strip()[:40]
        if not code:
            return jsonify({"ok": False}), 400
        lines = [x.strip() for x in str(j.get("text") or "").splitlines() if x.strip()][:5]
        db = get_db()
        try:
            d = _descs(db)
            if lines:
                d[code] = {"text": "\n".join(l[:400] for l in lines), "pos": "bottom" if j.get("pos") == "bottom" else "top"}
            else:
                d.pop(code, None)
            set_setting(db, "rs_desc", json.dumps(d, ensure_ascii=False))
            db.commit()
            return jsonify({"ok": True})
        finally:
            db.close()

    @app.route("/management/report-quick-edit/title", methods=["POST"])
    @roles_required("admin")
    def quickedit_title():
        j = request.get_json(silent=True) or {}
        code = (j.get("code") or "").strip()[:40]
        if not code:
            return jsonify({"ok": False}), 400
        db = get_db()
        try:
            t = _titles(db)
            title = (j.get("title") or "").strip()[:120]
            if title:
                t[code] = title
            else:
                t.pop(code, None)
            set_setting(db, "rs_titles", json.dumps(t, ensure_ascii=False))
            db.commit()
            return jsonify({"ok": True})
        finally:
            db.close()

    # ---- تطبيق عنوان التقرير المخصص: نلتقط كود التحليل لحظة رسم قالب reports/*
    if before_render_template is not None:
        @before_render_template.connect_via(app)
        def _grab_code(sender, template, context, **extra):
            try:
                if (template.name or "").startswith("reports/") and "base_report" not in template.name:
                    ot = context.get("ot")
                    code = None
                    if ot is not None:
                        try:
                            code = ot["test_code"]
                        except (KeyError, TypeError, IndexError):
                            code = None
                    if code:
                        g._lab_title_code = code
            except Exception:
                pass

    def _visit_has_esr_cbc():
        """زر «تنسيق ESR» يظهر فقط لو بزيارة المريض CBC + ESR."""
        try:
            va = request.view_args or {}
            db = get_db()
            try:
                if "visit_id" in va:
                    vid = va["visit_id"]
                else:
                    r = db.execute("SELECT o.visit_id FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE ot.id=?",
                                   (va.get("order_test_id"),)).fetchone()
                    vid = r["visit_id"] if r else None
                if vid is None:
                    return False
                rows = db.execute("SELECT td.code AS code, td.name AS name FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
                                  "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=?", (vid,)).fetchall()
            finally:
                db.close()
            codes = [(r["code"] or "").upper() for r in rows]
            names = [(r["name"] or "").lower() for r in rows]
            has_cbc = "CBC" in codes
            has_esr = any(c == "ESR" or c.startswith("ESR") for c in codes) or any("sedimentation" in n or n.strip() == "esr" for n in names)
            return has_cbc and has_esr
        except Exception:
            return True   # عند أي خطأ لا نخفي الزر

    import re
    _H = re.compile(rb'(<(?:div|h[1-6])\b[^>]*class="[^"]*\breport-(?:heading|title)\b[^"]*"[^>]*>)(.*?)(</(?:div|h[1-6])>)', re.S)

    @app.after_request
    def _apply_title_and_button(resp):
        try:
            if resp.mimetype != "text/html" or resp.direct_passthrough:
                return resp
            code = getattr(g, "_lab_title_code", None)
            path = request.path
            if code:
                db = get_db()
                try:
                    title = _titles(db).get(code)
                    desc = _descs(db).get(code)
                finally:
                    db.close()
                data = resp.get_data()
                new = data
                from markupsafe import escape
                if title:
                    new = _H.sub(lambda m: m.group(1) + str(escape(title)).encode("utf-8") + m.group(3), new, count=1)
                if desc and desc.get("text"):
                    blk = ('<div class="lab-desc" style="width:100%;margin:6px 0 10px;direction:ltr;text-align:left;font-size:13px;line-height:1.55;">' +
                           "".join('<div style="width:100%;">' + str(escape(l)) + '</div>' for l in desc["text"].split("\n")[:5]) + '</div>').encode("utf-8")
                    if desc.get("pos") == "bottom" and b'<div class="footer-block">' in new:
                        new = new.replace(b'<div class="footer-block">', blk + b'<div class="footer-block">', 1)
                    else:
                        m = _H.search(new)
                        if m:
                            new = new[:m.end()] + blk + new[m.end():]
                if new != data:
                    resp.set_data(new)
            if (b"</body>" in resp.get_data() and b'id="labSameTab"' not in resp.get_data()
                    and "/print" not in path and not path.startswith("/api")):
                data = resp.get_data()
                i = data.rfind(b"</body>")
                resp.set_data(data[:i] + _SAMETAB.encode("utf-8") + data[i:])
            if request.method == "GET" and resp.status_code == 200 and request.endpoint in ("visit_results_entry", "result_entry"):
                data = resp.get_data()
                if b"</body>" in data and b'id="labNoEsrBtn"' not in data and not _visit_has_esr_cbc():
                    i = data.rfind(b"</body>")
                    resp.set_data(data[:i] + b'<style id="labNoEsrBtn">a[href="/management/esr-layout"]{display:none!important}</style>' + data[i:])
            if path.rstrip("/") == "/management/report-designer":
                data = resp.get_data()
                if b'id="qeBtn"' not in data and b"</body>" in data:
                    i = data.rfind(b"</body>")
                    resp.set_data(data[:i] + (BTN % url_for("quickedit_page")).encode("utf-8") + data[i:])
        except Exception:
            app.logger.exception("lab_quickedit after_request")
        return resp
