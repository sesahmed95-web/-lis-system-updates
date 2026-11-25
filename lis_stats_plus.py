# -*- coding: utf-8 -*-
"""
lis_stats_plus.py (v99) - تفاصيل الإحصائيات داخل الـLIS (إضافة فقط، لا يغيّر أي ملف ثاني):

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
    tdc = _cols(db, "test_definitions")
    sc = next((c for c in ("short_name", "abbreviation", "abbr", "code") if c in tdc), None)
    sh = ("COALESCE(td.%s,'')" % sc) if sc else "''"
    out = {}
    for i in range(0, len(vids), 500):
        part = vids[i:i + 500]
        q = ("SELECT o.visit_id AS vid, td.name AS name, COALESCE(ot.price, td.price, 0) AS price, %s AS fl, %s AS fc, %s AS sh "
             "FROM order_tests ot JOIN orders o ON o.id=ot.order_id JOIN test_definitions td ON td.id=ot.test_definition_id "
             "WHERE o.visit_id IN (%s) AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY ot.id"
             % (fl, fc, sh, ",".join("?" * len(part))))
        for r in db.execute(q, part).fetchall():
            out.setdefault(r["vid"], []).append({"name": r["name"], "price": r["price"] or 0,
                                                 "fwd_lab": (r["fl"] or "").strip(), "fwd_cost": r["fc"] or 0, "short": r["sh"]})
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



# ------------------------------------------------------------------ اختصارات التحاليل
_ABBR = [
    ("CBC", "Complete blood count", ["complete blood count", "cbc"]),
    ("BF", "Blood Film", ["blood film", "bf", "blood picture"]),
    ("Retic", "Retic Count", ["retic count", "retic", "reticulocyte count"]),
    ("ESR", "Erythrocyte Sedimentation Rate", ["esr", "erythrocyte sedimentation rate"]),
    ("PT", "Prothrombin Time", ["pt", "prothrombin time"]),
    ("PTT", "Partial Thromboplastin Time", ["ptt", "aptt", "partial thromboplastin time"]),
    ("INR", "INR", ["inr"]),
    ("Coag", "Coagulation Tests", ["coagulation tests", "coag"]),
    ("D-Dimer", "D-Dimer", ["d-dimer", "d dimer", "ddimer"]),
    ("CRP", "C-Reactive Protein", ["c-reactive protein (quantitative)", "c-reactive protein", "crp"]),
    ("Ferritin", "Ferritin", ["ferritin"]),
    ("G6PD", "G6PD", ["g6pd"]),
    ("Blood Group", "Blood Group & Rh", ["blood group & rh", "blood group"]),
    ("Coombs D", "Coombs Direct", ["coombs direct"]),
    ("Coombs I", "Coombs Indirect", ["coombs indirect"]),
    ("LDH", "LDH", ["ldh"]),
    ("Hb Electro", "Hb Electrophoresis", ["hb electrophoresis", "hb.electrophoresis", "hb electro"]),
    ("Hb.H prep", "Hb.H preparation", ["hb.h preparation", "hb h preparation", "hb.h prep", "hb h prep"]),
    ("Sickling", "Sickling test", ["sickling test", "sickling"]),
    ("BMB", "Bone Marrow Biopsy", ["bmb", "bone marrow biopsy"]),
    ("BMA", "Bone Marrow Aspiration", ["bma", "bone marrow aspiration"]),
    ("Fluid", "Fluid Analysis", ["fluid", "fluid analysis"]),
    ("CSF", "CSF", ["csf"]),
]


def _ak(x):
    return " ".join(str(x or "").lower().split())


def _abbr_entry(name):
    k = _ak(name)
    for e in _ABBR:
        if k in e[2] or _ak(e[0]) == k:
            return e
    return None


def _abbr(name, short_db=None):
    """الاختصار: من عمود اختصار بقاعدة البيانات إن وُجد، ثم من القاموس، وإلا الاسم نفسه."""
    if short_db and str(short_db).strip():
        return str(short_db).strip()
    e = _abbr_entry(name)
    return e[0] if e else str(name or "")


def _full(name):
    e = _abbr_entry(name)
    return e[1] if e else str(name or "")


def _split_tests(txt):
    out = []
    for part in re.split(r"[,\n،؛;]+", str(txt or "")):
        part = part.strip()
        if part:
            out.append(part)
    return out


def _cloud_rows(ctx, f, t):
    """صفوف سجل المرضى (السحابة) بنفس الفترة، موحّدة الشكل. إن لم يتوفر الربط يرجع [] ."""
    fn = ctx.get("cloud_logs")
    if not fn:
        return []
    try:
        logs = fn(f, t) or []
    except Exception:
        return []
    out = []
    for lg in logs:
        d = str(lg.get("date") or "")
        if not (f <= d <= t):
            continue
        for r in lg.get("rows") or []:
            if not (r.get("name") or r.get("tests") or r.get("paid") or r.get("refDoctor") or r.get("expenses")):
                continue
            out.append({"date": d, "name": r.get("name") or "", "age": r.get("age"), "unit": r.get("ageUnit") or "",
                        "gender": r.get("gender") or "", "sender": r.get("refDoctor") or "",
                        "is_lab": r.get("priceType") == "lab", "tests": [(x, None) for x in _split_tests(r.get("tests"))],
                        "total": (float(r["total"]) if str(r.get("total") or "").replace(".", "", 1).isdigit() else None), "paid": float(r.get("paid") or 0) if str(r.get("paid") or "").replace(".", "", 1).isdigit() else 0.0,
                        "exp": float(r.get("expenses") or 0) if str(r.get("expenses") or "").replace(".", "", 1).isdigit() else 0.0,
                        "exp_note": r.get("expNote") or "", "lis_id": str(r.get("lisId") or "").lstrip("vV"), "reg": str(r.get("lisReg") or ""),
                        "comp": r.get("comp") or {}, "src": "سجل"})
    return out


def _local_rows(db, f, t):
    """مرضى الـLIS بنفس الشكل الموحّد."""
    vs = _visits(db, f, t)
    vids = [v["vid"] for v in vs]
    tests = _visit_tests(db, vids)
    inv = _invoices(db, vids)
    out = []
    for v in vs:
        tt, pp = inv.get(v["vid"], (0, 0))
        out.append({"date": (v["created"] or "")[:10], "name": v["pname"] or "", "age": v["age"], "unit": v["unit"] or "",
                    "gender": v["gender"] or "", "sender": v["center"] or v["doctor"] or "", "is_lab": bool(v["center"]),
                    "tests": [(x["name"], x["price"], x.get("short")) for x in tests.get(v["vid"], [])], "total": tt, "paid": pp,
                    "exp": 0.0, "exp_note": "", "lis_id": str(v["vid"]), "reg": str(v["reg"] or ""), "comp": {}, "src": "LIS"})
    return out


def _all_rows(db, f, t, ctx, lab_q=""):
    """مرضى البرنامجين معاً (LIS + سجل المرضى) بدون تكرار، مرتبين بالتاريخ ثم التسلسل."""
    loc = _local_rows(db, f, t)
    seen_ids = {r["lis_id"] for r in loc if r["lis_id"]}
    seen_regs = {r["reg"] for r in loc if r["reg"]}
    rows = list(loc)
    for r in _cloud_rows(ctx, f, t):
        if (r["lis_id"] and r["lis_id"] in seen_ids) or (r["reg"] and r["reg"] in seen_regs):
            continue
        rows.append(r)
    if lab_q:
        q = _ak(lab_q)
        rows = [r for r in rows if q in _ak(r["sender"])]
    rows.sort(key=lambda r: r["date"])      # الترتيب ثابت داخل اليوم (LIS أولاً ثم السجل)
    return rows


def _default_range(db, ctx):
    """من بداية الشهر إلى آخر يوم أُدخل فيه مرضى (بالبرنامجين)."""
    now = datetime.now()
    ms = now.strftime("%Y-%m-01")
    last = ""
    try:
        r = db.execute("SELECT MAX(substr(created_at,1,10)) FROM visits WHERE substr(created_at,1,10)>=?", (ms,)).fetchone()
        last = (r[0] or "") if r else ""
    except Exception:
        pass
    for r in _cloud_rows(ctx, ms, now.strftime("%Y-%m-31")):
        if r["date"] > last:
            last = r["date"]
    return ms, (last or now.strftime("%Y-%m-%d"))

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
.fwd{background:#fef3c7}.dayh{margin:14px 0 6px;font-weight:700}tr.sum td{background:#e0f2fe;font-weight:800}.grand{margin-top:14px}.grand td{font-size:15px;padding:10px}.pr div{line-height:1.7}.modes{display:flex;gap:6px;flex-wrap:wrap}.btn.on{background:#205072;color:#fff}.chk{font:700 13px Tahoma;display:flex;align-items:center;gap:4px}
input[type=date],input[type=text]{padding:6px 8px;border:1px solid #94a3b8;border-radius:8px;font:13px Tahoma}
#msg{padding:8px 16px;color:#065f46;font-weight:700}
@media print{.top,#msg{display:none}body{background:#fff}.card{border:0;padding:0}}
"""

