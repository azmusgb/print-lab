"""`lab page`: one read-only HTML page for a project, from its local records (no server, nothing written but the page).

A preview of the Stage 2 Print lab page (design: docs/superpowers/specs/2026-10-24-print-lab-design.md, "Print lab
page"): what needs the owner first (a verdict due, an approval), then each open question as a sentence with its
experiments, then the notebook (one row per experiment, its spine in the spool's colour) with the photos of each print
run. Phone first; dark and light follow the system.

Spool colours come from Bambuddy (the household's spool inventory) when it answers: the experiment's filament text is
matched against each spool's colour name. LAB_BAMBUDDY_URL changes the address; "off" skips it.
"""
import html
import json
import re
import os
import urllib.request
from datetime import datetime
from pathlib import Path

NEUTRAL = "#8a8f98"
STATUS = {  # label, tone
    "draft": ("Draft", "muted"), "planned": ("Planned", "muted"), "built": ("Built", "muted"),
    "needs_approval": ("Needs your approval", "attention"), "approved": ("Approved · ready to print", "info"),
    "printing": ("Printing", "info"), "printed": ("Printed · verdict due", "attention"),
    "answered": ("Answered", "good"), "stopped": ("Stopped", "muted"), "superseded": ("Superseded", "muted"),
}
OUTCOME = {"confirmed": ("Prediction confirmed", "good"), "refuted": ("Prediction refuted", "bad"),
           "inconclusive": ("Inconclusive", "muted")}


