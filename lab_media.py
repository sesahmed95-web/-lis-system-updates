# -*- coding: utf-8 -*-
"""
lab_media.py - تنظيف صور/لقطات نتائج الأجهزة (Hb Electrophoresis، CBC...) حتى تنطبع بالتقرير مرتبة
بدون ما يبين إنها صورة موبايل: قص الورقة من الخلفية، إزالة ظلال الإضاءة، إزالة حبر الكتابة بالقلم الملوّن،
وخلفية بيضاء نظيفة. يعتمد على Pillow فقط (بدون numpy/OpenCV).
"""
from PIL import Image, ImageChops, ImageFilter, ImageOps

MAX_SIDE = 1800


def _otsu(hist):
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    wb = sb = 0
    best, thr = -1.0, 128
    for i in range(256):
        wb += hist[i]
        if wb == 0:
            continue
        wf = total - wb
        if wf == 0:
            break
        sb += i * hist[i]
        mb, mf = sb / wb, (sum_all - sb) / wf
        var = wb * wf * (mb - mf) ** 2
        if var > best:
            best, thr = var, i
    return thr


def _paper_mask(gray):
    """(box, mask_small) لأكبر منطقة فاتحة = الورقة. mask_small بحجم مصغّر (عرض 120)."""
    w, h = gray.size
    sw = 120
    sh = max(1, int(h * sw / w))
    small = gray.resize((sw, sh), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
    hist = small.histogram()
    thr = _otsu(hist)
    # عتبة أعلى من أوتسو حتى لا تلتصق خلفية فاتحة (طاولة/رخام) بالورقة
    tot, acc, p95 = sum(hist), 0, 255
    for v in range(256):
        acc += hist[v]
        if acc >= 0.95 * tot:
            p95 = v
            break
    thr = int(thr - 0.05 * max(0, p95 - thr))
    m = small.point(lambda v: 255 if v > thr else 0).filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    px = m.load()
    seen = [[False] * sw for _ in range(sh)]
    best = None
    for y0 in range(sh):
        for x0 in range(sw):
            if px[x0, y0] and not seen[y0][x0]:
                stack, comp = [(x0, y0)], []
                seen[y0][x0] = True
                while stack:
                    x, y = stack.pop()
                    comp.append((x, y))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < sw and 0 <= ny < sh and px[nx, ny] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                if best is None or len(comp) > len(best):
                    best = comp
    if not best:
        return None, None
    xs = [c[0] for c in best]
    ys = [c[1] for c in best]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    area = (x2 - x1 + 1) * (y2 - y1 + 1)
    if len(best) < 0.12 * sw * sh or area > 0.97 * sw * sh:
        return None, None
    mk = Image.new("L", (sw, sh), 0)
    mp = mk.load()
    for x, y in best:
        mp[x, y] = 255
    # املأ الثقوب (النص/الرسم داخل الورقة) بملء المستطيل المحيط لكل صف
    for y in range(y1, y2 + 1):
        row = [x for x in range(sw) if mp[x, y]]
        if row:
            for x in range(min(row), max(row) + 1):
                mp[x, y] = 255
    sx, sy = w / sw, h / sh
    pad = 0.006 * max(w, h)
    box = (max(0, int(x1 * sx - pad)), max(0, int(y1 * sy - pad)),
           min(w, int((x2 + 1) * sx + pad)), min(h, int((y2 + 1) * sy + pad)))
    return box, mk


def _pen_mask(rgb, gray):
    """حبر القلم الأزرق/الملوّن فقط (الطباعة الأصلية سوداء/رمادية محايدة)."""
    r, g, b = rgb.split()
    blue = ImageChops.subtract(b, r).point(lambda v: 255 if v > 32 else 0)
    dark = gray.point(lambda v: 255 if v < 185 else 0)
    return ImageChops.multiply(blue, dark).filter(ImageFilter.MaxFilter(5))


def clean_result_image(src_path, dst_path, mode="paper"):
    """mode='paper': ورقة/وصل مطبوع من الجهاز (قص + إزالة الظل + إزالة حبر القلم + خلفية بيضاء).
       mode='screen': لقطة شاشة الجهاز (تحسين خفيف فقط — نحافظ على الألوان)."""
    im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
    if max(im.size) > MAX_SIDE * 1.6:
        im.thumbnail((int(MAX_SIDE * 1.6), int(MAX_SIDE * 1.6)), Image.LANCZOS)
    if mode == "screen":
        return rectify_and_clean(src_path, dst_path)
    box, pmask = _paper_mask(im.convert("L"))
    if box and (box[2] - box[0]) * (box[3] - box[1]) > 0.80 * im.size[0] * im.size[1]:
        box = None        # الصورة أصلاً شبه ورقة كاملة/نظيفة: لا نقص منها شي
    if box:
        im = im.crop(box)
    gray = im.convert("L")
    w, h = gray.size
    k = 8
    small = gray.resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
    bg = small.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(5)).resize((w, h), Image.BILINEAR)
    pen = _pen_mask(im, gray)
    gray = Image.composite(bg, gray, pen)                          # مكان حبر القلم = لون خلفية الورقة
    diff = ImageChops.subtract(bg, gray)                            # الحبر أغمق من خلفية الورقة
    norm = ImageChops.invert(diff.point(lambda v: 0 if v < 16 else min(255, int(v * 1.8))))
    norm = ImageOps.autocontrast(norm, cutoff=1)
    if box:                                                          # حافة ضيقة بيضاء: تخفي بقايا خلفية الطاولة
        nw, nh = norm.size
        mx, my = int(nw * 0.035), int(nh * 0.012)
        edge = Image.new("L", norm.size, 255)
        edge.paste(norm.crop((mx, my, nw - mx, nh - my)), (mx, my))
        norm = edge
    norm = norm.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90, threshold=3))
    if max(norm.size) > MAX_SIDE:
        norm.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    norm.save(dst_path, "PNG", optimize=True)
    return dst_path


