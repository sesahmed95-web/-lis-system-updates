# fix_doctors.py
# سكربت لمرة وحدة: يحدّث أسماء وشهادات الدكاترة الثلاثة بنفس النص المطابق
# لصورة الريبورت المرجعي (8/11)، ويضبط حجم خط ترويستهم = 14.
# لازم تحطه بنفس مجلد app.py / database.py / lis.db، والسيرفر لازم يكون
# مطفي وقت التشغيل (استخدم restart_server.ps1 بعده لتشغيله من جديد).

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lis.db")


def normalize(s):
    """توحيد أشكال الألف (أ/إ/آ) حتى يضبط التطابق بغض النظر عن طريقة الكتابة."""
    if not s:
        return ""
    return s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").strip()


# النص منقول حرفياً من صورة الريبورت المرجعي (localhost:9090/reports/print/10)
TARGETS = [
    {
        "key": "خليل",  # جزء مميز من الاسم الحالي يُستخدم للتطابق فقط
        "name": "خليل حمود عبد السادة",
        "title": "الدكتور",
        "degree_ar": "بكالوريوس طب وجراحة عامة\nطبيب ممارس امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nHematopathologist",
        "sort_order": 0,
    },
    {
        "key": "اسراء",
        "name": "أسراء عبد الباقر جنام",
        "title": "الدكتورة",
        "degree_ar": "بكالوريوس طب وجراحة عامة\nاختصاص امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nF.I.B.M.S Hematopathologist",
        "sort_order": 1,
    },
    {
        "key": "هدى",
        "name": "هدى نصيف جاسم",
        "title": "الدكتورة",
        "degree_ar": "بكالوريوس طب وجراحة عامة\nاختصاص امراض الدم التشخيصي",
        "degree_en": "M.B.Ch.B\nM.SC.Hematopathologist",
        "sort_order": 2,
    },
]

LETTERHEAD_FONT_SIZE = "14"


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ ما لقيت lis.db بهذا المسار: {DB_PATH}")
        print("   تأكد إنك حاطط هذا الملف بنفس مجلد app.py / database.py.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # احتياط: لو ما رجّعت نسخة database.py المحدّثة بعد (وعمود font_size
    # مو موجود أصلاً بجدول الدكاترة)، أضيفه هنا حتى ما يفشل السكربت.
    cols = [r[1] for r in cur.execute("PRAGMA table_info(examining_doctors_list)").fetchall()]
    if "font_size" not in cols:
        cur.execute("ALTER TABLE examining_doctors_list ADD COLUMN font_size INTEGER")
        print("+ أضفت عمود font_size (ما كان موجود).")

    rows = cur.execute("SELECT * FROM examining_doctors_list").fetchall()

    for t in TARGETS:
        match = None
        for r in rows:
            if t["key"] in normalize(r["name"] or ""):
                match = r
                break
        if match:
            cur.execute(
                "UPDATE examining_doctors_list SET name=?, title=?, degree_ar=?, degree_en=?, "
                "show_on_letterhead=1, sort_order=?, font_size=NULL WHERE id=?",
                (t["name"], t["title"], t["degree_ar"], t["degree_en"], t["sort_order"], match["id"]),
            )
            print(f"✔ حدّثت: \"{match['name']}\" → \"{t['name']}\"")
        else:
            cur.execute(
                "INSERT INTO examining_doctors_list "
                "(name, title, degree_ar, degree_en, sort_order, show_on_letterhead, font_size) "
                "VALUES (?, ?, ?, ?, ?, 1, NULL)",
                (t["name"], t["title"], t["degree_ar"], t["degree_en"], t["sort_order"]),
            )
            print(f"➕ ما لقيت مطابقة لـ \"{t['key']}\" — أضفت دكتور جديد: \"{t['name']}\"")

    # حجم خط ترويسة الدكاترة العام = 14 (نفس مقاس صورة الريبورت المرجعي).
    # font_size=NULL فوق لكل دكتور يعني: يرث هذا الحجم العام، مو حجم مستقل.
    existing_setting = cur.execute(
        "SELECT key FROM settings WHERE key='letterhead_font_size'"
    ).fetchone()
    if existing_setting:
        cur.execute(
            "UPDATE settings SET value=? WHERE key='letterhead_font_size'",
            (LETTERHEAD_FONT_SIZE,),
        )
    else:
        cur.execute(
            "INSERT INTO settings (key, value) VALUES ('letterhead_font_size', ?)",
            (LETTERHEAD_FONT_SIZE,),
        )
    print(f"✔ حجم خط الترويسة العام = {LETTERHEAD_FONT_SIZE}px")

    conn.commit()
    conn.close()
    print("\nتم بنجاح. لازم تشغّل restart_server.ps1 (أو تطفي البرنامج وتشغله يدوياً)")
    print("حتى تنعكس هذي التعديلات بالتقارير المطبوعة.")


if __name__ == "__main__":
    main()
