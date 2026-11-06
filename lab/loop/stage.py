"""`lab exp stage`: put the checked build in Bambuddy's `print-lab` folder, for Pi Hub to start (spec: one tap to print,
S1-S3; platform amendment A12).

Staging re-runs the check as `lab exp send` does (S2), uploads the build's sliced file, downloads it back and compares
its sha256 with the build's (S3): a mismatch deletes the upload and stages nothing. A staged build records its library
file under `staged`, and the experiment the status the check found (ready or approved); Pi Hub starts only a file the mirror names there. Staging never queues or starts anything.
"""
import hashlib

from lab import bambuddy
from lab.loop.commands import load_experiment, save_experiment
from lab.loop.send import checked_build
from lab.records.project import ProjectPaths
from lab.records.store import now, record_lock


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
                           "bambuddy": version}
        save_experiment(paths, e)
    return out | {"library_file": fid, "folder": folder, "already": False}
