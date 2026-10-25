import json

from lab import page


def _project(tmp_path):
    p = tmp_path / "projects" / "tile"
    (p / "questions").mkdir(parents=True)
    (p / "experiments").mkdir()
    (p / "photos").mkdir()
    (p / "photos" / "PR-1-1.jpg").write_bytes(b"\xff\xd8jpeg")
    (p / "questions" / "Q-1.json").write_text(json.dumps({
        "id": "Q-1", "question": "What causes the <bands>?", "status": "active", "experiments": ["E-1", "E-2"],
        "budget": {"max_minutes": 180, "max_g": 100},
        "plans": [{"after": "E-1", "if": "no difference", "next": "slower walls"}]}))
    (p / "experiments" / "E-1.json").write_text(json.dumps({
        "id": "E-1", "status": "answered", "question_text": "Does sharing the plate matter?", "test_kind": "height_strip",
        "factor": {"name": "objects_on_plate", "values": [1, 2]},
        "controlled": {"filament": "Kexcelled K5 PLA M, Light Matte Terracotta (lot C6)"},
        "owner_verdict": {"kind": "ranking", "note": "they look good", "at": "2026-10-24T23:14:18+00:00"},
        "prediction_outcome": "refuted",
        "print_runs": [{"id": "PR-1", "photos": [{"path": "photos/PR-1-1.jpg", "source": "IMG_1.HEIC"},
                                                  {"path": "photos/missing.jpg"}]}]}))
    (p / "experiments" / "E-2.json").write_text(json.dumps({
        "id": "E-2", "status": "needs_approval", "question_text": "Full pair", "test_kind": "full_part"}))
    return p


def test_page_shows_needs_questions_notebook_and_photos(tmp_path):
    html = page.build(_project(tmp_path), colours={"light matte terracotta": "#c97b5a", "terracotta": "#000000"})
    assert "What causes the &lt;bands&gt;?" in html and "<bands>" not in html  # escaped
    assert "1 of 2 experiments answered" in html and "After E-1, if no difference: slower walls" in html
    assert "Needs your approval" in html and "Approve or change this test before it prints." in html
    assert "--spine:#c97b5a" in html  # the longest matching spool name wins
    assert 'src="photos/PR-1-1.jpg"' in html and "missing.jpg" not in html  # only photos that exist
    assert "Prediction refuted" in html and "they look good" in html
    assert html.index('id="E-2"') < html.index('id="E-1"')  # newest first


def test_page_without_questions_says_so(tmp_path):
    p = tmp_path / "projects" / "empty"
    p.mkdir(parents=True)
    html = page.build(p, colours={})
    assert "No open question." in html and "Nothing needs you right now." in html


def test_bambuddy_off_and_unreachable_give_no_colours():
    assert page.bambuddy_colours(url="off") == {}
    assert page.bambuddy_colours(url="http://127.0.0.1:9", timeout=0.5) == {}
    assert page.spool_colour("Grey PLA", {}) == page.NEUTRAL


def test_cli_writes_the_page(tmp_path, monkeypatch, capsys):
    from lab import cli
    _project(tmp_path)
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    assert cli.main(["--project", "tile", "page"]) == 0
    out = tmp_path / "projects" / "tile" / "page.html"
    assert out.is_file() and "Print lab · tile" in out.read_text()


def test_factor_values_read_as_words():
    assert page._value(["250", "250", "200"]) == "250/200"
    assert page._value("sources/hexagon_v58.3mf") == "hexagon_v58.3mf"
    assert page._value(2) == "2"


def test_bambuddy_colours_only_accept_hex(monkeypatch):
    import io, json as j, urllib.request
    spools = [{"color_name": "Grey", "rgba": "9A9A9AFF"}, {"color_name": "Evil", "rgba": "red;}</style><script>"}]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(j.dumps(spools).encode()))
    assert page.bambuddy_colours(url="http://x") == {"grey": "#9A9A9A"}


def test_current_experiment_and_wipe(tmp_path):
    p = _project(tmp_path)
    (p / "photos" / "PR-9-1.jpg").write_bytes(b"\xff\xd8x")
    (p / "experiments" / "E-3.json").write_text(json.dumps({
        "id": "E-3", "status": "printed", "question_text": "Slower walls?", "why_this_test": "The <only> difference.",
        "reference_variants": ["E-1-A"],
        "print_runs": [{"id": "PR-9", "photos": [{"path": "photos/PR-9-1.jpg"}]}]}))
    q = json.loads((p / "questions" / "Q-1.json").read_text()); q["experiments"].append("E-3")
    (p / "questions" / "Q-1.json").write_text(json.dumps(q))
    html = page.build(p, colours={})
    assert "Why this test?</b> The &lt;only&gt; difference." in html  # the open experiment, up front
    assert 'class="wipe"' in html and 'src="photos/PR-1-1.jpg"' in html and 'class="after" src="photos/PR-9-1.jpg"' in html
    assert "Record a verdict from the photos." in html
