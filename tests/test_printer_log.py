import json

import pytest

from lab.printer.log import LayerLog, StateMerger, flatten, heights_from_gcode, match_marks, summarize
from lab.printer.mqtt import PUSHALL, ReadOnlyPublisher, load_printer_env


def report(**print_fields):
    return {"print": {"command": "push_status", **print_fields}}


# Field names as P1/X1 firmware sends them, plus the H2D/X2D "device" block, so the parser is tested on both shapes.
FULL = report(gcode_state="RUNNING", layer_num=1, total_layer_num=150, mc_percent=1, nozzle_temper=210.0,
              bed_temper=60.0, chamber_temper=27.0, cooling_fan_speed="15", big_fan1_speed="0", big_fan2_speed="0",
              heatbreak_fan_speed="15", hms=[], wifi_signal="-50dBm", sequence_id="1",
              device={"ctc": {"info": {"temp": 27}}, "airduct": {"modeCur": 0, "parts": [{"id": 16, "state": 0}]}})


def test_flatten_keeps_only_tracked_fields_with_dotted_names():
    f = flatten(FULL)
    assert f["layer_num"] == 1
    assert f["big_fan1_speed"] == "0"
    assert f["chamber_temper"] == 27.0
    assert f["device.ctc.info.temp"] == 27
    assert f["device.airduct.parts.0.state"] == 0
    assert "wifi_signal" not in f and "sequence_id" not in f and "command" not in f


def test_partial_reports_merge_into_the_full_state():
    m = StateMerger()
    m.update(FULL)
    m.update(report(big_fan1_speed="10", layer_num=2))
    s = m.state
    assert s["big_fan1_speed"] == "10" and s["layer_num"] == 2
    assert s["nozzle_temper"] == 210.0  # kept from the earlier full report


def test_a_line_per_layer_and_per_change_nothing_otherwise():
    log = LayerLog()
    m = StateMerger()
    out = []
    for t, r in enumerate([FULL,
                           report(nozzle_temper=210.4),              # temperature wobble under 1 °C: no line
                           report(layer_num=2),                      # new layer: a line
                           report(big_fan1_speed="60"),              # fan change within the layer: a line
                           report(chamber_temper=27.6),              # under 1 °C from the last line: no line
                           report(chamber_temper=28.2)]):            # 1.2 °C from the last line: a line
        m.update(r)
        line = log.offer(m.state, t=float(t))
        if line:
            out.append(line)
    assert [o["layer"] for o in out] == [1, 2, 2, 2]
    assert out[2]["changed"] == ["big_fan1_speed"]
    assert out[3]["changed"] == ["chamber_temper"]


def test_summary_lists_fan_and_chamber_events_with_heights():
    lines = [
        {"t": 0.0, "layer": 1, "state": {"big_fan1_speed": "0", "big_fan2_speed": "0", "chamber_temper": 27.0}},
        {"t": 60.0, "layer": 87, "changed": ["big_fan1_speed"],
         "state": {"big_fan1_speed": "60", "big_fan2_speed": "0", "chamber_temper": 31.0}},
        {"t": 90.0, "layer": 88, "state": {"big_fan1_speed": "60", "big_fan2_speed": "0", "chamber_temper": 31.0}},
    ]
    heights = {1: 0.2, 87: 17.4, 88: 17.6}
    ev = summarize(lines, heights)
    assert ev == [{"layer": 87, "z_mm": 17.4, "t": 60.0, "field": "big_fan1_speed", "from": "0", "to": "60"}]


def test_heights_come_from_the_slice_not_from_a_fixed_layer_height():
    gcode = "; CHANGE_LAYER\n; Z_HEIGHT: 0.2\nG1\n; CHANGE_LAYER\n; Z_HEIGHT: 0.4\n; CHANGE_LAYER\n; Z_HEIGHT: 0.56\n"
    assert heights_from_gcode(gcode) == {1: 0.2, 2: 0.4, 3: 0.56}


