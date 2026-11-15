# اختبار مفتاح Gemini مباشرة (بدون البرنامج).  شغّله:  python ai_key_test.py   ثم الصق المفتاح عند الطلب.
import json, urllib.request, urllib.error

key = "".join(input("الصق مفتاح Gemini هنا ثم Enter: ").split())

def call(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                 method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return None, {"error": {"message": "%s: %s" % (type(e).__name__, e)}}

st, j = call("https://generativelanguage.googleapis.com/v1beta/models?pageSize=50")
print("\n1) قائمة الموديلات -> HTTP", st)
if st != 200:
    print("   رسالة Google:", (j.get("error") or {}).get("message", "")[:300])
else:
    names = [m["name"].split("/")[-1] for m in j.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    print("   موديلات متاحة (أول 8):", ", ".join(names[:8]))
    st2, j2 = call("https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent",
                   {"contents": [{"parts": [{"text": "قل: جاهز"}]}]})
    print("2) تجربة رد نصي -> HTTP", st2)
    if st2 == 200:
        print("   الرد:", j2["candidates"][0]["content"]["parts"][0].get("text", "")[:60])
        print("\n✔ المفتاح سليم. إذا البرنامج ما زال يرفض، المشكلة بإعدادات البرنامج (نسخة/نافذة) مو بالمفتاح.")
    else:
        print("   رسالة Google:", (j2.get("error") or {}).get("message", "")[:300])
input("\nEnter للإغلاق ...")