_TITLES = {"day": "تفاصيل المرضى والتحاليل", "in": "مختبرات أرسلت لنا عينات", "out": "تحاليل أرسلناها لمختبرات أخرى",
           "exp": "الصرفيات", "doc": "حسابات الأطباء"}


def _head(title, lab_name):
    return ("<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>%s</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><style>%s</style></head><body>" % (_E(title), _CSS))


def _period(f, t):
    return f if f == t else "من %s إلى %s" % (f, t)


def _day_body(db, f, t, ctx=None, lab_q="", full=False):
    ctx = ctx or {}
    rows = _all_rows(db, f, t, ctx, lab_q)
    ntests = sum(len(r["tests"]) for r in rows)

    def tot(r):
        if r["total"] is not None:
            return r["total"]
        s_ = sum((x[1] or 0) for x in r["tests"])
        return s_ if s_ else r["paid"]
    g_tot = sum(tot(r) for r in rows)
    g_paid = sum(r["paid"] for r in rows)
    h = ["<div class='kpi'><div><b>%d</b><span>عدد المرضى</span></div><div><b>%d</b><span>عدد التحاليل</span></div>"
         "<div><b>%s</b><span>المجموع الكلي</span></div><div><b>%s</b><span>إجمالي المدفوع</span></div></div>"
         % (len(rows), ntests, _n(g_tot), _n(g_paid))]
    if not rows:
        return "".join(h) + "<p class='muted'>لا توجد زيارات بهذه الفترة.</p>"
    days = []
    for r in rows:
        if not days or days[-1][0] != r["date"]:
            days.append((r["date"], []))
        days[-1][1].append(r)
    for day, drows in days:
        h.append("<div class='dayh'><b>%s</b> — %d مريض</div>" % (_E(day), len(drows)))
        h.append("<table><thead><tr><th>#</th><th>اسم المريض</th><th>العمر</th><th>الجنس</th><th>الطبيب المرسل</th>"
                 "<th>سعر التحاليل</th><th>التحاليل</th><th>المجموع الكلي</th><th>المدفوع</th></tr></thead><tbody>")
        dt = dp = 0.0
        for i, r in enumerate(drows, 1):
            prices = "".join("<div>%s</div>" % (_n(x[1]) if x[1] is not None else "—") for x in r["tests"]) or "—"
            tags = []
            for x in r["tests"]:
                nm = _full(x[0]) if full else _abbr(x[0], x[2] if len(x) > 2 else None)
                tags.append("<span class='tag'>%s</span>" % _E(nm))
            age = ("%s %s" % (r["age"] if r["age"] not in (None, "") else "", r["unit"] or "")).strip() or "—"
            tt = tot(r)
            dt += tt
            dp += r["paid"]
            sender = (r["is_lab"] and r["sender"]) and ("مختبر: " + r["sender"]) or r["sender"] or "—"
            h.append("<tr><td>%d</td><td><b>%s</b></td><td class='num'>%s</td><td>%s</td><td>%s</td><td class='num pr'>%s</td><td>%s</td>"
                     "<td class='num'>%s</td><td class='num'>%s</td></tr>"
                     % (i, _E(r["name"]), _E(age), _E(r["gender"] or "—"), _E(sender), prices, "".join(tags) or "—", _n(tt), _n(r["paid"])))
        h.append("<tr class='sum'><td colspan='7'><b>مجموع اليوم</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr></tbody></table>" % (_n(dt), _n(dp)))
    h.append("<table class='grand'><tbody><tr class='sum'><td><b>المجموع الكلي للتحاليل</b></td><td class='num'><b>%s</b></td>"
             "<td><b>المدفوع</b></td><td class='num'><b>%s</b></td></tr></tbody></table>" % (_n(g_tot), _n(g_paid)))
    return "".join(h)