def test_owner_marks_line_up_with_events_nearby():
    ev = [{"layer": 87, "z_mm": 17.4, "t": 60.0, "field": "big_fan1_speed", "from": "0", "to": "60"}]
    marks = [{"variant": "E-023-A", "mark_z_mm": 17.0, "defect_z_mm": 17.0},
             {"variant": "E-023-A", "mark_z_mm": 40.0, "defect_z_mm": 40.0}]
    m = match_marks(marks, ev, within_mm=0.6)
    assert m[0]["events"] == ev and m[1]["events"] == []


def test_the_publisher_sends_only_the_pushall_request():
    sent = []
    pub = ReadOnlyPublisher(lambda topic, payload: sent.append((topic, payload)), serial="SERIAL1")
    pub.pushall()
    assert sent == [("device/SERIAL1/request", json.dumps(PUSHALL))]
    with pytest.raises(PermissionError):
        pub.send("device/SERIAL1/request", {"print": {"command": "stop"}})


def test_printer_env_is_read_from_a_private_file(tmp_path):
    p = tmp_path / "printer.env"
    p.write_text("PRINTER_HOST=10.0.0.136\nBAMBU_SERIAL=S1\nBAMBU_TOKEN=abc\n")
    p.chmod(0o644)
    with pytest.raises(PermissionError, match="600"):
        load_printer_env(p)
    p.chmod(0o600)
    assert load_printer_env(p) == {"host": "10.0.0.136", "serial": "S1", "code": "abc", "cert_sha256": None}


def test_a_missing_printer_env_says_what_to_create(tmp_path):
    with pytest.raises(FileNotFoundError, match="PRINTER_HOST"):
        load_printer_env(tmp_path / "printer.env")


def test_log_command_writes_lines_and_a_run_summary(tmp_path, monkeypatch):
    from lab.printer import run_log
    from loop_fixtures import make_project, minimal_experiment, minimal_question, started
    e = started(minimal_experiment("E-009"))
    paths = make_project(tmp_path, minimal_question(), [e])
    reports = [FULL, report(layer_num=2), report(big_fan1_speed="60"), report(layer_num=3),
               report(gcode_state="FINISH")]

    def fake_listen(env, on_report, *, should_stop, **_):
        for r in reports:
            on_report(r)
            if should_stop():
                return

    clock = iter(range(0, 10_000, 60))
    monkeypatch.setattr(run_log, "_now", lambda: f"2026-10-25T09:{next(clock) // 60:02d}:00+00:00")
    out = run_log.log_run(paths, "E-009", env={"host": "h", "serial": "S1", "code": "SECRET-CODE-123"}, listen=fake_listen,
                          heights={1: 0.2, 2: 0.4, 3: 0.6})
    run = out["print_runs"][0]
    log = run["printer_log"]
    assert log["final_state"] == "FINISH"
    assert log["events"] == [{"layer": 2, "z_mm": 0.4, "t": "2026-10-25T09:02:00+00:00", "field": "big_fan1_speed",
                              "from": "0", "to": "60"}]
    lines = (paths.root / log["path"]).read_text().splitlines()
    assert len(lines) == 5  # layer 1, layer 2, fan change, layer 3, finish
    assert "SECRET-CODE-123" not in (paths.root / log["path"]).read_text()
    assert "SECRET-CODE-123" not in (paths.experiments / "E-009.json").read_text()
    # A finish heard without a gap gives the printer's minutes (review finding 2); grams stay unknown.
    assert run["usage"] == {"actual_minutes": 4.0, "actual_g": None, "usage_source": "printer_log",
                            "completion_fraction": None}


def test_log_command_refuses_a_run_that_already_has_a_log(tmp_path):
    from lab.printer import run_log
    from loop_fixtures import make_project, minimal_experiment, minimal_question, started
    e = started(minimal_experiment("E-009"))
    e["print_runs"][0]["printer_log"] = {"path": "telemetry/PR-009-01.jsonl"}
    paths = make_project(tmp_path, minimal_question(), [e])
    with pytest.raises(ValueError, match="already has a printer log"):
        run_log.log_run(paths, "E-009", env={}, listen=lambda *a, **k: None, heights={})


