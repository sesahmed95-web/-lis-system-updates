# -*- coding: utf-8 -*-
"""
v44 — قالب «Hemoglobin Electrophoresis (Capillary)»: منحنى + جدول نتائج بنفس تصميم نموذج Sebia.
- يعرض فقط القمم الموجودة (لها نسبة). Hb A يُحسب تلقائياً = 100 − (Hb A2 + Hb F + Hb S الموجودة) إذا ما كان مكتوباً.
- ارتفاع كل قمة يتناسب مع مساحتها (النسبة) فالقمم الصغيرة تبقى صغيرة.
- تدريج الزمن بالثواني أسفل المخطط. لا يضيف أي بيانات غير موجودة (لا Z-zones ولا أسماء/تواريخ مخترعة).
"""
import math
import re
from html import escape

POS = {"hba": 150, "hbf": 185, "hbd": 207, "hbs": 221, "hba2": 248, "hbe": 234, "hbc": 263, "hbh": 104}
SIG = {"hba": (4.0, 5.0), "hbf": (1.9, 2.2), "hbd": (1.9, 2.2), "hbs": (1.9, 2.2), "hba2": (1.8, 2.1), "hbe": (1.8, 2.1), "hbc": (1.9, 2.2), "hbh": (2.4, 2.8)}
LABEL = {"hba": "Hb A", "hbf": "Hb F", "hba2": "Hb A2", "hbs": "Hb S", "hbd": "Hb D", "hbc": "Hb C", "hbe": "Hb E", "hbh": "Hb H"}
COLORS = {"hba": "#1D4ED8", "hbf": "#16A34A", "hba2": "#DC2626", "hbs": "#9333EA", "hbd": "#EA580C", "hbc": "#0891B2", "hbe": "#CA8A04", "hbh": "#DB2777"}
# مناطق (Z) كما بشاشة جهاز Sebia/Phoresis: (الاسم، بداية، نهاية) بمحور 0..300 — كل قمة تقع بمنتصف منطقتها
ZONES = [("Z15", 0, 44), ("Z14", 44, 58), ("Z13", 58, 78), ("Z12", 78, 118), ("Z11", 118, 132), ("Z10", 132, 142),
         ("Z(A)", 142, 158), ("Z8", 158, 175), ("Z(F)", 175, 196), ("Z(D)", 196, 214), ("Z(S)", 214, 227),
         ("Z(E)", 227, 241), ("Z(A2)", 241, 256), ("Z(C)", 256, 271), ("Z1", 271, 300)]
ORDER = ["hba", "hbf", "hba2", "hbs", "hbd", "hbc", "hbe", "hbh"]


def _num(v):
    try:
        f = float(str(v).replace(",", "").replace("*", "").replace("%", "").strip())
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _key(name):
    k = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if k in ("a", "f", "a2", "s", "d", "c", "e", "h"):
        k = "hb" + k
    if k == "hba0" or k == "hba1":
        k = "hba"
    return k


