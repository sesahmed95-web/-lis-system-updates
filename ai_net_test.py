# تشخيص: ليش السيرفر ما يوصل لخدمة Gemini؟  شغّله من نفس مجلد البرنامج:  python ai_net_test.py
import socket, ssl, sys, urllib.request, urllib.error, os

def step(name, fn):
    try:
        print("[OK ]", name, "->", fn())
    except urllib.error.HTTPError as e:
        print("[OK ]", name, "-> وصل للخدمة (رد HTTP %s) = الاتصال سليم" % e.code)
    except Exception as e:
        print("[FAIL]", name, "->", type(e).__name__, ":", e)

print("Python", sys.version.split()[0])
print("Proxy env:", {k: v for k, v in os.environ.items() if "proxy" in k.lower()} or "لا يوجد")
step("DNS google.com", lambda: socket.gethostbyname("google.com"))
step("DNS generativelanguage.googleapis.com", lambda: socket.gethostbyname("generativelanguage.googleapis.com"))
step("HTTPS google.com", lambda: urllib.request.urlopen("https://www.google.com", timeout=15).status)
step("HTTPS Gemini API", lambda: urllib.request.urlopen("https://generativelanguage.googleapis.com/v1beta/models", timeout=20).status)
step("شهادات SSL", lambda: ssl.get_default_verify_paths().cafile or "نظام ويندوز")
input("\nاضغط Enter للإغلاق ...")