def test_the_printer_certificate_must_match_the_pinned_fingerprint():
    from lab.printer.mqtt import check_certificate
    der = b"printer-cert-bytes"
    import hashlib
    fp = hashlib.sha256(der).hexdigest()
    check_certificate({"cert_sha256": fp.upper()}, lambda: der)  # case-insensitive match passes
    with pytest.raises(ConnectionError, match="doesn't match"):
        check_certificate({"cert_sha256": "00" * 32}, lambda: der)
    with pytest.raises(ConnectionError, match=f"BAMBU_CERT_SHA256={fp}"):
        check_certificate({}, lambda: der)  # nothing pinned yet: refuse, and say what to pin


def test_printer_env_reads_the_pinned_fingerprint(tmp_path):
    p = tmp_path / "printer.env"
    p.write_text("PRINTER_HOST=h\nBAMBU_SERIAL=S1\nBAMBU_TOKEN=abc\nBAMBU_CERT_SHA256=AB:CD\n")
    p.chmod(0o600)
    assert load_printer_env(p)["cert_sha256"] == "abcd"


def _self_signed(tmp_path, name):
    import shutil
    import subprocess
    if not shutil.which("openssl"):
        pytest.skip("openssl not installed")
    key, crt = tmp_path / f"{name}.key", tmp_path / f"{name}.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "2", "-subj", f"/CN={name}"], check=True, capture_output=True)
    return key, crt


def _handshake(ctx, crt, key):
    """Run one TLS handshake against a throwaway local server presenting crt; True if the client accepted it."""
    import socket
    import ssl
    import threading
    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.load_cert_chain(crt, key)
    ls = socket.socket()
    ls.bind(("127.0.0.1", 0))
    ls.listen(1)

    def serve():
        conn, _ = ls.accept()
        try:
            with srv_ctx.wrap_socket(conn, server_side=True):
                pass
        except (ssl.SSLError, OSError):
            pass
    th = threading.Thread(target=serve, daemon=True)
    th.start()
    try:
        with socket.create_connection(ls.getsockname(), timeout=5) as raw, ctx.wrap_socket(raw):
            return True
    except ssl.SSLError:
        return False
    finally:
        ls.close()
        th.join(5)


def test_every_handshake_must_present_the_pinned_certificate(tmp_path):
    """The context paho uses trusts only the pinned certificate, so a reconnect to a different device fails too."""
    import ssl
    from lab.printer.mqtt import pinned_context
    key_a, crt_a = _self_signed(tmp_path, "printer")
    key_b, crt_b = _self_signed(tmp_path, "impostor")
    der_a = ssl.PEM_cert_to_DER_cert(crt_a.read_text())
    ctx = pinned_context(der_a)
    assert _handshake(ctx, crt_a, key_a) is True
    assert _handshake(ctx, crt_b, key_b) is False


# ---- review fixes -------------------------------------------------------------------------------------------------

def _project(tmp_path):
    from loop_fixtures import make_project, minimal_experiment, minimal_question, started
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])


def _clock(monkeypatch, step_s=60):
    from lab.printer import run_log
    import datetime
    t0 = datetime.datetime(2026, 10, 25, 9, 0, tzinfo=datetime.timezone.utc)
    n = iter(range(10_000))
    monkeypatch.setattr(run_log, "_now", lambda: (t0 + datetime.timedelta(seconds=step_s * next(n))).isoformat())


def _feed(reports, interrupt_after=None):
    def listen(env, on_report, *, should_stop, **_):
        for i, r in enumerate(reports):
            if interrupt_after is not None and i == interrupt_after:
                raise KeyboardInterrupt
            on_report(r)
            if should_stop():
                return
    return listen


