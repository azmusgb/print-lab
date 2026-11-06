"""The gallery: one page per `lab design make` run, so the owner can compare the kept candidates and pick one.

Drawn with the appliance-ui kit (assets/ui, copied from the kit unchanged), as the Home Platform design contract asks.
Each kept candidate shows its face, print time and filament from the slice, the heights where the slice prints sparse
infill (the risk bands), warnings, and the command that registers it as a source. Dropped ones are listed with why."""
import json
from html import escape
from pathlib import Path

from lab.adapters.bambu import EXPECTED_VERSION
from lab.records.project import ProjectPaths

_UI = Path(__file__).resolve().parent / "assets" / "ui"
_FONTS = "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,400..700&display=swap"

_STYLE = """
body{margin:0;background:var(--ui-bg);color:var(--ui-text);font:400 var(--ui-fs-3)/1.45 var(--ui-font)}
.wrap{max-width:80rem;margin:0 auto;padding-block:calc(var(--ui-space)*8);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,17rem),1fr));gap:calc(var(--ui-space)*8)
  calc(var(--ui-space)*6);margin:0;padding:0;list-style:none}
.cand{display:grid;gap:calc(var(--ui-space)*2.5);align-content:start;min-width:0}
.cand svg{display:block;width:100%;height:auto;max-width:100%}
.cand h3{margin:0;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;font:650 var(--ui-fs-4)/1.2 var(--ui-font);
  font-stretch:var(--ui-stretch-heading)}
.cand h3 code,.mono{font:400 var(--ui-fs-2)/1.4 var(--ui-mono);color:var(--ui-muted)}
.facts{display:flex;flex-wrap:wrap;gap:4px 20px;margin:0}
.facts dt{color:var(--ui-muted);font-size:var(--ui-fs-1)}
.facts dd{margin:0;font:650 var(--ui-fs-4)/1.3 var(--ui-font);font-stretch:var(--ui-stretch-heading);
  font-variant-numeric:tabular-nums}
.strip{position:relative;height:10px;border-radius:var(--ui-r-1);background:var(--ui-surface-2);overflow:hidden}
.strip span{position:absolute;top:0;bottom:0;min-width:3px;background:var(--ui-warn)}
.note{margin:0;color:var(--ui-muted);font-size:var(--ui-fs-2)}
.warns{margin:0;padding:0;list-style:none;display:grid;gap:4px}
.warns li{display:flex;gap:8px;align-items:baseline;font-size:var(--ui-fs-2)}
.cmd{display:flex;gap:8px;align-items:start;min-width:0}
.cmd code{flex:1;min-width:0;padding:6px 8px;border-radius:var(--ui-r-1);background:var(--ui-surface-2);
  font:400 var(--ui-fs-1)/1.45 var(--ui-mono);overflow-wrap:anywhere;user-select:all}
.cmd .ui-btn{flex:none}
.wide{overflow-x:auto}
"""

_SCRIPT = """
document.querySelectorAll('[data-copy]').forEach(function (b) {
  b.addEventListener('click', function () {
    var code = document.getElementById(b.getAttribute('data-copy'));
    var done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); };
    var select = function () { var r = document.createRange(); r.selectNodeContents(code);
      var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = 'Selected'; };
    try { navigator.clipboard.writeText(code.textContent).then(done, select); } catch (e) { select(); }
  });
});
"""


def _kit_css() -> str:
    tokens = (_UI / "tokens.css").read_text()
    # The kit's @font-face points at a file beside it; a standalone page takes Archivo from Google Fonts instead.
    tokens = "\n".join(line for line in tokens.splitlines() if not line.startswith("@font-face"))
    return tokens + "\n" + (_UI / "components.css").read_text()


def _minutes(m: float) -> str:
    return f"{int(m // 60)} h {round(m % 60):02d} min"


def _range(vals: list[float], fmt) -> str:
    return "Not sliced" if not vals else fmt(min(vals)) if min(vals) == max(vals) else \
        f"{fmt(min(vals))} to {fmt(max(vals))}"


def _candidate(paths: ProjectPaths, gate: dict, run: dict, shared: set[str]) -> str:
    did, seed = gate["id"], gate["seed"]
    folder = paths.root / "designs" / gate["family"] / did
    svg = (folder / "render.svg").read_text() if (folder / "render.svg").is_file() else ""
    height = (gate.get("validity") or {}).get("extents_mm", [0, 0, 0])[2] or 1.0
    s = gate.get("slice") or {}
    if "minutes" in s:
        facts = (f'<dl class="facts"><div><dt>Print time</dt><dd>{_minutes(s["minutes"])}</dd></div>'
                 f'<div><dt>Filament</dt><dd>{s["grams"]:g} g</dd></div></dl>')
        bands = s.get("sparse_infill", [])
        marks = "".join(f'<span style="left:{b["from_mm"] / height * 100:.2f}%;width:'
                        f'{(b["to_mm"] - b["from_mm"]) / height * 100:.2f}%"></span>' for b in bands)
        words = "; ".join(f'{b["from_mm"]:g}–{b["to_mm"]:g} mm' for b in bands) or "none"
        risk = (f'<div class="strip" role="img" aria-label="Sparse infill along the {height:.0f} mm print height: '
                f'{escape(words)}">{marks}</div><p class="note">Sparse infill at {escape(words)} of '
                f'{height:.0f} mm (print height, bed at 0)</p>')
    elif "error" in s:
        facts, risk = "", f'<p class="ui-notice ui-notice--bad">Slice failed: {escape(s["error"])}</p>'
    else:
        facts, risk = "", '<p class="note">Not sliced (made with --no-slice).</p>'
    warns = "".join(f'<li><span class="ui-chip ui-chip--warn">Warning</span><span>{escape(w)}</span></li>'
                    for w in gate.get("warnings", []) if w not in shared)
    cmd = f"uv run lab design choose {did}"
    return (f'<li class="cand" id="d-{did}">{svg}<h3>Seed {seed} <code>{did}</code></h3>{facts}{risk}'
            + (f'<ul class="warns">{warns}</ul>' if warns else "")
            + f'<div class="cmd"><code id="c-{did}">{escape(cmd)}</code>'
              f'<button class="ui-btn" type="button" data-copy="c-{did}">Copy</button></div></li>')


