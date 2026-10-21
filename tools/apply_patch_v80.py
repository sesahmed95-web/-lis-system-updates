# -*- coding: utf-8 -*-
r"""
apply_patch_v80.py - ESR تحت CBC + Retic داخل بطاقة BF (فوق v79).
  1) CBC + ESR بنفس الزيارة: ESR يطلع بسطر واحد أسفل جدول CBC (الاسم يسار، النتيجة بالوسط، المدى الطبيعي بالطرف المقابل)،
     أحمر لو خارج المدى، ولا يطلع بتقرير/صفحة منفصلة (طباعة مفردة، حزمة النتائج، اللوحة المجمّعة، PDF، واتساب).
     ESR لحاله (بدون CBC) يبقى يطبع بالجدول العادي أو ضمن اللوحة المجمّعة.
  2) BF + Retic بنفس الزيارة: بطاقة Retic المنفصلة تختفي من شاشة الإدخال، وحقلا Reticulocyte count و Corrected Retic count
     يبقون داخل بطاقة BF، وعند حفظ BF تُنسخ القيمتان تلقائيًا لتحليل Retic ويصير Completed.
     BF بدون Retic: الحقلان ينلغون من بطاقة BF. Retic بدون BF: بطاقته المنفصلة مثل ما هي.
شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v80.py     (نسخة احتياطية app.py.bak_v80، ويوقف بدون تغيير لو app.py مختلف)
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")

HELPERS = r'''
# ============================== v80: ESR تحت CBC + Retic داخل BF ==============================
_V80_ESR_DOTS = False      # True = خطوط منقّطة بين الاسم والنتيجة والمدى (الافتراضي: بدون خطوط حسب الطلب)
_V80_RETIC_NAMES = ("Reticulocyte count", "Corrected Retic count")


def _v80_is_esr(code, name):
    c = (code or "").strip().upper()
    n = (name or "").strip().lower()
    return c == "ESR" or n == "esr" or n.startswith("esr ") or n.startswith("esr(") or "erythrocyte sedimentation" in n


def _v80_esr_html(db, cbc_ot_id):
    """سطر ESR الجاهز (HTML) لتقرير CBC، أو None لو ما عنده ESR/ما عنده نتيجة."""
    cbc = db.execute(
        "SELECT ot.order_id, p.id AS patient_id, p.gender, p.age, p.age_unit FROM order_tests ot "
        "JOIN orders o ON o.id = ot.order_id JOIN visits v ON v.id = o.visit_id JOIN patients p ON p.id = v.patient_id "
        "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE ot.id=? AND td.code='CBC'", (cbc_ot_id,)).fetchone()
    if not cbc:
        return None
    esr_ots = [r for r in db.execute(
        "SELECT ot.id, ot.analyzer, td.code AS code, td.name AS name FROM order_tests ot "
        "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE ot.order_id=? ORDER BY ot.id",
        (cbc["order_id"],)).fetchall() if _v80_is_esr(r["code"], r["name"])]
    lines = []
    for eo in esr_ots:
        for r in db.execute(
                "SELECT r.value_numeric, r.value_text, r.flag, tp.id AS pid, tp.name AS pname, tp.unit AS unit "
                "FROM results r JOIN test_parameters tp ON tp.id = r.test_parameter_id "
                "WHERE r.order_test_id=? ORDER BY tp.sort_order, tp.id", (eo["id"],)).fetchall():
            num, txt = r["value_numeric"], (r["value_text"] or "").strip()
            if num is None and not txt:
                continue
            if num is not None:
                val = str(int(num)) if float(num) == int(num) else str(num)
            else:
                val = txt
            rng = None
            try:
                rng = find_reference_range(db, r["pid"], cbc["gender"], cbc["age"], cbc["age_unit"],
                                           patient_id=cbc["patient_id"], analyzer=eo["analyzer"])
            except Exception:
                rng = None
            rtxt, low, high = "", None, None
            if rng is not None:
                try:
                    low, high = rng["low"], rng["high"]
                except (KeyError, IndexError, TypeError):
                    low = high = None
                try:
                    rtxt = (rng["range_text"] or "").strip()
                except (KeyError, IndexError, TypeError):
                    rtxt = ""
                if not rtxt and (low is not None or high is not None):
                    def _n(x):
                        return str(int(x)) if float(x) == int(x) else str(x)
                    rtxt = (_n(low) + " - " + _n(high)) if (low is not None and high is not None) else \
                           (("> " + _n(low)) if low is not None else ("< " + _n(high)))
            bad = (r["flag"] or "") in ("Low", "High", "Critical")
            if num is not None:
                if low is not None and num < low:
                    bad = True
                if high is not None and num > high:
                    bad = True
            lines.append((r["pname"] or "ESR", val, (r["unit"] or "").strip(), rtxt, bad))
    if not lines:
        return None
    dots = "border-bottom:2px dotted #666;transform:translateY(-3px);" if _V80_ESR_DOTS else ""
    out = ['<div class="lis-esr" dir="ltr" style="direction:ltr;margin:12px 0 0;padding-top:9px;border-top:1.5px solid #222;'
           'font-family:\'Times New Roman\',Georgia,serif;color:#111;">']
    for nm, val, unit, rtxt, bad in lines:
        col = "color:#c00;" if bad else ""
        out.append(
            '<div style="display:flex;align-items:baseline;gap:6px;font-size:13.5px;line-height:1.6;">'
            '<span style="font-weight:700;white-space:nowrap;">%s</span>'
            '<span style="flex:1;min-width:20px;%s"></span>'
            '<span style="font-weight:700;white-space:nowrap;text-align:center;min-width:90px;%s">%s</span>'
            '<span style="flex:1;min-width:20px;%s"></span>'
            '<span style="white-space:nowrap;min-width:120px;text-align:right;color:#333;">%s</span></div>'
            % (_html_escape(nm), dots, col, _html_escape((val + " " + unit).strip()), dots,
               _html_escape(("Normal: " + rtxt) if rtxt else "")))
    out.append("</div>")
    return "".join(out)


def _v80_insert_after_cbc_table(html, block):
    if 'class="lis-esr"' in html:
        return html
    pos = html.rfind("PLT")
    if pos < 0:
        pos = html.rfind("HGB")
    end = html.find("</table>", pos) if pos >= 0 else -1
    if end < 0:
        end = html.rfind("</table>")
    if end >= 0:
        end += len("</table>")
        return html[:end] + block + html[end:]
    i = html.rfind("</body>")
    return (html[:i] + block + html[i:]) if i >= 0 else (html + block)


def _print_report_impl(order_test_id):
    """v80: نفس تقرير v79 + سطر ESR أسفل جدول CBC لو عند المريض ESR بنفس الزيارة."""
    res = _print_report_impl_v79(order_test_id)
    try:
        if isinstance(res, str):
            db = get_db()
            block = _v80_esr_html(db, order_test_id)
            if block:
                return _v80_insert_after_cbc_table(res, block)
    except Exception:
        _v74_log_exc("v80 ESR under CBC failed (order_test %s)" % order_test_id)
    return res


def _v80_retic_row(db, order_id):
    return db.execute(
        "SELECT ot2.*, td2.code AS test_code, v.id AS visit_id, p.gender, p.age, p.age_unit "
        "FROM order_tests ot2 JOIN test_definitions td2 ON td2.id = ot2.test_definition_id "
        "JOIN orders o2 ON o2.id = ot2.order_id JOIN visits v ON v.id = o2.visit_id JOIN patients p ON p.id = v.patient_id "
        "WHERE ot2.order_id=? AND td2.code='RETIC'", (order_id,)).fetchone()


def _v80_sync_bf_to_retic(db, ot, parameters, user_id, now, patient_id):
    """عند حفظ BF: ينسخ Reticulocyte count / Corrected Retic count لتحليل Retic بنفس الزيارة ويكمّله."""
    try:
        if "test_code" not in ot.keys() or ot["test_code"] != "BF":
            return
        bf_params = {p["name"]: p for p in parameters if p["name"] in _V80_RETIC_NAMES}
        if "Reticulocyte count" not in bf_params:
            return
        rt = _v80_retic_row(db, ot["order_id"])
        if not rt:
            return
        rparams = db.execute("SELECT * FROM test_parameters WHERE test_definition_id=?", (rt["test_definition_id"],)).fetchall()
        rby = {p["name"]: p for p in rparams}

        def _has(r):
            return r is not None and (r["value_numeric"] is not None or (r["value_text"] or "") != "")
        copied = False
        for nm, bp in bf_params.items():
            rp = rby.get(nm)
            if not rp:
                continue
            src = db.execute("SELECT * FROM results WHERE order_test_id=? AND test_parameter_id=?", (ot["id"], bp["id"])).fetchone()
            if not _has(src):
                continue
            note = src["note"] if "note" in src.keys() else None
            dst = db.execute("SELECT * FROM results WHERE order_test_id=? AND test_parameter_id=?", (rt["id"], rp["id"])).fetchone()
            if dst:
                if dst["value_numeric"] != src["value_numeric"] or dst["value_text"] != src["value_text"]:
                    db.execute(
                        "INSERT INTO result_history (result_id, order_test_id, test_parameter_id, prev_value_numeric, "
                        "prev_value_text, prev_flag, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (dst["id"], rt["id"], rp["id"], dst["value_numeric"], dst["value_text"], dst["flag"], user_id, now))
                db.execute("UPDATE results SET value_numeric=?, value_text=?, flag=?, note=?, entered_by=?, entered_at=? WHERE id=?",
                           (src["value_numeric"], src["value_text"], src["flag"], note, user_id, now, dst["id"]))
            else:
                db.execute("INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, note, "
                           "entered_by, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (rt["id"], rp["id"], src["value_numeric"], src["value_text"], src["flag"], note, user_id, now))
            copied = True
        if copied and rt["status"] != "Verified":
            db.execute("UPDATE order_tests SET status='Completed' WHERE id=?", (rt["id"],))
        # Corrected لو ما انكتب ببطاقة BF: يُحسب (من HCT الـCBC) ثم يُنسخ لبطاقة BF حتى يظهر هناك
        cbp = bf_params.get("Corrected Retic count")
        crp = rby.get("Corrected Retic count")
        if copied and cbp and crp:
            bsrc = db.execute("SELECT * FROM results WHERE order_test_id=? AND test_parameter_id=?", (ot["id"], cbp["id"])).fetchone()
            if not _has(bsrc):
                _apply_retic_correction(db, rt, rparams, {}, "", user_id, now, patient_id)
                rc = db.execute("SELECT * FROM results WHERE order_test_id=? AND test_parameter_id=?", (rt["id"], crp["id"])).fetchone()
                if _has(rc):
                    if bsrc:
                        db.execute("UPDATE results SET value_numeric=?, value_text=?, flag=?, note=?, entered_by=?, entered_at=? WHERE id=?",
                                   (rc["value_numeric"], rc["value_text"], rc["flag"], rc["note"], user_id, now, bsrc["id"]))
                    else:
                        db.execute("INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, note, "
                                   "entered_by, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (ot["id"], cbp["id"], rc["value_numeric"], rc["value_text"], rc["flag"], rc["note"], user_id, now))
    except Exception:
        _v74_log_exc("v80 BF->RETIC sync failed")


def _v80_retic_sibling_id(db, ot):
    try:
        if "test_code" in ot.keys() and ot["test_code"] == "BF":
            rt = _v80_retic_row(db, ot["order_id"])
            return rt["id"] if rt else None
    except Exception:
        pass
    return None


def _v80_adjust_entry_boxes(db, visit_id, boxes):
    """شاشة إدخال نتائج الزيارة: BF+Retic => بطاقة Retic تختفي (حقولها ببطاقة BF). BF بدون Retic => ينلغي حقلا Retic من BF."""
    try:
        codes = {r["c"] for r in db.execute(
            "SELECT td.code AS c FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
            "JOIN test_definitions td ON td.id = ot.test_definition_id WHERE o.visit_id=?", (visit_id,)).fetchall()}
        bf = [b for b in boxes if b["ot"]["test_code"] == "BF"]
        if not bf:
            return boxes
        if "RETIC" in codes:
            if "Reticulocyte count" in {p["name"] for p in bf[0]["parameters"]}:
                return [b for b in boxes if b["ot"]["test_code"] != "RETIC"]
            return boxes
        for b in bf:
            b["parameters"] = [p for p in b["parameters"] if p["name"] not in _V80_RETIC_NAMES]
    except Exception:
        _v74_log_exc("v80 entry boxes adjust failed")
    return boxes

'''

# (اسم, النص القديم, النص الجديد)
EDITS = [
 ("rename_impl",
  'def _print_report_impl(order_test_id):\n    db = get_db()\n    ot = db.execute(',
  'def _print_report_impl_v79(order_test_id):\n    db = get_db()\n    ot = db.execute('),
 ("bundle_skip_esr",
  '    seen_codes = set()\n    reports = []\n',
  '    if any((_o["test_code"] or "") == "CBC" for _o in order_tests):   # v80: ESR يطلع داخل تقرير CBC\n'
  '        order_tests = [_o for _o in order_tests if not _v80_is_esr(_o["test_code"], _o["test_name"])]\n'
  '    seen_codes = set()\n    reports = []\n'),
 ("merge_skip_esr",
  '    seen_codes = set()\n    order_test_ids = []\n',
  '    if any((_o["test_code"] or "") == "CBC" for _o in order_tests):   # v80: ESR يطلع داخل تقرير CBC\n'
  '        order_tests = [_o for _o in order_tests if not _v80_is_esr(_o["test_code"], _o["test_name"])]\n'
  '    seen_codes = set()\n    order_test_ids = []\n'),
 ("whatsapp_skip_esr",
  '        seen_codes = set()\n        items = []\n',
  '        if any((_o["test_code"] or "") == "CBC" for _o in order_tests):   # v80: ESR يطلع داخل تقرير CBC\n'
  '            order_tests = [_o for _o in order_tests if not _v80_is_esr(_o["test_code"], _o["test_name"])]\n'
  '        seen_codes = set()\n        items = []\n'),
 ("panel_core_skip_esr",
  '    order_tests = [_o for _o in order_tests if _merged_ok(_o)]\n',
  '    _v80_has_cbc = any((_o["test_code"] or "") == "CBC" for _o in order_tests)   # v80: ESR يطلع داخل تقرير CBC\n'
  '    order_tests = [_o for _o in order_tests if _merged_ok(_o)\n'
  '                   and not (_v80_has_cbc and _v80_is_esr(_o["test_code"], _o["test_name"]))]\n'),
 ("panel_skip_esr",
  '    panel_ids, extra_ids = [], []\n    for r in rows:\n',
  '    if any((_r["code"] or "") == "CBC" for _r in rows):   # v80: ESR يطلع داخل تقرير CBC\n'
  '        rows = [_r for _r in rows if not _v80_is_esr(_r["code"], _r["name"])]\n'
  '    panel_ids, extra_ids = [], []\n    for r in rows:\n'),
 ("sync_on_save",
  '        except Exception:\n            pass\n\n    return touched\n\n\ndef _apply_retic_correction(',
  '        except Exception:\n            pass\n    elif "test_code" in ot.keys() and ot["test_code"] == "BF":\n'
  '        _v80_sync_bf_to_retic(db, ot, parameters, user_id, now, patient_id)   # v80: Retic داخل BF\n\n'
  '    return touched\n\n\ndef _apply_retic_correction('),
 ("entry_post_touch",
  '            if touched:\n                any_saved = True\n                touched_ot_ids.append(ot["id"])\n',
  '            if touched:\n                any_saved = True\n                touched_ot_ids.append(ot["id"])\n'
  '                _rt80 = _v80_retic_sibling_id(db, ot)   # v80: Retic اللي انكمل من BF يدخل بتحديث PDF/الأرشيف\n'
  '                if _rt80 and _rt80 not in touched_ot_ids:\n                    touched_ot_ids.append(_rt80)\n'),
 ("entry_get_boxes",
  '    _pv_cfg = get_result_layout(db)\n    _pv_has_merge = bool(get_visit_previous_merges(db, visit_id))\n    return render_template("front_desk/visit_results_entry.html"',
  '    boxes = _v80_adjust_entry_boxes(db, visit_id, boxes)   # v80\n'
  '    _pv_cfg = get_result_layout(db)\n    _pv_has_merge = bool(get_visit_previous_merges(db, visit_id))\n    return render_template("front_desk/visit_results_entry.html"'),
 ("helpers",
  '\nif __name__ == "__main__":\n    init_db()',
  HELPERS + '\nif __name__ == "__main__":\n    init_db()'),
]


def main():
    s = open(P, encoding="utf-8").read()
    if "_v80_is_esr" in s:
        sys.exit("Already patched - nothing to do.")
    if "_v74_log_exc" not in s:
        sys.exit("STOPPED: this patch needs v74+ (v79 ALL_IN_ONE) app.py. Nothing changed.")
    for n, a, _ in EDITS:
        c = s.count(a)
        if c != 1:
            sys.exit("STOPPED: anchor '%s' found %d times (expected 1). app.py differs from v79 - nothing changed." % (n, c))
    new = s
    for n, a, b in EDITS:
        new = new.replace(a, b)
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v80")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: app.py patched (backup app.py.bak_v80). Restart the program completely.")


if __name__ == "__main__":
    main()
