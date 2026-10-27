import json

from lab import page
from lab.cli import main
from loop_fixtures import make_project, minimal_question


def test_lab_page_writes_json_only_and_commands_keep_it_current(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    monkeypatch.setenv("LAB_SYNC", "off")
    p = make_project(tmp_path, minimal_question("Q-001", ()), [])
    (p.root / "page.html").write_text("<p>an old page</p>")
    assert main(["page"]) == 0
    ix = json.loads((p.root / "page.json").read_text())
    assert ix["schema"] == "print-lab-index/1" and not (p.root / "page.html").exists()
    out = capsys.readouterr().out
    assert "page.json" in out and "#/printLab" in out
    assert main(["question", "new", "Is the top edge clean?", "--budget", "2h,50g"]) == 0
    assert "Is the top edge clean?" in (p.root / "page.json").read_text()  # refreshed by the command


def test_bambuddy_off_gives_no_colours_and_unreachable_gives_none():
    assert page.bambuddy_colours(url="off") == {}
    assert page.bambuddy_colours(url="http://127.0.0.1:9", timeout=0.5) is None  # couldn't read: not "no spools"
    assert page.spool_colour("Grey PLA", {}) == page.NEUTRAL


def _bambuddy(key):
    """A stand-in Bambuddy that answers the spool list only with the right X-API-Key (sign-in is on)."""
    import http.server, threading
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_GET(self):
            ok = self.headers.get("X-API-Key") == key
            body = json.dumps([{"color_name": "Terracotta", "rgba": "C0623AFF"}] if ok else {"detail": "Authentication required"}).encode()
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_bambuddy_is_asked_with_the_print_lab_key(tmp_path, monkeypatch):
    srv, url = _bambuddy("bb_test")
    try:
        (tmp_path / "key").write_text("bb_test\n")
        monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "key"))
        assert page.bambuddy_colours(url=url) == {"terracotta": "#C0623A"}
        monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "missing"))
        assert page.bambuddy_colours(url=url) is None  # refused without the key
    finally:
        srv.shutdown()


def test_a_bambuddy_that_doesnt_answer_keeps_the_saved_colours(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setenv("LAB_SYNC", "off")
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "http://127.0.0.1:9")
    p = make_project(tmp_path, minimal_question("Q-001", ()), [])
    (p.root / "page.json").write_text(json.dumps({"colours": {"terracotta": "#c0623a"}}))
    assert main(["page"]) == 0
    assert json.loads((p.root / "page.json").read_text())["colours"] == {"terracotta": "#c0623a"}
