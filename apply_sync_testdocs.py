# -*- coding: utf-8 -*-
"""
apply_sync_testdocs.py  (sync_testdocs_v1)
يربط «الطبيب الفاحص لكل تحليل» + الصرفيات العامة + تسويات الأطباء بين الـLIS وسجل المرضى:
  ledger_sync.py : يرسل testDocs مع كل زيارة، ويطبّق تعديل الطبيب لكل تحليل القادم من السجل، ويرفع lab_expenses للسحابة،
                   ويجلب التسويات والصرفيات (fetch_accounts)
  lis_stats_plus.py : «حسابات الأطباء» تضيف تسويات السجل، و«الصرفيات» تضيف صرفيات السجل غير المرفوعة من الـLIS
شرط مسبق: طبّقت per-test doctor (زيب lis_per_test_doctor_v2) ونشرت worker.js الجديد.
التشغيل من مجلد البرنامج (فيه ledger_sync.py):   py apply_sync_testdocs.py      (نسخ: *.bak_synctd ، تشغيله مرتين لا يضر)
"""
import io, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "sync_testdocs_v1"


def rd(p):
    with io.open(p, encoding="utf-8", newline="") as f:
        return f.read()


def wr(p, s):
    shutil.copy2(p, p + ".bak_synctd")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def once(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit("توقفت: موضع «%s» وجدته %d مرة (المطلوب 1). لم يُكتب شيء بهذا الملف. أرسل لي الملف." % (what, n))
    return s.replace(old, new, 1)


HELPERS = '''# ===================== sync_testdocs_v1 =====================
def _clean_td(x):
    return re.sub(r"[=|]+", " ", str(x or "")).strip()


def _testdocs_str(db, vid):
    """«BF=د.خليل|BMA=د.هدى»: التحاليل التي لها طبيب فاحص خاص (order_tests.examining_doctor). فاضي = الكل عند طبيب الزيارة."""
    try:
        rows = db.execute(
            "SELECT td.name AS n, ot.examining_doctor AS d FROM orders o JOIN order_tests ot ON ot.order_id=o.id "
            "JOIN test_definitions td ON td.id=ot.test_definition_id WHERE o.visit_id=? AND TRIM(COALESCE(ot.examining_doctor,''))<>'' "
            "AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected') ORDER BY ot.id", (vid,)).fetchall()
    except Exception:
        return ""
    return "|".join("%s=%s" % (_clean_td(r["n"]), _clean_td(r["d"])) for r in rows)


def _parse_testdocs(txt):
    out = []
    for seg in str(txt or "").split("|"):
        if "=" in seg:
            t, d = seg.split("=", 1)
            if t.strip() and d.strip():
                out.append((t.strip(), d.strip()))
    return out


def _canon_testdocs(idx, txt):
    """يوحّد الأسماء (BF = Blood Film...) إلى «رقم التحليل=الطبيب» مرتبة، ليُقارن السجل بالـLIS بدون اختلاف تسمية."""
    m = {}
    for t, d in _parse_testdocs(txt):
        tid = _match_test(idx, t)
        m[str(tid) if tid else "n:" + _nt(t)] = d
    return "|".join("%s=%s" % (k, m[k]) for k in sorted(m))


def _apply_testdocs(db, vid, canon):
    """يطبّق «tid=الطبيب|...» القادم من السجل على تحاليل الزيارة (ما ليس بالقائمة يرجع لطبيب الزيارة)."""
    want = {}
    for k, d in _parse_testdocs(canon):
        if k.isdigit():
            want[int(k)] = d
    try:
        for r in db.execute("SELECT ot.id, ot.test_definition_id tid FROM order_tests ot JOIN orders o ON o.id=ot.order_id "
                            "WHERE o.visit_id=? AND COALESCE(ot.status,'') NOT IN ('Cancelled','Canceled','Rejected')", (vid,)).fetchall():
            db.execute("UPDATE order_tests SET examining_doctor=? WHERE id=?", (want.get(r["tid"]) or None, r["id"]))
    except Exception:
        pass


def _recompute_fee(db, vid):
    try:
        import database
        database.recompute_examining_doctor_fee(db, vid)
    except Exception:
        pass


_ACC = {"t": 0.0, "v": None}


def fetch_accounts(db, ttl=60):
    """التسويات (docAdj) والصرفيات العامة (genExp) والأسعار من السحابة (settings/app). None عند الفشل."""
    if _ACC["v"] is not None and time.time() - _ACC["t"] < ttl:
        return _ACC["v"]
    c = cfg(db)
    if not (c["url"].startswith("https://") and c["key"]):
        return None
    try:
        code, j = _request(c["url"] + "/api/lis/accounts", c["key"], None, 25)
        if code == 200 and j.get("ok"):
            _ACC.update(t=time.time(), v=j)
            return j
    except Exception:
        pass
    return _ACC["v"]


def push_accounts(db, c):
    """lab_expenses (الصرفيات العامة بالـLIS) → السحابة. تُرفع الجديدة/المعدّلة وتُحذف المحذوفة. يرجع عدد العمليات."""
    try:
        cols = {r[1] for r in db.execute("PRAGMA table_info(lab_expenses)").fetchall()}
    except Exception:
        return 0
    if not ({"id", "expense_date", "amount"} <= cols):
        return 0
    kcol = "kind" if "kind" in cols else "''"
    ncol = "note" if "note" in cols else "''"
    since = (date.today() - timedelta(days=400)).isoformat()
    cur = {}
    for r in db.execute("SELECT id, expense_date AS d, amount AS a, %s AS k, %s AS n FROM lab_expenses WHERE expense_date>=? ORDER BY id" % (kcol, ncol), (since,)).fetchall():
        d = str(r["d"] or "")[:10]
        try:
            a = float(r["a"] or 0)
        except (TypeError, ValueError):
            continue
        if a <= 0 or not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", d):
            continue
        cur["lis-e%d" % r["id"]] = [d, a, " — ".join(x for x in ((r["k"] or "").strip(), (r["n"] or "").strip()) if x)]
    try:
        prev = json.loads(_get(db, "ledger_exp_ids", "{}") or "{}")
    except Exception:
        prev = {}
    ops = []
    for k, v in cur.items():
        if prev.get(k) != v:
            if k in prev:
                ops.append({"op": "exp_del", "id": k})
            ops.append({"op": "exp", "id": k, "date": v[0], "amount": v[1], "note": v[2]})
    for k in prev:
        if k not in cur:
            ops.append({"op": "exp_del", "id": k})
    if not ops:
        return 0
    for i in range(0, len(ops), 150):
        code, j = _request(c["url"] + "/api/lis/accounts", c["key"], {"ops": ops[i:i + 150]}, 30)
        if code != 200 or not j.get("ok"):
            return 0
    _set(db, "ledger_exp_ids", json.dumps(cur, ensure_ascii=False))
    db.commit()
    _ACC["v"] = None
    return len(ops)
# ===================== end sync_testdocs_v1 =====================


'''


def patch_sync():
    p = os.path.join(HERE, "ledger_sync.py")
    if not os.path.exists(p):
        sys.exit("ما لقيت ledger_sync.py بهذا المجلد")
    s = rd(p)
    if MARK in s:
        print("ledger_sync.py: موجود مسبقاً"); return
    s = once(s, "def collect_day(db, day):", HELPERS + "def collect_day(db, day):", "collect_day")
    s = once(s, '            "sentTests": _sent_str(db, v["id"]),\n        })',
             '            "sentTests": _sent_str(db, v["id"]),\n            "testDocs": _testdocs_str(db, v["id"]),\n        })', "صف collect_day")
    s = once(s, '"sent": " | ".join(sorted("%s>%s" % (_nt(t), _nt(l)) for t, l in _parse_sent(r.get("sentTests"))))}',
             '"sent": " | ".join(sorted("%s>%s" % (_nt(t), _nt(l)) for t, l in _parse_sent(r.get("sentTests")))),\n'
             '            **({"testDocs": r["testDocsCanon"]} if "testDocsCanon" in r else {})}', "_state")
    s = once(s, '    if (C["labDoctor"], C["expenses"], C["expNote"]) != (L["labDoctor"], L["expenses"], L["expNote"]):',
             '    if "testDocs" in C and "testDocs" in L and C["testDocs"] != L["testDocs"]:\n'
             '        _apply_testdocs(db, vid, C["testDocs"])\n'
             '    if (C["labDoctor"], C["expenses"], C["expNote"]) != (L["labDoctor"], L["expenses"], L["expNote"]):', "تطبيق labDoctor")
    s = once(s, '    n_active = db.execute("SELECT COUNT(*) FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=?',
             '    _recompute_fee(db, vid)      # أجر الفاحصين بعد أي تغيير بطبيب الزيارة أو طبيب التحليل أو التحاليل\n'
             '    n_active = db.execute("SELECT COUNT(*) FROM order_tests ot JOIN orders o ON o.id=ot.order_id WHERE o.visit_id=?', "إعادة حساب الأجر")
    s = once(s, "    days_cache, n = {}, 0\n", "    days_cache, n = {}, 0\n    idx_td = None\n", "days_cache")
    s = once(s, "        Cs, Ls = _state(it), _state(Lrow)\n",
             '        if "testDocs" in it:\n'
             '            if idx_td is None:\n'
             '                idx_td = _test_index(db)\n'
             '            it["testDocsCanon"] = _canon_testdocs(idx_td, it.get("testDocs"))\n'
             '            Lrow["testDocsCanon"] = _canon_testdocs(idx_td, Lrow.get("testDocs"))\n'
             "        Cs, Ls = _state(it), _state(Lrow)\n", "حساب الحالتين")
    s = once(s, '    n = max(1, min(400, int(days or c["back"])))\n',
             '    n = max(1, min(400, int(days or c["back"])))\n'
             '    try:\n        push_accounts(db, c)\n    except Exception:\n        pass\n', "_sync")
    compile(s, p, "exec")
    wr(p, s); print("ledger_sync.py: تم")


def patch_stats():
    p = os.path.join(HERE, "lis_stats_plus.py")
    if not os.path.exists(p):
        print("lis_stats_plus.py غير موجود (تخطيته)"); return
    s = rd(p)
    if MARK in s:
        print("lis_stats_plus.py: موجود مسبقاً"); return
    s = once(s, "    if not ents:\n        return \"<p class='muted'>لا توجد أجور أطباء فاحصين بهذه الفترة.</p>\"\n",
             "    # " + MARK + ": تسويات الأطباء المسجّلة بالسجل (نفس المصدر)\n"
             "    try:\n"
             "        import ledger_sync as _ls\n"
             "        for a in ((_ls.fetch_accounts(db) or {}).get(\"docAdj\") or []):\n"
             "            d, nm = str(a.get(\"date\") or \"\"), str(a.get(\"docName\") or \"\").strip()\n"
             "            if nm and f <= d <= t and float(a.get(\"amount\") or 0):\n"
             "                ents.setdefault(nm, []).append((d, \"—\", \"تسوية: \" + str(a.get(\"note\") or \"\"), float(a[\"amount\"])))\n"
             "    except Exception:\n        pass\n"
             "    for _v in ents.values():\n        _v.sort(key=lambda x: x[0])\n"
             "    if not ents:\n        return \"<p class='muted'>لا توجد أجور أطباء فاحصين بهذه الفترة.</p>\"\n", "فحص ents الفارغ")
    s = once(s, "(_E(nm), len(v), _n(sum(x[3] for x in v)))", "(_E(nm), len([x for x in v if x[1] != \"—\"]), _n(sum(x[3] for x in v)))", "عدد المرضى")
    s = once(s, "    for r in _cloud_rows(ctx, f, t):\n        if r[\"exp\"] > 0:\n",
             "    try:\n"
             "        import ledger_sync as _ls\n"
             "        for a in ((_ls.fetch_accounts(db) or {}).get(\"genExp\") or []):\n"
             "            d = str(a.get(\"date\") or \"\")\n"
             "            if a.get(\"src\") != \"lis\" and f <= d <= t and float(a.get(\"amount\") or 0) > 0:\n"
             "                items.append((d, str(a.get(\"note\") or \"—\"), \"—\", float(a[\"amount\"])))\n"
             "    except Exception:\n        pass\n"
             "    for r in _cloud_rows(ctx, f, t):\n        if r[\"exp\"] > 0:\n", "صرفيات السحابة")
    s = s.replace("def _doc_body(", "# " + MARK + "\ndef _doc_body(", 1)
    compile(s, p, "exec")
    wr(p, s); print("lis_stats_plus.py: تم")


if __name__ == "__main__":
    patch_sync(); patch_stats()
    print("\nانتهى. أعد تشغيل البرنامج.")
