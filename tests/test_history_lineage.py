import json
from pathlib import Path

from lab.history.audit import audit_text, load_outcomes
from lab.history.lineage import transitions
from lab.history.revisions import Revision

OUTCOMES = Path(__file__).parent.parent / "projects" / "hex-tile" / "history" / "outcomes.json"


def rev(v, params=None, settings=None, nozzle_profile="0.4", name_nozzle=None):
    return Revision(version=v, scad_params=params or {}, settings=settings, nozzle_profile=nozzle_profile,
                    nozzle_in_name=name_nozzle)


def test_grade_one_factor_A():
    t = transitions([rev(50, {"skin": 1.2, "rim": 2}), rev(51, {"skin": 1.4, "rim": 2})])
    assert t[0].factors == 1 and t[0].grade == "A" and t[0].scad_changes == {"skin": [1.2, 1.4]}


def test_grade_many_factors_D():
    a = {f"p{i}": 0 for i in range(6)}
    t = transitions([rev(41, a), rev(42, {k: 1 for k in a})])
    assert t[0].grade == "D"


def test_grade_v56_F():
    t = transitions([rev(55, {"skin": 1.2}), rev(56, {"skin": 1.2}, name_nozzle="0.6", nozzle_profile="0.4")])
    assert t[0].grade == "F"


def test_settings_ids_ignored():
    s1 = {"layer_height": "0.2", "print_settings_id": "A"}
    s2 = {"layer_height": "0.2", "print_settings_id": "B"}
    assert transitions([rev(1, settings=s1), rev(2, settings=s2)])[0].factors == 0


def test_gap_v45():
    t = transitions([rev(44, {"a": 1}), rev(46, {"a": 1})])
    assert t[0].from_v == 44 and t[0].to_v == 46 and t[0].gap == [45]


def test_outcomes_file_valid():
    data = json.loads(OUTCOMES.read_text())
    assert len(data) >= 18 and all({"at", "version", "owner_words", "defects", "confirmed"} <= set(d) for d in data)
    assert not any(d["confirmed"] for d in data)


def test_audit_sections_present():
    text = audit_text([rev(55), rev(56, name_nozzle="0.6")], transitions([rev(55), rev(56, name_nozzle="0.6")]),
                      load_outcomes(OUTCOMES))
    for heading in ("Revisions", "Evidence", "Persistent defects", "Changes that never touched it", "Not yet tried",
                    "Next experiment"):
        assert f"## {heading}" in text


def test_audit_lists_ripple_versions():
    text = audit_text([rev(55)], [], load_outcomes(OUTCOMES))
    line = next(l for l in text.splitlines() if l.startswith("- upper-edge ripple"))
    for v in ("v36", "v37", "v39", "v51", "v56"):
        assert v in line


def test_scad_code_change_counts():
    a, b = rev(44, {"skin": 1.2}), rev(46, {"skin": 1.2})
    a.scad_code, b.scad_code = "aaa", "bbb"
    t = transitions([a, b])[0]
    assert t.factors == 1 and "scad code" in t.scad_changes


def test_missing_scad_falls_back_to_mesh():
    a = rev(41, settings={"layer_height": "0.2"})
    b = rev(42, {"skin": 1.2}, settings={"layer_height": "0.2"})
    a.mesh = {"6in": {"volume_cm3": 60.14}}
    b.mesh = {"6in": {"volume_cm3": 60.22 * 1.1}}
    t = transitions([a, b])[0]
    assert "model (6in volume)" in t.scad_changes and t.factors == 1
