# -*- coding: utf-8 -*-
"""
lab_hbcurve.py - إعادة رسم منحنى Hb Electrophoresis (HPLC / طباعة جهاز / Capillary) من جدول القمم
+ تنظيف تعليق التقرير المنسّق (حجم خط، رموز) بدون أي مكتبة خارجية (Python القياسي فقط).

الفكرة: الصورة الملتقطة بالموبايل لا تنطبع. نقرأ الأرقام (بالذكاء الصناعي أو يدوياً) ونراجعها،
ثم يرسم البرنامج المنحنى SVG نظيف. المنحنى "مُعاد بناؤه" من جدول القمم وليس الإشارة الخام للجهاز،
ولذلك يُكتب تحته سطر صغير يوضح ذلك.
"""
import math
import re
from html import escape
from html.parser import HTMLParser

SOURCES = ("printout", "hplc", "capillary")

# ---------------------------------------------------------------- أسماء التحليل (إنجليزي فقط)
_AR = re.compile(r"[؀-ۿݐ-ݿ]")
_TITLES = {
    "printout": "Hb Variant Analysis (HPLC)",
    "hplc": "Hb Variant Analysis (HPLC)",
    "capillary": "Hb Electrophoresis (Capillary)",
}


def en_title(test_name, source=None, fallback="Hb Electrophoresis"):
    """عنوان التقرير دائماً إنجليزي. إذا كان اسم التحليل بالعربية (أو فارغاً) نستعمل عنواناً إنجليزياً."""
    name = (test_name or "").strip()
    if source in _TITLES:
        return _TITLES[source]
    if name and not _AR.search(name):
        return name
    return fallback


# ---------------------------------------------------------------- تنظيف البيانات
def _s(v, n=60):
    return str(v if v is not None else "").strip()[:n]


def _num(v):
    try:
        f = float(str(v).replace(",", "").replace("*", "").strip())
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def normalize(data):
    """يقبل dict خام (من الذكاء أو من الشاشة) ويرجّع dict نظيف بحقول معروفة فقط. لا يخترع أي قيمة."""
    d = data if isinstance(data, dict) else {}
    src = d.get("source") if d.get("source") in SOURCES else "hplc"
    peaks = []
    for p in (d.get("peaks") or [])[:40]:
        if not isinstance(p, dict):
            continue
        name = _s(p.get("name"), 40)
        if not name:
            continue
        row = dict((k, _s(p.get(k), 20)) for k in ("rt", "abs", "area", "pct", "conc"))
        row["name"] = name
        peaks.append(row)
    key = []
    for kv in (d.get("key") or [])[:12]:
        if isinstance(kv, (list, tuple)) and len(kv) == 2 and _s(kv[0]):
            key.append([_s(kv[0], 30), _s(kv[1], 30)])
    hidden = sorted({int(x) for x in (d.get("hidden") or []) if str(x).isdigit() and int(x) < 500})[:300]
    return {"source": src, "device_line": _s(d.get("device_line"), 200), "peaks": peaks,
            "total_area": _s(d.get("total_area"), 30), "key": key, "hidden": hidden}


COLUMNS = {
    "printout": [("Peak", "name"), ("Time (s)", "rt"), ("ABS", "abs"), ("Area", "area"), ("Result %", "pct")],
    "hplc": [("Peak Name", "name"), ("RT (min)", "rt"), ("Area", "area"), ("Area %", "pct"), ("Concentration %", "conc")],
    "capillary": [("Fractions", "name"), ("%", "pct"), ("Ref. %", ""), ("Ref. Conc.", "")],
}


def table_rows(d):
    cols = COLUMNS[d["source"]]
    return [c[0] for c in cols], [[(p.get(c[1], "") if c[1] else "") for c in cols] for p in d["peaks"]]


