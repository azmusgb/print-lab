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
    assert load_printer_env(p) == {"host": "10.0.0.136", "serial": "S1", "code": "abc"}


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
    out = run_log.log_run(paths, "E-009", env={"host": "h", "serial": "S1", "code": "c"}, listen=fake_listen,
                          heights={1: 0.2, 2: 0.4, 3: 0.6})
    run = out["print_runs"][0]
    log = run["printer_log"]
    assert log["final_state"] == "FINISH"
    assert log["events"] == [{"layer": 2, "z_mm": 0.4, "t": "2026-10-25T09:02:00+00:00", "field": "big_fan1_speed",
                              "from": "0", "to": "60"}]
    lines = (paths.root / log["path"]).read_text().splitlines()
    assert len(lines) == 5  # layer 1, layer 2, fan change, layer 3, finish
    assert "c" not in json.loads(lines[0]).get("state", {}).values()
    assert run["usage"] is None  # usage stays the owner's call (or `telemetry --apply`)


def test_log_command_refuses_a_run_that_already_has_a_log(tmp_path):
    from lab.printer import run_log
    from loop_fixtures import make_project, minimal_experiment, minimal_question, started
    e = started(minimal_experiment("E-009"))
    e["print_runs"][0]["printer_log"] = {"path": "telemetry/PR-009-01.jsonl"}
    paths = make_project(tmp_path, minimal_question(), [e])
    with pytest.raises(ValueError, match="already has a printer log"):
        run_log.log_run(paths, "E-009", env={}, listen=lambda *a, **k: None, heights={})
