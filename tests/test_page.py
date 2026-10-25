import json

from lab import page
from lab.cli import main
from loop_fixtures import make_project, minimal_question
from test_page_index import _project


def _html(tmp_path, **kw):
    p = _project(tmp_path)
    (p.root / "photos").mkdir(exist_ok=True)
    (p.root / "photos" / "PR-001-01-1.jpg").write_bytes(b"\xff\xd8jpeg")
    e = json.loads((p.experiments / "E-001.json").read_text())
    e["print_runs"][0]["photos"] = [{"path": "photos/PR-001-01-1.jpg", "source": "IMG_1.HEIC"},
                                    {"path": "photos/missing.jpg", "source": "IMG_2.HEIC"}]
    e["question_text"] = "Do <slow> walls help?"
    (p.experiments / "E-001.json").write_text(json.dumps(e))
    return p, page.build(p.root, colours=kw.get("colours", {}))


def test_question_card_shows_spend_next_and_stop(tmp_path):
    _, html = _html(tmp_path)
    assert "80 / 180 min" in html and "24 / 100 g" in html
    assert "E-002 would add 63 min, 19 g" in html and "Continue" in html


def test_needs_you_gives_the_action_why_and_command_in_order(tmp_path):
    _, html = _html(tmp_path)
    needs = html[html.index('class="card needs"'):html.index("</section>", html.index('class="card needs"'))]
    assert needs.index("E-004") < needs.index("E-002") and "E-003" not in needs
    assert "Judge the print" in needs and "63 / 45 min per test" in needs
    assert "<code>uv run lab exp approve E-002 --reason &quot;...&quot;</code>" in needs


def test_cards_show_outcome_validity_and_requested_vs_realized(tmp_path):
    _, html = _html(tmp_path)
    assert "Prediction supported" in html and "Fair comparison" in html
    assert "1A: 250 asked, 147 printed mm/s" in html and "1B: 80 mm/s" in html
    assert "Do &lt;slow&gt; walls help?" in html and "<slow>" not in html


def test_finished_work_folds_under_earlier_and_only_real_photos_show(tmp_path):
    _, html = _html(tmp_path)
    earlier = html[html.index('class="earlier"'):]
    assert 'id="E-003"' in earlier and 'id="E-001"' in earlier and 'id="E-004"' not in earlier
    assert 'src="photos/PR-001-01-1.jpg"' in html and "missing.jpg" not in html


def test_unreadable_records_are_named_not_hidden(tmp_path):
    p, _ = _html(tmp_path)
    (p.experiments / "E-099.json").write_text("{")
    assert "experiments/E-099.json" in page.build(p.root, colours={})


def test_empty_project_says_what_to_do(tmp_path):
    p = tmp_path / "projects" / "empty"
    p.mkdir(parents=True)
    html = page.build(p, colours={})
    assert "No open question." in html and "Nothing needs you right now." in html


def test_lab_page_writes_html_and_json_and_commands_keep_it_current(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    p = make_project(tmp_path, minimal_question("Q-001", ()), [])
    assert main(["page"]) == 0
    ix = json.loads((p.root / "page.json").read_text())
    assert ix["schema"] == "print-lab-index/1" and (p.root / "page.html").is_file()
    assert main(["question", "new", "Is the top edge clean?", "--budget", "2h,50g"]) == 0
    assert "Is the top edge clean?" in (p.root / "page.html").read_text()  # refreshed by the command


def test_bambuddy_off_and_unreachable_give_no_colours():
    assert page.bambuddy_colours(url="off") == {}
    assert page.bambuddy_colours(url="http://127.0.0.1:9", timeout=0.5) == {}
    assert page.spool_colour("Grey PLA", {}) == page.NEUTRAL
