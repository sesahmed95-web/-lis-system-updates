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
from datetime import datetime

from database import get_db, get_setting, set_setting

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


def process_astm_message(records):
    """records: list of ASTM record strings (already split on CR), e.g.
    ['H|\\^&|...', 'P|1||009||SALIH ABASS...', 'O|1|009||...', 'R|1|^^^WBC|7.87|10*3/uL|...', 'L|1|N']"""
    db = get_db()
    specimen_id = None
    matched = []
    unmatched = []

    for rec in records:
        if not rec:
            continue
        fields = rec.split("|")
        rec_type = fields[0][:1].upper() if fields[0] else ""

        if rec_type == "O" and len(fields) > 2 and fields[2].strip():
            specimen_id = fields[2].strip()
        elif rec_type == "P" and not specimen_id and len(fields) > 3 and fields[3].strip():
            # fallback: some analyzers only send the ID in the Patient record
            specimen_id = fields[3].strip()

        elif rec_type == "R" and len(fields) > 4:
            test_field = fields[2]
            value_field = fields[3].strip()
            units_field = fields[4].strip() if len(fields) > 4 else ""
            candidates = _normalize_test_code_candidates(test_field)

            mapcode = None
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
                unmatched.append(f"{test_field}={value_field}")
                continue

            if not specimen_id:
                unmatched.append(f"{test_field}={value_field} (no specimen id yet)")
                continue

            order_test = db.execute(
                "SELECT * FROM order_tests WHERE barcode=? AND test_definition_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (specimen_id, mapcode["test_definition_id"]),
            ).fetchone()
            if not order_test:
                # fallback: barcode may have been typed without the test suffix
                order_test = db.execute(
                    "SELECT * FROM order_tests WHERE barcode LIKE ? AND test_definition_id=? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (specimen_id + "%", mapcode["test_definition_id"]),
                ).fetchone()
            if not order_test:
                unmatched.append(f"{test_field}={value_field} (specimen '{specimen_id}' not found/not ordered)")
                continue

            rng = db.execute(
                "SELECT * FROM reference_ranges WHERE test_parameter_id=? LIMIT 1",
                (mapcode["test_parameter_id"],),
            ).fetchone()
            flag = "Normal"
            value_numeric = None
            value_text = None
            if mapcode["result_type"] == "Numeric":
                try:
                    value_numeric = float(value_field)
                    if rng and rng["low"] is not None and value_numeric < rng["low"]:
                        flag = "Low"
                    elif rng and rng["high"] is not None and value_numeric > rng["high"]:
                        flag = "High"
                        if rng["high"] and value_numeric > rng["high"] * 2:
                            flag = "Critical"
                except ValueError:
                    value_text = value_field
            else:
                value_text = value_field

            now = datetime.now().isoformat(timespec="seconds")
            existing = db.execute(
                "SELECT id FROM results WHERE order_test_id=? AND test_parameter_id=?",
                (order_test["id"], mapcode["test_parameter_id"]),
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE results SET value_numeric=?, value_text=?, flag=?, entered_at=? WHERE id=?",
                    (value_numeric, value_text, flag, now, existing["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO results (order_test_id, test_parameter_id, value_numeric, value_text, flag, entered_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (order_test["id"], mapcode["test_parameter_id"], value_numeric, value_text, flag, now),
                )
            db.execute("UPDATE order_tests SET status='Completed' WHERE id=? AND status NOT IN ('Rejected')",
                       (order_test["id"],))
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
