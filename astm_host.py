"""
astm_host.py
============
Host Interface (Server) that receives results from lab analyzers using the
ASTM E1381 / E1394 low-level protocol over TCP/IP (the protocol used by
Beckman Coulter analyzers such as the DxH 520, and by most CBC/Chemistry
analyzers that support "LIS connectivity").

This module runs a small background TCP server that:
 1. Speaks the ASTM low-level handshake (ENQ/ACK/NAK, STX...ETX/ETB frames,
    checksum, EOT) so the analyzer's "Host Transmission Error" stops.
 2. Parses the ASTM records it receives (H, P, O, R, L).
 3. Matches each result's test code against the `mapcodes` table
    (Master Definitions -> Mapcodes, "Machine Code" column) to find the
    matching internal test_parameter.
 4. Matches the Specimen ID sent by the analyzer against the barcode that
    was printed for that sample (Samples Accession / Print Barcode) to find
    the correct order_test row.
 5. Inserts/updates the `results` table exactly like manual result entry,
    including computing Low/High/Critical flags from `reference_ranges`.
 6. Logs every raw message into `host_interface_log` (visible on the
    Master Definitions -> Host Interface page) so failures can be diagnosed.

Every incoming message is logged even if nothing could be matched, so a
supervisor can see exactly what the analyzer sent and adjust the Mapcodes
table or the analyzer's Specimen ID entry accordingly.
"""

import socket
import threading
import time
from datetime import datetime, timedelta

from database import get_db, get_setting, set_setting, find_reference_range

ENQ = 0x05
ACK = 0x06
NAK = 0x15
STX = 0x02
ETX = 0x03
ETB = 0x17
EOT = 0x04
CR = 0x0D
LF = 0x0A

_server_thread = None
_server_socket = None
_stop_flag = threading.Event()


def _checksum(data: bytes) -> str:
    total = sum(data) % 256
    return f"{total:02X}"


