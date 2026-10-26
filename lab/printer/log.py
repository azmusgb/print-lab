"""Turn the printer's MQTT reports into one line per layer and per change, and summarise fan events by height.

Bambu printers send a full report after a `pushall` request and partial reports after that, so reports are merged
into one running state. Only fields that describe the print's thermal and fan state are kept; field names differ
between printer families (P1/X1 `big_fan1_speed`, H2D/X2D `device.airduct…`), so fields are chosen by name pattern.
"""
import re

TRACKED = re.compile(r"(fan|temp|airduct|ctc|chamber|^layer_num$|^total_layer_num$|gcode_state|print_error|^hms"
                     r"|mc_percent|stg_cur|mc_print_stage)", re.I)
EVENT_FIELDS = re.compile(r"(fan|airduct)", re.I)
TEMP_STEP = 1.0  # °C; smaller temperature changes don't earn a line of their own


def _walk(obj, prefix: str, out: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            _walk(v, f"{prefix}.{i}", out)
    else:
        out[prefix] = obj


def flatten(report: dict) -> dict:
    """The tracked fields of one report's `print` block, with dotted names for nested values."""
    flat: dict = {}
    _walk(report.get("print") or {}, "", flat)
    return {k: v for k, v in flat.items() if TRACKED.search(k)}


class StateMerger:
    """The printer's state as of the latest report: partial reports update only the fields they carry."""

    def __init__(self):
        self.state: dict = {}

    def update(self, report: dict) -> dict:
        # A list in a report is the whole list: drop entries the printer no longer lists (e.g. cleared HMS codes).
        for prefix in _list_paths(report.get("print") or {}, ""):
            for k in [k for k in self.state if k == prefix or k.startswith(prefix + ".")]:
                del self.state[k]
        self.state.update(flatten(report))
        return self.state


def _list_paths(obj, prefix: str) -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _list_paths(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        out.append(prefix)
    return out


def _is_temp(key: str) -> bool:
    return "temp" in key.lower()


def _changed(old: dict, new: dict) -> list[str]:
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if a == b:
            continue
        if _is_temp(k) and isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < TEMP_STEP:
            continue
        out.append(k)
    return out


class LayerLog:
    """Decides when the state deserves a line: on a new layer, or when anything tracked changed since the last line
    (temperatures only when they moved by TEMP_STEP or more)."""

    def __init__(self):
        self.last: dict | None = None

    def offer(self, state: dict, *, t: float) -> dict | None:
        layer = state.get("layer_num")
        if self.last is None:
            line = {"t": t, "layer": layer, "changed": [], "state": dict(state)}
        else:
            changed = _changed(self.last["state"], state)
            if layer == self.last["layer"] and not [c for c in changed if c != "mc_percent"]:
                return None
            if not changed:
                return None
            line = {"t": t, "layer": layer, "changed": [c for c in changed if c not in ("layer_num", "mc_percent")],
                    "state": dict(state)}
        self.last = line
        return line


def heights_from_gcode(gcode: str) -> dict[int, float]:
    """Layer number (1-based, in print order) → the layer's top height in mm, from the slice's own markers."""
    out, layer = {}, 0
    for raw in gcode.splitlines():
        if raw.startswith("; CHANGE_LAYER"):
            layer += 1
        elif raw.startswith("; Z_HEIGHT:") and layer and layer not in out:
            out[layer] = round(float(raw.split(":", 1)[1]), 3)
    return out


def summarize(lines: list[dict], heights: dict[int, float]) -> list[dict]:
    """Every change of a fan or air-duct field between consecutive lines, with the layer and height it happened at."""
    events, prev = [], None
    for line in lines:
        s = line["state"]
        if prev is not None:
            for k in sorted(set(prev) | set(s)):
                if EVENT_FIELDS.search(k) and prev.get(k) != s.get(k):
                    events.append({"layer": line["layer"], "z_mm": heights.get(line["layer"]), "t": line["t"],
                                   "field": k, "from": prev.get(k), "to": s.get(k)})
        prev = s
    return events


def match_marks(marks: list[dict], events: list[dict], *, within_mm: float = 0.6) -> list[dict]:
    """For each defect height the owner marked, the logged events within `within_mm` of it. A match is a lead to
    test, not a cause."""
    out = []
    for m in marks:
        z = m.get("defect_z_mm") if m.get("defect_z_mm") is not None else m.get("mark_z_mm")
        near = [e for e in events if z is not None and e.get("z_mm") is not None and abs(e["z_mm"] - z) <= within_mm]
        out.append({**m, "events": near})
    return out