def _lnk(label, url, interactive):
    return ("<a href='%s' style='color:#075985;font-weight:700;text-decoration:none'>%s</a>" % (_E(url), _E(label))) if interactive else _E(label)


def _exp_body(db, f, t, ctx=None, lab_q="", full=False, interactive=True):
    """الصرفيات (v99): التاريخ + بيان الصرف + المبلغ فقط (بدون اسم المريض) + المجموع. النقر على التاريخ يفتح صرفيات ذلك اليوم."""
    ctx = ctx or {}
    items = []
    vc = _cols(db, "visits")
    if "expenses" in vc:
        note = "COALESCE(v.expenses_note,'')" if "expenses_note" in vc else "''"
        for r in db.execute("SELECT substr(v.created_at,1,10) AS d, v.expenses AS a, %s AS n FROM visits v "
                            "WHERE COALESCE(v.expenses,0)>0 AND substr(v.created_at,1,10) BETWEEN ? AND ? ORDER BY v.created_at" % note, (f, t)).fetchall():
            items.append((r["d"], (r["n"] or "").strip() or "—", float(r["a"])))
    lc = _cols(db, "lab_expenses")
    if lc:
        kcol = "kind" if "kind" in lc else "''"
        ncol = "note" if "note" in lc else "''"
        for r in db.execute("SELECT expense_date AS d, amount AS a, %s AS k, %s AS n FROM lab_expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date, id" % (kcol, ncol), (f, t)).fetchall():
            if (r["a"] or 0) > 0:
                items.append((r["d"], " — ".join(x for x in (r["k"], r["n"]) if x) or "—", float(r["a"])))
    try:
        import ledger_sync as _ls
        for a in ((_ls.fetch_accounts(db) or {}).get("genExp") or []):
            d = str(a.get("date") or "")
            if a.get("src") != "lis" and f <= d <= t and float(a.get("amount") or 0) > 0:
                items.append((d, str(a.get("note") or "—"), float(a["amount"])))
    except Exception:
        pass
    for r in _cloud_rows(ctx, f, t):
        if r["exp"] > 0:
            items.append((r["date"], (r["exp_note"] or "").strip() or "—", r["exp"]))
    items.sort(key=lambda x: x[0])
    total = sum(x[2] for x in items)
    h = ["<div class='kpi'><div><b>%d</b><span>عدد الصرفيات</span></div><div><b>%s</b><span>إجمالي الصرفيات</span></div></div>" % (len(items), _n(total))]
    if not items:
        return "".join(h) + "<p class='muted'>لا توجد صرفيات بهذه الفترة.</p>"
    h.append("<table><thead><tr><th>#</th><th>التاريخ</th><th>بيان الصرف</th><th>المبلغ</th></tr></thead><tbody>")
    for i, x in enumerate(items, 1):
        day = _lnk(x[0], "/stats-plus/view?kind=exp&from=%s&to=%s" % (x[0], x[0]), interactive and f != t)
        h.append("<tr><td>%d</td><td class='num'>%s</td><td>%s</td><td class='num'>%s</td></tr>" % (i, day, _E(x[1]), _n(x[2])))
    h.append("<tr class='sum'><td colspan='3'><b>المجموع</b></td><td class='num'><b>%s</b></td></tr></tbody></table>" % _n(total))
    return "".join(h)


