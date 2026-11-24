# -*- coding: utf-8 -*-
"""
lis_stats_plus.py - تفاصيل الإحصائيات داخل الـLIS (إضافة فقط، لا يغيّر أي ملف ثاني):

  * الضغط على أي تاريخ بصفحة «الإحصائيات» يفتح تفاصيل ذلك اليوم: كل مريض + تحاليله + أسعارها + المدفوع.
  * «مختبرات أرسلت لنا»: كل مختبر مُرسِل بالفترة ← مرضاه ← التحليل وقيمته.
  * «تحاليل أرسلناها لمختبرات»: كل مختبر استلم منا تحاليل ← اسم المريض ← نوع التحليل ← السعر والتكلفة.
  * كل صفحة فيها: رجوع، الشاشة الرئيسية، تنزيل PDF، وإرسال PDF بالواتساب.
  * المختبر/الطبيب بلا نشاط بالفترة ما يظهر.

الربط: install(app, ctx) من app.py (انظر مقطع v97 بآخره).
"""
import html as _h
import re
from datetime import datetime

_E = _h.escape
_TITLE_RE = re.compile("<title>[^<]*(الإحصائيات|الاحصائيات)".encode("utf-8"))


def _n(x):
    try:
        f = float(x or 0)
    except (TypeError, ValueError):
        f = 0.0
    return "{:,.0f}".format(f) if f == int(f) else "{:,.2f}".format(f)


def _cols(db, table):
    try:
        return {r[1] for r in db.execute("PRAGMA table_info(%s)" % table).fetchall()}
    except Exception:
        return set()


def _dates(args):
    now = datetime.now()
    f = (args.get("from") or "").strip()
    t = (args.get("to") or "").strip()
    ok = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not ok.match(f):
        f = now.strftime("%Y-%m-01")
    if not ok.match(t):
        t = now.strftime("%Y-%m-%d") if f[:7] == now.strftime("%Y-%m") else f
    if f > t:
        f, t = t, f
    return f, t


# ------------------------------------------------------------------ البيانات
def _visit_tests(db, vids):
    """{visit_id: [ {name, price, fwd_lab, fwd_cost} ]} — بدون التحاليل الملغاة."""
    if not vids:
        return {}
    otc = _cols(db, "order_tests")
    fl = "COALESCE(ot.forwarded_lab_name,'')" if "forwarded_lab_name" in otc else "''"
    fc = "COALESCE(ot.forwarded_cost,0)" if "forwarded_cost" in otc else "0"
    out = {}
    for i in range(0, len(vids), 500):
        part = vids[i:i + 500]
        q = ("SELECT o.visit_id AS vid, td.name AS name, COALESCE(ot.price, td.price, 0) AS price, %s AS fl, %s AS fc "
             "FROM order_tests ot JOIN orders o ON o.id=ot.order_id JOIN test_definitions td ON td.id=ot.test_definition_id "
             "WHERE o.visit_id IN (%s) AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY ot.id"
             % (fl, fc, ",".join("?" * len(part))))
        for r in db.execute(q, part).fetchall():
            out.setdefault(r["vid"], []).append({"name": r["name"], "price": r["price"] or 0,
                                                 "fwd_lab": (r["fl"] or "").strip(), "fwd_cost": r["fc"] or 0})
    return out


def _invoices(db, vids):
    out = {}
    for i in range(0, len(vids), 500):
        part = vids[i:i + 500]
        for r in db.execute("SELECT visit_id, total_amount, paid_amount FROM invoices WHERE visit_id IN (%s) ORDER BY id"
                            % ",".join("?" * len(part)), part).fetchall():
            out[r["visit_id"]] = (r["total_amount"] or 0, r["paid_amount"] or 0)
    return out


def _visits(db, f, t, only_center=False):
    vc = _cols(db, "visits")
    ex = "COALESCE(v.examining_doctor,'')" if "examining_doctor" in vc else "''"
    where = "substr(v.created_at,1,10) BETWEEN ? AND ?"
    if only_center:
        where += " AND v.referral_center_id IS NOT NULL"
    q = ("SELECT v.id AS vid, v.registration_number AS reg, v.created_at AS created, v.referral_center_id AS cid, "
         "p.full_name AS pname, p.age AS age, p.age_unit AS unit, p.gender AS gender, "
         "COALESCE(d.full_name,'') AS doctor, COALESCE(rc.name,'') AS center, %s AS exam "
         "FROM visits v JOIN patients p ON p.id=v.patient_id "
         "LEFT JOIN doctors d ON d.id=v.doctor_id LEFT JOIN referral_centers rc ON rc.id=v.referral_center_id "
         "WHERE %s ORDER BY v.created_at, v.id" % (ex, where))
    return [dict(r) for r in db.execute(q, (f, t)).fetchall()]


