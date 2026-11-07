"""`lab exp stage` (one tap to print, S1-S3): the checked build goes into Bambuddy's print-lab folder, proven byte for
byte, and nothing is ever queued or started. Bambuddy is a fake here; the adapter's HTTP calls are tested at the end
against a local server."""
import json
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lab import bambuddy
from lab.loop.guards import start
from lab.loop.stage import stage
from lab.page_index import build_index
from lab.records.schema import load
from test_guards import built, edit, proj  # noqa: F401  (fixture)


class FakeBambuddy:
    """The adapter's staging calls, in memory. `corrupt` makes the download differ from the upload."""

    def __init__(self, ver="1.3.0", corrupt=False):
        self.ver, self.corrupt = ver, corrupt
        self.files, self.calls, self.next_id = {}, [], 1

    def version(self):
        self.calls.append("version")
        if self.ver != bambuddy.SUPPORTED_VERSION:
            raise bambuddy.BambuddyError(f"Bambuddy is {self.ver}")
        return self.ver

    def staging_folder(self):
        self.calls.append("folder")
        return 7

    def upload(self, path, folder_id):
        self.calls.append(("upload", path.name, folder_id))
        fid, self.next_id = self.next_id, self.next_id + 1
        self.files[fid] = path.read_bytes()
        return {"id": fid, "filename": path.name}

    def download(self, fid):
        self.calls.append(("download", fid))
        return self.files[fid] + (b"x" if self.corrupt else b"")

    def library_file(self, fid):
        self.calls.append(("get", fid))
        return {"id": fid} if fid in self.files else None

    def delete(self, fid):
        self.calls.append(("delete", fid))
        self.files.pop(fid)


def _build(proj, eid):
    return load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]


def test_stage_uploads_the_checked_build_and_records_it(proj):
    eid = built(proj)
    fake = FakeBambuddy()
    r = stage(proj, eid, client=fake)
    b = _build(proj, eid)
    assert r == {"experiment": eid, "build": b["id"], "file": Path(b["sliced"]).name, "library_file": 1,
                 "folder": 7, "already": False}
    assert fake.files[1] == (proj.root / b["sliced"]).read_bytes()
    assert b["staged"]["library_file"] == 1 and b["staged"]["sha256"] == b["sliced_sha256"]
    assert b["staged"]["bambuddy"] == "1.3.0" and b["staged"]["folder"] == 7
    # the lab name goes up as the file name, so the print-log entry links back to the build (one-print P2)
    assert bambuddy.parse_lab_name(r["file"].removesuffix(".gcode.3mf"))["build"] == b["id"]


def test_stage_records_what_the_file_asks_slot_1_to_hold(proj):  # A12: the Start sheet compares it with the AMS tray
    eid = built(proj)
    stage(proj, eid, client=FakeBambuddy())
    assert _build(proj, eid)["staged"]["filament"] == {"type": "PLA", "colour": "#F95D73"}


def test_a_file_that_names_no_filament_records_none(proj, monkeypatch):
    from lab.loop import stage as stage_mod
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: None)
    assert stage_mod._file_filament("x.gcode.3mf") is None
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: {"filament_colour": ["", None], "filament_type": []})
    assert stage_mod._file_filament("x.gcode.3mf") is None
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: {"filament_type": ["PETG"]})
    assert stage_mod._file_filament("x.gcode.3mf") == {"type": "PETG", "colour": None}
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: (_ for _ in ()).throw(OSError("unreadable")))
    assert stage_mod._file_filament("x.gcode.3mf") is None


def test_stage_records_the_model_and_the_plate_size(proj):  # A12: the Start sheet says what is about to print
    eid = built(proj)
    stage(proj, eid, client=FakeBambuddy())
    staged = _build(proj, eid)["staged"]
    assert staged["model"] and "_" not in staged["model"]
    assert "size" in staged  # None for the fixture's file, which has no plate box


def test_the_model_is_named_plainly_from_its_source():
    from lab.loop.stage import _file_model
    assert _file_model({"inputs": {"model": {"sources/RIFT_10IN_batch5_shadow_storm.3mf": "abc"}}}) == \
        "RIFT 10IN batch5 shadow storm"
    assert _file_model({"inputs": {"model": {}}}) is None
    assert _file_model({}) is None