# sync_testdocs_v1
def _per_test_entries(db, f, t, ex_col, shc, full):
    """per_test_doctor_v1: أجور الفاحصين لكل تحليل حسب طبيبه (order_tests.examining_doctor أو طبيب الزيارة)."""
    rates = {}
    for r in db.execute("SELECT doctor_name, test_definition_id, rate FROM examining_doctor_rates").fetchall():
        rates[((r[0] or "").strip(), r[1])] = r[2]
    rows = db.execute(
        "SELECT v.id AS vid, substr(v.created_at,1,10) AS d, COALESCE(v.examining_doctor,'') AS vdoc, p.full_name AS pn, "
        "ot.test_definition_id AS tid, ot.examining_doctor AS odoc, td.name AS name, %s AS sh "
        "FROM visits v JOIN patients p ON p.id=v.patient_id JOIN orders o ON o.visit_id=v.id "
        "JOIN order_tests ot ON ot.order_id=o.id JOIN test_definitions td ON td.id=ot.test_definition_id "
        "WHERE %s AND (ot.fee_waived IS NULL OR ot.fee_waived=0) AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') "
        "AND substr(v.created_at,1,10) BETWEEN ? AND ? ORDER BY v.created_at" % (shc, ex_col), (f, t)).fetchall()
    per = {}
    for r in rows:
        doc = ((r["odoc"] or "").strip() or (r["vdoc"] or "").strip())
        if not doc:
            continue
        rate = rates.get((doc, r["tid"]))
        if not rate:
            continue
        e = per.setdefault((doc, r["vid"]), [r["d"], r["pn"] or "—", [], 0.0])
        e[2].append(_full(r["name"]) if full else _abbr(r["name"], r["sh"]))
        e[3] += float(rate)
    ents = {}
    for (doc, _vid), (d, pn, names, fee) in per.items():
        ents.setdefault(doc, []).append((d, pn, "، ".join(names) or "—", fee))
    for v in ents.values():
        v.sort(key=lambda x: x[0])
    return ents