# ------------------------------------------------------------------ HTML
_CSS = """
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,"Segoe UI",Arial,sans-serif;background:#f1f5f9;color:#0f2a3d;direction:rtl}
.top{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #cbd5e1;padding:10px 16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.top h1{font-size:18px;margin:0 8px 0 auto}
.btn{border:1px solid #205072;background:#fff;color:#205072;border-radius:9px;padding:7px 13px;font:600 13px Tahoma;cursor:pointer;text-decoration:none;display:inline-block}
.btn.p{background:#205072;color:#fff}.btn.g{background:#15803d;border-color:#15803d;color:#fff}
.wrap{max-width:1180px;margin:14px auto;padding:0 14px}
.card{background:#fff;border:1px solid #d5dee8;border-radius:12px;padding:14px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{background:#bfe3f7;padding:8px;text-align:right}
td{padding:7px 8px;border-bottom:1px solid #e5ebf1;vertical-align:top}tr.sub td{background:#f8fafc;color:#334155;font-size:12.5px}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.kpi div{background:#eef3f8;border-radius:10px;padding:9px 14px;min-width:130px}
.kpi b{display:block;font-size:20px}.kpi span{font-size:12px;color:#475569}
.muted{color:#64748b}.num{white-space:nowrap}.tag{display:inline-block;background:#e0f2fe;border-radius:6px;padding:1px 7px;margin:1px;font-size:12px}
.fwd{background:#fef3c7}
input[type=date],input[type=text]{padding:6px 8px;border:1px solid #94a3b8;border-radius:8px;font:13px Tahoma}
#msg{padding:8px 16px;color:#065f46;font-weight:700}
@media print{.top,#msg{display:none}body{background:#fff}.card{border:0;padding:0}}
"""

_TITLES = {"day": "تفاصيل المرضى والتحاليل", "in": "مختبرات أرسلت لنا عينات", "out": "تحاليل أرسلناها لمختبرات أخرى"}


def _head(title, lab_name):
    return ("<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>%s</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><style>%s</style></head><body>" % (_E(title), _CSS))


def _period(f, t):
    return f if f == t else "من %s إلى %s" % (f, t)


def _day_body(db, f, t):
    vs = _visits(db, f, t)
    vids = [v["vid"] for v in vs]
    tests = _visit_tests(db, vids)
    inv = _invoices(db, vids)
    tot_paid = sum(inv.get(v["vid"], (0, 0))[1] for v in vs)
    tot_total = sum(inv.get(v["vid"], (0, 0))[0] for v in vs)
    ntests = sum(len(tests.get(v, [])) for v in vids)
    h = ["<div class='kpi'><div><b>%d</b><span>عدد المرضى</span></div><div><b>%d</b><span>عدد التحاليل</span></div>"
         "<div><b>%s</b><span>إجمالي الفواتير</span></div><div><b>%s</b><span>إجمالي المدفوع</span></div></div>"
         % (len(vs), ntests, _n(tot_total), _n(tot_paid))]
    if not vs:
        return "".join(h) + "<p class='muted'>لا توجد زيارات بهذه الفترة.</p>"
    h.append("<table><thead><tr><th>#</th><th>الوصل</th><th>المريض</th><th>الطبيب / المختبر المُرسِل</th>"
             "<th>التحاليل (السعر)</th><th>الكلي</th><th>المدفوع</th></tr></thead><tbody>")
    last_day = None
    for i, v in enumerate(vs, 1):
        day = (v["created"] or "")[:10]
        if f != t and day != last_day:
            h.append("<tr class='sub'><td colspan='7'><b>%s</b></td></tr>" % _E(day))
            last_day = day
        sender = v["center"] and ("مختبر: " + v["center"]) or v["doctor"] or "—"
        ts = []
        for x in tests.get(v["vid"], []):
            cls = "tag fwd" if x["fwd_lab"] else "tag"
            extra = (" ← " + x["fwd_lab"]) if x["fwd_lab"] else ""
            ts.append("<span class='%s'>%s (%s)%s</span>" % (cls, _E(x["name"]), _n(x["price"]), _E(extra)))
        tt, pp = inv.get(v["vid"], (0, 0))
        age = ("%s %s" % (v["age"] if v["age"] is not None else "", v["unit"] or "")).strip()
        h.append("<tr><td>%d</td><td class='num'>%s</td><td><b>%s</b><div class='muted'>%s %s</div></td><td>%s</td><td>%s</td>"
                 "<td class='num'>%s</td><td class='num'>%s</td></tr>"
                 % (i, _E(str(v["reg"] or "")), _E(v["pname"] or ""), _E(v["gender"] or ""), _E(age), _E(sender),
                    "".join(ts) or "—", _n(tt), _n(pp)))
    h.append("</tbody></table>")
    return "".join(h)


