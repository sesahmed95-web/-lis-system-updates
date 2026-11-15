# يصلّح قراءة الصور بـ Gemini: إذا الموديل المختار رجّع MODEL_404 أو كان مشغولاً، يجرّب موديلات Gemini ثانية تلقائياً.
# التشغيل (من مجلد البرنامج):  python patch_vision_models.py        ← يعدّل app.py ويحفظ نسخة app.py.bak_vision
import io, shutil, sys

P = "app.py"
src = io.open(P, encoding="utf-8").read()
if "v34: قراءة الصور بتجربة عدة موديلات" in src:
    print("التعديل مطبّق مسبقاً."); sys.exit(0)

START = '        model = _pick_gemini_model(key, cfg["model"])\n        body = {"contents": [{"role": "user", "parts": [{"inlineData"'
END = '        raise _AIErr("جاء ردّ فارغ من الخدمة. أعد المحاولة.")\n\n    @bp.route("/ai/api/extract-image", methods=["POST"])'
i = src.find(START); j = src.find(END, i)
if i < 0 or j < 0 or src.count(START) != 1:
    print("ما لقيت مكان التعديل المتوقع في app.py (النسخة تختلف). لا تغيير."); sys.exit(1)

NEW = '''        # v34: قراءة الصور بتجربة عدة موديلات (MODEL_404 / مشغول / الحد المجاني) بدل ما تفشل من أول موديل
        _first = _pick_gemini_model(key, cfg["model"])
        _order = [_first] + [m_ for m_ in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-pro") if m_ != _first]
        _last = None
        for model in _order:
            body = {"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": img_b64}}, {"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 4096, "thinkingConfig": {"thinkingBudget": 0}}}
            url_ = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
            try:
                try:
                    j = _post(url_, {"x-goog-api-key": key}, body, 90)
                except _AIErr as e400:
                    if "(400)" not in str(e400):
                        raise
                    body["generationConfig"].pop("thinkingConfig", None)
                    j = _post(url_, {"x-goog-api-key": key}, body, 90)
            except _AIErr as e_:
                _last = e_
                if str(e_) == "MODEL_404" or "مشغولة" in str(e_) or "الحد المجاني" in str(e_):
                    continue
                raise
            try:
                txt = "".join(p_.get("text", "") for p_ in j["candidates"][0]["content"]["parts"]).strip()
                if txt:
                    return txt
            except Exception:
                pass
            _last = _AIErr("جاء ردّ فارغ من الخدمة. أعد المحاولة.")
        if _last is not None and str(_last) == "MODEL_404":
            raise _AIErr("ما لقيت موديل Gemini متاح لقراءة الصور بهذا المفتاح. امسح خانة «موديل قراءة الصور» وأعد المحاولة.")
        raise _last or _AIErr("جاء ردّ فارغ من الخدمة. أعد المحاولة.")

    @bp.route("/ai/api/extract-image", methods=["POST"])'''
shutil.copyfile(P, P + ".bak_vision")
io.open(P, "w", encoding="utf-8", newline="").write(src[:i] + NEW + src[j + len(END):])
print("تم. أعد تشغيل البرنامج. (النسخة الاحتياطية: app.py.bak_vision)")
