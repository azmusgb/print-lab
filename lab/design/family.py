"""What every family shares: its parameters, reading a params.json (a family's own or a Fusion export), and a design's
id."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Param:
    name: str
    default: float
    lo: float
    hi: float
    meaning: str
    unit: str = "mm"


def resolve(params: list[Param], given: dict[str, float] | None = None) -> dict[str, float]:
    """Defaults overlaid with `given`. Unknown names and values outside a parameter's range are refused, so a typo can't
    build a different part silently."""
    given = dict(given or {})
    known = {p.name: p for p in params}
    unknown = sorted(set(given) - set(known))
    if unknown:
        raise ValueError(f"unknown parameter(s): {', '.join(unknown)}")
    out = {}
    for p in params:
        v = float(given.get(p.name, p.default))
        if not p.lo <= v <= p.hi:
            raise ValueError(f"{p.name} = {v:g} {p.unit} is outside {p.lo:g}–{p.hi:g} {p.unit}")
        out[p.name] = v
    return out


def read_params(path: Path, only: list[Param] | None = None) -> dict[str, float]:
    """Parameter values from a params.json: Fusion's Send to lab shape ({"parameters": [{"name", "value", ...}]}) or a
    plain {"name": value} map. With `only`, names the family doesn't know are dropped (a Fusion design can carry extra
    user parameters)."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and isinstance(data.get("parameters"), list):
        values = {p["name"]: float(p["value"]) for p in data["parameters"]}
    elif isinstance(data, dict):
        values = {k: float(v) for k, v in data.items()}
    else:
        raise ValueError(f"{path}: not a params.json")
    if only is not None:
        names = {p.name for p in only}
        values = {k: v for k, v in values.items() if k in names}
    return values


def design_id(family: str, version: int, params: dict[str, float], seed: int) -> str:
    """A short, stable id for (family, version, params, seed): the same inputs always give the same id."""
    key = json.dumps({"family": family, "version": version, "seed": seed,
                      "params": {k: round(v, 6) for k, v in sorted(params.items())}}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:12]
