"""`lab exp send`: open the build the check passed in Bambu Connect, so the printer gets exactly that G-code.

Re-slicing in Bambu Studio prints different G-code from the build that was checked and approved (E-020's first run).
Sending records nothing: the owner presses Print in Bambu Connect, then runs `lab exp start`.
"""
import subprocess

from lab.loop.commands import load_experiment
from lab.loop.guards import check_experiment
from lab.records.project import ProjectPaths

APP = "Bambu Connect"


def _open(app: str, path) -> None:
    subprocess.run(["open", "-a", app, str(path)], check=True)


def checked_build(paths: ProjectPaths, exp_id: str, verb: str = "send"):
    """The check, re-run as `start` would, when it passes (its `build` is the one to print); ValueError saying why
    when it doesn't."""
    e = load_experiment(paths, exp_id)
    if e["status"] == "printing":
        raise ValueError(f"{exp_id} is already printing ({e['print_runs'][-1]['id']}). If that print stopped, "
                         f"record it with `lab exp usage {e['print_runs'][-1]['id']} --failed-at …` first.")
    if e["status"] not in ("built", "ready", "needs_approval", "approved"):
        past = {"send": "sent"}.get(verb, f"{verb}d")
        raise ValueError(f"{exp_id} is {e['status']}; only a built experiment can be {past}.")
    b = next((x for x in reversed(e.get("builds") or []) if x.get("ok")), None)
    sliced = (b or {}).get("sliced")
    f = paths.root / sliced if sliced else None
    if f is None or not f.exists():  # before the check, which reads the sliced file
        raise ValueError(f"{(b or {}).get('id', exp_id)} has no sliced file{f' at {sliced}' if sliced else ''}; "
                         f"rebuild it with `lab exp build {exp_id} --replace`.")
    r = check_experiment(paths, exp_id)
    if r.status not in ("ready", "approved"):
        hint = (f"\nApprove it first: lab exp approve {exp_id} --reason \"…\"" if r.status == "needs_approval" else "")
        raise ValueError(f"Can't {verb} {exp_id}:\n"
                         + "\n".join(f"  {x.code}: {x.message}" for x in r.failed()) + hint)
    return r


def send(paths: ProjectPaths, exp_id: str, *, app: str = APP, opener=_open) -> dict:
    """Re-check the live state as `start` does, then open the passing build's sliced file in `app`."""
    b = checked_build(paths, exp_id).build
    f = paths.root / b["sliced"]
    opener(app, f)
    return {"experiment": exp_id, "build": b["id"], "file": str(f), "app": app}
