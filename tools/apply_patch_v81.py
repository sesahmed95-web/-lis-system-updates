# -*- coding: utf-8 -*-
r"""
apply_patch_v81.py - بطاقة المريض الجديدة (فوق v80): نافذة صغيرة فورية من مربع البحث العلوي.
  - اكتب اسم المريض/رقمه/باركوده بمربع البحث العلوي => قائمة نتائج فورية => اختر => تنفتح البطاقة فوق نفس الصفحة (بدون مسطرة جانبية).
  - بالبطاقة: معلومات المريض كاملة (+ صحة وهوية وزيارة منزلية)، الطبيب المُرسِل والفاحص، التحاليل وأسعارها،
    إرسال تحاليل محددة لمختبر آخر (أو إلغاؤه) + إضافة/حذف تحليل، الفاتورة والدفع، كل الباركودات.
  - ESR تحت CBC: يُوضع بعد جدول CBC بالضبط (قالب cbc.html الحقيقي).
شغّله مرة واحدة من مجلد البرنامج:   python tools\apply_patch_v81.py     (نسخة احتياطية app.py.bak_v81، ويوقف لو app.py مختلف)
وانسخ templates\patient_card.html فوق الموجود.
"""
import os, py_compile, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "app.py")

JS = r'''(function(){
 if(window.__lisPcInit)return; window.__lisPcInit=1;
 var ov=null, fr=null, dd=null, inp=null, seq=0, timer=null, items=[], hi=-1;
 function build(){
  if(ov)return;
  ov=document.createElement("div"); ov.id="lisPcOv";
  ov.style.cssText="position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:100000;display:none;align-items:center;justify-content:center;padding:14px;";
  var box=document.createElement("div");
  box.style.cssText="width:min(1320px,98vw);height:min(880px,96vh);border-radius:13px;overflow:hidden;background:#fff;box-shadow:0 24px 70px rgba(0,0,0,.45);";
  fr=document.createElement("iframe"); fr.style.cssText="border:0;width:100%;height:100%;display:block;background:#F1F5F9;";
  box.appendChild(fr); ov.appendChild(box); document.body.appendChild(ov);
  ov.addEventListener("mousedown",function(e){ if(e.target===ov) closeCard(); });
 }
 function openCard(id){ build(); fr.src="/patient-card/"+id+"?modal=1"; ov.style.display="flex"; hideDd(); }
 function closeCard(){ if(!ov)return; ov.style.display="none"; fr.src="about:blank"; if(inp){inp.focus();} }
 window.lisOpenPatientCard=openCard;
 window.addEventListener("message",function(e){ if(e.data&&e.data.lisCard==="close") closeCard(); });
 document.addEventListener("keydown",function(e){ if(e.key==="Escape"&&ov&&ov.style.display==="flex") closeCard(); },true);
 function findInput(){
  var a=document.querySelectorAll("input");
  for(var i=0;i<a.length;i++){ var p=a[i].placeholder||""; if(p.indexOf("باركود")>=0&&p.indexOf("اسم")>=0){ var r=a[i].getBoundingClientRect(); if(r.top<150&&r.width>60) return a[i]; } }
  return null;
 }
 function hideDd(){ if(dd){dd.style.display="none";} items=[]; hi=-1; }
 function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];}); }
 function paint(){
  if(!dd){ dd=document.createElement("div"); dd.id="lisPcDd"; document.body.appendChild(dd); }
  var r=inp.getBoundingClientRect(), w=Math.max(r.width,440);
  dd.style.cssText="position:fixed;top:"+(r.bottom+4)+"px;left:"+Math.max(8,Math.min(r.left,window.innerWidth-w-8))+"px;width:"+w+"px;max-height:62vh;overflow:auto;background:#fff;border:1px solid #94A3B8;border-radius:11px;box-shadow:0 12px 36px rgba(0,0,0,.28);z-index:99999;direction:rtl;font:13px Tahoma,Arial,sans-serif;display:block;";
  if(!items.length){ dd.innerHTML="<div style=\"padding:12px;color:#64748B\">ما لكيت مريض بهذا الاسم/الرقم</div>"; return; }
  dd.innerHTML=items.map(function(x,i){
   return "<div data-i=\""+i+"\" style=\"padding:8px 12px;cursor:pointer;border-bottom:1px solid #EEF2F6;"+(i===hi?"background:#E0F2FE;":"")+"\"><b style=\"color:#205072\">"+esc(x.name)+"</b> <span style=\"color:#475569\">#"+esc(x.reg)+" · "+esc(x.age||"")+" "+esc(x.unit||"")+" · "+esc(x.date)+"</span>"+(x.tests?"<div style=\"font-size:11.5px;color:#64748B;margin-top:2px\">"+esc(x.tests)+"</div>":"")+"</div>";
  }).join("");
  Array.prototype.forEach.call(dd.children,function(el){ el.onmousedown=function(e){ e.preventDefault(); openCard(items[+el.dataset.i].visit_id); }; });
 }
 function search(q){
  var my=++seq;
  fetch("/api/pc/search?q="+encodeURIComponent(q)).then(function(r){return r.json();}).then(function(d){ if(my!==seq)return; items=d.items||[]; hi=items.length?0:-1; paint(); }).catch(function(){});
 }
 function attach(){
  inp=findInput(); if(!inp) return;
  ["input","keyup"].forEach(function(ev){
   document.addEventListener(ev,function(e){
    if(e.target!==inp) return;
    e.stopImmediatePropagation();
    if(ev==="keyup"&&(e.key==="Enter"||e.key==="ArrowDown"||e.key==="ArrowUp"||e.key==="Escape")) return;
    var q=inp.value.trim();
    clearTimeout(timer);
    if(q.length<2){ hideDd(); return; }
    timer=setTimeout(function(){ search(q); },170);
   },true);
  });
  document.addEventListener("keydown",function(e){
   if(e.target!==inp) return;
   if(e.key==="Enter"){ e.preventDefault(); e.stopImmediatePropagation(); if(items.length) openCard(items[Math.max(hi,0)].visit_id); else if(inp.value.trim().length>=2) search(inp.value.trim()); }
   else if(e.key==="ArrowDown"||e.key==="ArrowUp"){ if(!items.length) return; e.preventDefault(); e.stopImmediatePropagation(); hi=(hi+(e.key==="ArrowDown"?1:-1)+items.length)%items.length; paint(); }
   else if(e.key==="Escape"){ hideDd(); }
   else { e.stopImmediatePropagation(); }
  },true);
  document.addEventListener("mousedown",function(e){ if(dd&&e.target!==inp&&!dd.contains(e.target)) hideDd(); });
  inp.setAttribute("title","اكتب اسم المريض أو رقمه أو الباركود — تظهر بطاقة المريض فورًا");
 }
 if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",attach); else attach();
})();'''