def test_the_plate_size_comes_from_the_slicers_box_and_top_layer(tmp_path, monkeypatch):
    import zipfile
    from lab.loop.stage import _file_size
    f = tmp_path / "x.gcode.3mf"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("Metadata/plate_1.json", json.dumps({"bbox_all": [92.77, 15.64, 163.24, 240.30]}))
        z.writestr("Metadata/plate_1.gcode", "; total layer number: 140\n; max_z_height: 28.00\n")
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: {"brim_type": "outer_only"})
    assert _file_size(f) == {"x": 70.5, "y": 224.7, "z": 28.0, "brim": True}
    monkeypatch.setattr("lab.adapters.bambu.read_settings", lambda p: {"brim_type": "no_brim"})
    assert _file_size(f)["brim"] is False
    assert _file_size(tmp_path / "missing.3mf") is None


def test_stage_never_queues_or_starts(proj):
    eid = built(proj)
    fake = FakeBambuddy()
    stage(proj, eid, client=fake)
    kinds = {c if isinstance(c, str) else c[0] for c in fake.calls}
    assert kinds <= {"version", "folder", "upload", "download", "get"}


def test_a_copy_that_differs_is_deleted_and_nothing_is_staged(proj):
    eid = built(proj)
    fake = FakeBambuddy(corrupt=True)
    with pytest.raises(ValueError, match="isn't the checked build.*deleted; nothing is staged"):
        stage(proj, eid, client=fake)
    assert fake.files == {} and ("delete", 1) in fake.calls
    assert "staged" not in _build(proj, eid)


def test_staging_again_keeps_the_file_bambuddy_still_has(proj):
    eid = built(proj)
    fake = FakeBambuddy()
    stage(proj, eid, client=fake)
    r = stage(proj, eid, client=fake)
    assert r["already"] and r["library_file"] == 1 and list(fake.files) == [1]


def test_staging_again_uploads_when_bambuddy_lost_the_file(proj):
    eid = built(proj)
    fake = FakeBambuddy()
    stage(proj, eid, client=fake)
    fake.files.clear()
    r = stage(proj, eid, client=fake)
    assert not r["already"] and r["library_file"] == 2 and _build(proj, eid)["staged"]["library_file"] == 2


def test_stage_refuses_what_send_refuses_and_uploads_nothing(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["stops"].append({"reason": "wrong way", "at": "t", "resumed_at": None,
                                                     "resume": None}), "questions")
    fake = FakeBambuddy()
    with pytest.raises(ValueError, match=r"Can't stage [\s\S]*owner_stopped"):
        stage(proj, eid, client=fake)
    assert fake.calls == []


def test_stage_names_the_approve_command_when_approval_is_needed(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_minutes=10), "questions")
    with pytest.raises(ValueError, match=rf"question_time[\s\S]*lab exp approve {eid}"):
        stage(proj, eid, client=FakeBambuddy())


def test_stage_refuses_while_printing(proj):
    eid = built(proj)
    start(proj, eid)
    with pytest.raises(ValueError, match="already printing"):
        stage(proj, eid, client=FakeBambuddy())


def test_stage_refuses_a_sliced_file_changed_since_the_build(proj, monkeypatch):
    eid = built(proj)
    real = __import__("lab.loop.stage", fromlist=["checked_build"]).checked_build
    monkeypatch.setattr("lab.loop.stage.checked_build",
                        lambda p, e, v: SimpleNamespace(build={**real(p, e, v).build, "sliced_sha256": "0" * 64}))
    fake = FakeBambuddy()
    with pytest.raises(ValueError, match="changed since"):
        stage(proj, eid, client=fake)
    assert fake.calls == []


def test_stage_refuses_another_bambuddy_version(proj):
    eid = built(proj)
    fake = FakeBambuddy(ver="1.4.0")
    with pytest.raises(bambuddy.BambuddyError, match="1.4.0"):
        stage(proj, eid, client=fake)
    assert fake.files == {}


def test_the_mirror_shows_the_staged_build_only_while_it_can_print(proj):
    eid = built(proj)
    stage(proj, eid, client=FakeBambuddy())
    ix = build_index(proj.root)
    e = next(x for x in ix["experiments"] if x["id"] == eid)
    assert e["staged"]["library_file"] == 1 and e["staged"]["sha256"] == _build(proj, eid)["sliced_sha256"]
    start(proj, eid)
    e = next(x for x in build_index(proj.root)["experiments"] if x["id"] == eid)
    assert e["staged"] is None


