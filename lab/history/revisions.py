"""What each past revision was: its SCAD parameters, the slicer settings in its 3MF, and measured mesh facts."""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lab.adapters.bambu import read_settings
from lab.adapters.threemf import load_object
from lab.geometry.facets import facet_switches, front_facets
from lab.geometry.mesh import load_mesh, mesh_facts
from lab.geometry.sections import layer_outlines, outline_jumps
from lab.history.inventory import Artifact

_PARAM = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);", re.M)


@dataclass
class Revision:
    version: int
    artifacts: list[str] = field(default_factory=list)
    scad_params: dict = field(default_factory=dict)
    settings: dict | None = None
    nozzle_profile: str | None = None
    nozzle_in_name: str | None = None
    scad_code: str | None = None
    mesh: dict = field(default_factory=dict)


def _value(text: str):
    t = text.strip()
    if t in ("true", "false"):
        return t == "true"
    try:
        f = float(t)
        return int(f) if f.is_integer() and "." not in t else f
    except ValueError:
        return t.strip('"')


def scad_params(path: Path) -> dict:
    """Top-level `name = value;` assignments with literal values (expressions are kept as text)."""
    return {k: _value(v) for k, v in _PARAM.findall(Path(path).read_text(errors="replace"))}


def scad_code(path: Path) -> str:
    """The SCAD source without comments, blank lines and top-level parameter assignments: changes here are changes to
    how the model is built, not to its numbers."""
    import hashlib
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", Path(path).read_text(errors="replace"), flags=re.S)
    text = _PARAM.sub("", text)
    body = "\n".join(l.strip() for l in text.splitlines() if l.strip())
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _measure(m) -> dict:
    facts = asdict(mesh_facts(m))
    facts["switches"] = [asdict(s) for s in facet_switches(front_facets(m))]
    facts["outline_jumps"] = [j for j in outline_jumps(layer_outlines(m)) if j[0] > 5]
    return facts


def revisions(artifacts: list[Artifact], lineage: str) -> list[Revision]:
    from lab.history.inventory import dedupe
    mine = [a for a in dedupe([a for a in artifacts if a.lineage == lineage]) if a.version is not None
            and not a.duplicate_of]
    out = []
    for v in sorted({a.version for a in mine}):
        arts = [a for a in mine if a.version == v]
        rev = Revision(version=v, artifacts=[a.path for a in arts])
        for a in (a for a in arts if a.kind == "scad"):
            rev.scad_params = scad_params(Path(a.path))
            rev.scad_code = scad_code(Path(a.path))
        projects = [a for a in arts if a.kind == "3mf"]
        if projects:
            p = next((a for a in projects if a.nozzle == "0.4"), projects[0])
            rev.nozzle_in_name = p.nozzle
            rev.settings = read_settings(Path(p.path))
            nd = rev.settings.get("nozzle_diameter")
            rev.nozzle_profile = f"{float(nd[0] if isinstance(nd, list) else nd):g}" if nd else None
        for a in arts:
            if a.kind == "stl" and a.size_in and f"{a.size_in}in" not in rev.mesh:
                try:
                    rev.mesh[f"{a.size_in}in"] = _measure(load_mesh(Path(a.path)))
                except Exception as e:  # one unreadable file must not stop the history
                    rev.mesh[f"{a.size_in}in"] = {"error": str(e)}
        for p in projects:
            for size in ("3in", "6in", "10in"):
                if size not in rev.mesh:
                    try:
                        rev.mesh[size] = _measure(load_object(Path(p.path), size))
                    except Exception:
                        pass
        out.append(rev)
    return out
