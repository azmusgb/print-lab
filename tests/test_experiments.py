from lab.experiments import Experiment, check_plan, differing_factors, load, next_id, next_print_run_id, save

BASE = {"model": {"rib_w": 2.5, "rib_kiss": 0.1}, "settings": {"layer_height": "0.2", "outer_wall_speed": ["80"],
                                                             "brim_width": "10"}}


def changed(**kw):
    import copy
    after = copy.deepcopy(BASE)
    for k, v in kw.items():
        (after["model"] if k in after["model"] else after["settings"])[k] = v
    return after


def exp(**kw):
    base = dict(id="E-001", project="hex-tile", question="Q", hypothesis="H", prediction="P", why_this_test="W",
                test_kind="height_strip", factor={"name": "layer_height", "values": ["0.2", "0.16"], "unit": "mm"},
                baseline={"filament_dried": True, "vibration_calibration": True, "nozzle_confirmed": True,
                          "plate": "textured PEI"})
    base.update(kw)
    return Experiment(**base)


def test_ids_sequence(tmp_path):
    assert next_id(tmp_path) == "E-001"
    save(exp(), tmp_path)
    assert next_id(tmp_path) == "E-002" and next_print_run_id(tmp_path) == "PR-001"


def test_roundtrip_json(tmp_path):
    e = exp(dependent_adjustments={"brim_width": "wider plate spacing"})
    save(e, tmp_path)
    assert load(tmp_path / "experiments" / "E-001.json") == e


def test_differing_factors():
    assert differing_factors(BASE, changed(layer_height="0.16", rib_w=3.0), ignore=set()) == ["layer_height", "rib_w"]


def test_one_factor_ok():
    assert [f for f in check_plan(exp(), BASE, changed(layer_height="0.16")) if f.severity == "blocking"] == []


def test_stacked_changes_blocked():
    fs = check_plan(exp(), BASE, changed(layer_height="0.16", outer_wall_speed=["90"]))
    f = next(f for f in fs if f.rule == "stacked-changes")
    assert f.severity == "blocking" and "outer_wall_speed" in f.why


def test_dependent_adjustment_allowed():
    e = exp(dependent_adjustments={"brim_width": "the leaned part needs a wider brim"})
    assert [f for f in check_plan(e, BASE, changed(layer_height="0.16", brim_width="15")) if f.severity == "blocking"] == []


def test_full_part_needs_override():
    fs = check_plan(exp(test_kind="full_part"), BASE, changed(layer_height="0.16"))
    assert any(f.rule == "override-needed" and f.severity == "blocking" for f in fs)


def test_baseline_incomplete_info():
    fs = check_plan(exp(baseline={"filament_dried": False}), BASE, changed(layer_height="0.16"))
    f = next(f for f in fs if f.rule == "baseline-incomplete")
    assert f.severity == "info" and "vibration_calibration" in f.data["missing"] and "filament_dried" in f.data["missing"]