def _in_body(db, f, t):
    vs = _visits(db, f, t, only_center=True)
    vids = [v["vid"] for v in vs]
    tests = _visit_tests(db, vids)
    labs = {}
    for v in vs:
        lab = labs.setdefault(v["center"] or ("مختبر #%s" % v["cid"]), {"rows": [], "total": 0.0, "n": 0, "pat": 0})
        lab["pat"] += 1
        for x in tests.get(v["vid"], []):
            lab["rows"].append((v["created"][:10], v["pname"], x["name"], x["price"]))
            lab["total"] += x["price"] or 0
            lab["n"] += 1
    if not labs:
        return "<p class='muted'>لا توجد عينات واردة من مختبرات بهذه الفترة.</p>"
    gt = sum(l["total"] for l in labs.values())
    h = ["<div class='kpi'><div><b>%d</b><span>عدد المختبرات</span></div><div><b>%d</b><span>عدد المرضى</span></div>"
         "<div><b>%d</b><span>عدد التحاليل</span></div><div><b>%s</b><span>إجمالي القيمة</span></div></div>"
         % (len(labs), sum(l["pat"] for l in labs.values()), sum(l["n"] for l in labs.values()), _n(gt))]
    h.append("<table><thead><tr><th>المختبر المُرسِل</th><th>المرضى</th><th>التحاليل</th><th>القيمة</th></tr></thead><tbody>")
    for name, l in sorted(labs.items(), key=lambda kv: -kv[1]["total"]):
        h.append("<tr><td><b>%s</b></td><td>%d</td><td>%d</td><td class='num'>%s</td></tr>" % (_E(name), l["pat"], l["n"], _n(l["total"])))
    h.append("</tbody></table>")
    for name, l in sorted(labs.items(), key=lambda kv: -kv[1]["total"]):
        h.append("<div class='card'><h3 style='margin:0 0 8px'>%s</h3><table><thead><tr><th>التاريخ</th><th>المريض</th>"
                 "<th>التحليل</th><th>القيمة</th></tr></thead><tbody>" % _E(name))
        for d, p, tn, pr in l["rows"]:
            h.append("<tr><td class='num'>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td></tr>" % (_E(d), _E(p or ""), _E(tn), _n(pr)))
        h.append("<tr class='sub'><td colspan='3'><b>المجموع</b></td><td class='num'><b>%s</b></td></tr></tbody></table></div>" % _n(l["total"]))
    return "".join(h)


def _out_body(db, f, t):
    otc = _cols(db, "order_tests")
    if "forwarded_lab_name" not in otc:
        return "<p class='muted'>لا توجد تحاليل مرسلة لمختبرات أخرى.</p>"
    fc = "COALESCE(ot.forwarded_cost,0)" if "forwarded_cost" in otc else "0"
    q = ("SELECT TRIM(ot.forwarded_lab_name) AS lab, substr(v.created_at,1,10) AS d, p.full_name AS pname, v.registration_number AS reg, "
         "td.name AS tname, COALESCE(ot.price, td.price, 0) AS price, %s AS cost "
         "FROM order_tests ot JOIN orders o ON o.id=ot.order_id JOIN visits v ON v.id=o.visit_id JOIN patients p ON p.id=v.patient_id "
         "JOIN test_definitions td ON td.id=ot.test_definition_id "
         "WHERE TRIM(COALESCE(ot.forwarded_lab_name,''))<>'' AND substr(v.created_at,1,10) BETWEEN ? AND ? "
         "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY v.created_at, ot.id" % fc)
    rows = db.execute(q, (f, t)).fetchall()
    if not rows:
        return "<p class='muted'>لم تُرسَل تحاليل لمختبرات أخرى بهذه الفترة.</p>"
    labs = {}
    for r in rows:
        l = labs.setdefault(r["lab"], {"rows": [], "price": 0.0, "cost": 0.0})
        l["rows"].append(r)
        l["price"] += r["price"] or 0
        l["cost"] += r["cost"] or 0
    h = ["<div class='kpi'><div><b>%d</b><span>عدد المختبرات</span></div><div><b>%d</b><span>عدد التحاليل</span></div>"
         "<div><b>%s</b><span>سعرها على المريض</span></div><div><b>%s</b><span>تكلفتها علينا</span></div></div>"
         % (len(labs), len(rows), _n(sum(l["price"] for l in labs.values())), _n(sum(l["cost"] for l in labs.values())))]
    h.append("<table><thead><tr><th>المختبر</th><th>عدد التحاليل</th><th>سعر المريض</th><th>التكلفة</th></tr></thead><tbody>")
    for name, l in sorted(labs.items(), key=lambda kv: -len(kv[1]["rows"])):
        h.append("<tr><td><b>%s</b></td><td>%d</td><td class='num'>%s</td><td class='num'>%s</td></tr>" % (_E(name), len(l["rows"]), _n(l["price"]), _n(l["cost"])))
    h.append("</tbody></table>")
    for name, l in sorted(labs.items(), key=lambda kv: -len(kv[1]["rows"])):
        h.append("<div class='card'><h3 style='margin:0 0 8px'>%s</h3><table><thead><tr><th>التاريخ</th><th>المريض</th><th>نوع التحليل</th>"
                 "<th>سعر المريض</th><th>التكلفة</th></tr></thead><tbody>" % _E(name))
        for r in l["rows"]:
            h.append("<tr><td class='num'>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
                     % (_E(r["d"]), _E(r["pname"] or ""), _E(r["tname"]), _n(r["price"]), _n(r["cost"])))
        h.append("<tr class='sub'><td colspan='3'><b>المجموع</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr></tbody></table></div>" % (_n(l["price"]), _n(l["cost"])))
    return "".join(h)