def test_cli_stage_prints_what_it_staged(proj, monkeypatch, capsys):
    from lab import cli
    eid = built(proj)
    monkeypatch.setenv("LAB_HOME", str(proj.root.parent.parent))
    monkeypatch.setenv("LAB_SYNC", "off")
    fake = FakeBambuddy()
    real = __import__("lab.loop.stage", fromlist=["stage"]).stage
    monkeypatch.setattr("lab.loop.stage.stage", lambda p, e: real(p, e, client=fake))
    assert cli.main(["exp", "stage", eid]) == 0
    out = capsys.readouterr().out
    assert "Staged" in out and "library file 1" in out and "Nothing is queued or started" in out


# --- the adapter's HTTP calls, against a local server ---

class _Handler(BaseHTTPRequestHandler):
    store: dict = {}
    seen: list = []

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.seen.append(("GET", self.path, self.headers.get("X-API-Key")))
        if self.path == "/api/v1/updates/version":
            return self._send(200, {"version": self.store.get("version", "1.3.0")})
        if self.path == "/api/v1/library/folders/":
            return self._send(200, self.store.get("folders", [{"id": 3, "name": "print-lab", "parent_id": None}]))
        if self.path == "/api/v1/library/files/5/download":
            return self._send(200, self.store["file"], "application/octet-stream")
        return self._send(404, {"detail": "File not found"})

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = self.rfile.read(n)
        self.seen.append(("POST", self.path, self.headers.get("X-API-Key")))
        start = body.index(b"\r\n\r\n") + 4
        self.store["file"] = body[start:body.rindex(b"\r\n--")]
        return self._send(200, {"id": 5, "filename": "x"})

    def do_DELETE(self):
        self.seen.append(("DELETE", self.path, self.headers.get("X-API-Key")))
        return self._send(200, {"status": "success"})


@pytest.fixture
def server(monkeypatch, tmp_path):
    _Handler.store, _Handler.seen = {}, []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    keyfile = tmp_path / "key"
    keyfile.write_text("k-123\n")
    monkeypatch.setenv("LAB_BAMBUDDY_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(keyfile))
    yield _Handler
    srv.shutdown()


def test_adapter_uploads_and_reads_back_the_same_bytes(server, tmp_path):
    f = tmp_path / "hex-tile_E-001_BLD-001-01.gcode.3mf"
    f.write_bytes(bytes(range(256)) * 10)
    assert bambuddy.version() == "1.3.0"
    folder = bambuddy.staging_folder()
    rec = bambuddy.upload(f, folder)
    assert folder == 3 and rec["id"] == 5
    assert bambuddy.download(5) == f.read_bytes()
    assert ("POST", "/api/v1/library/files/?folder_id=3&generate_stl_thumbnails=false", "k-123") in server.seen
    assert all(k == "k-123" for _, _, k in server.seen)


def test_adapter_refuses_another_version(server):
    server.store["version"] = "1.4.0"
    with pytest.raises(bambuddy.BambuddyError, match="1.4.0.*proven on 1.3.0"):
        bambuddy.version()


def test_adapter_needs_exactly_one_staging_folder(server):
    server.store["folders"] = []
    with pytest.raises(bambuddy.BambuddyError, match="0 top-level 'print-lab'"):
        bambuddy.staging_folder()


def test_adapter_reports_a_missing_file_as_none_and_refusals_with_the_reason(server):
    assert bambuddy.library_file(99) is None
    with pytest.raises(bambuddy.BambuddyError, match="404 File not found"):
        bambuddy.download(99)


def test_adapter_off_or_without_a_key_refuses(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    with pytest.raises(bambuddy.BambuddyError, match="off"):
        bambuddy.version()
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "none"))
    with pytest.raises(bambuddy.BambuddyError, match="No Bambuddy API key"):
        bambuddy.version()


def test_cli_approve_points_at_pi_hubs_start_not_lab_exp_start(proj, monkeypatch, capsys):
    from lab import cli
    from test_guards import edit as edit_
    eid = built(proj)
    edit_(proj, "Q-009", lambda q: q["budget"].update(max_minutes=10), "questions")
    monkeypatch.setenv("LAB_HOME", str(proj.root.parent.parent))
    monkeypatch.setenv("LAB_SYNC", "off")
    assert cli.main(["exp", "check", eid]) == 2
    assert cli.main(["exp", "approve", eid, "--reason", "worth it"]) == 0
    out = capsys.readouterr().out
    assert "Start on Pi Hub then records the start itself" in out
    assert f"Only if you send it from Bambu Connect, run `lab exp start {eid}`" in out
