"""Bad input is refused at the shared builders and parsers, so a typo (or a request from the phone) can't write a
bad record: usage figures, new questions, budgets, experiment plans and setup-log events."""
import json
import math

import pytest

from lab import cli
from lab.loop.builders import plan_experiment
from lab.loop.commands import new_question, record_usage
from lab.loop.setup_log import append_event
from lab.records.store import parse_budget
from loop_fixtures import PLAN, minimal_experiment, minimal_question, make_project, project_with_sources


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


@pytest.fixture
def usage_proj(tmp_path):
    e = minimal_experiment()
    e["status"] = "printing"
    e["print_runs"] = [{"id": "PR-009-01", "build_id": "BLD-009-01", "started_at": "t"}]
    return make_project(tmp_path, minimal_question(), [e])


@pytest.mark.parametrize("kw", [{"minutes": -500}, {"minutes": float("nan")}, {"minutes": math.inf},
                                {"grams": -1}, {"grams": float("nan")}, {"grams": -math.inf}])
def test_usage_refuses_negative_nan_and_infinite(usage_proj, kw):
    with pytest.raises(ValueError, match="--minutes|--grams"):
        record_usage(usage_proj, "PR-009-01", **kw)
    run = json.loads((usage_proj.experiments / "E-009.json").read_text())["print_runs"][0]
    assert "usage" not in run


def test_usage_still_takes_zero_and_real_figures(usage_proj):
    e = record_usage(usage_proj, "PR-009-01", minutes=0, grams=12.5)
    assert e["print_runs"][0]["usage"]["actual_g"] == 12.5


@pytest.mark.parametrize("pct", [0, 100, -5, float("nan"), math.inf])
def test_usage_failed_at_range(usage_proj, pct):
    with pytest.raises(ValueError, match="--failed-at"):
        record_usage(usage_proj, "PR-009-01", failed_at_pct=pct)


def test_cli_usage_gives_a_message_not_a_traceback(usage_proj, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(usage_proj.root.parent.parent))
    rc = cli.main(["exp", "usage", "PR-009-01", "--minutes", "-500", "--grams", "nan", "--project", "hex-tile"])
    assert rc != 0 and "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("text", ["", "   "])
def test_question_needs_text(proj, text):
    with pytest.raises(ValueError, match="question"):
        new_question(proj, text, {})


@pytest.mark.parametrize("text", ["0m,0g", "0m", "0g", "0h"])
def test_budget_refuses_zero(text):
    with pytest.raises(ValueError, match="more than 0"):
        parse_budget(text)


@pytest.mark.parametrize("text", ["3h,4h", "100g,50g", "3h,90m"])
def test_budget_refuses_a_repeated_kind(text):
    with pytest.raises(ValueError, match="twice|once"):
        parse_budget(text)


def test_budget_good_forms_unchanged():
    assert parse_budget("2h30m,100g") == {"minutes": 150, "g": 100}


@pytest.mark.parametrize("values", [["250", ""], [""], ["250", "fast"], ["250", "-5"], ["nan"], ["250", "inf"]])
def test_plan_refuses_bad_setting_values(proj, values):
    with pytest.raises(ValueError, match="values"):
        plan_experiment(proj, "Q-009", **{**PLAN, "values": values})
    assert not list(proj.experiments.glob("E-*.json"))


def test_plan_refuses_non_whole_plate_count(proj):
    with pytest.raises(ValueError, match="values"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": "objects_on_plate", "values": ["2.5"], "expect": "A=A"})


@pytest.mark.parametrize("z", [(20.0, 10.0), (10.0, 10.0), (-1.0, 5.0), (float("nan"), 5.0), (0.0, math.inf)])
def test_plan_refuses_bad_strip_range(proj, z):
    with pytest.raises(ValueError, match="strip"):
        plan_experiment(proj, "Q-009", **{**PLAN, "z": z})
    assert not list(proj.experiments.glob("E-*.json"))


@pytest.mark.parametrize("extra", [["--z", "10"], ["--z", "a:b"], ["--z", "20:10"], ["--adjust", "foo"],
                                   ["--adjust", "=3"], ["--values", ""]])
def test_cli_plan_gives_a_message_not_a_traceback(proj, monkeypatch, capsys, extra):
    monkeypatch.setenv("LAB_HOME", str(proj.root.parent.parent))
    base = {"--factor": "inner_wall_speed", "--values": "250,80", "--z": "60:72", "--expect": "B>A:clearly",
            "--judge-on": "bands", "--source": PLAN["source"], "--object": "v58_06_6in", "--base": PLAN["base"],
            "--hypothesis": "h", "--prediction": "p", "--project": "hex-tile"}
    argv = ["exp", "plan", "Q-009", "t"]
    for k, v in {**base, **dict(zip(extra[::2], extra[1::2]))}.items():
        argv += [k, v]
    if "--adjust" in extra:
        argv += ["--adjust", extra[extra.index("--adjust") + 1]]
    rc = cli.main(argv)
    err = capsys.readouterr().err
    assert rc != 0 and err.strip() and "Traceback" not in err
    assert "unpack" not in err and "sequence element" not in err
    assert not list(proj.experiments.glob("E-*.json"))


def test_setup_log_refuses_an_unknown_kind(proj):
    with pytest.raises(ValueError, match="filament_dried"):
        append_event(proj, "filament_driedd", {})
    assert not proj.setup_log.exists() or not proj.setup_log.read_text().strip()


def test_setup_log_known_kind_still_logs(proj):
    assert append_event(proj, "nozzle_changed", {"diameter_mm": 0.4})["kind"] == "nozzle_changed"


def test_cli_setup_set_needs_equals(proj, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(proj.root.parent.parent))
    rc = cli.main(["setup", "log", "nozzle_changed", "--set", "foo"])
    assert rc != 0 and "KEY=VALUE" in capsys.readouterr().err
    assert not proj.setup_log.exists() or not proj.setup_log.read_text().strip()


@pytest.mark.parametrize("v", ["²", "٣", "①", "2.5", "0"])
def test_plate_count_check_never_throws_a_raw_error(proj, v):
    with pytest.raises(ValueError, match="whole object counts"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": "objects_on_plate", "values": [v], "expect": "A=A"})
