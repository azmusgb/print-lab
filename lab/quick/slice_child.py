"""The slicing step of the Quick Print worker, run as its own process so the worker can kill it (and Studio under it)
the moment the hub cancels or refuses the attempt. Reads a spec JSON, writes a result JSON; never talks to the hub.

    python -m lab.quick.slice_child <spec.json> <result.json>
Spec: {model, base, out_dir, name, settings, transform, model_sha256, jobs_dir}.
Result: {ok: true, slice: {...}} or {ok: false, outcome, cause, message}."""
import json
import sys
from pathlib import Path

CAUSES_FAILED = ("slice_failed", "slice_timeout", "studio_version", "missing_binary", "output_invalid")


def classify(e: Exception) -> dict:
    """The hub's outcome and cause for a slicing exception (A19 P3a contract)."""
    from lab.jobs import LabToolError
    msg = str(e)[:300]
    if isinstance(e, LabToolError):
        low = (e.job.stderr + " " + msg).lower()
        if "timeoutexpired" in low:
            return {"outcome": "failed", "cause": "slice_timeout", "message": msg}
        if "not found at" in low or "couldn't read the bambu studio version" in low:
            return {"outcome": "failed", "cause": "missing_binary", "message": msg}
        if "is installed, but the lab is checked against" in low:
            return {"outcome": "failed", "cause": "studio_version", "message": msg}
        return {"outcome": "failed", "cause": "slice_failed", "message": msg}
    if "start sequence" in msg:
        return {"outcome": "needs_attention", "cause": "start_sequence", "message": msg}
    if "valid 3MF" in msg or "The slice has no" in msg:
        return {"outcome": "failed", "cause": "output_invalid", "message": msg}
    return {"outcome": "failed", "cause": "slice_failed", "message": msg}


def run(spec: dict) -> dict:
    import numpy as np

    from lab.quick.engine import slice_quick
    try:
        tf = spec.get("transform")
        res = slice_quick(Path(spec["model"]), Path(spec["base"]), Path(spec["out_dir"]), settings=spec.get("settings") or {},
                          transform=np.array(tf, dtype=float).reshape(4, 4) if tf else None,
                          expect_model_sha256=spec.get("model_sha256"), name=spec.get("name", "quick"),
                          jobs_dir=spec.get("jobs_dir"))
        return {"ok": True, "slice": res.to_json()}
    except Exception as e:
        return {"ok": False, **classify(e)}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    spec = json.loads(Path(argv[0]).read_text())
    Path(argv[1]).write_text(json.dumps(run(spec)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
