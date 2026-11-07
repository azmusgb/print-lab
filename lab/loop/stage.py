"""`lab exp stage`: put the checked build in Bambuddy's `print-lab` folder, for Pi Hub to start (spec: one tap to print,
S1-S3; platform amendment A12).

Staging re-runs the check as `lab exp send` does (S2), uploads the build's sliced file, downloads it back and compares
its sha256 with the build's (S3): a mismatch deletes the upload and stages nothing. A staged build records its library
file under `staged`, and the experiment the status the check found (ready or approved); Pi Hub starts only a file the mirror names there. Staging never queues or starts anything.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

from lab import bambuddy
from lab.loop.commands import load_experiment, save_experiment
from lab.loop.send import checked_build
from lab.records.project import ProjectPaths
from lab.records.store import now, record_lock


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_filament(sliced) -> dict | None:
    """What the sliced file asks slot 1 to hold: {"type", "colour"} from its first filament entry, so Pi Hub's Start
    sheet can compare it with the AMS tray. None when the file doesn't say."""
    try:
        from lab.adapters.bambu import read_settings
        cfg = read_settings(sliced) or {}
    except Exception:
        return None
    pick = lambda key: next((str(v) for v in (cfg.get(key) or []) if v), None)  # noqa: E731
    out = {"type": pick("filament_type"), "colour": pick("filament_colour")}
    return out if any(out.values()) else None


def _file_model(build: dict) -> str | None:
    """The source model's plain name ("RIFT 10IN batch5 shadow storm"), from the first model the build was made from."""
    models = (build.get("inputs") or {}).get("model") or {}
    first = next(iter(models), None)
    name = Path(first).name.split(".")[0].replace("_", " ").strip() if first else ""
    return name or None


def _file_size(sliced) -> dict | None:
    """What the plate prints, in mm: {"x", "y", "z", "brim"} from the slicer's plate box and its top layer. The box
    includes any brim, so `brim` says whether to expect that. None when the file doesn't say."""
    try:
        with zipfile.ZipFile(sliced) as z:
            box = json.loads(z.read("Metadata/plate_1.json"))["bbox_all"]
            top = re.search(rb"^; max_z_height: ([0-9.]+)", z.read("Metadata/plate_1.gcode"), re.M)
            from lab.adapters.bambu import read_settings
            brim = (read_settings(sliced) or {}).get("brim_type") not in (None, "no_brim", "auto_brim")
        out = {"x": round(box[2] - box[0], 1), "y": round(box[3] - box[1], 1),
               "z": float(top.group(1)) if top else None, "brim": bool(brim)}
        return out if out["x"] > 0 and out["y"] > 0 else None
    except Exception:
        return None


def stage(paths: ProjectPaths, exp_id: str, *, client=bambuddy) -> dict:
    """Stage the build the check passes; {"experiment", "build", "file", "library_file", "folder", "already"}.
    `client` is the Bambuddy adapter (a fake in tests)."""
    r = checked_build(paths, exp_id, "stage")
    b = r.build
    f = paths.root / b["sliced"]
    data = f.read_bytes()
    if _sha256(data) != b.get("sliced_sha256"):  # the check verifies the files; this is the bytes about to go up
        raise ValueError(f"{f.name} changed since {b['id']} was built; rebuild it with `lab exp build {exp_id} "
                         "--replace`.")
    version = client.version()
    out = {"experiment": exp_id, "build": b["id"], "file": f.name}
    staged = b.get("staged")
    if staged and staged.get("sha256") == b["sliced_sha256"]:
        rec = client.library_file(staged["library_file"])
        if rec is not None:
            return out | {"library_file": staged["library_file"], "folder": staged["folder"], "already": True}
    folder = client.staging_folder()
    up = client.upload(f, folder)
    fid = up["id"]
    back = client.download(fid)
    if _sha256(back) != b["sliced_sha256"]:
        client.delete(fid)
        raise ValueError(f"Bambuddy's copy of {f.name} (library file {fid}) isn't the checked build: sha256 "
                         f"{_sha256(back)[:12]}… != {b['sliced_sha256'][:12]}…. It was deleted; nothing is staged.")
    with record_lock(paths.locks, exp_id, f"lab exp stage {exp_id}"):
        e = load_experiment(paths, exp_id)
        build = next((x for x in e.get("builds") or [] if x["id"] == b["id"]), None)
        newest = next((x for x in reversed(e.get("builds") or []) if x.get("ok")), None)
        if build is None or build is not newest or build.get("sliced_sha256") != b["sliced_sha256"]:
            client.delete(fid)
            raise ValueError(f"{exp_id} was rebuilt while {b['id']} was being staged; the upload was deleted. "
                             f"Stage it again.")
        if e["status"] in ("built", "ready", "needs_approval", "approved"):
            e["status"] = r.status  # what the check just found, as `lab exp check` records it
        build["staged"] = {"library_file": fid, "folder": folder, "sha256": b["sliced_sha256"], "at": now(),
                           "bambuddy": version, "filament": _file_filament(f),
                           "model": _file_model(b), "size": _file_size(f)}
        save_experiment(paths, e)
    return out | {"library_file": fid, "folder": folder, "already": False}


IDLE_MINUTES = 10  # the spec's "idle for 10 minutes" before `lab pull` stages, so a just-finished plate isn't offered
RETRY_SECONDS = 3600  # a build that failed to stage is tried again an hour later, not on every pull


def idle_since(entries: list[dict] | None):
    """When the printer last finished, from Bambuddy's print log (newest first): None while a print is running or the
    log can't be read; the epoch when it has no prints."""
    from datetime import datetime, timezone
    if entries is None:
        return None
    if any(x.get("status") == "printing" for x in entries[:5]):
        return None
    ends = [bambuddy.parse_time(x.get("completed_at")) for x in entries]
    ends = [t for t in ends if t is not None]
    return max(ends) if ends else datetime.fromtimestamp(0, timezone.utc)


def stage_waiting(paths: ProjectPaths, entries: list[dict] | None, failed: dict, *, client=bambuddy,
                  now=None) -> list[dict]:
    """`lab pull`'s staging (A12 plan, decision 7): every ready or approved experiment whose newest build isn't staged
    yet is staged, once the printer has been idle IDLE_MINUTES. `failed` ({build id: epoch seconds}) is updated in place
    so a failure waits RETRY_SECONDS. Events like apply_pending's: applied, or error with the reason."""
    import time
    from datetime import datetime, timedelta, timezone
    from lab.loop.commands import all_experiments
    now = now or datetime.now(timezone.utc)
    since = idle_since(entries)
    if since is None or now - since < timedelta(minutes=IDLE_MINUTES):
        return []
    events = []
    for e in all_experiments(paths).values():
        if e["status"] not in ("ready", "approved"):
            continue
        b = next((x for x in reversed(e.get("builds") or []) if x.get("ok")), None)
        if not b or (b.get("staged") or {}).get("sha256") == b.get("sliced_sha256"):
            continue
        if time.time() - failed.get(b["id"], 0) < RETRY_SECONDS:
            continue
        try:
            r = stage(paths, e["id"], client=client)
            failed.pop(b["id"], None)
            events.append({"id": f"stage-{b['id']}", "status": "applied",
                           "message": f"{e['id']} staged in Bambuddy ({b['id']}, library file {r['library_file']}): "
                                      "ready to start from Pi Hub."})
        except (ValueError, bambuddy.BambuddyError) as err:
            failed[b["id"]] = time.time()
            events.append({"id": f"stage-{b['id']}", "status": "error",
                           "message": f"Couldn't stage {e['id']} ({b['id']}): {err}"})
    return events
