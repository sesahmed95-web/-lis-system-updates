# -*- coding: utf-8 -*-
r"""
make_branding_preset.py  -  fixes an ALREADY INSTALLED client WITHOUT a new Setup:
lab name / phone / address / LOGO / doctors + their degrees / report design / home-screen images / results-portal link.

Run it on YOUR computer, from your program folder (it reads YOUR lis.db read-only; nothing in it is changed):
    python tools\make_branding_preset.py

It writes  portal_preset.json  to  Documents\LabClientPresets\<name>\ . Send that file to the client and ask him to:
  1) close the program   2) copy the file into the program folder (normally C:\LabSystem)   3) open the program again.
The program applies it on start, then renames it to portal_preset.applied.json (so it runs only once).
Never upload this file to GitHub (it can contain the client's portal key). Your tokens/passwords are never read.
"""
import base64, json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

DESIGN_KEYS = (
    "result_layout_json", "combined_panel_group_order", "results_entry_test_order",
    "logo_width", "logo_position", "letterhead_font_size", "letterhead_font_family",
    "report_underline_style", "report_row_pad", "report_col_pad", "test_name_font_size", "result_value_font_size",
    "show_result_flag", "flag_color_low", "flag_color_high", "conclusion_marker_colors",
    "patient_info_top_gap", "patient_info_row_gap", "patient_info_label_width", "patient_info_col_gap",
    "barcode_test_names_mode", "barcode_show_lab_name", "vb_names_mode", "theme_primary_color", "theme_page_bg_color",
    "report_header_style", "report_header_accent", "report_header_subtitle",
    "dashboard_bg_path", "dashboard_bg_overlay_opacity", "dashboard_bg_blur", "dashboard_bg_position",
    "dashboard_bg_size_mode", "dashboard_bg_size_percent", "dashboard_overlay_color",
    "dashboard_bg_brightness", "dashboard_hero_text_color",
    "exam_abnormal_red", "report_design_exam", "report_design_coag", "auto_flag_color_enabled", "label_layout_tube",
    "label_layout_request", "barcode_copies", "barcode_group_mode", "known_analyzers", "whatsapp_country_code",
    "landing_title", "landing_title_en", "landing_bg_banner_size", "landing_bg_logo_size", "landing_bg_overlay_opacity",
    "landing_bg_position", "landing_bg_shape", "landing_image_opacity", "landing_image_position", "landing_image_shape",
    "landing_gradient_color", "landing_bg_image_path", "landing_bglogo_image_path", "landing_lab_image_path",
    "landing_reception_image_path", "landing_together_image_path",
)



def ask(q, default=""):
    v = input(q + (" [%s]" % default if default else "") + ": ").strip().strip('"')
    return v or default


def yes(q, default="y"):
    return (ask(q + " (y/n)", default).lower() or default).startswith("y")


def read_mine(db_path):
    con = sqlite3.connect("file:" + db_path.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        keys = ("logo_path",) + DESIGN_KEYS
        st = {r["key"]: r["value"] for r in con.execute(
            "SELECT key, value FROM settings WHERE key IN (%s)" % ",".join("?" * len(keys)), keys)}
        cols = [r[1] for r in con.execute("PRAGMA table_info(examining_doctors_list)")]
        want = [c for c in ("name", "title", "degree_ar", "degree_en", "sort_order", "font_size") if c in cols]
        docs = [dict(r) for r in con.execute("SELECT " + ", ".join(want) +
               " FROM examining_doctors_list WHERE show_on_letterhead=1 ORDER BY sort_order, id")] if "name" in want else []
        tcols = [r[1] for r in con.execute("PRAGMA table_info(test_definitions)")]
        tw = [c for c in ("code", "report_group", "panel_color", "panel_page_break", "row_spacing", "done_by_note") if c in tcols]
        tds = [dict(r) for r in con.execute("SELECT " + ", ".join(tw) + " FROM test_definitions")] if len(tw) > 1 else []
    finally:
        con.close()
    return st, docs, tds


def b64file(rel):
    for base in (os.path.join(PROJECT, "static"),):
        fp = os.path.join(base, rel.replace("/", os.sep))
        if os.path.isfile(fp) and os.path.getsize(fp) <= 3 * 1024 * 1024:
            with open(fp, "rb") as fh:
                return {"filename": os.path.basename(fp), "b64": base64.b64encode(fh.read()).decode("ascii")}
    return None


def main():
    print("== Branding preset for an installed client ==  (Enter = skip a field)\n")
    s = {}
    for key, q in (("app_name_ar", "Lab name - Arabic"), ("app_name", "Lab name - English"),
                   ("lab_phone", "Phone"), ("lab_address", "Address")):
        v = ask(q)
        if v:
            s[key] = v
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

    db_path = os.path.join(PROJECT, "lis.db")
    if os.path.exists(db_path) and yes("\nTake the logo, doctors + degrees, report design and home-screen images from YOUR program (" + db_path + ")"):
        st, docs, tds = read_mine(db_path)
        payload["settings"].update({k: v for k, v in st.items() if k != "logo_path" and (v or "").strip()})
        if docs:
            payload["letterhead_doctors"] = docs
        if tds:
            payload["test_designs"] = tds
        lg = b64file(st.get("logo_path") or "") if (st.get("logo_path") or "").strip() else None
        if lg:
            payload["logo"] = lg
        files, seen = [], set()
        for k in DESIGN_KEYS:
            if k.endswith("_path") and (st.get(k) or "").strip() not in ("", "-"):
                f = b64file(st[k])
                if f and f["filename"] not in seen:
                    files.append(f); seen.add(f["filename"])
        if files:
            payload["files"] = files
        print("  logo: %s | doctors: %d (with degrees: %d) | images: %d | design settings: %d" % (
            "YES" if lg else "NOT FOUND", len(docs), sum(1 for d in docs if d.get("degree_ar") or d.get("degree_en")),
            len(files), len(payload["settings"])))
    lp = ask("\nOr a specific logo image path (png/jpg, max 3 MB) - Enter to keep the one above / skip")
    if lp:
        ext = lp.rsplit(".", 1)[-1].lower()
        if not os.path.exists(lp) or ext not in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
            sys.exit("Logo file not found or not an image - no file created.")
        raw = open(lp, "rb").read()
        if len(raw) > 3 * 1024 * 1024:
            sys.exit("Logo is bigger than 3 MB - no file created.")
        payload["logo"] = {"filename": "logo_" + str(len(raw)) + "." + ext, "b64": base64.b64encode(raw).decode()}
    if not (payload["settings"] or payload.get("logo") or payload.get("letterhead_doctors")):
        sys.exit("Nothing to write - no file created.")
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
