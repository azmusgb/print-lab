"""`lab source <term>`: where Bambu Studio's own code uses a setting, read at the tag that matches the installed slicer
(v02.08.02.61 for 02.08.02.61), so a question about how a setting behaves can cite the code instead of a guess.

The source (src/ only) is checked out once per tag into ~/.cache/print-lab/bambustudio/<tag> and reused offline.
A finding the owner wants kept (`--note`) is recorded in capabilities/<version>-source.json. The code says what the
slicer intends; a real slice still proves it before the lab relies on it (capability tests).
"""
import json
import os
import subprocess
from pathlib import Path

from lab.adapters.bambu import EXPECTED_VERSION
from lab.records.store import atomic_write_json, now

UPSTREAM = "https://github.com/bambulab/BambuStudio"
CAP_DIR = Path(__file__).resolve().parent.parent / "capabilities"
CONTEXT = 2  # lines either side of a hit


def _cache() -> Path:
    return Path(os.environ.get("LAB_SOURCE_CACHE", Path.home() / ".cache" / "print-lab" / "bambustudio"))


def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def checkout(version: str) -> tuple[str, Path]:
    """The tag for this slicer version and its local src/ checkout (cloned on first use)."""
    tag = f"v{version}"
    where = _cache() / tag
    if (where / "src").is_dir():
        return tag, where
    repo = os.environ.get("LAB_BAMBU_SOURCE_REPO", UPSTREAM)
    where.parent.mkdir(parents=True, exist_ok=True)
    tmp = where.with_name(tag + ".partial")
    if tmp.exists():
        subprocess.run(["rm", "-rf", str(tmp)], check=True)
    r = _git("clone", "-q", "--depth", "1", "--branch", tag, "--filter=blob:none", "--sparse", repo, str(tmp))
    if r.returncode != 0:
        subprocess.run(["rm", "-rf", str(tmp)], check=False)
        if "not found" in r.stderr or "Remote branch" in r.stderr:
            raise ValueError(f"Bambu Studio has no tag {tag} at {repo}; is {version} the installed version?")
        raise OSError(f"Couldn't fetch Bambu Studio {tag}: {r.stderr.strip()[:200]}")
    _git("sparse-checkout", "set", "src", cwd=tmp)
    tmp.rename(where)
    return tag, where


def lookup(term: str, version: str = EXPECTED_VERSION, note: str | None = None, limit: int = 40) -> dict:
    tag, where = checkout(version)
    r = _git("grep", "-n", "-w", "-F", "--", term, "--", "src", cwd=where)
    hits = []
    for line in r.stdout.splitlines()[:limit]:
        path, n, _ = line.split(":", 2)
        n = int(n)
        text = (where / path).read_text(errors="replace").splitlines()
        hits.append({"path": path, "line": n,
                     "context": "\n".join(text[max(0, n - 1 - CONTEXT):n + CONTEXT]),
                     "url": f"{UPSTREAM}/blob/{tag}/{path}#L{n}"})
    out = {"term": term, "version": version, "tag": tag, "hits": hits,
           "more": max(0, len(r.stdout.splitlines()) - limit)}
    if note:
        f = CAP_DIR / f"{version}-source.json"
        saved = json.loads(f.read_text()) if f.exists() else []
        saved.append({"term": term, "tag": tag, "at": now(), "note": note,
                      "hits": [f"{h['path']}:{h['line']}" for h in hits]})
        CAP_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_json(f, saved)
    return out


def cmd_source(args) -> int:
    r = lookup(args.term, note=args.note, limit=args.limit)
    if not r["hits"]:
        print(f"'{args.term}' isn't in Bambu Studio {r['tag']} (src/).")
        return 1
    for h in r["hits"]:
        print(f"{h['path']}:{h['line']}  {h['url']}")
        print("    " + h["context"].replace("\n", "\n    ") + "\n")
    if r["more"]:
        print(f"... and {r['more']} more (--limit)")
    if args.note:
        print(f"Noted in capabilities/{r['version']}-source.json")
    return 0


def register(sub) -> None:
    s = sub.add_parser("source", help="where Bambu Studio's code (the installed version's tag) uses a setting")
    s.add_argument("term", help="a setting key or name, e.g. max_volumetric_speed")
    s.add_argument("--note", help="keep this finding, in your words, against the slicer version")
    s.add_argument("--limit", type=int, default=40)
    s.set_defaults(fn=cmd_source)
