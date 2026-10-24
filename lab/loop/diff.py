"""The one-factor rule, checked on the finished build: every difference between the variants (and against any
reference variant on an earlier plate) must be the declared factor or a declared dependent adjustment (spec: The
actual-difference check)."""
import hashlib
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np

from lab.adapters.bambu import read_settings
from lab.loop.outcome import _factors
from lab.records.project import ProjectPaths

SKIP = {"name", "extruder"}


def _norm(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def _objects(art: Path) -> list[tuple[str, dict]]:
    with zipfile.ZipFile(art) as z:
        root = ET.fromstring(z.read("Metadata/model_settings.config"))
    out = []
    for o in root.findall("object"):
        meta = {m.get("key"): m.get("value") for m in o.findall("metadata")}
        out.append((meta.get("name", ""), {k: v for k, v in meta.items() if k not in SKIP}))
    return out


def _variant_of(name: str) -> str:
    return re.sub(r" \(\d+ of \d+\)$", "", name)


def variant_facts(art: Path) -> dict[str, dict]:
    """Per variant on a built plate: its effective settings, copies and a mesh fingerprint."""
    from lab.adapters.threemf import load_object
    base = read_settings(art) or {}
    facts: dict[str, dict] = {}
    for name, own in _objects(art):
        vid = _variant_of(name)
        if vid in facts:
            facts[vid]["copies"] += 1
            continue
        eff = {k: _norm(v) for k, v in base.items()}
        for k, v in own.items():
            eff[k] = [str(v)] * len(eff[k]) if k in eff and len(eff[k]) > 1 else [str(v)]
        m = load_object(art, name)
        verts = m.vertices
        if m.bounds[1][2] > 2.0:  # ignore the ID tab (first 1.6 mm): its text differs by design
            verts = verts[verts[:, 2] > 1.7]
        mesh = hashlib.sha256(np.round(np.asarray(sorted(map(tuple, np.round(verts, 3)))), 3).tobytes()).hexdigest()
        facts[vid] = {"settings": eff, "copies": 1, "mesh": mesh}
    return facts


def _compare(a_id, a, b_id, b) -> list[dict]:
    out = []
    for k in sorted(set(a["settings"]) | set(b["settings"])):
        if a["settings"].get(k) != b["settings"].get(k):
            out.append({"where": "settings", "key": k, "a": a_id, "b": b_id,
                        "a_value": a["settings"].get(k), "b_value": b["settings"].get(k)})
    if a["copies"] != b["copies"]:
        out.append({"where": "plate", "key": "copies", "a": a_id, "b": b_id, "a_value": a["copies"],
                    "b_value": b["copies"]})
    if a["mesh"] != b["mesh"]:
        out.append({"where": "geometry", "key": "mesh", "a": a_id, "b": b_id})
    return out


def actual_differences(paths: ProjectPaths, exp: dict, build: dict, others: dict | None = None) -> list[dict]:
    from lab.records.schema import load
    facts = variant_facts(paths.root / build["artifact"])
    ids = [v["id"] for v in exp["variants"] if v.get("role", "variant") == "variant" and v["id"] in facts]
    diffs = []
    st = (exp.get("build_spec") or {}).get("stepped")
    if st and "STEP-1" in facts and "STEP-2" in facts:
        from lab.adapters.threemf import read_height_ranges
        ids = ["STEP-1", "STEP-2"]
        for idx, rs in read_height_ranges(paths.root / build["artifact"]).items():
            for _, _, opts in rs:
                for k in opts:
                    if k != st["key"]:
                        diffs.append({"where": "height_ranges", "key": k, "a": "STEP-1", "b": "STEP-2"})
    for other in ids[1:]:
        diffs += _compare(ids[0], facts[ids[0]], other, facts[other])
    for v in exp["variants"]:
        if v.get("role") == "anchor" and v["id"] in facts:
            oid = v["same_as"].rsplit("-", 1)[0]
            from lab.loop.outcome import printed_build
            orig = (others or {}).get(oid) or (load(paths.experiments / f"{oid}.json", "experiment")
                                               if (paths.experiments / f"{oid}.json").exists() else {})
            ob = printed_build(orig)
            if ob and ob.get("artifact") and (paths.root / ob["artifact"]).exists():
                of = variant_facts(paths.root / ob["artifact"])
                if v["same_as"] in of:
                    mine, theirs = dict(facts[v["id"]]), dict(of[v["same_as"]])
                    mine["copies"] = theirs["copies"]  # the anchor is one piece of what was printed
                    diffs += [{**d, "anchor": True} for d in _compare(v["same_as"], theirs, v["id"], mine)]
    for ref in exp.get("reference_variants") or []:
        rexp_id = ref.rsplit("-", 1)[0]
        rexp = (others or {}).get(rexp_id)
        if rexp is None and (paths.experiments / f"{rexp_id}.json").exists():
            rexp = load(paths.experiments / f"{rexp_id}.json", "experiment")
        from lab.loop.outcome import printed_build
        rb = printed_build(rexp or {})
        if not rb or not (paths.root / rb["artifact"]).exists():
            continue
        rf = variant_facts(paths.root / rb["artifact"])
        if ref in rf:
            for vid in ids:
                diffs += _compare(ref, rf[ref], vid, facts[vid])
    return diffs


def undeclared(diffs: list[dict], exp: dict) -> tuple[list[dict], list[dict]]:
    """(differences nobody declared, differences inside a bundle factor)."""
    f = _factors().get(exp["factor"]["name"], {})
    adjust = set((exp.get("dependent_adjustments") or {}).keys())
    bad, bundle = [], []
    for d in diffs:
        if d.get("anchor"):
            bad.append(d)  # an anchor must be identical to what it repeats
            continue
        if f.get("kind") == "setting" and d["where"] == "settings" and d["key"] == f["settings_key"]:
            continue
        if f.get("kind") == "plate" and d["where"] == "plate":
            continue
        if d["where"] == "settings" and d["key"] in adjust:
            continue
        if f.get("scope") == "bundle" and ((f["kind"] == "model_version" and d["where"] == "geometry")
                                           or (f["kind"] == "filament_profile" and d["where"] == "settings")):
            bundle.append(d)
            continue
        bad.append(d)
    return bad, bundle
