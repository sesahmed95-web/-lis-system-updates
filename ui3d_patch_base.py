# -*- coding: utf-8 -*-
"""يضيف/يحدّث مظهر 3D + رابط الإعدادات في base.html الموجود عندك (بدون استبدال الملف).
الاستخدام:  python ui3d_patch_base.py "المسار\\templates\\base.html"
يحفظ نسخة base.html.bak، ويمكن تشغيله أكثر من مرة (يستبدل كتلة 3D القديمة بالجديدة)."""
import sys, re, shutil
BLOCK = "<style>\n  /* ===== مظهر 3D (اختياري) — يعمل فقط عند html.ui3d؛ لا يمس الطباعة ===== */\n  html.ui3d body { background: radial-gradient(1200px 600px at 20% -10%, #ffffff 0%, var(--page-bg) 60%) fixed; }\n  html.ui3d .card, html.ui3d .rb-box {\n    border: 1px solid rgba(15,23,42,.08) !important; border-radius: 14px !important;\n    background: linear-gradient(180deg, #fff 0%, #F8FAFC 100%) !important;\n    box-shadow: 0 1px 0 #fff inset, 0 2px 4px rgba(15,23,42,.06), 0 10px 22px -8px rgba(15,23,42,.22), 0 24px 40px -22px rgba(15,23,42,.25) !important;\n    transition: transform .18s ease, box-shadow .18s ease;\n  }\n  html.ui3d .card:hover { transform: translateY(-2px); box-shadow: 0 1px 0 #fff inset, 0 4px 8px rgba(15,23,42,.08), 0 18px 30px -10px rgba(15,23,42,.28), 0 30px 50px -24px rgba(15,23,42,.3) !important; }\n  html.ui3d .btn {\n    border-radius: 10px !important; border: 1px solid rgba(0,0,0,.18) !important;\n    background-image: linear-gradient(180deg, rgba(255,255,255,.28), rgba(255,255,255,0) 55%) !important;\n    box-shadow: 0 3px 0 rgba(0,0,0,.28), 0 6px 10px -2px rgba(15,23,42,.25) !important;\n    transition: transform .08s ease, box-shadow .08s ease; position: relative; top: 0;\n  }\n  html.ui3d .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 0 rgba(0,0,0,.28), 0 9px 14px -2px rgba(15,23,42,.28) !important; }\n  html.ui3d .btn:active { transform: translateY(3px); box-shadow: 0 0 0 rgba(0,0,0,.28), 0 2px 4px rgba(15,23,42,.25) !important; }\n  html.ui3d .btn.secondary { background-color: #fff !important; background-image: linear-gradient(180deg, #fff, #EEF2F7) !important; }\n  html.ui3d input[type=text], html.ui3d input[type=number], html.ui3d input[type=search], html.ui3d input[type=password],\n  html.ui3d input[type=date], html.ui3d input[type=time], html.ui3d select, html.ui3d textarea {\n    border-radius: 9px !important; border: 1px solid #CBD5E1 !important; background: #FBFCFE !important;\n    box-shadow: inset 0 2px 4px rgba(15,23,42,.10), 0 1px 0 #fff !important;\n  }\n  html.ui3d input:focus, html.ui3d select:focus, html.ui3d textarea:focus {\n    outline: none !important; border-color: var(--primary) !important;\n    box-shadow: inset 0 2px 4px rgba(15,23,42,.10), 0 0 0 3px rgba(38,82,156,.18) !important; }\n  html.ui3d .sidebar { box-shadow: 8px 0 24px -8px rgba(15,23,42,.45), inset -1px 0 0 rgba(255,255,255,.12) !important; }\n  html.ui3d .nav-link { border-radius: 9px; transition: transform .12s ease, background .12s ease, box-shadow .12s ease; }\n  html.ui3d .nav-link:hover { transform: translateX(-3px); box-shadow: 0 6px 12px -4px rgba(0,0,0,.35); }\n  html.ui3d .nav-link.active { box-shadow: inset 0 2px 4px rgba(0,0,0,.28), 0 1px 0 rgba(255,255,255,.18); }\n  html.ui3d table { border-collapse: separate; border-spacing: 0; }\n  /* عناوين الجداول: سماوي فاتح لامع + كتابة سوداء واضحة */\n  html.ui3d table thead th, html.ui3d table th, html.ui3d .rb-box table th {\n    background: linear-gradient(180deg, #F0FAFF 0%, #A8E2FF 46%, #86D2F8 54%, #C4EDFF 100%) !important;\n    color: #000 !important; font-weight: 700 !important; text-shadow: 0 1px 0 rgba(255,255,255,.65);\n    border-bottom: 1px solid #5BB8E8 !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 2px 3px -1px rgba(15,23,42,.25);\n  }\n  html.ui3d table tbody tr { transition: transform .1s ease, box-shadow .1s ease; }\n  html.ui3d table tbody tr:hover { box-shadow: 0 6px 14px -6px rgba(15,23,42,.3); position: relative; z-index: 1; background: #fff; }\n  html.ui3d .badge { box-shadow: 0 2px 0 rgba(0,0,0,.18), 0 3px 6px -2px rgba(15,23,42,.25); }\n  @media print { html.ui3d .card, html.ui3d .btn, html.ui3d input, html.ui3d select, html.ui3d textarea { box-shadow: none !important; background-image: none !important; } html.ui3d body { background: #fff !important; } }\n\n</style>\n<script>\n  (function () {\n    if ({{ 'true' if ui_3d else 'false' }}) document.documentElement.classList.add('ui3d');\n  })();\n</script>\n"
LINK = """        <a class="nav-link {{ 'active' if request.path == url_for('ui_style_page') else '' }}" href="{{ url_for('ui_style_page') }}">🧊 مظهر الواجهة (3D)</a>\n"""
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
shutil.copy(p, p + ".bak")
pat = re.compile(r"<style>\n  /\* ===== مظهر 3D.*?</script>\n", re.S)
if pat.search(s):
    s = pat.sub(lambda m: BLOCK, s, count=1)
    print("تم تحديث كتلة 3D الموجودة.")
else:
    if "</head>" not in s:
        sys.exit("لم أجد </head> — الملف غير متوقع.")
    s = s.replace("</head>", BLOCK + "</head>", 1)
    print("تمت إضافة كتلة 3D.")
if "ui_style_page" not in s:
    m = re.search(r"^[ \t]*<a class=\"nav-link[^\n]*url_for\('app_settings'\)[^\n]*\n", s, re.M)
    if m:
        s = s[:m.start()] + LINK + s[m.start():]
    else:
        print("تنبيه: ما لقيت رابط الإعدادات؛ افتح /management/ui-style مباشرة.")
open(p, "w", encoding="utf-8").write(s)
print("نسخة احتياطية:", p + ".bak")
