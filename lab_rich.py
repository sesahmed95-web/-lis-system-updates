# -*- coding: utf-8 -*-
"""ملاحظات/تعليقات منسّقة (مثل الوورد) لأي تقرير: تُحفظ لكل (تحليل مطلوب، مفتاح) وتغلب النص العادي المحفوظ بالنتائج.
حذف التنسيق (زر ↺) يرجّع النص الأصلي من النتائج."""
import re
from html import escape
import lab_hbcurve as hbc

_KEY = re.compile(r"^[\w .\-/()#%+]{1,60}$", re.U)


def ensure(db):
    db.execute("CREATE TABLE IF NOT EXISTS lis_rich (order_test_id INTEGER NOT NULL, key TEXT NOT NULL, "
               "html TEXT NOT NULL DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (order_test_id, key))")


def get(db, ot_id, key):
    try:
        ensure(db)
        r = db.execute("SELECT html FROM lis_rich WHERE order_test_id=? AND key=?", (int(ot_id or 0), key)).fetchone()
        return r["html"] if r else None
    except Exception:
        return None


def save(db, ot_id, key, html):
    """يرجّع (ok, html_نظيف | رسالة_خطأ). html فارغ = حذف التنسيق والرجوع للنص الأصلي."""
    if not _KEY.match(str(key or "")):
        return False, "مفتاح غير صالح"
    ensure(db)
    clean = hbc.clean_comment_html(html)
    if not clean:
        db.execute("DELETE FROM lis_rich WHERE order_test_id=? AND key=?", (int(ot_id), key))
    else:
        db.execute("INSERT INTO lis_rich (order_test_id, key, html) VALUES (?,?,?) "
                   "ON CONFLICT(order_test_id, key) DO UPDATE SET html=excluded.html, updated_at=CURRENT_TIMESTAMP",
                   (int(ot_id), key, clean))
    db.commit()
    return True, clean


def render(db, ot_id, key, fallback="", fallback_html=None, style="", hide_empty=False, bullets=False):
    """HTML لبلوك الملاحظة. fallback = نص عادي (يُهرَّب وتُحفظ أسطره)، أو fallback_html جاهز وآمن (مثل render_conclusion)."""
    stored = get(db, ot_id, key) if ot_id else None
    if stored:
        inner = stored
    elif fallback_html is not None:
        inner = str(fallback_html)
    elif bullets:
        lines = [l for l in str(fallback or "").replace("\r\n", "\n").split("\n") if l.strip()]
        inner = ("<ul>" + "".join("<li>%s</li>" % escape(l) for l in lines) + "</ul>") if lines else ""
    else:
        inner = escape(str(fallback or "")).replace("\r\n", "\n").replace("\n", "<br>")
    if hide_empty and not re.sub(r"<[^>]*>|&nbsp;|\s", "", inner):
        return ""
    attrs = ' class="rich-note" dir="ltr"'
    if ot_id:
        attrs += ' data-ot="%d" data-rich="%s"' % (int(ot_id), escape(key, quote=True))
    if style:
        attrs += ' style="%s"' % escape(style, quote=True)
    return "<div%s>%s</div>" % (attrs, inner)