def log_message(direction, raw_message, status, parsed_summary=""):
    try:
        db = get_db()
        db.execute(
            "INSERT INTO host_interface_log (direction, raw_message, parsed_summary, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (direction, raw_message, parsed_summary, status, datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def _split_frame(frame_bytes: bytes):
    """Extract the record text out of one ASTM frame: STX seq TEXT (ETX|ETB) CS1 CS2 CR LF"""
    if not frame_bytes or frame_bytes[0] != STX:
        return None
    try:
        end_idx = frame_bytes.index(ETX)
        is_final = True
    except ValueError:
        end_idx = frame_bytes.index(ETB)
        is_final = False
    text = frame_bytes[2:end_idx]  # skip STX + sequence number
    checksum_expected = frame_bytes[end_idx + 1:end_idx + 3].decode(errors="ignore")
    checksum_actual = _checksum(frame_bytes[1:end_idx + 1])
    ok = checksum_expected.upper() == checksum_actual.upper()
    return text.decode(errors="ignore"), is_final, ok


def _normalize_test_code_candidates(field: str):
    """An ASTM Universal Test ID field usually looks like '^^^WBC' or '^^^WBC^1'.
    Returns a list of candidate strings to compare against Mapcodes.machine_code."""
    candidates = [field.strip()]
    parts = [p for p in field.split("^") if p.strip()]
    if parts:
        candidates.append(parts[-1].strip())
        candidates.append(parts[0].strip())
    return [c for c in candidates if c]



# ----------------------------------------------------------------------------
# مطابقة العينة + المريض + الأعلام (تحسينات هذي النسخة)
# ----------------------------------------------------------------------------
def _clean_id(value):
    return (value or "").strip().strip("*").strip()


def _find_specimen_order_tests(db, specimen_id):
    """كل صفوف order_tests العائدة لهذا الـSpecimen ID. الترتيب:
    1) tube_barcode = الباركود المطبوع للأنبوب (مثل 19004T1) — هذا اللي
       يقرأه الجهاز فعليًا من الأنبوب. 2) barcode الفردي للتحليل.
    3) رقم التسجيل للزيارة (لو أدخلوا الرقم يدويًا بالجهاز).
    4) بادئة (LIKE) كاحتياط أخير — نفس سلوك النسخة القديمة."""
    sid = _clean_id(specimen_id)
    if not sid:
        return []
    base = ("SELECT ot.* FROM order_tests ot JOIN orders o ON o.id = ot.order_id ")
    tail = " ORDER BY ot.created_at DESC, ot.id DESC"
    attempts = (
        ("WHERE ot.tube_barcode=?", (sid,)),
        ("WHERE ot.barcode=?", (sid,)),
        ("WHERE EXISTS (SELECT 1 FROM visits v WHERE v.id=o.visit_id "
         "AND CAST(v.registration_number AS TEXT)=?)", (sid,)),
        ("WHERE ot.tube_barcode LIKE ? OR ot.barcode LIKE ?", (sid + "%", sid + "%")),
    )
    for where, params in attempts:
        rows = db.execute(base + where + tail, params).fetchall()
        if rows:
            return rows
    return []


def _patient_for_order_test(db, order_test_id):
    return db.execute(
        "SELECT p.id AS pid, p.full_name, p.gender, p.age, p.age_unit, p.birth_date "
        "FROM order_tests ot JOIN orders o ON o.id = ot.order_id "
        "JOIN visits v ON v.id = o.visit_id JOIN patients p ON p.id = v.patient_id "
        "WHERE ot.id=?", (order_test_id,)
    ).fetchone()


def _dob_for_astm(pat):
    """تاريخ الميلاد بصيغة ASTM (YYYYMMDD) لحقل P.8 — الجهاز يحسب منه العمر ويختار
    المدى الطبيعي. لو التاريخ مسجّل نستخدمه، وإلا نشتقه من العمر ووحدته (تقريبي:
    للسنوات يُستخدم 1 يناير حتى يطلع العمر نفسه المكتوب بالزيارة)."""
    if not pat:
        return ""
    try:
        bd = pat["birth_date"] or ""
    except (KeyError, IndexError):
        bd = ""
    digits = "".join(ch for ch in str(bd) if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    try:
        age = int(float(pat["age"]))
    except (TypeError, ValueError, KeyError):
        return ""
    unit = (pat["age_unit"] or "Years").strip().lower()
    today = datetime.now().date()
    try:
        if unit.startswith("y"):
            return f"{today.year - age:04d}0101"
        if unit.startswith("m"):
            total = today.year * 12 + (today.month - 1) - age
            return f"{total // 12:04d}{total % 12 + 1:02d}{min(today.day, 28):02d}"
        if unit.startswith("w"):
            return (today - timedelta(weeks=age)).strftime("%Y%m%d")
        if unit.startswith("d"):
            return (today - timedelta(days=age)).strftime("%Y%m%d")
    except (ValueError, OverflowError):
        return ""
    return ""


def _flag_for(db, param_id, value_numeric, pat, analyzer):
    """نفس منطق شاشة إدخال النتائج: مرجع حسب جنس/عمر المريض (find_reference_range)
    بدل أول صف مرجعي (كان LIMIT 1 بالنسخة القديمة)."""
    try:
        rng = find_reference_range(
            db, param_id, pat["gender"] if pat else None, pat["age"] if pat else None,
            pat["age_unit"] if pat else None, patient_id=pat["pid"] if pat else None,
            analyzer=analyzer)
    except Exception:
        rng = db.execute("SELECT * FROM reference_ranges WHERE test_parameter_id=? LIMIT 1",
                         (param_id,)).fetchone()
    flag = "Normal"
    if rng and rng["low"] is not None and value_numeric < rng["low"]:
        flag = "Low"
    elif rng and rng["high"] is not None and value_numeric > rng["high"]:
        flag = "High"
        if rng["high"] and value_numeric > rng["high"] * 2:
            flag = "Critical"
    return flag


def _auto_match_param_by_name(db, specimen_tests, code_candidates):
    """احتياط لو ما فيه mapcode للرمز: نطابق رمز الجهاز مع اسم الـparameter
    (تطابق تام، بدون حساسية لحالة الأحرف) داخل التحاليل المطلوبة لهذي العينة
    فقط — فما يخلط مع تحاليل ثانية."""
    for ot in specimen_tests:
        for code in code_candidates:
            row = db.execute(
                "SELECT id AS test_parameter_id, result_type, test_definition_id "
                "FROM test_parameters WHERE test_definition_id=? AND lower(name)=lower(?) LIMIT 1",
                (ot["test_definition_id"], code),
            ).fetchone()
            if row:
                return row
    return None


def _ascii_clean(text):
    out = "".join(ch if ord(ch) < 128 else "" for ch in (text or ""))
    for bad in ("|", "^", "\\", "&", "\r", "\n"):
        out = out.replace(bad, " ")
    return " ".join(out.split())


def build_query_response(db, specimen_id):
    """رد الـLIS على استعلام الجهاز (Q record) بعد قراءة الباركود: معلومات
    المريض + التحاليل المطلوبة. لو العينة غير موجودة يُرد بـ"لا معلومات" (X)."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    header = "H|\\^&|||LIS||||||||P|1|" + ts
    sid = _clean_id(specimen_id)
    rows = _find_specimen_order_tests(db, sid)
    if not rows:
        return [header, f"Q|1|^{sid}||||||||||X", "L|1|N"]

    pat = _patient_for_order_test(db, rows[0]["id"])
    name = _ascii_clean(pat["full_name"]) if pat else ""
    parts = name.split()
    name_field = (f"{parts[-1]}^{' '.join(parts[:-1])}" if len(parts) > 1 else name)
    sex = {"male": "M", "female": "F"}.get(((pat["gender"] if pat else "") or "").strip().lower(), "U")
    pid = str(pat["pid"]) if pat else ""

    def_ids = sorted({r["test_definition_id"] for r in rows})
    codes = []
    if def_ids:
        marks = ",".join("?" * len(def_ids))
        for m in db.execute(
            "SELECT DISTINCT m.machine_code FROM mapcodes m "
            "JOIN test_parameters tp ON tp.id = m.test_parameter_id "
            f"WHERE m.send_enabled=1 AND tp.test_definition_id IN ({marks}) "
            "AND m.machine_code IS NOT NULL AND m.machine_code<>'' ORDER BY m.id", def_ids):
            if m["machine_code"] not in codes:
                codes.append(m["machine_code"])
    tests = "\\".join(f"^^^{c}" for c in codes)

    o = [""] * 26
    o[0], o[1], o[2], o[4], o[5], o[11], o[25] = "O", "1", sid, tests, "R", "A", "Q"
    # P.8 = تاريخ الميلاد (YYYYMMDD) حتى الجهاز يحسب العمر ويطبّق المدى الطبيعي المناسب
    p = f"P|1||{pid}||{name_field}||{_dob_for_astm(pat)}|{sex}"
    return [header, p, "|".join(o), "L|1|N"]


def _extract_query_ids(records):
    ids = []
    for rec in records:
        if rec[:1].upper() == "Q":
            raw = rec.split("|")[2] if len(rec.split("|")) > 2 else ""
            parts = [p.strip() for p in raw.split("^") if p.strip()]
            if parts:
                ids.append(parts[-1])
    return ids


def _read_ack(conn, timeout=5.0):
    conn.settimeout(timeout)
    try:
        while True:
            b = conn.recv(1)
            if not b:
                return None
            if b[0] in (ACK, NAK):
                return b[0]
    except socket.timeout:
        return None
    finally:
        conn.settimeout(30)


def _send_astm_message(conn, records):
    """يرسل رسالة ASTM كاملة للجهاز على نفس الاتصال: ENQ -> ACK، ثم إطارات
    (STX seq نص ETX/ETB checksum CR LF) كل إطار ينتظر ACK، ثم EOT."""
    conn.sendall(bytes([ENQ]))
    if _read_ack(conn) != ACK:
        return False
    text = ("\r".join(records) + "\r").encode("ascii", errors="replace")
    chunks = [text[i:i + 240] for i in range(0, len(text), 240)] or [b""]
    for i, chunk in enumerate(chunks):
        seq = str((i + 1) % 8).encode()
        term = bytes([ETX]) if i == len(chunks) - 1 else bytes([ETB])
        body = seq + chunk + term
        frame = bytes([STX]) + body + _checksum(body).encode() + b"\r\n"
        for _attempt in range(3):
            conn.sendall(frame)
            ack = _read_ack(conn)
            if ack == ACK:
                break
        else:
            conn.sendall(bytes([EOT]))
            return False
    conn.sendall(bytes([EOT]))
    return True


def process_astm_message(records):
    """records: list of ASTM record strings (already split on CR), e.g.
    ['H|\\^&|...', 'P|1||009||SALIH ABASS...', 'O|1|009||...', 'R|1|^^^WBC|7.87|10*3/uL|...', 'L|1|N']"""
    db = get_db()
    specimen_id = None
    specimen_tests = None      # order_tests العائدة لهذي العينة (تُحمَّل مرة وحدة)
    matched = []
    unmatched = []
    auto_send = get_setting(db, "host_auto_send_to_reception", "0") == "1"

    for rec in records:
        if not rec:
            continue
        fields = rec.split("|")
        rec_type = fields[0][:1].upper() if fields[0] else ""

        if rec_type == "O" and len(fields) > 2 and fields[2].strip():
            specimen_id = _clean_id(fields[2])
            specimen_tests = None
        elif rec_type == "P" and not specimen_id and len(fields) > 3 and fields[3].strip():
            # fallback: some analyzers only send the ID in the Patient record
            specimen_id = _clean_id(fields[3])
            specimen_tests = None

        elif rec_type == "R" and len(fields) > 4:
            test_field = fields[2]
            value_field = fields[3].strip()
            units_field = fields[4].strip() if len(fields) > 4 else ""
            candidates = _normalize_test_code_candidates(test_field)

            if not specimen_id:
                unmatched.append(f"{test_field}={value_field} (no specimen id yet)")
                continue
            if specimen_tests is None:
                specimen_tests = _find_specimen_order_tests(db, specimen_id)

            mapcode = None
            for code in candidates:
                mapcode = db.execute(
                    "SELECT m.*, tp.id as test_parameter_id, tp.result_type, tp.test_definition_id "
                    "FROM mapcodes m JOIN test_parameters tp ON tp.id = m.test_parameter_id "
                    "WHERE m.receive_enabled=1 AND m.machine_code=? COLLATE NOCASE "
                    "AND tp.test_definition_id IN (SELECT test_definition_id FROM order_tests WHERE id IN ({ids})) "
                    "LIMIT 1".format(ids=",".join(str(int(t["id"])) for t in specimen_tests) or "0"),
                    (code,),
                ).fetchone()
                if mapcode:
                    break
            if not mapcode:
                # الأولوية لرمز مطابق ضمن تحاليل هذي العينة؛ لو ما وُجد نجرب أي mapcode عام
                for code in candidates:
                    mapcode = db.execute(
                        "SELECT m.*, tp.id as test_parameter_id, tp.result_type, tp.test_definition_id "
                        "FROM mapcodes m JOIN test_parameters tp ON tp.id = m.test_parameter_id "
                        "WHERE m.receive_enabled=1 AND m.machine_code=? COLLATE NOCASE LIMIT 1",
                        (code,),
                    ).fetchone()
                    if mapcode:
                        break
            if not mapcode:
                mapcode = _auto_match_param_by_name(db, specimen_tests, candidates)
            if not mapcode:
                unmatched.append(f"{test_field}={value_field}")
                continue

            order_test = next(
                (t for t in specimen_tests if t["test_definition_id"] == mapcode["test_definition_id"]), None)
            if not order_test:
                unmatched.append(f"{test_field}={value_field} (specimen '{specimen_id}' not found/not ordered)")
                continue

            pat = _patient_for_order_test(db, order_test["id"])
            analyzer = order_test["analyzer"] if "analyzer" in order_test.keys() else None
            param_id = mapcode["test_parameter_id"]
            flag = "Normal"
            value_numeric = None
            value_text = None
            if mapcode["result_type"] == "Numeric":
                try:
                    value_numeric = float(value_field)
                    flag = _flag_for(db, param_id, value_numeric, pat, analyzer)
                except ValueError:
                    value_text = value_field
            else:
                value_text = value_field

            now = datetime.now().isoformat(timespec="seconds")
            existing = db.execute(
                "SELECT id, value_numeric, value_text, flag FROM results "
                "WHERE order_test_id=? AND test_parameter_id=?",
                (order_test["id"], param_id),
            ).fetchone()
            if existing:
                if existing["value_numeric"] != value_numeric or existing["value_text"] != value_text:
                    try:
                        db.execute(
                            "INSERT INTO result_history (result_id, order_test_id, test_parameter_id, "
                            "prev_value_numeric, prev_value_text, prev_flag, changed_by, changed_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (existing["id"], order_test["id"], param_id, existing["value_numeric"],
                             existing["value_text"], existing["flag"], None, now),
                        )
                    except Exception:
                        pass
                db.execute(
                    "UPDATE results SET value_numeric=?, value_text=?, flag=?, entered_at=? WHERE id=?",
                    (value_numeric, value_text, flag, now, existing["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, entered_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (order_test["id"], param_id, value_numeric, value_text, flag, now),
                )
            db.execute("UPDATE order_tests SET status='Completed' WHERE id=? AND status NOT IN ('Rejected')",
                       (order_test["id"],))
            if auto_send:
                db.execute(
                    "UPDATE order_tests SET sent_to_reception=1, sent_to_reception_at=?, reception_seen=0 "
                    "WHERE id=? AND sent_to_reception=0", (now, order_test["id"]))
            matched.append(f"{test_field}={value_field}{(' ' + units_field) if units_field else ''}")

    db.commit()
    db.close()
    summary = f"Specimen {specimen_id or '?'}: matched={len(matched)} unmatched={len(unmatched)}"
    if unmatched:
        summary += " | Unmatched: " + "; ".join(unmatched)
    status = "Processed" if matched else ("Unmatched" if unmatched else "Empty")
    return summary, status


def _handle_connection(conn, addr):
    conn.settimeout(30)
    buffer = b""
    frames_text = []
    got_enq = False
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data

            while buffer:
                b0 = buffer[0]
                if b0 == ENQ:
                    got_enq = True
                    conn.sendall(bytes([ACK]))
                    buffer = buffer[1:]
                elif b0 == STX:
                    if ETX in buffer or ETB in buffer:
                        # a full frame needs the terminator plus 2 checksum chars + CR LF
                        idx_etx = buffer.index(ETX) if ETX in buffer else None
                        idx_etb = buffer.index(ETB) if ETB in buffer else None
                        candidates_idx = [i for i in (idx_etx, idx_etb) if i is not None]
                        if not candidates_idx:
                            break
                        end_idx = min(candidates_idx)
                        frame_end = end_idx + 3  # + 2 checksum chars
                        if len(buffer) < frame_end + 2:  # + CR LF
                            break
                        frame = buffer[:frame_end + 2]
                        buffer = buffer[frame_end + 2:]
                        parsed = _split_frame(frame)
                        if parsed is None:
                            conn.sendall(bytes([NAK]))
                            continue
                        text, is_final, ok = parsed
                        if ok:
                            frames_text.append(text)
                            conn.sendall(bytes([ACK]))
                        else:
                            conn.sendall(bytes([NAK]))
                    else:
                        break
                elif b0 == EOT:
                    buffer = buffer[1:]
                    if frames_text:
                        full_text = "".join(frames_text)
                        raw_log = full_text.replace("\r", " | ")
                        records = full_text.split("\r")
                        query_ids = _extract_query_ids(records)
                        if query_ids:
                            # الجهاز يسأل عن معلومات عينة (بعد قراءة الباركود) —
                            # نرد على نفس الاتصال بمعلومات المريض والتحاليل.
                            log_message("IN", raw_log, "Query", "Host query: " + ", ".join(query_ids))
                            try:
                                qdb = get_db()
                                for qid in query_ids:
                                    reply = build_query_response(qdb, qid)
                                    sent = _send_astm_message(conn, reply)
                                    log_message("OUT", " | ".join(reply), "Sent" if sent else "Error",
                                                f"Reply to query {qid}" + ("" if sent else " (no ACK from analyzer)"))
                                qdb.close()
                            except Exception as e:
                                log_message("OUT", "", "Error", f"Query reply failed: {e}")
                        else:
                            try:
                                summary, status = process_astm_message(records)
                            except Exception as e:
                                summary, status = f"Error while processing: {e}", "Error"
                            log_message("IN", raw_log, status, summary)
                        frames_text = []
                    got_enq = False
                else:
                    # unexpected byte, drop it
                    buffer = buffer[1:]
    except socket.timeout:
        pass
    except (ConnectionResetError, OSError):
        pass
    finally:
        conn.close()


def _serve_forever(host, port):
    global _server_socket
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        _server_socket.bind((host, port))
        _server_socket.listen(5)
        _server_socket.settimeout(1.0)
        log_message("SYSTEM", "", "Started", f"Host Interface listening on {host}:{port}")
    except Exception as e:
        log_message("SYSTEM", "", "Error", f"Could not start listener on {host}:{port} - {e}")
        return

    while not _stop_flag.is_set():
        try:
            conn, addr = _server_socket.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_handle_connection, args=(conn, addr), daemon=True).start()

    try:
        _server_socket.close()
    except OSError:
        pass


def start_listener_if_enabled():
    """Call once at application startup. Reads settings and starts the
    background listener thread if the supervisor has enabled it."""
    global _server_thread
    db = get_db()
    enabled = get_setting(db, "host_listener_enabled", "0") == "1"
    host = get_setting(db, "host_listener_ip", "0.0.0.0")
    port = int(get_setting(db, "host_listener_port", "5000") or 5000)
    db.close()
    if not enabled:
        return
    if _server_thread and _server_thread.is_alive():
        return
    _stop_flag.clear()
    _server_thread = threading.Thread(target=_serve_forever, args=(host, port), daemon=True)
    _server_thread.start()


def stop_listener():
    _stop_flag.set()
    if _server_socket:
        try:
            _server_socket.close()
        except OSError:
            pass
