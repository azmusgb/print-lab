"""`lab quick worker`: the Mac's side of A19's fenced slice attempts (plan decision 6, P3a wire contract).

One pass: take the lock, claim a job from the Pi Hub (an empty claim is also the idle contact that feeds "Mac asleep,
last seen"), fetch and verify the model, slice in a killable child process while a heartbeat runs every 15 s, upload
the artifact, post the completion. The hub's attempt record is the authority: any 409 (canceled, expired, superseded,
terminal, generation) or `cancel: true` stops the slice, deletes the scratch and ends the pass cleanly, and a result is
never posted for an attempt the hub has refused. Nothing is retried."""
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from lab.sync import HOME, Target, _NoRedirect, _error, _open, targets  # noqa: F401 (_NoRedirect: same trust rules)

BASE = "/api/lab/quick/worker"  # Caddy passes the Mac only /api/lab/*
CHUNK = 8 << 20  # the hub takes at most 8 MiB per artifact request (Caddy caps bodies at 9 MB)
PRESET_DIR = Path(__file__).resolve().parents[2] / "presets" / "quick"
DEFAULT_TIMEOUT = 10.0
MISSED_BEATS = 6  # consecutive heartbeat failures after which the lease (90 s) is gone: stop, post nothing


class Refused(Exception):
    """The hub refused this attempt (409) or it is canceled: stop at once."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class HubError(Exception):
    """The hub couldn't be asked (network, 5xx, 401/404/413/422); the text is for the log."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Hub:
    def __init__(self, target: Target, timeout: float = DEFAULT_TIMEOUT):
        self.t, self.timeout = target, timeout

    def _req(self, method, path, body=None, headers=None, timeout=None):
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        h = {self.t.header: self.t.key, **(headers or {})}
        if isinstance(body, (dict, list)):
            h["Content-Type"] = "application/json"
        return urllib.request.Request(self.t.base + path, data=data, method=method, headers=h)

    def call(self, method, path, body=None, headers=None, timeout=None, raw=False):
        """JSON in and out (raw=True returns (bytes, headers)). 409 raises Refused(reason); other failures HubError."""
        req = self._req(method, path, body, headers)
        try:
            with _open(req, timeout or self.timeout, self.t.context) as r:
                payload = r.read()
                return (payload, r.headers) if raw else json.loads(payload or b"{}")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read() or b"{}")
            except ValueError:
                err = {}
            if e.code == 409:
                raise Refused(str(err.get("reason") or err.get("detail") or "refused")) from None
            raise HubError(f"HTTP {e.code} {path}: {_error(err, e.code)}") from None
        except (OSError, ValueError) as e:
            raise HubError(f"{path}: {e}") from None

    def claim(self, worker: dict) -> dict:
        return self.call("POST", f"{BASE}/claim", {"worker": worker})

    def heartbeat(self, job: dict, phase: str, worker: dict) -> dict:
        return self.call("POST", f"{BASE}/jobs/{job['id']}/attempts/{job['attempt']}/heartbeat",
                         {"generation": job["generation"], "phase": phase, "worker": worker})

    def download_model(self, job: dict, dest: Path) -> str:
        """Stream the model to dest; returns the sha256 of what arrived."""
        req = self._req("GET", f"{BASE}/jobs/{job['id']}/attempts/{job['attempt']}/model?generation={job['generation']}")
        try:
            with _open(req, 120, self.t.context) as r, open(dest, "wb") as f:
                h = hashlib.sha256()
                while chunk := r.read(1 << 20):
                    h.update(chunk)
                    f.write(chunk)
            return h.hexdigest()
        except urllib.error.HTTPError as e:
            if e.code == 409:
                try:
                    reason = json.loads(e.read() or b"{}").get("reason", "refused")
                except ValueError:
                    reason = "refused"
                raise Refused(str(reason)) from None
            raise HubError(f"HTTP {e.code} on the model download") from None
        except OSError as e:
            raise HubError(f"model download: {e}") from None

    def _put_chunk(self, job: dict, data: bytes, offset: int, size: int, sha: str) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.t.base + f"{BASE}/jobs/{job['id']}/attempts/{job['attempt']}/artifact"
            f"?generation={job['generation']}&offset={offset}",
            data=data, method="PUT",
            headers={self.t.header: self.t.key, "Content-Type": "application/octet-stream", "X-Sha256": sha,
                     "X-Size": str(size)})
        try:
            with _open(req, 120, self.t.context) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read() or b"{}")
            except ValueError:
                err = {}
            if e.code == 409:
                return 409, err
            raise HubError(f"HTTP {e.code} on the artifact upload: {_error(err, e.code)}") from None
        except OSError as e:
            raise HubError(f"artifact upload: {e}") from None

    def upload_artifact(self, job: dict, path: Path, sha: str, stop: threading.Event | None = None) -> dict:
        """Send the file in chunks of at most 8 MiB, each carrying the whole file's X-Size and X-Sha256. A wrong offset
        (409 reason "offset") continues from the offset the hub has; any other 409 is a refusal. The chunk that reaches
        the size makes the hub verify the sha and answer done."""
        size = path.stat().st_size
        offset, corrections = 0, 0
        with open(path, "rb") as f:
            while True:
                if stop is not None and stop.is_set():
                    raise Refused("canceled")
                f.seek(offset)
                code, body = self._put_chunk(job, f.read(CHUNK), offset, size, sha)
                if code == 409:
                    if body.get("reason") == "offset" and isinstance(body.get("offset"), int) and corrections < 5 \
                            and 0 <= body["offset"] <= size:
                        corrections += 1
                        offset = body["offset"]
                        continue
                    raise Refused(str(body.get("reason") or "refused"))
                if body.get("done"):
                    return body
                nxt = body.get("offset")
                if not isinstance(nxt, int) or nxt <= offset or nxt > size:
                    raise HubError("the hub's artifact offset did not advance")
                offset = nxt

    def complete(self, job: dict, body: dict) -> dict:
        return self.call("POST", f"{BASE}/jobs/{job['id']}/attempts/{job['attempt']}/complete",
                         {"generation": job["generation"], **body})