def _doc_body(db, f, t, ctx=None, lab_q="", full=False):
    """حسابات الأطباء الفاحصين (BF, Retic, Hb.H prep, Sickling, BMB, BMA, Fluid, CSF…) من جداول حسابات الـLIS (أجور الفاحصين)."""
    vc = _cols(db, "visits")
    if "examining_doctor" not in vc or "examining_doctor_fee" not in vc:
        return "<p class='muted'>لا توجد بيانات أجور فاحصين بهذا البرنامج.</p>"
    tdc = _cols(db, "test_definitions")
    ex_col = "td.is_examining_test=1" if "is_examining_test" in tdc else "0"
    shc = "COALESCE(td.short_name,'')" if "short_name" in tdc else "''"
    if "examining_doctor" in _cols(db, "order_tests"):
        ents = _per_test_entries(db, f, t, ex_col, shc, full)      # per_test_doctor: لكل تحليل حسب طبيبه
    else:
        ents = {}
        for v in db.execute("SELECT v.id AS vid, substr(v.created_at,1,10) AS d, v.examining_doctor AS doc, v.examining_doctor_fee AS fee, p.full_name AS pn "
                            "FROM visits v JOIN patients p ON p.id=v.patient_id WHERE TRIM(COALESCE(v.examining_doctor,''))<>'' AND COALESCE(v.examining_doctor_fee,0)>0 "
                            "AND substr(v.created_at,1,10) BETWEEN ? AND ? ORDER BY v.created_at", (f, t)).fetchall():
            names = [(_full(r["name"]) if full else _abbr(r["name"], r["sh"])) for r in db.execute(
                "SELECT td.name AS name, %s AS sh FROM orders o JOIN order_tests ot ON ot.order_id=o.id JOIN test_definitions td ON td.id=ot.test_definition_id "
                "WHERE o.visit_id=? AND %s AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected')" % (shc, ex_col), (v["vid"],)).fetchall()]
            ents.setdefault(v["doc"].strip(), []).append((v["d"], v["pn"] or "—", "، ".join(names) or "—", float(v["fee"])))
    # sync_testdocs_v1: تسويات الأطباء المسجّلة بالسجل (نفس المصدر)
    try:
        import ledger_sync as _ls
        for a in ((_ls.fetch_accounts(db) or {}).get("docAdj") or []):
            d, nm = str(a.get("date") or ""), str(a.get("docName") or "").strip()
            if nm and f <= d <= t and float(a.get("amount") or 0):
                ents.setdefault(nm, []).append((d, "—", "تسوية: " + str(a.get("note") or ""), float(a["amount"])))
    except Exception:
        pass
    for _v in ents.values():
        _v.sort(key=lambda x: x[0])
    if not ents:
        return "<p class='muted'>لا توجد أجور أطباء فاحصين بهذه الفترة.</p>"
    gt = sum(x[3] for v in ents.values() for x in v)
    h = ["<div class='kpi'><div><b>%d</b><span>عدد الأطباء</span></div><div><b>%s</b><span>إجمالي المستحق</span></div></div>" % (len(ents), _n(gt))]
    h.append("<table><thead><tr><th>الطبيب</th><th>عدد المرضى</th><th>المستحق</th></tr></thead><tbody>")
    for nm, v in sorted(ents.items(), key=lambda kv: -sum(x[3] for x in kv[1])):
        h.append("<tr><td><b>%s</b></td><td>%d</td><td class='num'>%s</td></tr>" % (_E(nm), len([x for x in v if x[1] != "—"]), _n(sum(x[3] for x in v))))
    h.append("</tbody></table>")
    for nm, v in sorted(ents.items()):
        h.append("<div class='card'><h3 style='margin:0 0 8px'>%s</h3><table><thead><tr><th>التاريخ</th><th>المريض</th><th>التحاليل</th><th>المبلغ</th></tr></thead><tbody>" % _E(nm))
        for d, p, tn, a_ in v:
            h.append("<tr><td class='num'>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td></tr>" % (_E(d), _E(p), _E(tn), _n(a_)))
        h.append("<tr class='sum'><td colspan='3'><b>المجموع</b></td><td class='num'><b>%s</b></td></tr></tbody></table></div>" % _n(sum(x[3] for x in v)))
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


