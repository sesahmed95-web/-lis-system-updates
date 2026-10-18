# -*- coding: utf-8 -*-
r"""
make_branding_preset.py  -  fixes lab NAME / PHONE / ADDRESS / LOGO (and the results-portal link) for an
ALREADY INSTALLED client, WITHOUT a new Setup.

  python tools\make_branding_preset.py

It writes  portal_preset.json  (Documents\LabClientPresets\<name>\).  Send that file to the client and ask him to:
  1) close the program   2) copy the file into the program folder (normally C:\LabSystem)   3) open the program again.
The program applies it on start, then renames it to portal_preset.applied.json (so it runs only once).
Never upload this file to GitHub (it can contain the portal key).
"""
import base64, json, os, re, sys


def ask(q, default=""):
    v = input(q + (" [%s]" % default if default else "") + ": ").strip().strip('"')
    return v or default


def main():
    print("== Branding preset for an installed client ==  (Enter = skip a field)\n")
    s = {}
    for key, q in (("app_name_ar", "Lab name - Arabic"), ("app_name", "Lab name - English"),
                   ("lab_phone", "Phone"), ("lab_address", "Address")):
        v = ask(q)
        if v:
            s[key] = v
    if not s:
        sys.exit("Nothing entered - no file created.")
    print("\nResults portal: Enter = leave as is | 0 = DISABLE it for this client | 1 = enter this client's own portal")
    p = ask("Portal choice")
    if p == "0":
        s["portal_enabled"] = "0"
    elif p == "1":
        url = ask("Portal URL (https://...workers.dev)")
        key = ask("Portal secret key (paste)")
        if not url.startswith("https://") or not key:
            sys.exit("Portal URL must start with https:// and the key is required - no file created.")
        s.update(portal_enabled="1", portal_mode="remote", portal_url=url, portal_api_key=key.replace(" ", ""))
    payload = {"settings": s}
    lp = ask("\nLogo image path (png/jpg, max 3 MB) - Enter to skip")
    if lp:
        ext = lp.rsplit(".", 1)[-1].lower()
        if not os.path.exists(lp) or ext not in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
            sys.exit("Logo file not found or not an image - no file created.")
        raw = open(lp, "rb").read()
        if len(raw) > 3 * 1024 * 1024:
            sys.exit("Logo is bigger than 3 MB - no file created.")
        payload["logo"] = {"filename": "logo_" + str(len(raw)) + "." + ext, "b64": base64.b64encode(raw).decode()}
    slug = re.sub(r"[^A-Za-z0-9]+", "-", s.get("app_name", "client")).strip("-").lower() or "client"
    out_dir = os.path.join(os.path.expanduser("~"), "Documents", "LabClientPresets", slug)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "portal_preset.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("\nDONE. File created:\n" + out)
    print("Send it to the client: close the program, copy it into C:\\LabSystem, open the program again.")
    try:
        os.startfile(out_dir)
    except Exception:
        pass


if __name__ == "__main__":
    main()