def render(paths: ProjectPaths, run_path: Path) -> str:
    """The gallery page for one run record, as HTML."""
    run = json.loads(Path(run_path).read_text())
    gates, dropped = [], []
    for c in run["candidates"]:
        if c["dropped"]:
            dropped.append(c)
            continue
        g = paths.root / "designs" / run["family"] / c["id"] / "gate.json"
        gates.append(json.loads(g.read_text()) if g.is_file() else {**c, "family": run["family"]})
    sliced = [g["slice"] for g in gates if "minutes" in (g.get("slice") or {})]
    total = len(run["candidates"])
    params = ", ".join(f"{k} {v:g}" for k, v in run["params"].items()) or "the family's defaults"
    state = ("ok", "Finished") if run.get("finished") else ("unknown", "Still running or stopped")
    face = (f'<section class="ui-faceplate" aria-label="This run"><div class="ui-faceplate__main">'
            f'<div class="ui-faceplate__nameplate"><span>{escape(run["family"])} v{run["version"]}</span>'
            f'<span>Run {escape(run["run"])}</span><span class="ui-chip ui-chip--{state[0]}">{state[1]}</span></div>'
            f'<p class="ui-readout">{len(gates)}<span class="ui-readout__unit">of {total} kept</span></p>'
            f'<p class="ui-faceplate__caption">Every kept candidate is one valid closed solid, passes the project\'s '
            f'blocking design constraints and lab inspect, and was sliced with the settings of '
            f'{escape(run["base"])}. Parameters: {escape(params)}; only the facet layout (the seed) differs.</p>'
            f'<dl class="ui-faceplate__readings">'
            f'<div><dt>Print time</dt><dd>{_range([s["minutes"] for s in sliced], _minutes)}</dd></div>'
            f'<div><dt>Filament</dt><dd>{_range([s["grams"] for s in sliced], lambda g: f"{g:g} g")}</dd></div>'
            f'<div><dt>Dropped</dt><dd>{len(dropped)}</dd></div></dl></div></section>')
    # A warning every kept candidate shares is about the run (a setting, a parameter), so it's said once.
    shared = set.intersection(*(set(g.get("warnings", [])) for g in gates)) if gates else set()
    common = "".join(f'<p class="ui-notice ui-notice--warn">Every kept candidate: {escape(w)}</p>' for w in sorted(shared))
    kept = (f'{common}<ul class="grid">{"".join(_candidate(paths, g, run, shared) for g in gates)}</ul>' if gates else
            '<p class="ui-empty">No candidate passed the gate. The dropped list says why; widen the parameters or '
            'try other seeds.</p>')
    drop = ""
    if dropped:
        rows = "".join(f'<tr><td data-label="Seed" class="ui-table__num">{c["seed"]}</td>'
                       f'<td data-label="Design"><span class="mono">{c["id"]}</span></td>'
                       f'<td data-label="Why">{escape("; ".join(c["dropped"]))}</td></tr>' for c in dropped)
        drop = (f'<section class="ui-section"><h2>Dropped</h2><div class="wide ui-cq"><table class="ui-table '
                f'ui-table--stack" role="table"><caption>Candidates the gate refused, with its reasons</caption>'
                f'<thead><tr><th scope="col" class="ui-table__num">Seed</th><th scope="col">Design</th>'
                f'<th scope="col">Why</th></tr></thead><tbody>{rows}</tbody></table></div></section>')
    return (f'<title>{escape(paths.name)} designs, run {escape(run["run"][:8])}</title>\n'
            '<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<link rel="stylesheet" href="{_FONTS}">\n<style>{_kit_css()}\n{_STYLE}</style>\n'
            '<div class="wrap"><main class="ui-page">'
            '<header class="ui-page__head"><h1 class="ui-page__title">Design candidates</h1>'
            '<p class="ui-page__purpose">Generated by the lab, gated before anyone looks. Compare the faces and the '
            'risk bands, then register the one to print.</p></header>'
            f'{face}<section class="ui-section"><h2>Kept</h2><p class="ui-section__note">The face as seen from the '
            'front (relief exaggerated 3×). The bar is the print height, bed on the left; marks are where the slice '
            f'prints sparse infill.</p>{kept}</section>{drop}'
            f'<p class="ui-sources"><span>Base: {escape(run["base"])}</span><span>Started {escape(run["started"])}'
            f'</span><span>Slices: Bambu Studio {EXPECTED_VERSION}</span></p>'
            f'</main></div>\n<script>{_SCRIPT}</script>\n')


def write(paths: ProjectPaths, run_path: Path) -> Path:
    out = Path(run_path).with_suffix(".html")
    out.write_text(render(paths, run_path))
    return out