def parse_range(text):
    """'96.8 - 97.8' / '≤ 0.5' / '=< 0.5' / '< 1' / '≥ 2' → (lo, hi) أو (None, None)"""
    t = str(text or "").strip().replace("–", "-").replace("—", "-").replace(",", ".")
    m = re.match(r"^([\d.]+)\s*-\s*([\d.]+)$", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(r"^(?:<=|=<|≤|<)\s*([\d.]+)$", t)
    if m:
        return None, float(m.group(1))
    m = re.match(r"^(?:>=|=>|≥|>)\s*([\d.]+)$", t)
    if m:
        return float(m.group(1)), None
    return None, None


def _fmt(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def _g(xs, peaks):
    ys = []
    for x in xs:
        y = 0.0
        for mu, h, sl, sr in peaks:
            s = sl if x < mu else sr
            z = (x - mu) / s
            if -6 < z < 6:
                y += h * math.exp(-0.5 * z * z)
        ys.append(y)
    return ys


def build(data, opts=None):
    """data: dict من lab_hbcurve.normalize. يرجّع None إذا ما كو نسب صالحة."""
    o = opts or {}
    items = {}
    extra = []                                   # قمم معروفة الاسم لكن غير ضمن القائمة (تظهر بالجدول فقط)
    for p in (data or {}).get("peaks") or []:
        pc = _num(p.get("pct"))
        if pc is None or pc <= 0:
            continue
        k = _key(p.get("name"))
        if k in LABEL:
            items.setdefault(k, {"pct": pc, "pos": _num(p.get("rt")), "name": LABEL[k]})
        else:
            extra.append({"name": str(p.get("name") or "").strip(), "pct": pc, "pos": _num(p.get("rt")), "k": k})
    calc_a = False
    if "hba" not in items and o.get("calc_a", 1):
        have = [v["pct"] for k, v in items.items() if k != "hba"] + [e["pct"] for e in extra]
        if have:
            a = round(100.0 - sum(have), 2)
            if a > 0:
                items["hba"] = {"pct": a, "pos": None, "name": "Hb A"}
                calc_a = True
    if not items and not extra:
        return None
    rows = []
    for k in ORDER:
        if k in items:
            nt = o.get("norm_" + k.replace("hb", "")) or ""
            lo, hi = parse_range(nt)
            pc = items[k]["pct"]
            flag = "▼" if (lo is not None and pc < lo) else "▲" if (hi is not None and pc > hi) else ""
            t0 = (nt or "").strip()
            if not flag and t0[:1] == "<" and t0[:2] != "<=" and hi is not None and pc >= hi:
                flag = "▲"   # أصغر من (صارم): القيمة المساوية خارج الطبيعي
            if not flag and t0[:1] == ">" and t0[:2] != ">=" and lo is not None and pc <= lo:
                flag = "▼"   # أكبر من (صارم)
            rows.append({"k": k, "name": items[k]["name"], "pct": _fmt(pc), "norm": nt, "flag": flag})
    for e in extra:
        rows.append({"k": e["k"], "name": e["name"], "pct": _fmt(e["pct"]), "norm": "", "flag": ""})
    # ---- المنحنى: فقط القمم المعروفة الموقع
    pk = []
    for k in ORDER:
        if k in items:
            pos = items[k]["pos"] if items[k]["pos"] is not None else POS.get(k)
            if pos is None:
                continue
            sl, sr = SIG[k]
            pk.append((k, pos, items[k]["pct"], sl, sr))
    for e in extra:
        if e["pos"] is not None:
            pk.append((e["k"], e["pos"], e["pct"], 2.4, 2.8))
    svg = ""
    if pk:
        bw = bool(o.get("bw", 1))
        zon = bool(o.get("show_zones", 1))
        W, H, L, R, T, B = 660, (285 if zon else 230), 16, 16, (42 if zon else 26), 36
        pw, ph = W - L - R, H - T - B
        hs = [pc ** 0.75 for k, pos, pc, sl, sr in pk]      # الارتفاع يتناسب مع النسبة (القمم الصغيرة تبقى صغيرة)
        hm = max(hs)
        hs = [max(h, hm * 0.035) for h in hs]
        sx = lambda x: L + x / 300.0 * pw
        sy = lambda y: T + ph - y / hm * ph * 0.92
        base = T + ph
        xs = [i * 300.0 / 1200.0 for i in range(1201)]
        out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="Arial, Helvetica, sans-serif" font-size="10">' % (W, H),
               '<rect width="%d" height="%d" fill="#fff"/>' % (W, H)]
        if zon:
            for i, (zn, z0, z1) in enumerate(ZONES):
                x0, x1 = sx(z0), sx(z1)
                has = any(z0 <= pos < z1 for (k, pos, pc, sl, sr) in pk)
                cx = (x0 + x1) / 2
                ry = 0   # خط مستقيم واحد
                tw = 4.0 * len(zn) + 5
                if has:
                    out.append('<rect x="%s" y="%d" width="%s" height="13" fill="#fff" stroke="#000" stroke-width=".8"/>' % (_fmt(cx - tw / 2), 6.5 + ry, _fmt(tw)))
                out.append('<text x="%s" y="%d" text-anchor="middle" font-size="7" font-weight="%s">%s</text>' % (_fmt(cx), 16.5 + ry, "700" if has else "400", escape(zn)))
        if not bw:   # كل قمة بلونها
            for (k, pos, pc, sl, sr), h in zip(pk, hs):
                ys = _g(xs, [(pos, h, sl, sr)])
                pts = " ".join("%s,%s" % (_fmt(sx(x)), _fmt(sy(y))) for x, y in zip(xs, ys) if y > hm * 0.002 or abs(x - pos) < 2)
                if pts:
                    out.append('<polygon points="%s" fill="%s" fill-opacity=".45"/>' % (pts, COLORS.get(k, "#555")))
        ysum = _g(xs, [(pos, h, sl, sr) for (k, pos, pc, sl, sr), h in zip(pk, hs)])
        poly = " ".join("%s,%s" % (_fmt(sx(x)), _fmt(sy(y))) for x, y in zip(xs, ysum))
        if bw:
            out.append('<polygon points="%s,%s %s,%s %s" fill="#e2e2e2"/>' % (_fmt(sx(0)), _fmt(base), poly, _fmt(sx(300)), _fmt(base)))
        out.append('<polyline points="%s" fill="none" stroke="#000" stroke-width="0.9" stroke-linejoin="round"/>' % poly)
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#000" stroke-width="0.7"/>' % (L, base, L + pw, base))
        if o.get("show_scale", 1):
            for xv in range(20, 301, 20):
                out.append('<line x1="%s" y1="%d" x2="%s" y2="%d" stroke="#000"/>' % (_fmt(sx(xv)), base, _fmt(sx(xv)), base + 4))
                out.append('<text x="%s" y="%d" text-anchor="middle" font-size="9">%d</text>' % (_fmt(sx(xv)), base + 15, xv))
            out.append('<text x="%s" y="%d" text-anchor="middle" font-size="10" font-weight="700">Time (s)</text>' % (_fmt(L + pw / 2), H - 6))
        # أسماء القمم: كل اسم فوق قمته مباشرة؛ إذا تلاصق مع اسم قمة مجاورة يرتفع الأعلى (القمة الأطول) بدون أي تراكب
        labs = []
        for (k, pos, pc, sl, sr), h in zip(pk, hs):
            nm = LABEL.get(k) or next((e["name"] for e in extra if e["k"] == k), k)
            labs.append({"k": k, "nm": nm, "px": sx(pos), "py": sy(h), "w": 6.2 * len(nm) + 8})
        placed = []
        for L_ in sorted(labs, key=lambda d: -d["py"]):          # من الأقصر (py أكبر) إلى الأطول
            ty0 = L_["py"] - 8
            ty = ty0
            for step in range(0, 8):
                ty = ty0 - step * 15
                if ty < T - 12:
                    ty = ty0
                    break
                r = (L_["px"] - L_["w"] / 2 - 2, ty - 12, L_["px"] + L_["w"] / 2 + 2, ty + 3)
                if not any(r[0] < q[2] and r[2] > q[0] and r[1] < q[3] and r[3] > q[1] for q in placed):
                    break
            L_["ty"] = max(ty, 22)
            placed.append((L_["px"] - L_["w"] / 2 - 2, L_["ty"] - 12, L_["px"] + L_["w"] / 2 + 2, L_["ty"] + 3))
        for L_ in labs:
            px, ty, w = L_["px"], L_["ty"], L_["w"]
            if L_["py"] - ty > 14:     # اسم مرفوع: خط رفيع يربطه بقمته
                out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#000" stroke-width=".5"/>' % (_fmt(px), _fmt(ty + 2), _fmt(px), _fmt(L_["py"] - 1)))
            out.append('<rect x="%s" y="%s" width="%s" height="13" fill="#fff" stroke="#000" stroke-width=".7"/>' % (_fmt(px - w / 2), _fmt(ty - 11), _fmt(w)))
            out.append('<text x="%s" y="%s" text-anchor="middle" font-size="9" font-weight="700">%s</text>' % (_fmt(px), _fmt(ty - 1.5), escape(L_["nm"])))
        out.append("</svg>")
        svg = "".join(out)
    return {"svg": svg, "rows": rows, "calc_a": calc_a, "device_line": (data or {}).get("device_line", "")}