NEW_CODE = r'''
# ============================== v81: بطاقة المريض (بحث فوري + نافذة بلا مسطرة) ==============================
_V81_PC_JS = ("<script id=\"lis-pc-js\">" + __JS__ + "</script>")


def _pc_partner_prices(db):
    """{اسم المختبر: {test_definition_id: الكلفة}} لتعبئة كلفة الإرسال تلقائيًا."""
    try:
        labs, prices = _partner_context(db)
        return {l["name"]: dict(prices.get(str(l["id"]), {})) for l in labs}
    except Exception:
        return {}


def _pc_state(db, visit_id):
    b = _visit_balance(db, visit_id)
    return {"total": b["total"], "paid": b["paid"], "remaining": b["remaining"]}


def _pc_locked(db, visit_id):
    inv = db.execute("SELECT is_locked FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    return bool(inv and inv["is_locked"])


@app.route("/api/pc/search")
@login_required
def api_pc_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    db = get_db()
    seq = _visit_seq_clause(q)
    rows = db.execute(
        "SELECT v.id, v.registration_number, v.created_at, p.full_name, p.age, p.age_unit, "
        "(SELECT GROUP_CONCAT(COALESCE(NULLIF(td.short_name,''), td.name), ', ') FROM order_tests ot "
        " JOIN orders o ON o.id = ot.order_id JOIN test_definitions td ON td.id = ot.test_definition_id "
        " WHERE o.visit_id = v.id) AS tests "
        "FROM visits v JOIN patients p ON p.id = v.patient_id "
        "WHERE p.full_name LIKE ? OR CAST(v.registration_number AS TEXT) LIKE ? OR p.phone LIKE ? "
        "OR EXISTS (SELECT 1 FROM order_tests ot JOIN orders o ON o.id = ot.order_id WHERE o.visit_id = v.id AND ot.barcode LIKE ?)"
        + (" OR " + seq[0] if seq else "") + " ORDER BY v.id DESC LIMIT 20",
        (f"%{q}%", _scan_like(q), f"%{q}%", f"%{q}%") + tuple(seq[1] if seq else ())).fetchall()
    return jsonify({"items": [{"visit_id": r["id"], "reg": r["registration_number"], "name": r["full_name"],
                               "age": r["age"], "unit": r["age_unit"], "tests": r["tests"] or "",
                               "date": (r["created_at"] or "")[:16].replace("T", " ")} for r in rows]})


@app.route("/api/patient-card/<int:visit_id>/state")
@login_required
def api_pc_state(visit_id):
    return jsonify(ok=True, **_pc_state(get_db(), visit_id))


@app.route("/api/patient-card/<int:visit_id>/extra", methods=["POST"])
@login_required
def api_pc_extra(visit_id):
    db = get_db()
    v = _pc_visit(db, visit_id)
    if not v:
        return jsonify(ok=False, error="الزيارة غير موجودة"), 404
    if _pc_locked(db, visit_id):
        return jsonify(ok=False, error="الفاتورة مقفلة — لا يمكن التعديل."), 400
    p = request.get_json(silent=True) or {}
    s = lambda k: (str(p.get(k) or "")).strip()
    db.execute("UPDATE patients SET address=?, national_id=?, passport_number=?, travel_certificate_number=?, lab_card_number=? WHERE id=?",
               (s("address"), s("national_id"), s("passport_number"), s("travel_certificate_number"), s("lab_card_number"), v["patient_id"]))
    home = 1 if s("is_home_visit") in ("1", "true", "True") else 0
    try:
        fee = float(s("home_visit_fee") or 0) if home else 0.0
    except ValueError:
        fee = 0.0
    db.execute("UPDATE visits SET weight=?, height=?, symptoms=?, disease=?, therapy=?, is_home_visit=?, home_visit_address=?, home_visit_fee=? WHERE id=?",
               (s("weight") or None, s("height") or None, s("symptoms"), s("disease"), s("therapy"),
                home, s("home_visit_address") if home else "", fee, visit_id))
    _pc_recalc_invoice(db, visit_id)
    db.commit()
    log_action("Update", "visit", visit_id, "patient-card extra")
    return jsonify(ok=True)


@app.route("/api/patient-card/<int:visit_id>/forward", methods=["POST"])
@login_required
def api_pc_forward(visit_id):
    """إرسال تحاليل محددة لمختبر آخر دفعة وحدة (الكلفة من قائمة أسعار المختبر إن وُجدت) — مختبر فارغ = إلغاء الإرسال."""
    db = get_db()
    p = request.get_json(silent=True) or {}
    ids = [int(x) for x in (p.get("ot_ids") or []) if str(x).isdigit()]
    lab = (p.get("lab") or "").strip() or None
    if not ids:
        return jsonify(ok=False, error="حدّد تحليلًا واحدًا على الأقل"), 400
    _ensure_partner_labs(db)
    pl = db.execute("SELECT id FROM partner_labs WHERE name=?", (lab,)).fetchone() if lab else None
    n = 0
    for oid in ids:
        ot = db.execute("SELECT ot.id, ot.test_definition_id FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE ot.id=? AND o.visit_id=?",
                        (oid, visit_id)).fetchone()
        if not ot:
            continue
        cost = 0.0
        if lab and pl:
            pr = db.execute("SELECT cost FROM partner_lab_prices WHERE lab_id=? AND test_definition_id=?", (pl["id"], ot["test_definition_id"])).fetchone()
            cost = float(pr["cost"] or 0) if pr else 0.0
        db.execute("UPDATE order_tests SET forwarded_lab_name=?, forwarded_cost=? WHERE id=?", (lab, cost if lab else 0, oid))
        n += 1
    db.commit()
    log_action("ForwardTest", "visit", visit_id, ("patient-card lab=%s n=%d" % (lab, n)) if lab else "patient-card cleared n=%d" % n)
    return jsonify(ok=True, n=n)


@app.route("/api/patient-card/<int:visit_id>/remove/<int:ot_id>", methods=["POST"])
@login_required
def api_pc_remove(visit_id, ot_id):
    db = get_db()
    ot = db.execute("SELECT ot.id, ot.status FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE ot.id=? AND o.visit_id=?", (ot_id, visit_id)).fetchone()
    if not ot:
        return jsonify(ok=False, error="التحليل غير موجود"), 404
    if _pc_locked(db, visit_id):
        return jsonify(ok=False, error="الفاتورة مقفلة — لا يمكن الحذف."), 400
    if ot["status"] in ("Completed", "Verified"):
        return jsonify(ok=False, error="هذا التحليل مكتمل ونتيجته محفوظة — احذفه من «التعديل الكامل» (محمي بكلمة مرور)."), 403
    visit_remove_test(visit_id, ot_id)      # نفس دالة صفحة التعديل (تحفظ نسخة للتراجع وتحدّث أجر الفاحص)
    try:
        get_flashed_messages()              # نمسح رسالة flash حتى ما تطلع بصفحة ثانية
    except Exception:
        pass
    try:
        recompute_examining_doctor_fee(db, visit_id)
    except Exception:
        pass
    _pc_recalc_invoice(db, visit_id)
    db.commit()
    return jsonify(ok=True, **_pc_state(db, visit_id))


@app.route("/api/patient-card/<int:visit_id>/pay", methods=["POST"])
@login_required
def api_pc_pay(visit_id):
    db = get_db()
    inv = db.execute("SELECT * FROM invoices WHERE visit_id=?", (visit_id,)).fetchone()
    if not inv:
        return jsonify(ok=False, error="ما توجد فاتورة لهذي الزيارة"), 404
    if inv["is_locked"]:
        return jsonify(ok=False, error="الفاتورة مقفلة"), 400
    try:
        amount = float(str((request.get_json(silent=True) or {}).get("amount") or "0").replace(",", "").strip())
    except ValueError:
        return jsonify(ok=False, error="المبلغ غير صالح"), 400
    if amount <= 0:
        return jsonify(ok=False, error="أدخل مبلغًا أكبر من صفر"), 400
    now = datetime.now().isoformat(timespec="seconds")
    new_paid = float(inv["paid_amount"] or 0) + amount
    status = "Paid" if new_paid >= float(inv["total_amount"] or 0) else "Partial"
    db.execute("INSERT INTO payments (invoice_id, amount, method, user_id, paid_at) VALUES (?, ?, 'Cash', ?, ?)",
               (inv["id"], amount, session.get("user_id"), now))
    db.execute("UPDATE invoices SET paid_amount=?, status=? WHERE id=?", (new_paid, status, inv["id"]))
    db.commit()
    log_action("Payment", "invoice", inv["id"], "amount=%s (patient-card)" % amount)
    return jsonify(ok=True, **_pc_state(db, visit_id))


@app.after_request
def _pc_inject_search_popup(resp):
    """يحقن سكربت بحث البطاقة بكل صفحات البرنامج (اللي ترث base.html): مربع البحث العلوي يعرض مرضى فورًا ويفتح البطاقة."""
    try:
        if resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough:
            return resp
        data = resp.get_data()
        if b"lis-sidebar-hidden" not in data or b'id="lis-pc-js"' in data or b"</body>" not in data:
            return resp
        head, _, tail = data.rpartition(b"</body>")
        resp.set_data(head + _V81_PC_JS.encode("utf-8") + b"</body>" + tail)
    except Exception:
        pass
    return resp

'''.replace("__JS__", "__JSVAR__")

