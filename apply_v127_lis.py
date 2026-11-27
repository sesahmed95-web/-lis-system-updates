# -*- coding: utf-8 -*-
"""apply_v127_lis.py — يضيف مفاتيح المساعد الذكي لملف الربط التلقائي links_<HWID>.json (v95).
آمن: يرفض إن كان مطبّقاً أو الموضع غير موجود، ويحفظ app.py.bak_v127 قبل التعديل."""
import os, shutil, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
s = open(P, encoding="utf-8").read()
if "v127: ai links" in s:
    print("مطبّق مسبقاً"); sys.exit(0)
R = []
# 1) التطبيق عند العميل
R.append(('''        done.append("بوابة النتائج")
    db.commit()''', '''        done.append("بوابة النتائج")
    # v127: ai links — مفتاح المساعد الذكي (ومفتاح قراءة الصور اختياري)
    ak = re.sub(r"[^\\x21-\\x7e]|[\\"']", "", str(data.get("ai_key") or ""))[:200]
    avk = re.sub(r"[^\\x21-\\x7e]|[\\"']", "", str(data.get("ai_vision_key") or ""))[:200]
    if ak:
        set_setting(db, "ai_api_key", ak)
        ap = str(data.get("ai_provider") or "gemini")
        set_setting(db, "ai_provider", ap if ap in ("gemini", "groq", "anthropic") else "gemini")
        set_setting(db, "ai_enabled", "1")
        done.append("المساعد الذكي")
    if avk:
        set_setting(db, "ai_vision_key", avk)
        done.append("قراءة الصور")
    db.commit()'''))
# 2) حقول المولّد
R.append(('''    err = ""
    if request.method == "POST":
        data = {}''', '''    ak, avk = (f.get("ai_key") or "").strip(), (f.get("ai_vision_key") or "").strip()  # v127
    err = ""
    if request.method == "POST":
        data = {}
        if ak:
            data.update(ai_key=ak, ai_provider=(f.get("ai_provider") or "gemini"))
        if avk:
            data.update(ai_vision_key=avk)'''))
R.append(('''err = "أدخل (رابط + مفتاح) للسجل أو للبوابة (أو للاثنين)"''', '''err = "أدخل (رابط + مفتاح) للسجل أو للبوابة، أو مفتاح المساعد الذكي"'''))
R.append(('''return _v93_rts(_V95_LINK_HTML, err=err, hw=hw, lu=lu, lk=lk, pu=pu, pk=pk)''',
          '''return _v93_rts(_V95_LINK_HTML, err=err, hw=hw, lu=lu, lk=lk, pu=pu, pk=pk, ak=ak, avk=avk)'''))
R.append(('''<input name="portal_key" autocomplete="off" value="{{pk}}">''', '''<input name="portal_key" autocomplete="off" value="{{pk}}">
<label>مفتاح المساعد الذكي (Gemini API key)</label><input name="ai_key" autocomplete="off" value="{{ak}}">
<input type="hidden" name="ai_provider" value="gemini">
<label>مفتاح قراءة الصور (اختياري — اتركه فاضي إذا نفس المزوّد)</label><input name="ai_vision_key" autocomplete="off" value="{{avk}}">'''))
R.append(('''f.portal_key.value=j.portal_key||'';})}''', '''f.portal_key.value=j.portal_key||'';f.ai_key.value=j.ai_key||'';f.ai_vision_key.value=j.ai_vision_key||'';})}'''))
R.append(('''portal_url=get_setting(db, "portal_url", "") or "", portal_key=get_setting(db, "portal_api_key", "") or "")''',
          '''portal_url=get_setting(db, "portal_url", "") or "", portal_key=get_setting(db, "portal_api_key", "") or "",
                   ai_key=get_setting(db, "ai_api_key", "") or "", ai_vision_key=get_setting(db, "ai_vision_key", "") or "")'''))
for a, b in R:
    if s.count(a) != 1:
        print("!! الموضع غير موجود/مكرّر:", a[:60].replace("\n", " ")); sys.exit(1)
shutil.copy2(P, P + ".bak_v127")
for a, b in R:
    s = s.replace(a, b)
open(P, "w", encoding="utf-8").write(s)
print("تم v127: مفتاح المساعد الذكي مضاف لملف الربط")