def key_results(d):
    """النتائج الرئيسية: ما كتبه المستخدم إن وُجد، وإلا نشتقها من الجدول بدون أي حساب جديد."""
    if d["key"]:
        return d["key"]
    want = {"printout": ("HbF", "HbA2"), "hplc": ("F", "A2", "S-window"), "capillary": ("Hb A", "Hb D", "Hb S", "Hb A2", "Hb F", "Hb C")}[d["source"]]
    out = []
    for w in want:
        for p in d["peaks"]:
            if p["name"].lower().replace(" ", "") == w.lower().replace(" ", ""):
                val = p["conc"] if d["source"] == "hplc" and p.get("conc") else p.get("pct", "")
                if val:
                    out.append([p["name"], val + " %"])
                break
    return out


# ---------------------------------------------------------------- رسم المنحنى
_W, _H = 660, 320
_L, _R, _T, _B = 58, 16, 22, 48


def _fmt(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def _build(points, xmin, xmax, ymax, xt, xlabel, ylabel, yticks=None, labels=(), zones=(), fill="#c9c9c9", hidden=()):
    """points: [(x,y)] قيم فعلية. labels: [(x, ytop, text, boxed)]."""
    pw, ph = _W - _L - _R, _H - _T - _B
    sx = lambda x: _L + (x - xmin) / (xmax - xmin) * pw
    sy = lambda y: _T + ph - (y / ymax) * ph
    hid = set(hidden or ())
    cnt = [0]

    def T(markup):
        """نص قابل للحذف: يأخذ رقماً ثابتاً (data-t) ويُحذف إن كان بقائمة hidden. markup فيه {A} مكان وسم البداية."""
        cnt[0] += 1
        return "" if cnt[0] - 1 in hid else markup.replace("<text ", '<text class="hbt" data-t="%d" ' % (cnt[0] - 1), 1)

    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="Arial, Helvetica, sans-serif" font-size="10">' % (_W, _H)]
    o.append('<rect width="%d" height="%d" fill="#fff"/>' % (_W, _H))
    for z in zones:
        o.append('<line x1="%s" y1="%d" x2="%s" y2="%d" stroke="#9a9a9a" stroke-width=".6" stroke-dasharray="4 4"/>' % (_fmt(sx(z)), _T, _fmt(sx(z)), _T + ph))
    base = _T + ph
    poly = " ".join("%s,%s" % (_fmt(sx(x)), _fmt(sy(y))) for x, y in points)
    o.append('<polygon points="%s,%s %s" fill="%s" fill-opacity=".75"/>' % (_fmt(sx(points[0][0])), _fmt(base), poly + " " + "%s,%s" % (_fmt(sx(points[-1][0])), _fmt(base)), fill))
    o.append('<polyline points="%s" fill="none" stroke="#000" stroke-width="1.1" stroke-linejoin="round"/>' % poly)
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#000"/>' % (_L, base, _L + pw, base))
    if yticks is not None:
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#000"/>' % (_L, _T, _L, base))
        for yv, txt in yticks:
            o.append('<line x1="%d" y1="%s" x2="%d" y2="%s" stroke="#000"/>' % (_L - 4, _fmt(sy(yv)), _L, _fmt(sy(yv))))
            o.append(T('<text x="%d" y="%s" text-anchor="end" dominant-baseline="middle">%s</text>' % (_L - 7, _fmt(sy(yv)), escape(txt))))
    for xv in xt:
        o.append('<line x1="%s" y1="%s" x2="%s" y2="%d" stroke="#000"/>' % (_fmt(sx(xv)), _fmt(base), _fmt(sx(xv)), base + 4))
        o.append(T('<text x="%s" y="%d" text-anchor="middle">%s</text>' % (_fmt(sx(xv)), base + 16, ("%g" % xv))))
    o.append(T('<text x="%s" y="%d" text-anchor="middle" font-size="11">%s</text>' % (_fmt(_L + pw / 2), _H - 8, escape(xlabel))))
    o.append(T('<text transform="translate(14 %s) rotate(-90)" text-anchor="middle" font-size="11">%s</text>' % (_fmt(_T + ph / 2), escape(ylabel))))
    for x, yv, txt, boxed in labels:
        px, py = sx(x), max(_T + 6, sy(yv) - 4)
        if boxed:
            w = 7 * len(txt) + 8
            tt = T('<text x="%s" y="%s" text-anchor="middle" font-size="9">%s</text>' % (_fmt(px), _fmt(py - 5), escape(txt)))
            if tt:
                o.append('<rect x="%s" y="%s" width="%d" height="14" fill="#fff" stroke="#000" stroke-width=".6"/>' % (_fmt(px - w / 2), _fmt(py - 15), w))
                o.append(tt)
        else:
            o.append(T('<text transform="translate(%s %s) rotate(-90)" font-size="8">%s</text>' % (_fmt(px + 3), _fmt(py), escape(txt))))
    o.append("</svg>")
    return "".join(o)


def _sum_curve(xs, peaks):
    """peaks: [(mu, h, sl, sr)] → قيم y لكل x. (Gaussian مقسوم: ذيل أيمن أطول عند sr>sl)"""
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


_CAP_POS = {"hba": 151, "hbf": 181, "hbd": 207, "hbs": 213, "hbe": 242, "hba2": 242, "hbc": 262}


def curve_svg(d):
    """يرجّع SVG نظيف، أو "" إذا ما كو بيانات كافية للرسم (نرسم فقط القمم المعروفة المواقع)."""
    d = normalize(d)
    src = d["source"]
    pk = d["peaks"]
    if not pk:
        return ""
    if src == "printout":
        xmax, items = 360.0, []
        for p in pk:
            rt, h = _num(p["rt"]), _num(p["abs"])
            if rt is None or h is None or h <= 0 or not 0 <= rt <= xmax:
                continue
            a = _num(p["area"])
            s = max(1.2, min(3.2, (a / h) / 63.0 * 2.2)) if a and a > 0 else 2.5
            items.append((rt, h, s, s, "%g" % rt))
        if not items:
            return ""
        top = max(i[1] for i in items)
        ymax = math.ceil(top * 1.25 / 100.0) * 100.0
        xs = [i * xmax / 1500.0 for i in range(1501)]
        ys = _sum_curve(xs, [(m, h, sl, sr) for m, h, sl, sr, _ in items])
        step = 100 if ymax <= 600 else 200
        return _build(list(zip(xs, ys)), 0, xmax, ymax, range(0, 361, 50), "Time (s)", "ABS",
                      yticks=[(v, "%d" % v) for v in range(0, int(ymax) + 1, step)],
                      labels=[(m, h, t, False) for m, h, sl, sr, t in items], hidden=d["hidden"])
    if src == "hplc":
        items = []
        for p in pk:
            rt = _num(p["rt"])
            ar = _num(p["area"])
            pc = _num(p["pct"]) if _num(p["pct"]) is not None else _num(p["conc"])
            w = ar if ar and ar > 0 else pc
            if rt is None or not w or w <= 0:
                continue
            items.append((rt, w, p["name"]))
        if not items:
            return ""
        tot = sum(i[1] for i in items)
        raw = []
        for rt, w, n in items:
            s = 0.075 if w / tot > 0.05 else 0.06
            raw.append((rt, (w / tot) / (s * 2.5066), s, "%.3f" % rt))
        hm = max(r[1] for r in raw)
        xmax = max(6.0, math.ceil(max(i[0] for i in items) + 0.6))
        xs = [i * xmax / 1800.0 for i in range(1801)]
        ys = _sum_curve(xs, [(m, h / hm * 100.0, s, s) for m, h, s, _ in raw])
        return _build(list(zip(xs, ys)), 0, xmax, 125.0, range(0, int(xmax) + 1), "Time (min.)", "Relative response",
                      labels=[(m, h / hm * 100.0, t, False) for m, h, s, t in raw], hidden=d["hidden"])
    # capillary
    items = []
    for p in pk:
        pc = _num(p["pct"])
        pos = _num(p["rt"])
        if pos is None:
            pos = _CAP_POS.get(re.sub(r"[^a-z0-9]", "", p["name"].lower()))
        if pc is None or pc <= 0 or pos is None:
            continue
        nm = p["name"].lower().replace(" ", "")
        sl = 9.0 if nm == "hba" else 3.0 if nm in ("hba2", "hbe") else 6.0
        sr = sl * (1.35 if nm == "hba" else 1.1)
        items.append((pos, pc / ((sl + sr) / 2 * 2.5066), sl, sr, p["name"]))
    if not items:
        return ""
    hm = max(i[1] for i in items)
    xs = [i * 300.0 / 2400.0 for i in range(2401)]
    ys = _sum_curve(xs, [(m, h / hm * 0.27, sl, sr) for m, h, sl, sr, _ in items])
    zones = (20, 40, 60, 80, 100, 120, 140, 165, 180, 195, 215, 230, 260, 280)
    return _build(list(zip(xs, ys)), 0, 300.0, 0.3, range(0, 301, 50), "Migration position", "Relative O.D.", zones=zones,
                  labels=[(m, h / hm * 0.27, t, True) for m, h, sl, sr, t in items], hidden=d["hidden"])


# ---------------------------------------------------------------- تعليق منسّق آمن
_OK_TAGS = {"b", "strong", "i", "em", "u", "br", "p", "div", "span", "ul", "ol", "li", "sub", "sup", "blockquote"}
_FONT_PX = {"1": 10, "2": 13, "3": 16, "4": 18, "5": 24, "6": 32, "7": 48}
_RE_SIZE = re.compile(r"font-size\s*:\s*(\d{1,3}(?:\.\d+)?)\s*(px|pt)", re.I)


def _style_ok(style):
    out = []
    m = _RE_SIZE.search(style or "")
    if m:
        px = float(m.group(1)) * (1.333 if m.group(2).lower() == "pt" else 1)
        out.append("font-size:%dpx" % max(8, min(72, round(px))))
    s = (style or "").lower()
    if re.search(r"font-weight\s*:\s*(bold|[6-9]00)", s):
        out.append("font-weight:700")
    if re.search(r"font-style\s*:\s*italic", s):
        out.append("font-style:italic")
    if re.search(r"text-decoration[^;]*underline", s):
        out.append("text-decoration:underline")
    m2 = re.search(r"text-align\s*:\s*(left|right|center|justify)", s)
    if m2:
        out.append("text-align:" + m2.group(1))
    vals = {}
    ms = re.search(r"(?<![-\w])margin\s*:\s*([\d.]+)(?:px)?\s+([\d.]+)(?:px)?\s+([\d.]+)(?:px)?\s+([\d.]+)(?:px)?", s)
    if ms:   # الشكل المختصر الذي يخرجه المتصفح عند Indent: margin: 0 0 0 40px
        vals["right"], vals["left"] = float(ms.group(2)), float(ms.group(4))
    for side in ("left", "right"):
        m3 = re.search(r"margin-%s\s*:\s*(\d{1,3}(?:\.\d+)?)px" % side, s)
        if m3:
            vals[side] = float(m3.group(1))
    for side in ("left", "right"):
        if vals.get(side, 0) > 0:
            out.append("margin-%s:%dpx" % (side, min(300, round(vals[side]))))
    return ";".join(out)


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.open_font = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object"):
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag == "font":                       # execCommand('fontSize') القديم
            px = _FONT_PX.get(str(a.get("size") or ""))
            self.out.append('<span style="font-size:%dpx">' % px if px else "<span>")
            self.open_font.append(True)
            return
        if tag not in _OK_TAGS:
            return
        at = ""
        st = _style_ok(a.get("style"))
        if st:
            at += ' style="%s"' % st
        if a.get("dir") in ("ltr", "rtl"):
            at += ' dir="%s"' % a["dir"]
        self.out.append("<%s%s>" % (tag, at))

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object"):
            self.skip = max(0, self.skip - 1)
        elif not self.skip:
            if tag == "font":
                if self.open_font:
                    self.open_font.pop()
                    self.out.append("</span>")
            elif tag in _OK_TAGS and tag != "br":
                self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data))


def clean_comment_html(raw):
    p = _Clean()
    try:
        p.feed(str(raw or "")[:30000])
        p.close()
    except Exception:
        return ""
    html = "".join(p.out)
    return html if re.sub(r"<[^>]*>|&nbsp;|\s", "", html) else ""