def _out_body(db, f, t, lab_q="", full=False, interactive=True):
    """تحاليل أرسلناها لمختبرات أخرى (v99): باليوم ثم المختبر: عدد التحاليل + المبلغ (التكلفة علينا) + سعر المريض.
    النقر على التاريخ يفتح تفاصيل ذلك اليوم، والنقر على اسم المختبر يفتح تفاصيل ذلك المختبر (المريض + التحليل + المبلغ)."""
    from urllib.parse import quote
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
    rows = [r for r in db.execute(q, (f, t)).fetchall() if not lab_q or lab_q.lower() in (r["lab"] or "").lower()]
    if not rows:
        return "<p class='muted'>لم تُرسَل تحاليل لمختبرات أخرى بهذه الفترة%s.</p>" % ((" (المختبر: %s)" % _E(lab_q)) if lab_q else "")
    days = {}
    labs = {}
    for r in rows:
        dl = days.setdefault(r["d"], {}).setdefault(r["lab"], {"rows": [], "price": 0.0, "cost": 0.0, "n": 0})
        dl["rows"].append(r)
        dl["n"] += 1
        dl["price"] += r["price"] or 0
        dl["cost"] += r["cost"] or 0
        tl = labs.setdefault(r["lab"], {"price": 0.0, "cost": 0.0, "n": 0})
        tl["n"] += 1
        tl["price"] += r["price"] or 0
        tl["cost"] += r["cost"] or 0
    tot_n, tot_cost, tot_price = len(rows), sum(l["cost"] for l in labs.values()), sum(l["price"] for l in labs.values())

    def day_url(d):
        return "/stats-plus/view?kind=out&from=%s&to=%s&lab=%s" % (d, d, quote(lab_q))

    def lab_url(d, lab):
        return "/stats-plus/view?kind=out&from=%s&to=%s&lab=%s" % (d, d, quote(lab))

    h = ["<div class='kpi'><div><b>%d</b><span>عدد المختبرات</span></div><div><b>%d</b><span>عدد التحاليل</span></div>"
         "<div><b>%s</b><span>المبلغ المرسَل للمختبرات</span></div><div><b>%s</b><span>سعرها على المرضى</span></div></div>"
         % (len(labs), tot_n, _n(tot_cost), _n(tot_price))]
    detailed = (f == t) or bool(lab_q)
    if not detailed:
        h.append("<table><thead><tr><th>التاريخ</th><th>المختبر</th><th>عدد التحاليل</th><th>المبلغ (التكلفة)</th><th>سعر المريض</th></tr></thead><tbody>")
        for d in sorted(days):
            dn = sum(l["n"] for l in days[d].values())
            dc = sum(l["cost"] for l in days[d].values())
            dp = sum(l["price"] for l in days[d].values())
            h.append("<tr style='background:#E0F2FE'><td class='num'><b>%s</b></td><td><b>مجموع اليوم (%d مختبر)</b></td><td><b>%d</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr>"
                     % (_lnk(d, day_url(d), interactive), len(days[d]), dn, _n(dc), _n(dp)))
            for lab, l in sorted(days[d].items(), key=lambda kv: -kv[1]["cost"]):
                h.append("<tr><td></td><td>%s</td><td>%d</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
                         % (_lnk(lab, lab_url(d, lab), interactive), l["n"], _n(l["cost"]), _n(l["price"])))
        h.append("<tr class='sum'><td colspan='2'><b>المجموع الكلي للفترة</b></td><td><b>%d</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr></tbody></table>"
                 % (tot_n, _n(tot_cost), _n(tot_price)))
        h.append("<div class='card'><h3 style='margin:0 0 8px'>مجموع كل مختبر بالفترة</h3><table><thead><tr><th>المختبر</th><th>عدد التحاليل</th><th>المبلغ (التكلفة)</th><th>سعر المريض</th></tr></thead><tbody>")
        for lab, l in sorted(labs.items(), key=lambda kv: -kv[1]["cost"]):
            url = "/stats-plus/view?kind=out&from=%s&to=%s&lab=%s" % (f, t, quote(lab))
            h.append("<tr><td>%s</td><td>%d</td><td class='num'>%s</td><td class='num'>%s</td></tr>" % (_lnk(lab, url, interactive), l["n"], _n(l["cost"]), _n(l["price"])))
        h.append("</tbody></table></div>")
        return "".join(h)
    # عرض تفصيلي: يوم واحد أو مختبر محدد
    if len(labs) > 1 or f != t:
        h.append("<table><thead><tr><th>المختبر</th><th>عدد التحاليل</th><th>المبلغ (التكلفة)</th><th>سعر المريض</th></tr></thead><tbody>")
        for lab, l in sorted(labs.items(), key=lambda kv: -kv[1]["cost"]):
            h.append("<tr><td><b>%s</b></td><td>%d</td><td class='num'>%s</td><td class='num'>%s</td></tr>" % (_E(lab), l["n"], _n(l["cost"]), _n(l["price"])))
        h.append("<tr class='sum'><td><b>المجموع</b></td><td><b>%d</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr></tbody></table>" % (tot_n, _n(tot_cost), _n(tot_price)))
    for d in sorted(days):
        for lab, l in sorted(days[d].items(), key=lambda kv: -kv[1]["cost"]):
            h.append("<div class='card'><h3 style='margin:0 0 8px'>%s — %s</h3><table><thead><tr><th>المريض</th><th>نوع التحليل</th>"
                     "<th>سعر المريض</th><th>المبلغ (التكلفة)</th></tr></thead><tbody>" % (_E(d), _E(lab)))
            for r in l["rows"]:
                h.append("<tr><td>%s</td><td>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
                         % (_E(r["pname"] or ""), _E(r["tname"]), _n(r["price"]), _n(r["cost"])))
            h.append("<tr class='sub'><td colspan='2'><b>مجموع %s بتاريخ %s (%d تحليل)</b></td><td class='num'><b>%s</b></td><td class='num'><b>%s</b></td></tr></tbody></table></div>"
                     % (_E(lab), _E(d), l["n"], _n(l["price"]), _n(l["cost"])))
    return "".join(h)