def _page(db, kind, f, t, lab_name, interactive=True, phone=""):
    body = {"day": _day_body, "in": _in_body, "out": _out_body}[kind](db, f, t)
    title = "%s — %s" % (_TITLES[kind], _period(f, t))
    h = [_head(title, lab_name)]
    if interactive:
        q = "kind=%s&from=%s&to=%s" % (kind, f, t)
        h.append(
            "<div class='top'><a class='btn p' href='javascript:void(0)' onclick=\"if(history.length>1){history.back()}else{location.href='/'}\">↩ رجوع</a>"
            "<a class='btn' href='/'>🏠 الشاشة الرئيسية</a>"
            "<form method='get' style='display:flex;gap:6px;align-items:center'><input type='hidden' name='kind' value='%s'>"
            "<input type='date' name='from' value='%s'><input type='date' name='to' value='%s'><button class='btn'>عرض</button></form>"
            "<a class='btn' href='/stats-plus/view?kind=day&from=%s&to=%s'>المرضى</a>"
            "<a class='btn' href='/stats-plus/view?kind=in&from=%s&to=%s'>🧪 مختبرات أرسلت لنا</a>"
            "<a class='btn' href='/stats-plus/view?kind=out&from=%s&to=%s'>📤 أرسلنا لمختبرات</a>"
            "<a class='btn p' href='/stats-plus/pdf?%s'>📄 PDF</a>"
            "<input type='text' id='ph' placeholder='رقم واتساب (964…)' value='%s' style='width:150px;direction:ltr'>"
            "<button class='btn g' onclick='sendWa()'>📲 إرسال واتساب</button>"
            "<h1>%s</h1></div><div id='msg'></div><div class='wrap'><div class='card'>"
            % (kind, f, t, f, t, f, t, f, t, _E(q), _E(phone), _E(title)))
        h.append(body)
        h.append("</div></div><script>function sendWa(){var p=document.getElementById('ph').value;"
                 "fetch('/stats-plus/wa?%s',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:p})})"
                 ".then(function(r){return r.json()}).then(function(j){document.getElementById('msg').textContent=j.message||'تم'})"
                 ".catch(function(e){document.getElementById('msg').textContent='فشل: '+e})}</script></body></html>" % _E(q))
    else:
        h.append("<div class='wrap'><h2 style='text-align:center'>%s</h2><h3 style='text-align:center;margin-top:0'>%s</h3><div class='card'>%s</div></div></body></html>"
                 % (_E(lab_name), _E(title), body))
    return "".join(h)