# ---------------------------------------------------------------------------
# تصحيح المنظور + تنظيف لقطات/صور شاشة الجهاز حتى تطلع "كأنها مطبوعة من الجهاز مباشرة"
# ---------------------------------------------------------------------------
def _solve(a, b):
    """حل نظام خطي صغير (Gauss) بدون numpy."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        piv = m[c][c] or 1e-12
        m[c] = [v / piv for v in m[c]]
        for r in range(n):
            if r != c:
                f = m[r][c]
                m[r] = [v - f * w for v, w in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def _persp_coeffs(out_pts, in_pts):
    a, b = [], []
    for (x, y), (u, v) in zip(out_pts, in_pts):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    return _solve(a, b)


def warp_quad(im, quad):
    """quad = [(x,y)*4] بترتيب: أعلى-يسار، أعلى-يمين، أسفل-يمين، أسفل-يسار (بإحداثيات البكسل). يرجّع الصورة معدولة مستطيلة."""
    import math
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
    w = int(max(math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x3, y2 - y3)))
    h = int(max(math.hypot(x3 - x0, y3 - y0), math.hypot(x2 - x1, y2 - y1)))
    w, h = max(w, 50), max(h, 50)
    co = _persp_coeffs([(0, 0), (w, 0), (w, h), (0, h)], quad)
    return im.transform((w, h), Image.PERSPECTIVE, co, Image.BICUBIC)


def estimate_skew(gray, max_deg=10.0):
    """زاوية ميلان الصورة (درجات) من خطوط الجدول/النص: نجرّب زوايا ونختار الأوضح بالإسقاط الأفقي. Pillow فقط."""
    w, h = gray.size
    sc = 500.0 / max(w, h)
    sm = gray.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.BILINEAR)
    ink = ImageChops.subtract(sm.filter(ImageFilter.GaussianBlur(6)), sm).point(lambda v: 255 if v > 14 else 0)
    if ink.getbbox() is None:
        return 0.0

    def score(a):
        r = ink.rotate(a, resample=Image.BILINEAR, expand=False)
        v = list(r.resize((1, r.size[1]), Image.BOX).getdata())
        m = sum(v) / len(v)
        return sum((x - m) ** 2 for x in v)

    base = score(0.0)
    best_a, best_s = 0.0, base
    a = -max_deg
    while a <= max_deg + 1e-6:
        sc_ = score(a)
        if sc_ > best_s:
            best_a, best_s = a, sc_
        a += 1.0
    for da in (-0.75, -0.5, -0.25, 0.25, 0.5, 0.75):
        sc_ = score(best_a + da)
        if sc_ > best_s:
            best_a, best_s = best_a + da, sc_
    return best_a if best_s > base * 1.04 else 0.0


def rectify_and_clean(src_path, dst_path, quad_norm=None):
    """quad_norm: 4 نقاط بإحداثيات 0..1000 (من الذكاء الصناعي أو يدويًا). بدونه: تنظيف فقط.
    الخطوات: تعديل المنظور → تخفيف تموّج الشاشة (moire) بالتصغير → توحيد الخلفية للأبيض مع إبقاء الألوان."""
    im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
    if max(im.size) > 3000:
        im.thumbnail((3000, 3000), Image.LANCZOS)
    if quad_norm:
        W, H = im.size
        q = [(x * W / 1000.0, y * H / 1000.0) for x, y in quad_norm]
        im = warp_quad(im, q)
    if True:               # تعديل الميلان (بعد تصحيح المنظور يبقى ميلان بسيط)
        _a = estimate_skew(im.convert("L"), 4.0 if quad_norm else 10.0)
        if abs(_a) >= 0.3:
            im = im.rotate(_a, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    # تخفيف نقط الشاشة/التموج: تصغير ثم تكبير بسيط
    tw = 1500
    if im.size[0] > tw:
        im = im.resize((tw, int(im.size[1] * tw / im.size[0])), Image.LANCZOS)
    lum = im.convert("L")
    mean = sum(i * c for i, c in enumerate(lum.histogram())) / float(im.size[0] * im.size[1])
    if mean > 145:        # خلفية فاتحة (Variant II / Sebia ...): خلفية بيضاء نظيفة بنفس الألوان
        im = im.filter(ImageFilter.GaussianBlur(0.8))      # يمحو نقش/تموّج بكسلات الشاشة قبل التبييض
        k = 8
        w, h = im.size
        chans = []
        for ch in im.split():
            small = ch.resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
            bg = small.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(4)).resize((w, h), Image.BILINEAR)
            ink = ImageChops.subtract(bg, ch).point(lambda v: 0 if v < 24 else min(255, int(v * 1.4)))
            chans.append(ImageChops.invert(ink))
        im = Image.merge("RGB", chans)
    else:                 # شاشة داكنة (Phoresis): نحافظ على الشكل، نحسّن التباين فقط
        im = ImageOps.autocontrast(im, cutoff=0.3)
    if mean > 145:         # قص الهوامش البيضاء الزائدة حول المحتوى (مع هامش صغير)
        _bb = ImageChops.invert(im.convert("L")).point(lambda v: 255 if v > 40 else 0).getbbox()
        if _bb:
            _m = int(0.02 * max(im.size))
            _bb = (max(0, _bb[0] - _m), max(0, _bb[1] - _m), min(im.size[0], _bb[2] + _m), min(im.size[1], _bb[3] + _m))
            if (_bb[2] - _bb[0]) > 80 and (_bb[3] - _bb[1]) > 80:
                im = im.crop(_bb)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=3))
    im.save(dst_path, "PNG", optimize=True)
    return dst_path
