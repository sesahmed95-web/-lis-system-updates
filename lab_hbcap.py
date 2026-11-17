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

POS = {"hba": 151, "hbf": 181, "hbd": 207, "hbs": 213, "hba2": 242, "hbe": 250, "hbc": 262, "hbh": 112}
SIG = {"hba": (4.6, 5.8), "hbf": (2.4, 2.8), "hbd": (2.4, 2.8), "hbs": (2.4, 2.8), "hba2": (2.2, 2.6), "hbe": (2.2, 2.6), "hbc": (2.4, 2.8), "hbh": (3.0, 3.4)}
LABEL = {"hba": "Hb A", "hbf": "Hb F", "hba2": "Hb A2", "hbs": "Hb S", "hbd": "Hb D", "hbc": "Hb C", "hbe": "Hb E", "hbh": "Hb H"}
COLORS = {"hba": "#1D4ED8", "hbf": "#16A34A", "hba2": "#DC2626", "hbs": "#9333EA", "hbd": "#EA580C", "hbc": "#0891B2", "hbe": "#CA8A04", "hbh": "#DB2777"}
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
        W, H, L, R, T, B = 660, 215, 16, 16, 26, 36
        pw, ph = W - L - R, H - T - B
        hs = [pc ** 0.75 for k, pos, pc, sl, sr in pk]      # الارتفاع يتناسب مع النسبة (القمم الصغيرة تبقى صغيرة)
        hm = max(hs)
        hs = [max(h, hm * 0.035) for h in hs]
        sx = lambda x: L + x / 300.0 * pw
        sy = lambda y: T + ph - y / hm * ph * 0.82
        base = T + ph
        xs = [i * 300.0 / 1200.0 for i in range(1201)]
        out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="Arial, Helvetica, sans-serif" font-size="10">' % (W, H),
               '<rect width="%d" height="%d" fill="#fff"/>' % (W, H)]
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
        last_x, lvl = -999, 0
        for (k, pos, pc, sl, sr), h in sorted(zip(pk, hs), key=lambda t: t[0][1]):
            px, py = sx(pos), sy(h)
            lvl = lvl + 1 if px - last_x < 34 else 0
            last_x = px
            nm = LABEL.get(k) or next((e["name"] for e in extra if e["k"] == k), k)
            w = 6.2 * len(nm) + 8
            ty = max(T - 8, py - 8 - lvl * 16)
            out.append('<rect x="%s" y="%s" width="%s" height="13" fill="#fff" stroke="#000" stroke-width=".7"/>' % (_fmt(px - w / 2), _fmt(ty - 11), _fmt(w)))
            out.append('<text x="%s" y="%s" text-anchor="middle" font-size="9" font-weight="700">%s</text>' % (_fmt(px), _fmt(ty - 1.5), escape(nm)))
        out.append("</svg>")
        svg = "".join(out)
    return {"svg": svg, "rows": rows, "calc_a": calc_a, "device_line": (data or {}).get("device_line", "")}