# ------------------------------------------------------------------ تركيب
_INJECT = r"""<script id="lis-stats-plus">(function(){
 if(window.__spInit)return;window.__spInit=1;
 var D=/^\d{4}-\d{2}-\d{2}$/;
 function mark(){document.querySelectorAll('td').forEach(function(td){
  var t=(td.textContent||'').trim();
  if(D.test(t)&&!td.dataset.sp){td.dataset.sp='1';td.style.cursor='pointer';td.style.color='#0b5ea8';td.style.textDecoration='underline';
   td.title='اضغط لعرض مرضى وتحاليل هذا اليوم';
   td.addEventListener('click',function(){location.href='/stats-plus/view?kind=day&from='+t+'&to='+t;});}});}
 function range(){var d=document.querySelectorAll('input[type=date]');var f=d[0]&&d[0].value,t=d[1]&&d[1].value;
  var r=/^\d{4}-\d{2}-\d{2}$/;if(!r.test(f||''))f='';if(!r.test(t||''))t='';return (f?'&from='+f:'')+(t?'&to='+t:'');}
 function bar(){if(document.getElementById('spBar'))return;var b=document.createElement('div');b.id='spBar';
  b.style.cssText='position:fixed;bottom:14px;right:16px;z-index:9990;display:flex;gap:8px;direction:rtl';
  function mk(txt,kind){var a=document.createElement('a');a.textContent=txt;a.href='#';
   a.style.cssText='background:#205072;color:#fff;border-radius:10px;padding:9px 14px;font:700 13px Tahoma;text-decoration:none;box-shadow:0 3px 12px rgba(0,0,0,.3)';
   a.onclick=function(e){e.preventDefault();location.href='/stats-plus/view?kind='+kind+range();};return a;}
  b.appendChild(mk('🧪 مختبرات أرسلت لنا','in'));b.appendChild(mk('📤 تحاليل أرسلناها','out'));b.appendChild(mk('👥 تفاصيل المرضى','day'));
  document.body.appendChild(b);}
 function go(){mark();bar();}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
 try{new MutationObserver(mark).observe(document.body,{childList:true,subtree:true});}catch(e){}
})();</script>"""


def install(app, ctx):
    """ctx: get_db, login_required, get_setting, set_setting, make_pdf(html,name)->path, open_wa(phone,path,cc)->(bool,_)"""
    from flask import Response, request, send_file, jsonify

    get_db, login_required = ctx["get_db"], ctx["login_required"]
    get_setting, set_setting = ctx["get_setting"], ctx["set_setting"]

    def _args():
        kind = request.args.get("kind", "day")
        if kind not in _TITLES:
            kind = "day"
        f, t = _dates(request.args)
        return kind, f, t

    @app.route("/stats-plus/view")
    @login_required
    def sp_view():
        db = get_db()
        kind, f, t = _args()
        lab = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "") or "المختبر"
        return Response(_page(db, kind, f, t, lab, True, get_setting(db, "stats_wa_phone", "") or ""), mimetype="text/html")

    @app.route("/stats-plus/pdf")
    @login_required
    def sp_pdf():
        db = get_db()
        kind, f, t = _args()
        lab = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "") or "المختبر"
        path = ctx["make_pdf"](_page(db, kind, f, t, lab, False), "stats_%s_%s_%s" % (kind, f, t))
        return send_file(path, as_attachment=True, download_name="stats_%s_%s_%s.pdf" % (kind, f, t))

    @app.route("/stats-plus/wa", methods=["POST"])
    @login_required
    def sp_wa():
        db = get_db()
        kind, f, t = _args()
        phone = re.sub(r"\D", "", str((request.get_json(silent=True) or {}).get("phone") or ""))
        if phone:
            set_setting(db, "stats_wa_phone", phone)
            db.commit()
        lab = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "") or "المختبر"
        try:
            path = ctx["make_pdf"](_page(db, kind, f, t, lab, False), "stats_%s_%s_%s" % (kind, f, t))
        except Exception as e:
            return jsonify(ok=False, message="تعذّر توليد PDF: %s" % e)
        cc = get_setting(db, "whatsapp_country_code", "964")
        if phone.startswith("0"):
            phone = cc + phone[1:]
        try:
            opened, _ = ctx["open_wa"](phone, path, cc)
        except Exception as e:
            return jsonify(ok=False, message="تعذّر فتح واتساب: %s" % e)
        return jsonify(ok=bool(opened), message=("جهّزنا الملف وفتحنا واتساب — اسحب الملف من نافذة المجلد وأرسله." if opened
                                                  else "تعذّر فتح واتساب. نزّل الـPDF وأرسله يدوياً."))

    @app.after_request
    def _sp_inject(resp):
        try:
            if (request.method == "GET" and resp.status_code == 200 and resp.mimetype == "text/html" and not resp.direct_passthrough
                    and not request.path.startswith(("/stats-plus", "/static", "/api/"))):
                d = resp.get_data()
                if b"lis-stats-plus" not in d and b"</body>" in d and _TITLE_RE.search(d):
                    resp.set_data(d.replace(b"</body>", _INJECT.encode("utf-8") + b"</body>", 1))
        except Exception:
            pass
        return resp
