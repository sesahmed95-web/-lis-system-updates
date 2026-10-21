# -*- coding: utf-8 -*-
r"""
apply_patch_v75.py - "بطاقة المريض": نافذة مستقلة بلا مسطرة جانبية: معلومات المريض كاملة + تعديلها، كل الباركودات،
التحاليل وأسعارها، التحاليل المرسلة لمختبر آخر، وإضافة تحليل. + زر 🪟 بجانب نتائج البحث يفتحها.
شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v75.py      (نسخة احتياطية app.py.bak_v75، ويوقف لو app.py مختلف)
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")
ANCHOR = 'if __name__ == "__main__":'

BLOCK = r'''# --- v75: بطاقة المريض (نافذة مستقلة بلا مسطرة جانبية) ---
def _pc_recalc_invoice(db, visit_id):
    inv = db.execute("SELECT id, extra_charges FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if not inv:
        return
    tot = db.execute("SELECT COALESCE(SUM(ot.price),0) AS t FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=?", (visit_id,)).fetchone()["t"]
    fee = db.execute("SELECT COALESCE(home_visit_fee,0) AS f FROM visits WHERE id=?", (visit_id,)).fetchone()["f"]
    db.execute("UPDATE invoices SET total_amount=? WHERE id=?", (float(tot or 0) + float(fee or 0) + float(inv["extra_charges"] or 0), inv["id"]))


def _pc_visit(db, visit_id):
    return db.execute(
        "SELECT v.*, p.full_name, p.gender, p.age, p.age_unit, p.phone, p.title, p.email, d.full_name AS doctor_name, rc.name AS center_name "
        "FROM visits v JOIN patients p ON p.id = v.patient_id LEFT JOIN doctors d ON d.id = v.doctor_id "
        "LEFT JOIN referral_centers rc ON rc.id = v.referral_center_id WHERE v.id=?", (visit_id,)).fetchone()


@app.route("/patient-card/<int:visit_id>")
@login_required
def patient_card(visit_id):
    db = get_db()
    v = _pc_visit(db, visit_id)
    if not v:
        return "Not found", 404
    tests = [dict(r) for r in db.execute(
        "SELECT ot.id, ot.status, COALESCE(ot.price,0) AS price, COALESCE(ot.forwarded_lab_name,'') AS fwd_lab, "
        "COALESCE(ot.forwarded_cost,0) AS fwd_cost, td.name, td.department, td.sample_type "
        "FROM order_tests ot JOIN orders o ON o.id = ot.order_id JOIN test_definitions td ON td.id = ot.test_definition_id "
        "WHERE o.visit_id=? ORDER BY ot.id", (visit_id,)).fetchall()]
    groups = {}
    for t in tests:
        k = (globals().get("_tube_type_of") or (lambda s, d, n: s or ""))(t["sample_type"], t["department"], t["name"]) or ""
        if k:
            g = groups.setdefault(k, {"label": k, "ids": [], "n": 0})
            g["ids"].append(str(t["id"])); g["n"] += 1
    tube_groups = [{"label": g["label"], "ids": ",".join(g["ids"]), "n": g["n"]} for g in groups.values()]
    fwd_ids = ",".join(str(t["id"]) for t in tests if t["fwd_lab"])
    try:
        catalog = [dict(r) for r in db.execute("SELECT id, name, department FROM test_definitions ORDER BY department, name").fetchall()]
    except Exception:
        catalog = []
    exam = [r[0] for r in db.execute("SELECT name FROM examining_doctors_list ORDER BY sort_order, name").fetchall()]
    refd = [r[0] for r in db.execute("SELECT full_name FROM doctors ORDER BY full_name LIMIT 300").fetchall()]
    fwd_labs = [r[0] for r in db.execute("SELECT DISTINCT forwarded_lab_name FROM order_tests WHERE forwarded_lab_name IS NOT NULL AND forwarded_lab_name<>''").fetchall()]
    return render_template("patient_card.html", v=v, tests=tests, bal=type("B", (), _visit_balance(db, visit_id)),
                           tube_groups=tube_groups, fwd_ids=fwd_ids, catalog=catalog, exam_doctors=exam, ref_doctors=refd, fwd_labs=fwd_labs)


@app.route("/api/patient-card/<int:visit_id>/info", methods=["POST"])
@login_required
def api_pc_info(visit_id):
    db = get_db()
    v = _pc_visit(db, visit_id)
    if not v:
        return jsonify(ok=False, error="الزيارة غير موجودة"), 404
    inv = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if inv and inv["is_locked"]:
        return jsonify(ok=False, error="الفاتورة مقفلة — لا يمكن التعديل."), 400
    p = request.get_json(silent=True) or {}
    name = (p.get("patient_name") or "").strip()
    if not name:
        return jsonify(ok=False, error="اسم المريض مطلوب"), 400
    db.execute("UPDATE patients SET full_name=?, full_name_en=COALESCE(?, full_name_en), gender=?, age=?, age_unit=?, phone=?, title=?, email=? WHERE id=?",
               (name, transliterate_arabic_name(name) if name != v["full_name"] else None, p.get("gender") or v["gender"],
                p.get("age") or None, p.get("age_unit") or "Years", (p.get("phone") or "").strip(), p.get("title") or "Mr.",
                (p.get("email") or "").strip(), v["patient_id"]))
    doc_id = find_or_create_doctor(db, p.get("doctor_name", ""))
    center_id = find_or_create_referral_center(db, p.get("referral_lab_name", ""))
    exam = (p.get("examining_doctor") or "").strip()
    db.execute("UPDATE visits SET doctor_id=?, referral_center_id=?, fasting=?, notes=?, examining_doctor=?, attending_doctor=? WHERE id=?",
               (doc_id, center_id, p.get("fasting") or "Undefined", p.get("notes") or "", exam, exam, visit_id))
    if (doc_id or None) != (v["doctor_id"] or None) or (center_id or None) != (v["referral_center_id"] or None):
        for row in db.execute("SELECT ot.id, ot.test_definition_id FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=?", (visit_id,)).fetchall():
            pr = get_test_price(db, row["test_definition_id"], doc_id, center_id)
            db.execute("UPDATE order_tests SET price=?, doctor_id=?, price_missing=? WHERE id=?",
                       (pr if pr is not None else 0, doc_id, 1 if pr is None else 0, row["id"]))
    try:
        recompute_examining_doctor_fee(db, visit_id)
    except Exception:
        pass
    _pc_recalc_invoice(db, visit_id)
    db.commit()
    log_action("Update", "visit", visit_id, "patient-card")
    return jsonify(ok=True)


@app.route("/api/patient-card/<int:visit_id>/test/<int:ot_id>", methods=["POST"])
@login_required
def api_pc_test(visit_id, ot_id):
    db = get_db()
    row = db.execute("SELECT ot.id FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE ot.id=? AND o.visit_id=?", (ot_id, visit_id)).fetchone()
    if not row:
        return jsonify(ok=False, error="غير موجود"), 404
    inv = db.execute("SELECT is_locked FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    p = request.get_json(silent=True) or {}
    try:
        price = float(p.get("price")) if str(p.get("price", "")).strip() != "" else None
        cost = float(p.get("fwd_cost") or 0)
    except ValueError:
        return jsonify(ok=False, error="رقم غير صحيح"), 400
    lab = (p.get("fwd_lab") or "").strip() or None
    if price is not None:
        if inv and inv["is_locked"]:
            return jsonify(ok=False, error="الفاتورة مقفلة — لا يمكن تعديل السعر."), 400
        db.execute("UPDATE order_tests SET price=?, price_missing=0 WHERE id=?", (price, ot_id))
        _pc_recalc_invoice(db, visit_id)
    db.execute("UPDATE order_tests SET forwarded_lab_name=?, forwarded_cost=? WHERE id=?", (lab, cost if lab else 0, ot_id))
    db.commit()
    log_action("ForwardTest", "order_tests", ot_id, "patient-card lab=%s cost=%s" % (lab, cost))
    return jsonify(ok=True)


@app.route("/api/patient-card/<int:visit_id>/add-test", methods=["POST"])
@login_required
def api_pc_add_test(visit_id):
    db = get_db()
    v = _pc_visit(db, visit_id)
    order = db.execute("SELECT * FROM orders WHERE visit_id=?", (visit_id,)).fetchone()
    inv = db.execute("SELECT is_locked FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if not v or not order:
        return jsonify(ok=False, error="الزيارة غير موجودة"), 404
    if inv and inv["is_locked"]:
        return jsonify(ok=False, error="الفاتورة مقفلة — لا يمكن إضافة تحاليل."), 400
    tid = str((request.get_json(silent=True) or {}).get("test_id") or "")
    if not tid.isdigit() or not db.execute("SELECT id FROM test_definitions WHERE id=?", (tid,)).fetchone():
        return jsonify(ok=False, error="تحليل غير صحيح"), 400
    have = {str(r["test_definition_id"]) for r in db.execute("SELECT test_definition_id FROM order_tests WHERE order_id=?", (order["id"],)).fetchall()}
    if tid in have:
        return jsonify(ok=False, error="هذا التحليل موجود أصلًا بالزيارة."), 400
    reg = v["registration_number"]
    for t in [tid] + [x for x in expand_required_tests(db, [tid])[1:] if x not in have]:
        pr = get_test_price(db, t, v["doctor_id"], v["referral_center_id"])
        db.execute("INSERT INTO order_tests (order_id, test_definition_id, status, barcode, price, doctor_id, created_at, price_missing) "
                   "VALUES (?, ?, 'Accepted', ?, ?, ?, ?, ?)",
                   (order["id"], t, f"{reg}{str(t).zfill(3)}", pr if pr is not None else 0, v["doctor_id"],
                    datetime.now().isoformat(timespec="seconds"), 1 if pr is None else 0))
    try:
        recompute_examining_doctor_fee(db, visit_id)
    except Exception:
        pass
    _pc_recalc_invoice(db, visit_id)
    db.commit()
    log_action("AddTest", "visit", visit_id, "patient-card test=%s" % tid)
    return jsonify(ok=True)


@app.after_request
def _pc_inject_search_buttons(resp):
    """بصفحة نتائج البحث: زر 🪟 بجانب كل نتيجة (وزر عائم لو نتيجة واحدة) يفتح بطاقة المريض بنافذة مستقلة."""
    try:
        if request.path == "/search" and resp.mimetype == "text/html" and resp.status_code == 200:
            body = resp.get_data(as_text=True)
            if "lisPcBtns" not in body and "</body>" in body:
                js = ("<script id='lisPcBtns'>(function(){var seen={},first=null;document.querySelectorAll('a[href*=\"/visits/\"]').forEach(function(a){"
                      "var m=(a.getAttribute('href')||'').match(/\\/visits\\/(\\d+)/);if(!m)return;var id=m[1];first=first||id;seen[id]=1;"
                      "if(a.dataset.pcDone)return;a.dataset.pcDone=1;var b=document.createElement('a');b.href='#';b.textContent='🪟 بطاقة';b.title='بطاقة المريض';"
                      "b.style.cssText='margin:0 6px;background:#205072;color:#fff;border-radius:7px;padding:3px 9px;font-size:12px;text-decoration:none;white-space:nowrap';"
                      "b.onclick=function(e){e.preventDefault();window.open('/patient-card/'+id,'lisCard'+id,'width=1180,height=820,resizable=yes,scrollbars=yes');};"
                      "a.parentNode.insertBefore(b,a.nextSibling);});"
                      "var ids=Object.keys(seen);if(ids.length===1){var f=document.createElement('a');f.href='#';f.textContent='🪟 فتح بطاقة المريض';"
                      "f.style.cssText='position:fixed;bottom:16px;left:16px;z-index:9999;background:#15803D;color:#fff;border-radius:10px;padding:10px 16px;font:700 14px Tahoma;text-decoration:none;box-shadow:0 3px 12px rgba(0,0,0,.3)';"
                      "f.onclick=function(e){e.preventDefault();window.open('/patient-card/'+ids[0],'lisCard','width=1180,height=820,resizable=yes,scrollbars=yes');};document.body.appendChild(f);}})();</script>")
                resp.set_data(body.replace("</body>", js + "</body>", 1))
    except Exception:
        pass
    return resp


'''


def main():
    s = open(P, encoding="utf-8").read()
    if "def patient_card(" in s:
        sys.exit("Already patched - nothing to do.")
    if s.count(ANCHOR) != 1:
        sys.exit("STOPPED: anchor not found exactly once - app.py differs from what this patch expects. Nothing changed.")
    for need in ("find_or_create_doctor", "get_test_price", "expand_required_tests", "def _visit_balance", "def log_action"):
        if need not in s:
            sys.exit("STOPPED: app.py has no '%s' - nothing changed." % need)
    new = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v75")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: app.py patched (backup app.py.bak_v75). Copy templates\\patient_card.html, then restart the program.")


if __name__ == "__main__":
    main()