def worker_record(presets: list[str] | None = None, studio_version: str | None = None) -> dict:
    if studio_version is None:
        try:
            from lab.adapters.bambu import bambu_binary
            studio_version = bambu_binary()[1]
        except Exception:
            studio_version = ""
    if presets is None:
        presets = sorted(p.stem for p in PRESET_DIR.glob("*.3mf"))
    host = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname().split(".")[0]) or "host"  # the hub's id pattern
    return {"id": f"mac-{host}"[:40], "os": sys.platform,
            "studio_version": studio_version, "presets": presets}


class Lock:
    """One worker per Mac. The OS drops the lock when the process dies, however it dies."""

    def __init__(self, path: Path):
        self.path, self.f = Path(path), None

    def __enter__(self):
        from lab.pull import _flock_nb
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a")
        try:
            _flock_nb(self.f)
        except OSError:
            self.f.close()
            self.f = None
            raise BlockingIOError("another quick worker is running") from None
        return self

    def __exit__(self, *a):
        from lab.pull import _funlock
        if self.f:
            _funlock(self.f)
            self.f.close()


class Heartbeat(threading.Thread):
    """Beats every `every` seconds with the current phase. A refusal or `cancel: true` sets `stop`; MISSED_BEATS failures
    in a row end it too (the lease has lapsed, so nothing may be posted)."""

    def __init__(self, hub: Hub, job: dict, worker: dict, every: float):
        super().__init__(daemon=True)
        self.hub, self.job, self.worker, self.every = hub, job, worker, every
        self.phase = "preparing"
        self.stop = threading.Event()   # set: the attempt is over, abandon the work
        self.done = threading.Event()   # set by the worker when it is finished with the thread
        self.reason: str | None = None
        self.misses = 0

    def beat(self) -> None:
        try:
            r = self.hub.heartbeat(self.job, self.phase, self.worker)
            self.misses = 0
            if r.get("cancel"):
                self.reason = "canceled"
                self.stop.set()
        except Refused as e:
            self.reason = e.reason
            self.stop.set()
        except HubError:
            self.misses += 1
            if self.misses >= MISSED_BEATS:
                self.reason = "heartbeat_lost"
                self.stop.set()

    def run(self) -> None:
        while not self.done.is_set() and not self.stop.is_set():
            self.beat()
            self.done.wait(self.every)