def test_ctrl_c_keeps_what_was_logged(tmp_path, monkeypatch):
    from lab.printer import run_log
    paths = _project(tmp_path)
    _clock(monkeypatch)
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([FULL, report(layer_num=2), report(layer_num=3)],
                                                               interrupt_after=2), heights={})
    log = e["print_runs"][0]["printer_log"]
    assert log["final_state"] == "stopped" and log["ended_at"] is None and log["lines"] == 2
    assert e["print_runs"][0]["usage"] is None


def test_starting_after_the_print_ended_stops_at_once_and_saves_nothing(tmp_path):
    from lab.printer import run_log
    paths = _project(tmp_path)
    over = report(gcode_state="FINISH", layer_num=150, total_layer_num=150)
    with pytest.raises(ValueError, match="already over"):
        run_log.log_run(paths, "E-009", env={}, listen=_feed([over, over]), heights={})
    from lab.loop.commands import load_experiment
    assert "printer_log" not in load_experiment(paths, "E-009")["print_runs"][0]


def test_a_finished_log_records_the_printers_own_minutes(tmp_path, monkeypatch):
    """The log records usage itself, so a `lab pull` that already marked the run finished_unknown is corrected."""
    from lab.printer import run_log
    from lab.loop.commands import load_experiment, save_experiment
    paths = _project(tmp_path)
    e = load_experiment(paths, "E-009")
    e["print_runs"][0]["usage"] = {"actual_minutes": None, "actual_g": None, "usage_source": "finished_unknown",
                                   "completion_fraction": None}
    save_experiment(paths, e)
    _clock(monkeypatch)
    start = report(**{**FULL["print"], "gcode_start_time": "1792918800"})  # 2026-10-25 09:00 UTC, the printer's own start
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([start, report(layer_num=2), report(layer_num=3),
                                                                report(gcode_state="FINISH")]), heights={})
    u = e["print_runs"][0]["usage"]
    assert u["usage_source"] == "printer_log" and u["actual_minutes"] == 3.0 and u["actual_g"] is None
    assert e["print_runs"][0]["printer_log"]["ended_at"] == "2026-10-25T09:03:00+00:00"


def test_a_cancelled_print_is_not_recorded_as_finished(tmp_path, monkeypatch):
    from lab.printer import run_log
    from lab.loop.telemetry import apply_telemetry
    from unittest.mock import patch
    paths = _project(tmp_path)
    _clock(monkeypatch)
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([FULL, report(layer_num=2, mc_percent=37),
                                                                report(gcode_state="FAILED")]), heights={})
    run = e["print_runs"][0]
    assert run["usage"] is None and run["printer_log"]["final_state"] == "FAILED"
    assert run["printer_log"]["last_percent"] == 37
    ws = {"online": True, "printer": {"state": "idle", "progress": 0, "minutesLeft": 0, "seenAt": "x"}}
    with patch("lab.sync.fetch_workshop_status", return_value=ws), pytest.raises(ValueError, match="--failed-at 37"):
        apply_telemetry(paths, "E-009")


def test_a_reconnect_after_the_print_ended_uses_the_last_running_report(tmp_path, monkeypatch):
    """Connection lost mid-print, the print finishes, paho reconnects much later: the end is the last RUNNING
    report, not the reconnect time."""
    from lab.printer import run_log
    paths = _project(tmp_path)
    times = iter(["2026-10-25T09:00:00+00:00", "2026-10-25T09:01:00+00:00", "2026-10-25T09:02:00+00:00",
                  "2026-10-25T11:30:00+00:00"])
    monkeypatch.setattr(run_log, "_now", lambda: next(times))
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([FULL, report(layer_num=2), report(layer_num=3),
                                                                report(gcode_state="FINISH")]), heights={})
    log = e["print_runs"][0]["printer_log"]
    assert log["ended_at"] == "2026-10-25T09:02:00+00:00" and log["end_uncertain"] is True


