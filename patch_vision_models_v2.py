# تحسين قراءة الصور: مهلة أقصر لكل موديل + الانتقال للموديل التالي حتى عند انقطاع/تأخّر الرد، ورسالة واضحة بالنهاية.
# يشتغل فوق patch_vision_models.py (لازم تكون شغّلته قبل).  التشغيل من مجلد البرنامج:  python patch_vision_models_v2.py
import io, shutil, sys

P = "app.py"
src = io.open(P, encoding="utf-8").read()
if "v35: قراءة الصور" in src:
    print("التعديل مطبّق مسبقاً."); sys.exit(0)

START = "        # v34: قراءة الصور بتجربة عدة موديلات"
END = '\n    @bp.route("/ai/api/extract-image", methods=["POST"])'
i = src.find(START); j = src.find(END, i)
if i < 0 or j < 0:
    print("لازم تشغّل patch_vision_models.py أولاً (ما لقيت تعديل v34). لا تغيير."); sys.exit(1)

NEW = '''        # v35: قراءة الصور — مهلة أقصر لكل موديل، وينتقل للتالي عند 404 / مشغول / الحد المجاني / تأخّر الرد
        _first = _pick_gemini_model(key, cfg["model"])
        _order = [_first] + [m_ for m_ in ("gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-pro") if m_ != _first]
        _last, _t0 = None, time.time()
        for model in _order:
            if time.time() - _t0 > 170:
                break
            body = {"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": img_b64}}, {"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 4096, "thinkingConfig": {"thinkingBudget": 0}}}
            url_ = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
            try:
                try:
                    j = _post(url_, {"x-goog-api-key": key}, body, 45)
                except _AIErr as e400:
                    if "(400)" not in str(e400):
                        raise
                    body["generationConfig"].pop("thinkingConfig", None)
                    j = _post(url_, {"x-goog-api-key": key}, body, 45)
            except _AIErr as e_:
                _last = e_
                if str(e_) == "MODEL_404" or "مشغولة" in str(e_) or "الحد المجاني" in str(e_) or "ما كو اتصال" in str(e_):
                    continue
                raise
            try:
                txt = "".join(p_.get("text", "") for p_ in j["candidates"][0]["content"]["parts"]).strip()
                if txt:
                    return txt
            except Exception:
                pass
            _last = _AIErr("جاء ردّ فارغ من الخدمة. أعد المحاولة.")
        if _last is not None:
            _m = str(_last)
            if _m == "MODEL_404":
                raise _AIErr("ما لقيت موديل Gemini متاح لقراءة الصور بهذا المفتاح. امسح خانة «موديل قراءة الصور» وأعد المحاولة.")
            if "ما كو اتصال" in _m or "مشغولة" in _m:
                raise _AIErr("Google ما ردّت بالوقت المناسب بعد تجربة عدة موديلات (ضغط على الخدمة أو بطء بالإنترنت). أعد المحاولة بعد دقايق.")
            raise _last
        raise _AIErr("جاء ردّ فارغ من الخدمة. أعد المحاولة.")
'''
shutil.copyfile(P, P + ".bak_vision2")
io.open(P, "w", encoding="utf-8", newline="").write(src[:i] + NEW + src[j:])
print("تم. أعد تشغيل البرنامج. (النسخة الاحتياطية: app.py.bak_vision2)")
