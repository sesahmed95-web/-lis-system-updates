# -*- coding: utf-8 -*-
r"""
make_update_package.py - build a SIGNED in-app update (what clients get through the "Update now" bar).

One-time:      python tools\make_update_package.py --init-keys
               -> creates your private signing key in  %USERPROFILE%\.lab_update_signing_key.pem  (NEVER inside the project,
                  never send it to anyone) and prints the PUBLIC key: paste it into lab_updater.py -> PUBLIC_KEY_B64
                  (together with DEFAULT_UPDATE_URL), then build a NEW Setup once so clients carry the public key.

Every update: 1) edit the program as usual, put a bigger number in the VERSION file (e.g. 59 -> 60)
              2) python tools\make_update_package.py --notes "تحسين طباعة الباركود"
              3) upload the two files in update_packages\  (update.json + update_<ver>.zip) to your update address.
              Clients see "Update now / Later" within hours (or when they open the program).

What goes in the package: *.py in the program folder + templates\ + VERSION.
What never goes in: lis.db, static\ (logo/uploads), local_config.py (your GitHub token), portal_preset.json, tools\,
build files, client_builder.py, launcher.py, lab_overlay.py (the bootstrap is never updated), and your designer login
(replaced by a random one exactly like the client Setup builder does).
Updates cannot add new Python libraries or new files under static\ - for those build a new Setup.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEY_PATH = os.path.join(os.path.expanduser("~"), ".lab_update_signing_key.pem")
EXCLUDE_PY = {"local_config.py", "local_config.example.py", "lab_overlay.py", "client_builder.py", "launcher.py",
              "reset_pw.py", "ui3d_patch_base.py", "fix_doctors.py", "restore_doctor_degrees.py",
              "fix_patient_name_en_and_map_templates.py", "enable_examining_tests.py", "db_add_columns.py",
              "db_dedupe_copied_results.py", "apply_patient_meta_vars.py", "apply_transliteration_engine.py",
              "extract_patient_route.py", "extract_print_function.py", "check_report_template_map.py", "update_publisher.py"}


def _crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        return Ed25519PrivateKey, serialization
    except ImportError:
        sys.exit("ERROR: run  python -m pip install cryptography  first.")


def init_keys():
    Priv, ser = _crypto()
    if os.path.exists(KEY_PATH):
        sys.exit("A signing key already exists at %s - not overwritten (losing/replacing it means clients can no longer accept updates)." % KEY_PATH)
    k = Priv.generate()
    pem = k.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption())
    with open(KEY_PATH, "wb") as f:
        f.write(pem)
    try:
        os.chmod(KEY_PATH, 0o600)
    except Exception:
        pass
    pub = base64.b64encode(k.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)).decode()
    print("Private key saved to:", KEY_PATH, " (back it up somewhere safe, never share it)")
    print("\nPUBLIC_KEY_B64 = \"%s\"\n" % pub)
    print("Paste that line into lab_updater.py, set DEFAULT_UPDATE_URL, then build a new Setup.")


def sign(version, digest):
    Priv, ser = _crypto()
    if not os.path.exists(KEY_PATH):
        sys.exit("ERROR: no signing key. Run once:  python tools\\make_update_package.py --init-keys")
    with open(KEY_PATH, "rb") as f:
        k = ser.load_pem_private_key(f.read(), password=None)
    return base64.b64encode(k.sign(("%s|%s" % (version, digest)).encode("utf-8"))).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init-keys", action="store_true")
    ap.add_argument("--notes", default="")
    ap.add_argument("--version", default="")
    ap.add_argument("--src", default=ROOT)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if a.init_keys:
        return init_keys()
    src = os.path.abspath(a.src)
    ver = a.version or (open(os.path.join(src, "VERSION"), encoding="utf-8").read().strip() if os.path.exists(os.path.join(src, "VERSION")) else "")
    if not ver:
        sys.exit("ERROR: put a version number in the VERSION file (or pass --version).")
    out = os.path.abspath(a.out or os.path.join(src, "update_packages"))
    os.makedirs(out, exist_ok=True)

    spec = importlib.util.spec_from_file_location("seal", os.path.join(HERE, "seal_client_package.py"))
    seal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seal)

    files = []
    for fn in sorted(os.listdir(src)):
        if fn.endswith(".py") and fn not in EXCLUDE_PY and os.path.isfile(os.path.join(src, fn)):
            files.append((fn, os.path.join(src, fn)))
    for dp, dns, fns in os.walk(os.path.join(src, "templates")):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in fns:
            if fn.endswith(".html") or fn.endswith(".txt"):
                full = os.path.join(dp, fn)
                files.append((os.path.relpath(full, src).replace("\\", "/"), full))
    if not any(n == "app.py" for n, _ in files):
        sys.exit("ERROR: app.py not found in " + src)

    # syntax check before anything is signed
    for n, full in files:
        if n.endswith(".py"):
            with open(full, "r", encoding="utf-8") as f:
                compile(f.read(), full, "exec")

    zpath = os.path.join(out, "update_%s.zip" % ver)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for n, full in files:
            if n == "database.py":
                txt = open(full, encoding="utf-8").read()
                if "INSERT INTO designer_account" in txt:
                    txt, found = seal.scrub_designer_seed(txt)
                    if not found:
                        sys.exit("ERROR: designer login in database.py not recognised - stopped, nothing built.")
                z.writestr(n, txt.encode("utf-8"))
            else:
                z.write(full, n)
        z.writestr("VERSION", ver)
    data = open(zpath, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    manifest = {"version": ver, "file": os.path.basename(zpath), "sha256": digest, "sig": sign(ver, digest),
                "notes": a.notes}
    with open(os.path.join(out, "update.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("OK  version %s   %d files   %.1f KB" % (ver, len(files), len(data) / 1024))
    print("Upload BOTH files from:", out)
    print("   update.json  and  " + os.path.basename(zpath))


if __name__ == "__main__":
    main()
