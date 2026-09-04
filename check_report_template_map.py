# -*- coding: utf-8 -*-
"""
check_report_template_map.py
=============================
سكريبت تشخيصي فقط — ما يعدّل app.py إطلاقًا، بس يقرا ويطبعلك المعلومات
اللازمة نعرف منها ليش تقارير GUE/GSE/SFA ما تطلع بالتصميم الجديد.

طريقة التشغيل: بنفس مجلد app.py:
    python check_report_template_map.py
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

print("=== 1) هل REPORT_TEMPLATE_MAP موجود؟ ===")
m = re.search(r"REPORT_TEMPLATE_MAP\s*=\s*\{[^}]*\}", content, re.DOTALL)
if m:
    print(m.group(0))
else:
    print("❌ ما لكيت قاموس REPORT_TEMPLATE_MAP إطلاقًا بالملف!")

print("\n=== 2) هل أسماء القوالب الجديدة مذكورة بالملف؟ ===")
for name in ["urine_exam.html", "stool_exam.html", "seminal_fluid.html"]:
    count = content.count(name)
    print(f"  {name}: ذُكر {count} مرة" + (" ✅" if count else " ❌ غير موجود إطلاقًا"))

print("\n=== 3) هل أكواد الفحوصات GUE/GSE/SFA مذكورة بالملف بأي مكان؟ ===")
for code in ["GUE", "GSE", "SFA"]:
    count = content.count(f'"{code}"') + content.count(f"'{code}'")
    print(f"  {code}: ذُكر {count} مرة")

print("\n=== 4) دالة get_report_template أو ما يعادلها (لمعرفة منطق الاختيار) ===")
m2 = re.search(r"def\s+get_report_template\s*\([^)]*\):[\s\S]{0,600}", content)
if m2:
    print(m2.group(0))
else:
    print("ما لكيت دالة بهذا الاسم بالضبط — إذا اسمها مختلف عندك خبرني.")