def _e(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _load_dir(d: Path) -> list:
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return out


def bambuddy_colours(url=None, timeout=2.0) -> dict:
    """Spool colour name (lower case) → '#rrggbb', from Bambuddy; {} when it's off or doesn't answer."""
    url = url if url is not None else os.environ.get("LAB_BAMBUDDY_URL", "http://10.0.0.30:8000")
    if not url or url == "off":
        return {}
    try:
        with urllib.request.urlopen(f"{url}/api/v1/inventory/spools", timeout=timeout) as r:
            spools = json.load(r)
    except Exception:
        return {}
    out = {}
    for s in spools if isinstance(spools, list) else []:
        name, rgba = (s.get("color_name") or "").strip().lower(), s.get("rgba") or ""
        if name and re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", rgba):  # never anything else into a style
            out[name] = "#" + rgba[:6]
    return out


def spool_colour(filament: str, colours: dict) -> str:
    text = (filament or "").lower()
    for name in sorted(colours, key=len, reverse=True):  # "light matte terracotta" before "terracotta"
        if name in text:
            return colours[name]
    return NEUTRAL


def _when(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%-d %b %H:%M")
    except ValueError:
        return ""


def _value(v) -> str:
    """A factor value for people: a file by its name, a per-feature list by its distinct values ("250/200")."""
    if isinstance(v, list):
        seen = []
        for x in v:
            if str(x) not in seen:
                seen.append(str(x))
        return "/".join(seen)
    return Path(str(v)).name if "/" in str(v) else str(v)


def _pill(label, tone) -> str:
    return f'<span class="pill" data-tone="{tone}">{_e(label)}</span>'


def _photos(exp: dict, pdir: Path) -> list:
    shots = []
    for run in exp.get("print_runs") or []:
        for p in run.get("photos") or []:
            rel = p.get("path")
            if rel and (pdir / rel).is_file():
                shots.append((run.get("id"), rel, p.get("source") or ""))
    return shots


def _needs(exp: dict) -> str | None:
    s = exp.get("status")
    if s == "needs_approval":
        return "Approve or change this test before it prints."
    if s == "printed" or (exp.get("print_runs") and not exp.get("owner_verdict") and s not in ("answered", "stopped", "superseded")):
        return "Record a verdict from the photos."
    return None


def _wipe(exp: dict, pdir: Path, others: dict) -> str:
    """The evidence wipe: this test's first photo over its reference's, with a handle to drag between them."""
    ref_ids = {str(v).rsplit("-", 1)[0] for v in exp.get("reference_variants") or []}  # "E-002-A" → "E-002"
    mine = _photos(exp, pdir)
    ref = next((_photos(others[r], pdir) for r in sorted(ref_ids) if r in others and _photos(others[r], pdir)), [])
    if not mine or not ref:
        return ""
    after, before = mine[0][1], ref[0][1]
    ref_id = next(r for r in sorted(ref_ids) if r in others and _photos(others[r], pdir))
    return f"""<figure class="wipe" style="--cut:50%">
  <img src="{_e(before)}" alt="{_e(ref_id)}, the reference">
  <img class="after" src="{_e(after)}" alt="{_e(exp.get('id'))}">
  <input type="range" min="0" max="100" value="50" aria-label="Drag between {_e(ref_id)} and {_e(exp.get('id'))}"
         oninput="this.parentNode.style.setProperty('--cut', this.value + '%')">
  <figcaption><span>{_e(ref_id)}</span><span>{_e(exp.get('id'))}</span></figcaption>
</figure>"""


def _experiment(exp: dict, pdir: Path, colours: dict, others: dict | None = None) -> str:
    label, tone = STATUS.get(exp.get("status") or "", (exp.get("status") or "Unknown", "muted"))
    colour = spool_colour(str((exp.get("controlled") or {}).get("filament") or ""), colours)
    factor = exp.get("factor") or {}
    values = " vs ".join(_e(_value(v)) for v in factor.get("values") or [])
    meta = " · ".join(x for x in (_e(exp.get("test_kind", "").replace("_", " ")),
                                  f'{_e(factor.get("name", "").replace("_", " "))}: {values}' if factor.get("name") else "") if x)
    verdict = exp.get("owner_verdict") or {}
    outcome = OUTCOME.get(exp.get("prediction_outcome") or "")
    shots = _photos(exp, pdir)
    gallery = ""
    if shots:
        gallery = '<div class="shots">' + "".join(
            f'<a href="{_e(rel)}" target="_blank" rel="noopener"><img src="{_e(rel)}" alt="{_e(exp["id"])} print {_e(run)} {_e(src)}" loading="lazy"></a>'
            for run, rel, src in shots) + "</div>"
    wipe = _wipe(exp, pdir, others or {})
    details = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in (
        ("Hypothesis", exp.get("hypothesis")), ("Prediction", exp.get("prediction")),
        ("Why this test", exp.get("why_this_test"))) if v)
    controlled = "".join(f"<dt>{_e(k.replace('_', ' ').capitalize())}</dt><dd>{_e(v)}</dd>"
                         for k, v in (exp.get("controlled") or {}).items() if v)
    ai = "".join(f'<p class="ai">AI reading ({_e(round((o.get("confidence") or 0) * 100))}% sure{", unconfirmed" if not o.get("confirmed") else ""}): '
                 f'{_e(o.get("assessment"))}</p>' for o in exp.get("ai_observations") or [])
    return f"""
<article class="exp" style="--spine:{_e(colour)}">
  <header>
    <span class="id">{_e(exp.get("id"))}</span>{_pill(label, tone)}{_pill(*outcome) if outcome else ""}
  </header>
  <h3>{_e(exp.get("question_text"))}</h3>
  <p class="meta">{meta}</p>
  {f'<p class="verdict">Your verdict: {_e(verdict.get("note") or verdict.get("kind"))} <span class="when">{_e(_when(verdict.get("at")))}</span></p>' if verdict else ""}
  {wipe}
  {gallery}
  <details><summary>Details</summary><dl>{details}</dl>{f"<h4>Kept the same</h4><dl>{controlled}</dl>" if controlled else ""}{ai}</details>
</article>"""


def build(pdir: Path, colours: dict | None = None) -> str:
    pdir = Path(pdir)
    colours = bambuddy_colours() if colours is None else colours
    questions = _load_dir(pdir / "questions")
    exps = {e.get("id"): e for e in _load_dir(pdir / "experiments")}
    needs = [(e, _needs(e)) for e in exps.values() if _needs(e)]
    open_q = [q for q in questions if q.get("status") not in ("answered", "stopped")]

    needs_html = "".join(f'<li><a href="#{_e(e["id"])}"><b>{_e(e["id"])}</b> {_e(e.get("question_text"))}</a><span>{_e(why)}</span></li>'
                         for e, why in needs) or "<li class=\"empty\">Nothing needs you right now.</li>"
    q_html = ""
    for q in open_q:
        ids = q.get("experiments") or []
        done = sum(1 for i in ids if (exps.get(i) or {}).get("status") == "answered")
        plans = "".join(f'<li>After {_e(p.get("after"))}, if {_e(p.get("if"))}: {_e(p.get("next"))}</li>' for p in q.get("plans") or [])
        budget = q.get("budget") or {}
        current = next((exps[i] for i in reversed(ids) if i in exps and exps[i].get("status") not in ("answered", "stopped", "superseded")), None)
        now_html = ""
        if current:
            label, tone = STATUS.get(current.get("status") or "", (current.get("status") or "", "muted"))
            now_html = (f'<div class="now"><p class="qid"><a href="#{_e(current["id"])}">{_e(current["id"])}</a> {_pill(label, tone)}</p>'
                        f'<p class="now-q">{_e(current.get("question_text"))}</p>'
                        + (f'<p class="why"><b>Why this test?</b> {_e(current.get("why_this_test"))}</p>' if current.get("why_this_test") else "")
                        + "</div>")
        q_html += f"""
<section class="question">
  <p class="qid">{_e(q.get("id"))} · {done} of {len(ids)} experiments answered · budget {_e(budget.get("max_minutes"))} min, {_e(budget.get("max_g"))} g</p>
  <h2>{_e(q.get("question"))}</h2>
  {now_html}
  {f'<h4>Plans</h4><ul class="plans">{plans}</ul>' if plans else ""}
</section>"""
    if not q_html:
        q_html = '<section class="question"><h2>No open question.</h2><p>Ask the lab what to test next.</p></section>'

    order = sorted(exps.values(), key=lambda e: e.get("id") or "", reverse=True)
    notebook = "".join(f'<div id="{_e(e.get("id"))}">{_experiment(e, pdir, colours, exps)}</div>' for e in order)
    stamp = datetime.now().astimezone().strftime("%-d %b %Y %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Print lab · {_e(pdir.name)}</title>
<style>
:root {{ --bg:#f6f5f2; --card:#fff; --ink:#1d1d1b; --muted:#5f5d57; --line:#dedbd3; --good:#2f7d4f; --attention:#b26a00; --bad:#b3261e; --info:#2b6cb0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121417; --card:#1b1e23; --ink:#e9e7e2; --muted:#a29f98; --line:#2e3238; --good:#5cc489; --attention:#f0a640; --bad:#f2786f; --info:#7fb0e8; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Figtree, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:16px; }}
h1 {{ font-size:1.3rem; margin:.5rem 0 1rem; }}
h1 small {{ color:var(--muted); font-weight:400; font-size:.85rem; margin-left:.5rem; }}
.needs {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--attention); border-radius:12px; padding:12px 16px; margin-bottom:16px; }}
.needs h2 {{ font-size:1rem; margin:0 0 .5rem; }}
.needs ul {{ list-style:none; margin:0; padding:0; }}
.needs li {{ padding:.35rem 0; border-top:1px solid var(--line); display:flex; flex-direction:column; }}
.needs li:first-child {{ border-top:0; }}
.needs li span, .needs .empty {{ color:var(--muted); font-size:.9rem; }}
a {{ color:var(--info); }}
.question {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }}
.question h2 {{ font-size:1.5rem; line-height:1.25; margin:.25rem 0 .5rem; }}
.qid, .meta, .when {{ color:var(--muted); font-size:.85rem; margin:0; }}
.plans {{ margin:.25rem 0 0; padding-left:1.1rem; color:var(--muted); }}
h4 {{ margin:.75rem 0 .25rem; font-size:.85rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
.notebook h2 {{ font-size:1.1rem; margin:1.5rem 0 .5rem; }}
.exp {{ background:var(--card); border:1px solid var(--line); border-left:6px solid var(--spine); border-radius:12px; padding:12px 16px; margin-bottom:12px; }}
.exp header {{ display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; }}
.exp h3 {{ font-size:1.05rem; margin:.4rem 0 .2rem; }}
.id {{ font-weight:700; font-variant-numeric:tabular-nums; }}
.pill {{ font-size:.75rem; border-radius:999px; padding:.1rem .55rem; border:1px solid currentColor; }}
.pill[data-tone=good] {{ color:var(--good); }} .pill[data-tone=attention] {{ color:var(--attention); }}
.pill[data-tone=bad] {{ color:var(--bad); }} .pill[data-tone=info] {{ color:var(--info); }} .pill[data-tone=muted] {{ color:var(--muted); }}
.verdict {{ margin:.4rem 0 0; }}
.shots {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:6px; margin-top:.6rem; }}
.shots img {{ width:100%; aspect-ratio:1; object-fit:cover; border-radius:8px; border:1px solid var(--line); display:block; }}
details {{ margin-top:.5rem; }} summary {{ cursor:pointer; color:var(--info); }}
dl {{ margin:.25rem 0; }} dt {{ font-weight:600; font-size:.85rem; margin-top:.4rem; }} dd {{ margin:0; color:var(--muted); }}
.now {{ border-top:1px solid var(--line); margin-top:.75rem; padding-top:.6rem; }}
.now-q {{ margin:.2rem 0; font-weight:600; }}
.why {{ margin:.3rem 0 0; color:var(--muted); font-size:.95rem; }} .why b {{ color:var(--ink); }}
.wipe {{ position:relative; margin:.6rem 0 0; border-radius:10px; overflow:hidden; border:1px solid var(--line); }}
.wipe img {{ display:block; width:100%; aspect-ratio:4/3; object-fit:cover; }}
.wipe .after {{ position:absolute; inset:0; height:100%; clip-path:inset(0 0 0 var(--cut)); }}
.wipe input {{ position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:ew-resize; margin:0; }}
.wipe::after {{ content:""; position:absolute; top:0; bottom:0; left:var(--cut); width:3px; margin-left:-1px; background:#fff; box-shadow:0 0 4px #0008; pointer-events:none; }}
.wipe figcaption {{ position:absolute; left:0; right:0; bottom:0; display:flex; justify-content:space-between; padding:.3rem .6rem; font-size:.8rem; color:#fff; text-shadow:0 1px 3px #000; pointer-events:none; }}
.ai {{ font-size:.9rem; color:var(--muted); border-left:3px solid var(--line); padding-left:.6rem; }}
@media (min-width: 900px) {{ .layout {{ display:grid; grid-template-columns: 360px 1fr; gap:24px; align-items:start; }} .side {{ position:sticky; top:16px; }} }}
</style>
</head>
<body>
<main>
<h1>Print lab · {_e(pdir.name)}<small>read-only · built {_e(stamp)}</small></h1>
<div class="layout">
  <div class="side">
    <section class="needs"><h2>Needs you</h2><ul>{needs_html}</ul></section>
    {q_html}
  </div>
  <div class="notebook"><h2>Notebook</h2>{notebook}</div>
</div>
</main>
</body>
</html>
"""


def cmd_page(args) -> int:
    from lab.cli import project_dir
    pdir = project_dir(args.project)
    if not pdir.is_dir():
        raise FileNotFoundError(f"No project {args.project!r} at {pdir}.")
    out = Path(args.out) if args.out else pdir / "page.html"
    out.write_text(build(pdir))
    print(f"Wrote {out}")
    if args.open:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())
    return 0


def register(sub) -> None:
    s = sub.add_parser("page", help="build a read-only HTML page of the project (questions, notebook, photos)")
    s.add_argument("--out", help="where to write it (default: projects/<project>/page.html, next to the photos)")
    s.add_argument("--open", action="store_true", help="open it in the browser")
    s.set_defaults(fn=cmd_page)