def test_logging_again_after_a_stop_starts_a_fresh_file(tmp_path, monkeypatch):
    from lab.printer import run_log
    from lab.loop.commands import load_experiment, save_experiment
    paths = _project(tmp_path)
    (paths.root / "telemetry").mkdir(parents=True)
    (paths.root / "telemetry" / "PR-009-01.jsonl").write_text('{"old": 1}\n' * 7)
    _clock(monkeypatch)
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([FULL, report(gcode_state="FINISH")]), heights={})
    assert len((paths.root / e["print_runs"][0]["printer_log"]["path"]).read_text().splitlines()) == 2


def test_report_text_handles_a_mark_without_a_height_and_says_events_may_be_a_layer_early():
    from lab.printer.run_log import report_text
    run = {"id": "PR-009-01", "printer_log": {"lines": 3, "final_state": "FINISH", "events": [
        {"layer": 87, "z_mm": 17.4, "t": "x", "field": "big_fan1_speed", "from": "0", "to": "60"}]}}
    text = report_text(run, [{"variant": "E-009-A", "mark_z_mm": None, "defect_z_mm": None}])
    assert "height unknown" in text and "one layer" in text


def test_a_cleared_list_drops_its_old_entries():
    m = StateMerger()
    m.update(report(hms=[{"attr": 1, "code": 2}]))
    assert "hms.0.code" in m.state
    m.update(report(hms=[]))
    assert not [k for k in m.state if k.startswith("hms.")]


def test_an_unexpected_error_in_a_report_handler_stops_the_listener():
    from lab.printer.mqtt import _ListenerState
    st = _ListenerState()
    st.guard(lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        st.raise_if_failed()


def test_enrollment_shows_who_the_certificate_names_and_refuses_an_expired_one():
    from lab.printer.mqtt import check_certificate
    import hashlib
    der = b"cert"
    fp = hashlib.sha256(der).hexdigest()
    ok = {"subject": "CN=20P6AJ640601656", "issuer": "CN=BBL Device CA", "not_after": "2035-01-01", "expired": False}
    with pytest.raises(ConnectionError) as no_pin:
        check_certificate({"serial": "20P6AJ640601656"}, lambda: der, details=lambda d: ok)
    msg = str(no_pin.value)
    assert "CN=20P6AJ640601656" in msg and "BBL Device CA" in msg and "matches your printer's serial" in msg
    old = {**ok, "expired": True, "not_after": "2025-01-01"}
    with pytest.raises(ConnectionError, match="expired"):
        check_certificate({"cert_sha256": fp, "serial": "20P6AJ640601656"}, lambda: der, details=lambda d: old)


def test_a_different_job_on_the_printer_ends_the_log_without_a_finish(tmp_path, monkeypatch):
    from lab.printer import run_log
    paths = _project(tmp_path)
    _clock(monkeypatch)
    ours = report(**{**FULL["print"], "subtask_name": "hex-tile_E-009_BLD-009-01"})
    other = report(subtask_name="someone-elses-job", gcode_state="RUNNING", layer_num=1)
    e = run_log.log_run(paths, "E-009", env={}, listen=_feed([ours, report(layer_num=2), other,
                                                                report(gcode_state="FINISH")]), heights={})
    log = e["print_runs"][0]["printer_log"]
    assert log["final_state"] == "job_changed" and log["ended_at"] is None
    assert e["print_runs"][0]["usage"] is None


def test_an_estimate_never_becomes_a_finish_time_or_actual_usage(tmp_path):
    """E-021 regression: a finished print with no printer log keeps unknown minutes and grams, whatever the
    estimate or Local AI's last-seen time say."""
    from unittest.mock import patch
    from lab.loop.telemetry import get_run_telemetry
    from loop_fixtures import make_project, minimal_experiment, minimal_question, started
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"), minutes=106.4, g=33.8)])
    ws = {"online": True, "printer": {"state": "finish", "progress": 100, "minutesLeft": 0,
                                      "seenAt": "2026-10-25T10:58:00+00:00"}}
    with patch("lab.sync.fetch_workshop_status", return_value=ws):
        t = get_run_telemetry(paths, "E-009")
    assert t["elapsed_minutes"] is None and t["elapsed_source"] is None