def _page(db, kind, f, t, lab_name, interactive=True, phone="", ctx=None, lab_q="", full=False):
    ctx = ctx or {}
    if kind == "day":
        body = _day_body(db, f, t, ctx, lab_q, full)
    elif kind == "exp":
        body = _exp_body(db, f, t, ctx, lab_q, full, interactive)
    elif kind == "out":
        body = _out_body(db, f, t, lab_q, full, interactive)
    elif kind == "doc":
        body = _doc_body(db, f, t, ctx, lab_q, full)
    else:
        body = _in_body(db, f, t)
    title = "%s — %s" % (_TITLES[kind], _period(f, t))
    if lab_q and kind in ("day", "in", "out"):
        title += " — مختبر: " + lab_q
    h = [_head(title, lab_name)]
    if interactive:
        q = "kind=%s&from=%s&to=%s&lab=%s&full=%d" % (kind, f, t, lab_q, 1 if full else 0)
        modes = [("day", "👥 تفاصيل المرضى"), ("in", "🧪 مختبرات أرسلت لنا"), ("out", "📤 تحاليل أرسلناها"),
                 ("doc", "👨‍⚕️ حسابات الأطباء"), ("exp", "💸 الصرفيات")]
        mb = "".join("<button type='button' class='btn%s' onclick=\"go('%s')\">%s</button>" % (" on" if k == kind else "", k, lbl) for k, lbl in modes)
        h.append(
            "<div class='top'><a class='btn p' href='javascript:void(0)' onclick=\"if(history.length>1){history.back()}else{location.href='/'}\">↩ رجوع</a>"
            "<a class='btn' href='/'>🏠 الشاشة الرئيسية</a><div class='modes'>%s</div>"
            "<form id='f' method='get' style='display:flex;gap:6px;align-items:center;flex-wrap:wrap'><input type='hidden' name='kind' id='k' value='%s'>"
            "<input type='date' name='from' value='%s'><input type='date' name='to' value='%s'>"
            "<input type='text' name='lab' value='%s' list='labs' placeholder='بحث باسم المختبر المُرسِل' style='width:190px'><datalist id='labs'>%s</datalist>"
            "<label class='chk'><input type='checkbox' name='full' value='1' %s>أسماء كاملة</label><button class='btn'>عرض</button></form>"
            "<a class='btn p' href='/stats-plus/pdf?%s'>📄 PDF</a>"
            "<input type='text' id='ph' placeholder='رقم واتساب (964…)' value='%s' style='width:150px;direction:ltr'>"
            "<button class='btn g' onclick='sendWa()'>📲 إرسال واتساب</button>"
            "<h1>%s</h1></div><div id='msg'></div><div class='wrap'><div class='card'>"
            % (mb, kind, f, t, _E(lab_q), "".join("<option value='%s'>" % _E(n) for n in _lab_names(db, ctx, f, t)),
               "checked" if full else "", _E(q), _E(phone), _E(title)))
        h.append(body)
        h.append("</div></div><script>function go(k){document.getElementById('k').value=k;document.getElementById('f').submit()}"
                 "function sendWa(){var p=document.getElementById('ph').value;"
                 "fetch('/stats-plus/wa?%s',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:p})})"
                 ".then(function(r){return r.json()}).then(function(j){document.getElementById('msg').textContent=j.message||'تم'})"
                 ".catch(function(e){document.getElementById('msg').textContent='فشل: '+e})}</script></body></html>" % _E(q))
    else:
        h.append("<div class='wrap'><h2 style='text-align:center'>%s</h2><h3 style='text-align:center;margin-top:0'>%s</h3><div class='card'>%s</div></div></body></html>"
                 % (_E(lab_name), _E(title), body))
    return "".join(h)