EDITS = [
 ("pc_visit_cols",
  'SELECT v.*, p.full_name, p.gender, p.age, p.age_unit, p.phone, p.title, p.email, d.full_name AS doctor_name, rc.name AS center_name ',
  'SELECT v.*, p.full_name, p.gender, p.age, p.age_unit, p.phone, p.title, p.email, p.address, p.national_id, p.passport_number, '
  'p.travel_certificate_number, p.lab_card_number, d.full_name AS doctor_name, rc.name AS center_name '),
 ("pc_tests_cols",
  '"SELECT ot.id, ot.status, COALESCE(ot.price,0) AS price, COALESCE(ot.forwarded_lab_name,\'\') AS fwd_lab, "',
  '"SELECT ot.id, ot.test_definition_id, ot.status, COALESCE(ot.price,0) AS price, COALESCE(ot.forwarded_lab_name,\'\') AS fwd_lab, "'),
 ("pc_render_ctx",
  'tube_groups=tube_groups, fwd_ids=fwd_ids, catalog=catalog, exam_doctors=exam, ref_doctors=refd, fwd_labs=fwd_labs)',
  'tube_groups=tube_groups, fwd_ids=fwd_ids, catalog=catalog, exam_doctors=exam, ref_doctors=refd, fwd_labs=fwd_labs,\n'
  '                           pc_prices=_pc_partner_prices(db))'),
 ("esr_after_data_table",
  '    pos = html.rfind("PLT")\n    if pos < 0:\n        pos = html.rfind("HGB")\n    end = html.find("</table>", pos) if pos >= 0 else -1\n',
  '    pos = html.find(\'class="data-table"\')   # v81: جدول CBC الحقيقي (قالب cbc.html)\n'
  '    if pos < 0:\n        pos = html.rfind("PLT")\n    if pos < 0:\n        pos = html.rfind("HGB")\n'
  '    end = html.find("</table>", pos) if pos >= 0 else -1\n'),
 ("new_code",
  '@app.after_request\ndef _pc_inject_search_buttons(resp):',
  NEW_CODE + '\n@app.after_request\ndef _pc_inject_search_buttons(resp):'),
]


