# -*- coding: utf-8 -*-
"""
lis_cloud_bridge.py - يجلب مرضى «سجل المرضى» الذين لم ينزلوا للـLIS بعد (/api/lis/incoming) لتظهر بإحصائيات الـLIS
مع مرضى الـLIS. يعتمد على ledger_sync.py (نفس الرابط ledger_url والمفتاح ledger_key). مرضى الـLIS المرفوعين للسجل لا يتكررون.
تشخيص:  /stats-plus/cloud-test
"""
import time

_CACHE = {"t": 0, "v": None}
_STATE = {"err": "", "n": 0}


def make(get_db, get_setting):
    def cloud_logs(f, t):
        if _CACHE["v"] is None or time.time() - _CACHE["t"] > 60:
            try:
                import ledger_sync as ls
                db = get_db()
                c = ls.cfg(db)
                if not (c["url"].startswith("https://") and c["key"]):
                    raise RuntimeError("ledger_url/ledger_key غير مضبوطين")
                code, j = ls._request(c["url"] + "/api/lis/incoming?days=400", c["key"], None, 25)
                if code != 200 or not j.get("ok"):
                    raise RuntimeError("HTTP %s" % code)
                days = {}
                for it in j.get("items", []):
                    days.setdefault(str(it.get("date") or ""), []).append(it)
                _CACHE.update(t=time.time(), v=[{"date": d, "rows": r} for d, r in days.items()])
                _STATE.update(err="", n=len(j.get("items", [])))
            except Exception as e:
                _STATE["err"] = str(e)
                if _CACHE["v"] is None:
                    return []
        return [x for x in _CACHE["v"] if f <= x["date"] <= t]
    cloud_logs.state = _STATE
    return cloud_logs