def _lab_names(db, ctx, f, t):
    names = set()
    try:
        for r in db.execute("SELECT DISTINCT rc.name FROM visits v JOIN referral_centers rc ON rc.id=v.referral_center_id "
                            "WHERE substr(v.created_at,1,10) BETWEEN ? AND ?", (f, t)).fetchall():
            if r[0]:
                names.add(r[0])
    except Exception:
        pass
    for r in _cloud_rows(ctx, f, t):
        if r["is_lab"] and r["sender"]:
            names.add(r["sender"])
    return sorted(names)


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
 function labq(){var i=document.getElementById('spLab');return i&&i.value.trim()?'&lab='+encodeURIComponent(i.value.trim()):'';}
 function open_(kind){location.href='/stats-plus/view?kind='+kind+range()+labq();}
 function bar(){
  if(document.getElementById('spBar'))return;
  var dates=document.querySelectorAll('input[type=date]');if(!dates.length)return;
  var anchor=dates[dates.length-1];
  var showBtn=null;document.querySelectorAll('button,input[type=submit]').forEach(function(b){if(!showBtn&&/^\s*عرض\s*$/.test(b.textContent||b.value||''))showBtn=b;});
  var host=(showBtn&&showBtn.parentNode)||anchor.parentNode;
  var b=document.createElement('div');b.id='spBar';
  b.style.cssText='display:flex;gap:6px;flex-wrap:wrap;align-items:center;direction:rtl;margin:8px 0';
  function mk(txt,kind){var a=document.createElement('button');a.type='button';a.textContent=txt;
   a.style.cssText='background:#205072;color:#fff;border:0;border-radius:9px;padding:8px 12px;font:700 13px Tahoma;cursor:pointer';
   a.onclick=function(e){e.preventDefault();open_(kind);};return a;}
  var inp=document.createElement('input');inp.type='text';inp.id='spLab';inp.placeholder='بحث باسم المختبر المُرسِل';
  inp.style.cssText='padding:7px 9px;border:1px solid #94a3b8;border-radius:8px;font:13px Tahoma;width:190px';
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();open_('day');}});
  b.appendChild(inp);
  b.appendChild(mk('👥 تفاصيل المرضى','day'));b.appendChild(mk('🧪 مختبرات أرسلت لنا','in'));b.appendChild(mk('📤 تحاليل أرسلناها','out'));
  b.appendChild(mk('👨‍⚕️ حسابات الأطباء','doc'));b.appendChild(mk('💸 الصرفيات','exp'));
  if(showBtn&&showBtn.parentNode){showBtn.parentNode.insertBefore(b,showBtn.nextSibling);}else{anchor.parentNode.insertBefore(b,anchor.nextSibling);}
 }
 function go(){mark();bar();}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',go);else go();
 try{new MutationObserver(function(){mark();bar();}).observe(document.body,{childList:true,subtree:true});}catch(e){}
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

    def _opts():
        return (request.args.get("lab") or "").strip(), request.args.get("full") == "1"

    def _range(db):
        """بدون تواريخ بالرابط: من بداية الشهر إلى آخر يوم أُدخل فيه مرضى (بالبرنامجين)."""
        if not (request.args.get("from") or request.args.get("to")):
            return _default_range(db, ctx)
        return None

    @app.route("/stats-plus/view")
    @login_required
    def sp_view():
        db = get_db()
        kind, f, t = _args()
        dr = _range(db)
        if dr:
            f, t = dr
        lq, full = _opts()
        lab = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "") or "المختبر"
        return Response(_page(db, kind, f, t, lab, True, get_setting(db, "stats_wa_phone", "") or "", ctx, lq, full), mimetype="text/html")

    @app.route("/stats-plus/cloud-test")
    @login_required
    def sp_cloud_test():
        """تشخيص ربط مرضى السجل: يبين هل وصلت صفوف من السحابة وأي مسار اشتغل."""
        db = get_db()
        f, t = _default_range(db, ctx)
        fn = ctx.get("cloud_logs")
        rows = _cloud_rows(ctx, "2000-01-01", "2999-12-31") if fn else []
        st = getattr(fn, "state", {}) if fn else {}
        msg = "مرضى السجل غير النازلين للـLIS (المقروءين من السحابة): %d — المسار: %s — آخر خطأ: %s" % (len(rows), st.get("path") or "—", st.get("err") or "لا يوجد")
        return Response("<meta charset='utf-8'><body dir='rtl' style='font:16px Tahoma;padding:20px'>%s</body>" % _E(msg), mimetype="text/html")

    @app.route("/stats-plus/pdf")
    @login_required
    def sp_pdf():
        db = get_db()
        kind, f, t = _args()
        lab = get_setting(db, "app_name_ar", "") or get_setting(db, "app_name", "") or "المختبر"
        lq, full = _opts()
        path = ctx["make_pdf"](_page(db, kind, f, t, lab, False, "", ctx, lq, full), "stats_%s_%s_%s" % (kind, f, t))
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
            lq, full = _opts()
            path = ctx["make_pdf"](_page(db, kind, f, t, lab, False, "", ctx, lq, full), "stats_%s_%s_%s" % (kind, f, t))
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