def subprocess_slice(spec: dict, stop: threading.Event, timeout: float, work: Path, cmd: list[str] | None = None) -> dict:
    """Slice in a child process group, so a stop kills Studio too. Returns the child's result dict, or
    {"ok": False, "outcome": "failed", "cause": ...} if it timed out or died; returns {"stopped": True} on stop."""
    spec_p, res_p = work / "spec.json", work / "result.json"
    spec_p.write_text(json.dumps(spec))
    res_p.unlink(missing_ok=True)
    p = subprocess.Popen(cmd or [sys.executable, "-m", "lab.quick.slice_child", str(spec_p), str(res_p)],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def kill():
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            p.kill()
        p.wait()
    deadline = time.monotonic() + timeout
    while p.poll() is None:
        if stop.is_set():
            kill()
            return {"stopped": True}
        if time.monotonic() > deadline:
            kill()
            return {"ok": False, "outcome": "failed", "cause": "slice_timeout",
                    "message": f"Bambu Studio didn't finish within {int(timeout)} s"}
        time.sleep(0.2)
    try:
        return json.loads(res_p.read_text())
    except (OSError, ValueError):
        return {"ok": False, "outcome": "failed", "cause": "worker_ended",
                "message": f"the slicing process ended without a result (exit {p.returncode})"}


@dataclass
class PassResult:
    status: str  # idle | sliced | failed | needs_attention | refused | busy | hub_error
    detail: str = ""
    job: str | None = None


def run_once(hub: Hub, *, worker: dict | None = None, base: Path | None = None, scratch: Path | None = None,
             slicer=subprocess_slice, heartbeat_every: float = 15.0, log=print) -> PassResult:
    """One pass; see the module docstring. `slicer(spec, stop, timeout, work)` is injectable for tests."""
    worker = worker or worker_record()
    try:
        claim = hub.claim(worker)
    except Refused as e:
        return PassResult("refused", e.reason)
    except HubError as e:
        return PassResult("hub_error", str(e))
    job = claim.get("job")
    if not job:
        return PassResult("idle", claim.get("why") or "")
    scratch = Path(scratch or Path(tempfile.gettempdir()) / "lab-quick-worker")
    work = scratch / job["id"] / job["attempt"]
    work.mkdir(parents=True, exist_ok=True)
    hb = Heartbeat(hub, job, worker, heartbeat_every)
    hb.beat()  # the first beat is synchronous: a refusal here means we never start
    if not hb.stop.is_set():
        hb.start()
    try:
        return _work(hub, job, worker, hb, work, base, slicer, log)
    except Refused as e:
        return PassResult("refused", e.reason, job["id"])
    except HubError as e:
        return PassResult("hub_error", str(e), job["id"])
    finally:
        hb.done.set()
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def _fail(hub, job, outcome, cause, message, hb) -> PassResult:
    hb.done.set()
    hub.complete(job, {"outcome": outcome, "cause": cause, "message": message[:300]})
    return PassResult(outcome, f"{cause}: {message}"[:300], job["id"])


def _work(hub, job, worker, hb, work, base, slicer, log) -> PassResult:
    def stopped() -> PassResult | None:
        return PassResult("refused", hb.reason or "canceled", job["id"]) if hb.stop.is_set() else None

    if (r := stopped()):
        return r
    model = work / f"model.{job['model']['ext'].lstrip('.')}"
    got = hub.download_model(job, model)
    if got != job["model"]["sha256"]:
        return _fail(hub, job, "failed", "slice_failed", "the model changed in transit (sha256 differs)", hb)
    base = base or next(iter(sorted(PRESET_DIR.glob("*.3mf"))), None)
    if base is None or not Path(base).is_file():
        return _fail(hub, job, "failed", "slice_failed", "this Mac has no Quick Print base preset (presets/quick/*.3mf)", hb)
    if (r := stopped()):
        return r
    hb.phase = "slicing"
    hb.beat()
    if (r := stopped()):
        return r
    spec = {"model": str(model), "base": str(base), "out_dir": str(work / "out"), "name": f"quick_{job['id']}",
            "settings": job.get("settings") or {}, "transform": job.get("transform"),
            "model_sha256": job["model"]["sha256"], "jobs_dir": str(work / "jobs")}
    res = slicer(spec, hb.stop, float(job.get("timeout_s", 1800)), work)
    if res.get("stopped") or hb.stop.is_set():
        return PassResult("refused", hb.reason or "canceled", job["id"])
    if not res.get("ok"):
        return _fail(hub, job, res.get("outcome", "failed"), res.get("cause", "slice_failed"), res.get("message", ""), hb)
    sl = res["slice"]
    artifact = Path(sl["sliced"])
    sha = _sha256_file(artifact)
    if sha != sl["sliced_sha256"] or artifact.stat().st_size > int(job.get("max_artifact_bytes", 1 << 62)):
        return _fail(hub, job, "failed", "output_invalid", "the sliced file changed or is too large to send", hb)
    hb.phase = "uploading"
    hb.beat()
    if (r := stopped()):
        return r
    hub.upload_artifact(job, artifact, sha, hb.stop)
    if (r := stopped()):
        return r
    hb.done.set()
    out = hub.complete(job, {"outcome": "sliced", "artifact": {"sha256": sha, "bytes": artifact.stat().st_size},
                             "result": {"minutes": sl["minutes"], "grams": sl["grams"], "layers": sl["layers"],
                                        "studio_version": sl["studio_version"], "start_block_lines": sl["start_block_lines"],
                                        "base_sha256": sl["base_sha256"], "project_sha256": sl["project_sha256"],
                                        "model_sha256": sl["model_sha256"], "settings": sl["settings"]}})
    log(f"quick worker: {job['id']} sliced, {out.get('state', 'ok')}")
    return PassResult("sliced", out.get("state", ""), job["id"])


def cmd_worker(args) -> int:
    scratch = HOME / "quick-worker"
    try:
        with Lock(HOME / "quick-worker.lock"):
            ts = targets(args.base)
            t = ts[0] if ts else None
            if t is None or isinstance(t, tuple):
                print(f"quick worker: {t[1] if t else 'no Pi Hub key on this Mac'}", file=sys.stderr)
                return 1
            res = run_once(Hub(t), base=Path(args.preset) if args.preset else None, scratch=scratch)
    except BlockingIOError:
        return 0  # another worker holds the lock: not a failure
    if res.status in ("idle", "sliced", "refused"):
        if res.status != "idle":
            print(f"quick worker: {res.status} {res.job or ''} {res.detail}".strip())
        return 0
    print(f"quick worker: {res.status} {res.job or ''}: {res.detail}".strip(), file=sys.stderr)
    return 1


def register(qsub) -> None:
    w = qsub.add_parser("worker", help="Quick Print worker: claim one slice job from the Pi Hub, slice it, send it back")
    w.add_argument("--base", help="the Pi Hub address (default: the lab's)")
    w.add_argument("--preset", help="the Studio-saved base project (default: the one in presets/quick)")
    w.set_defaults(fn=cmd_worker)