def main():
    s = open(P, encoding="utf-8").read()
    if "_V81_PC_JS" in s:
        sys.exit("Already patched - nothing to do.")
    if "_v80_is_esr" not in s:
        sys.exit("STOPPED: needs v80 app.py first. Nothing changed.")
    for n, a, _ in EDITS:
        c = s.count(a)
        if c != 1:
            sys.exit("STOPPED: anchor '%s' found %d times (expected 1). app.py differs from v80 - nothing changed." % (n, c))
    new = s
    for n, a, b in EDITS:
        new = new.replace(a, b)
    # السكربت JS يُحقن كنص Python آمن
    new = new.replace('__JSVAR__', repr(JS), 1)
    fd, tmp = tempfile.mkstemp(suffix=".py"); os.close(fd)
    open(tmp, "w", encoding="utf-8", newline="").write(new)
    try:
        py_compile.compile(tmp, doraise=True)
    except py_compile.PyCompileError as e:
        os.remove(tmp); sys.exit("STOPPED: syntax error, nothing changed: %s" % e)
    os.remove(tmp)
    shutil.copy2(P, P + ".bak_v81")
    open(P, "w", encoding="utf-8", newline="").write(new)
    print("OK: app.py patched (backup app.py.bak_v81). Copy templates\\patient_card.html too, then restart the program.")


if __name__ == "__main__":
    main()
