"""`lab page`: one read-only HTML page for a project, drawn from `page_index.build_index` (no server; it writes only
page.html and page.json next to the photos).

Order: what needs the owner (each with its action, why and the command to run), then each open question (budget
spent and what the next test adds, stop state, evidence), then the notebook of open experiments, then "Earlier" for
answered and abandoned ones. page.json is the same projection Stage 1B pushes to Local AI. The colours and type
follow Local AI's design tokens (--ds-*), so the page ports without a redesign.

Spool colours come from Bambuddy (the household's spool inventory) when it answers: the experiment's filament text is
matched against each spool's colour name. LAB_BAMBUDDY_URL changes the address; "off" skips it. Bambuddy has sign-in
on, so the spool list is asked for with print-lab's own read-only API key, from ~/.config/bambuddy/print-lab-key
(LAB_BAMBUDDY_KEY_FILE changes the file). When Bambuddy doesn't answer or refuses, the colours saved in page.json are
kept. Commands that refresh the page reuse the saved colours, so they never wait on the network.
"""
import html
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from lab.page_index import build_index

NEUTRAL = "#8698b1"
STATUS = {  # label, tone (Local AI badge tones)
    "planned": ("Planned", "neutral"), "built": ("Built", "neutral"), "build_failed": ("Build failed", "bad"),
    "ready": ("Ready to print", "accent"), "needs_approval": ("Needs your approval", "attention"),
    "approved": ("Approved", "accent"), "printing": ("Printing", "attention"), "answered": ("Answered", "good"),
    "abandoned": ("Abandoned", "neutral"),
}
OUTCOME = {"supported": ("Prediction supported", "good"), "refuted": ("Prediction refuted", "accent"),
           "unresolved": ("Unresolved", "neutral"), "inconclusive": ("Inconclusive", "neutral")}
VALIDITY = {"valid": ("Fair comparison", "good"), "confounded": ("Confounded", "bad"),
            "unknown": ("Can't tell if fair", "attention")}
REASONS = {
    "witness_abnormal": "the witness wall printed abnormally",
    "witness_inconclusive": "the witness wall couldn't be judged",
    "anchor_shifted": "the control reprint came out different",
    "anchor_inconclusive": "the control reprint couldn't be judged",
    "layer_time_mismatch": "the plates spent different time per layer",
    "reference_not_printed": "the reference was never printed",
    "reference_unmeasurable": "the reference plate can't be measured",
    "cross_plate_no_anchor": "compared across plates with no control reprint",
    "cross_plate_by_design": "separate plates are the factor being tested",
    "production_mismatch": "this plate differs from how the tile will be printed",
}
DONE = ("answered", "abandoned")


def _e(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _n(x) -> str:
    return "–" if x is None else f"{float(x):.1f}".rstrip("0").rstrip(".")


def _bambuddy_key() -> str | None:
    path = Path(os.environ.get("LAB_BAMBUDDY_KEY_FILE") or Path.home() / ".config/bambuddy/print-lab-key")
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def bambuddy_colours(url=None, timeout=2.0) -> dict | None:
    """Spool colour name (lower case) → '#rrggbb', from Bambuddy; {} when it's off, None when it doesn't answer or
    refuses (so the caller keeps what it had rather than wiping it)."""
    url = url if url is not None else os.environ.get("LAB_BAMBUDDY_URL", "http://10.0.0.30:8000")
    if not url or url == "off":
        return {}
    key = _bambuddy_key()
    req = urllib.request.Request(f"{url}/api/v1/inventory/spools", headers={"X-API-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            spools = json.load(r)
    except Exception:
        return None
    out = {}
    for s in spools if isinstance(spools, list) else []:
        name, rgba = (s.get("color_name") or "").strip().lower(), s.get("rgba") or ""
        if name and re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", rgba):  # never anything else into a style
            out[name] = "#" + rgba[:6]
    return out


def spool_colour(filament: str, colours: dict) -> str:
    text = (filament or "").lower()
    for name in sorted(colours, key=len, reverse=True):  # "light matte terracotta" before "terracotta"
        if name in text and re.fullmatch(r"#[0-9a-fA-F]{6}", colours[name]):
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


def _num(v) -> str:
    return _n(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else _value(v)


def _badge(label, tone) -> str:
    return f'<span class="badge badge--{tone}">{_e(label)}</span>'


def _bar(label: str, spent, nxt, total, unit: str) -> str:
    """Spent, then what the next test would add, against the question's budget."""
    total = float(total or 0) or 1.0
    a, b = min(100.0, 100 * float(spent or 0) / total), min(100.0, 100 * float(nxt or 0) / total)
    b = min(b, 100 - a)
    over = float(spent or 0) + float(nxt or 0) > total + 1e-9
    return (f'<div class="meter{" meter--over" if over else ""}"><div class="meter__head"><span>{_e(label)}</span>'
            f'<span>{_n(spent)} / {_n(total)} {unit}</span></div>'
            f'<div class="meter__track" role="img" aria-label="{_n(spent)} of {_n(total)} {unit} used'
            f'{f", next test adds {_n(nxt)}" if nxt else ""}">'
            f'<span class="meter__spent" style="width:{a:.1f}%"></span>'
            f'<span class="meter__next" style="width:{b:.1f}%"></span></div></div>')


def _question(q: dict, by_id: dict) -> str:
    b, s, nxt = q["budget"], q["spent"], q.get("next")
    stop = q["stop"]
    stop_html = {"owner": ("bad", "Stopped by you"), "auto": ("attention", "Stopped automatically")}.get(stop["kind"])
    stop_line = (f'<p class="stop stop--{stop_html[0]}">{_e(stop["text"][0].upper() + stop["text"][1:])}</p>'
                 if stop_html else '<p class="stop">Continue: nothing has stopped this question.</p>')
    ev = q["evidence"]
    plans = "".join(f'<li>After {_e(p.get("after"))}, if {_e(p.get("if"))}: {_e(p.get("next"))}</li>'
                    for p in q.get("plans") or [])
    current = next((by_id[i] for i in reversed(q["experiments"]) if i in by_id and by_id[i]["status"] not in DONE), None)
    now = ""
    if current:
        now = (f'<div class="now"><p class="sub"><a href="#{_e(current["id"])}">{_e(current["id"])}</a> '
               f'{_badge(*STATUS.get(current["status"], (current["status"], "neutral")))}</p>'
               f'<p class="now__q">{_e(current["question_text"])}</p>'
               + (f'<p class="why"><b>Why this test?</b> {_e(current["why_this_test"])}</p>'
                  if current.get("why_this_test") else "") + "</div>")
    return f"""
<section class="card question">
  <p class="sub">{_e(q["id"])} · {q["answered"]} of {len(q["experiments"])} answered · {ev["informative"]} informative, {ev["uninformative"]} not</p>
  <h2>{_e(q["question"])}</h2>
  {_bar("Time", s["minutes"], nxt and nxt["minutes"], b["minutes"], "min")}
  {_bar("Material", s["g"], nxt and nxt["g"], b["g"], "g")}
  {f'<p class="sub">{_e(nxt["id"])} would add {_n(nxt["minutes"])} min, {_n(nxt["g"])} g</p>' if nxt else ""}
  {stop_line}
  {now}
  {f'<h3 class="label">Plans</h3><ul class="plans">{plans}</ul>' if plans else ""}
</section>"""


def _variants(x: dict) -> str:
    rows = []
    for v in x["variants"]:
        unit = f' {v["unit"]}' if v.get("unit") else ""
        name = _e(v.get("tab") or v["id"])
        if v.get("realized") is not None and v.get("as_asked") is False:
            rows.append(f'<li>{name}: {_e(_num(v["requested"]))} asked, {_e(_n(v["realized"]))} printed{_e(unit)}</li>')
        elif v.get("realized") is not None:
            rows.append(f'<li>{name}: {_e(_n(v["realized"]))}{_e(unit)}</li>')
        else:
            rows.append(f'<li>{name}: {_e(_num(v["requested"]))}{_e(unit)}</li>')
    rows = [r.replace("</li>", f' · {_e(v["grade"])}</li>') if v.get("grade") else r for r, v in zip(rows, x["variants"])]
    return f'<ul class="variants">{"".join(rows)}</ul>' if rows else ""


def _wipe(x: dict, by_id: dict) -> str:
    """The evidence wipe: this test's first photo over its reference's, with a handle to drag between them."""
    refs = [r.rsplit("-", 1)[0] for r in x.get("reference_variants") or []]
    ref = next((by_id[r] for r in refs if r in by_id and by_id[r]["photos"]), None)
    if not x["photos"] or not ref:
        return ""
    return f"""<figure class="wipe" style="--cut:50%">
  <img src="{_e(ref["photos"][0]["path"])}" alt="{_e(ref["id"])}, the reference">
  <img class="wipe__after" src="{_e(x["photos"][0]["path"])}" alt="{_e(x["id"])}">
  <input type="range" min="0" max="100" value="50" aria-label="Drag between {_e(ref["id"])} and {_e(x["id"])}"
         oninput="this.parentNode.style.setProperty('--cut', this.value + '%')">
  <figcaption><span>{_e(ref["id"])}</span><span>{_e(x["id"])}</span></figcaption>
</figure>"""


def _experiment(x: dict, by_id: dict, colours: dict) -> str:
    f = x["factor"]
    values = " vs ".join(_e(_value(v)) for v in f.get("values") or [])
    meta = " · ".join(t for t in (_e((x.get("test_kind") or "").replace("_", " ")),
                                  f'{_e((f.get("name") or "").replace("_", " "))}: {values}' if f.get("name") else "",
                                  _e(x["provenance"]) if x["provenance"] != "prospective" else "") if t)
    badges = [_badge(*STATUS.get(x["status"], (x["status"], "neutral")))]
    if x.get("outcome"):
        badges.append(_badge(*OUTCOME[x["outcome"]]))
    val = x.get("validity")
    if val and x.get("outcome"):
        badges.append(_badge(*VALIDITY[val["status"]]))
    why = "; ".join(REASONS.get(r["code"], r["code"]) for r in (val or {}).get("reasons") or [])
    est, use = x.get("estimate"), x.get("usage")
    cost = []
    if est:
        cost.append(f'estimated {_n(est.get("minutes"))} min, {_n(est.get("g"))} g')
    if use:
        cost.append(f'used {_n(use["minutes"])} min, {_n(use["g"])} g')
    if x.get("layer_time_median_s"):
        cost.append(f'{_n(x["layer_time_median_s"])} s per layer')
    v = x.get("verdict")
    verdict = ""
    if v:
        said = v.get("note") or (("good enough" if v.get("good_enough") else "not good enough")
                                 if v.get("kind") == "acceptance" else v.get("kind"))
        verdict = f'<p class="verdict">Your verdict: {_e(said)} <span class="sub">{_e(_when(v.get("at")))}</span></p>'
    shots = "".join(f'<a href="{_e(p["path"])}" target="_blank" rel="noopener"><img src="{_e(p["path"])}" '
                    f'alt="{_e(x["id"])} print {_e(p["run"])} {_e(p.get("source"))}" loading="lazy"></a>'
                    for p in x["photos"])
    check = x.get("check") or {}
    guards = "".join(f'<li class="guard guard--{"ok" if g["ok"] else g["result"]}">{_e(g["message"])}</li>'
                     for g in check.get("guards") or [] if not g["ok"])
    details = "".join(f"<dt>{_e(k)}</dt><dd>{_e(val_)}</dd>" for k, val_ in (
        ("Hypothesis", x.get("hypothesis")), ("Prediction", x.get("prediction")),
        ("Why this test", x.get("why_this_test")), ("Judge on", x.get("judge_on")),
        ("Abandoned because", x.get("abandoned_reason")), ("Filament", x.get("filament"))) if val_)
    ai = "".join(f'<p class="ai">AI reading ({_e(round((o.get("confidence") or 0) * 100))}% sure'
                 f'{", unconfirmed" if not o.get("confirmed") else ""}): {_e(o.get("assessment"))}</p>'
                 for o in x.get("ai_observations") or [])
    colour = spool_colour(x.get("filament") or "", colours)
    return f"""
<article class="card exp" id="{_e(x["id"])}" style="--spine:{_e(colour)}">
  <header><span class="exp__id">{_e(x["id"])}</span>{"".join(badges)}</header>
  <h3>{_e(x["question_text"])}</h3>
  <p class="sub">{meta}</p>
  {_variants(x)}
  {f'<p class="sub">{_e(", ".join(cost))}</p>' if cost else ""}
  {f'<p class="sub">Why: {_e(why)}</p>' if why and x.get("outcome") else ""}
  {verdict}
  {f'<p class="verdict">Finding: {_e(x["finding"])}</p>' if x.get("finding") else ""}
  {_wipe(x, by_id)}
  {f'<div class="shots">{shots}</div>' if shots else ""}
  <details><summary>Details</summary><dl>{details}</dl>
    {f'<h4 class="label">Last check ({_e(check.get("status", "").replace("_", " "))})</h4><ul class="guards">{guards}</ul>' if guards else ""}
    {ai}</details>
</article>"""


def build(pdir: Path, colours: dict | None = None, index: dict | None = None) -> str:
    pdir = Path(pdir)
    colours = bambuddy_colours() if colours is None else colours
    ix = index or build_index(pdir)
    by_id = {x["id"]: x for x in ix["experiments"]}
    needs = "".join(
        f'<li><a href="#{_e(n["id"])}"><b>{_e(n["action"])}</b> · {_e(n["id"])}</a>'
        f'<span>{_e(by_id[n["id"]]["question_text"])}</span><span class="sub">{_e(n["why"])}</span>'
        f'<code>{_e(n["command"])}</code></li>' for n in ix["needs"]) \
        or '<li class="empty-state">Nothing needs you right now.</li>'
    open_q = [q for q in ix["questions"] if q["status"] not in ("answered", "stopped")]
    questions = "".join(_question(q, by_id) for q in open_q) or \
        '<section class="card question"><h2>No open question.</h2><p class="sub">Start one with <code>uv run lab question new "..."</code>.</p></section>'
    active = [x for x in ix["experiments"] if x["status"] not in DONE]
    earlier = [x for x in ix["experiments"] if x["status"] in DONE]
    problems = "".join(f'<li><b>{_e(p["file"])}</b> {_e(p["error"])}</li>' for p in ix["problems"])
    stamp = _when(ix["generated_at"])
    from lab.sync import status
    st = status(pdir)
    synced = ("" if not st else f' Local AI: synced {_e(_when(st.get("at")))}.' if st.get("ok")
              else f' Local AI: not synced ({_e(st.get("message"))}).')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Print lab · {_e(ix["project"])}</title>
<style>
:root {{ color-scheme:dark;
  --ds-bg:#0a111c; --ds-surface:#121b2b; --ds-surface-2:#172238; --ds-line:#1b2740; --ds-line-card:#1f2c42;
  --ds-text:#eaf0f8; --ds-soft:#c3d3e3; --ds-muted:#93a4bc; --ds-accent:#6cb6ff; --ds-accent-text:#7cc0ff;
  --ds-attention:#ffb224; --ds-attention-text:#ffc352; --ds-good:#3ed598; --ds-good-text:#5be0a8;
  --ds-bad:#ff6b6b; --ds-bad-text:#ff8a8a; --ds-fs-1:13px; --ds-fs-2:15px; --ds-fs-3:17px; --ds-fs-4:22px;
  --ds-fs-badge:11px; --ds-r-sm:8px; --ds-r-md:12px; --ds-r-lg:16px;
  --ds-font:Figtree, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --ds-mono:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--ds-bg); color:var(--ds-text); font:var(--ds-fs-2)/1.5 var(--ds-font); }}
main {{ max-width:1180px; margin:0 auto; padding:16px; }}
a {{ color:var(--ds-accent-text); }} a:focus-visible, summary:focus-visible {{ outline:2px solid var(--ds-accent-text); outline-offset:2px; }}
.topbar h1 {{ font-size:var(--ds-fs-4); margin:4px 0 0; }}
.topbar .sub {{ margin:0 0 16px; }}
.sub {{ color:var(--ds-muted); font-size:var(--ds-fs-1); margin:0; }}
.label {{ color:var(--ds-muted); font-size:var(--ds-fs-1); font-weight:600; margin:12px 0 4px; }}
.card {{ background:var(--ds-surface); border:1px solid var(--ds-line-card); border-radius:var(--ds-r-lg); padding:16px; margin-bottom:12px; }}
.badge {{ font-size:var(--ds-fs-badge); font-weight:600; border-radius:999px; padding:2px 8px; border:1px solid currentColor; }}
.badge--good {{ color:var(--ds-good-text); }} .badge--bad {{ color:var(--ds-bad-text); }}
.badge--attention {{ color:var(--ds-attention-text); }} .badge--accent {{ color:var(--ds-accent-text); }}
.badge--neutral {{ color:var(--ds-muted); }}
.needs {{ border-left:4px solid var(--ds-attention); }}
.needs h2 {{ font-size:var(--ds-fs-3); margin:0 0 8px; }}
.needs ul {{ list-style:none; margin:0; padding:0; }}
.needs li {{ display:flex; flex-direction:column; gap:2px; padding:10px 0; border-top:1px solid var(--ds-line); }}
.needs li:first-child {{ border-top:0; padding-top:0; }}
.needs a {{ text-decoration:none; }} .needs a b {{ color:var(--ds-text); }}
code {{ font:var(--ds-fs-1)/1.4 var(--ds-mono); background:var(--ds-surface-2); border-radius:var(--ds-r-sm); padding:6px 8px; overflow-wrap:anywhere; user-select:all; }}
.needs code {{ margin-top:4px; }}
.empty-state {{ color:var(--ds-muted); }}
.problems {{ border-left:4px solid var(--ds-bad); }} .problems li {{ overflow-wrap:anywhere; }}
.question h2 {{ font-size:var(--ds-fs-4); line-height:1.25; margin:4px 0 12px; }}
.meter {{ margin:8px 0; }}
.meter__head {{ display:flex; justify-content:space-between; font-size:var(--ds-fs-1); color:var(--ds-soft); }}
.meter__track {{ display:flex; height:8px; border-radius:999px; background:var(--ds-surface-2); overflow:hidden; margin-top:4px; }}
.meter__spent {{ background:var(--ds-accent); }}
.meter__next {{ background:repeating-linear-gradient(135deg, var(--ds-accent) 0 3px, transparent 3px 6px); opacity:.7; }}
.meter--over .meter__next {{ background:repeating-linear-gradient(135deg, var(--ds-bad) 0 3px, transparent 3px 6px); opacity:1; }}
.stop {{ margin:8px 0 0; font-size:var(--ds-fs-1); color:var(--ds-good-text); }}
.stop--bad {{ color:var(--ds-bad-text); }} .stop--attention {{ color:var(--ds-attention-text); }}
.now {{ border-top:1px solid var(--ds-line); margin-top:12px; padding-top:10px; }}
.now__q {{ margin:4px 0; font-weight:600; }}
.why {{ margin:4px 0 0; color:var(--ds-muted); }} .why b {{ color:var(--ds-soft); }}
.plans {{ margin:0; padding-left:18px; color:var(--ds-muted); }}
.notebook > h2 {{ font-size:var(--ds-fs-3); margin:4px 0 8px; }}
.exp {{ border-left:6px solid var(--spine); }}
.exp header {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.exp__id {{ font-weight:700; font-variant-numeric:tabular-nums; }}
.exp h3 {{ font-size:var(--ds-fs-3); margin:6px 0 2px; }}
.variants {{ list-style:none; display:flex; flex-wrap:wrap; gap:6px; padding:0; margin:8px 0; }}
.variants li {{ background:var(--ds-surface-2); border-radius:var(--ds-r-sm); padding:2px 8px; font-size:var(--ds-fs-1); font-variant-numeric:tabular-nums; }}
.verdict {{ margin:8px 0 0; }}
.shots {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:6px; margin-top:10px; }}
.shots a:first-child {{ grid-column:1 / -1; }}
.shots img {{ width:100%; aspect-ratio:1; object-fit:cover; border-radius:var(--ds-r-sm); border:1px solid var(--ds-line); display:block; }}
.shots a:first-child img {{ aspect-ratio:4 / 3; }}
details {{ margin-top:10px; }} summary {{ cursor:pointer; color:var(--ds-accent-text); }}
dl {{ margin:4px 0; }} dt {{ font-weight:600; font-size:var(--ds-fs-1); margin-top:6px; }} dd {{ margin:0; color:var(--ds-muted); }}
.guards {{ margin:0; padding-left:18px; font-size:var(--ds-fs-1); }}
.guard--blocked {{ color:var(--ds-bad-text); }} .guard--needs_approval {{ color:var(--ds-attention-text); }}
.ai {{ font-size:var(--ds-fs-1); color:var(--ds-muted); border-left:3px solid var(--ds-line); padding-left:8px; }}
.wipe {{ position:relative; margin:10px 0 0; border-radius:var(--ds-r-md); overflow:hidden; border:1px solid var(--ds-line); }}
.wipe img {{ display:block; width:100%; aspect-ratio:4 / 3; object-fit:cover; }}
.wipe .wipe__after {{ position:absolute; inset:0; height:100%; clip-path:inset(0 0 0 var(--cut)); }}
.wipe input {{ position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:ew-resize; margin:0; }}
.wipe::after {{ content:""; position:absolute; top:0; bottom:0; left:var(--cut); width:3px; margin-left:-1px; background:#fff; pointer-events:none; }}
.wipe figcaption {{ position:absolute; left:0; right:0; bottom:0; display:flex; justify-content:space-between; padding:4px 10px; font-size:var(--ds-fs-1); color:#fff; text-shadow:0 1px 3px #000; pointer-events:none; }}
.earlier > summary {{ font-size:var(--ds-fs-3); font-weight:600; color:var(--ds-text); margin:16px 0 8px; }}
@media (min-width: 900px) {{ .layout {{ display:grid; grid-template-columns:380px 1fr; gap:24px; align-items:start; }} .side {{ position:sticky; top:16px; }} }}
</style>
</head>
<body>
<main>
<header class="topbar"><h1>Print lab · {_e(ix["project"])}</h1>
<p class="sub">Read-only. Built {_e(stamp)}; every <code>lab</code> command that changes a record rebuilds it.{synced}</p></header>
<div class="layout">
  <div class="side">
    <section class="card needs"><h2>Needs you</h2><ul>{needs}</ul></section>
    {f'<section class="card problems"><h2>Records that need fixing</h2><ul>{problems}</ul></section>' if problems else ""}
    {questions}
  </div>
  <div class="notebook"><h2>Notebook</h2>
    {"".join(_experiment(x, by_id, colours) for x in active) or '<p class="empty-state">No open experiments.</p>'}
    {f'<details class="earlier"><summary>Earlier ({len(earlier)})</summary>{"".join(_experiment(x, by_id, colours) for x in earlier)}</details>' if earlier else ""}
  </div>
</div>
</main>
</body>
</html>
"""


def write(pdir: Path, colours: dict | None = None, out: Path | None = None) -> Path:
    """page.html (or `out`) and page.json, from one index."""
    pdir = Path(pdir)
    if colours is None:
        colours = bambuddy_colours()
    if colours is None:  # Bambuddy didn't answer: keep the saved colours
        try:
            colours = json.loads((pdir / "page.json").read_text()).get("colours") or {}
        except (OSError, ValueError):
            colours = {}
    ix = build_index(pdir)
    ix["colours"] = colours
    out = Path(out) if out else pdir / "page.html"
    out.write_text(build(pdir, colours, ix))
    (pdir / "page.json").write_text(json.dumps(ix, indent=1))
    return out


def refresh(pdir: Path) -> None:
    """After a command changed a record: rebuild the page if there is one, reusing its saved spool colours."""
    pdir = Path(pdir)
    if not (pdir / "page.html").exists():
        return
    try:
        colours = json.loads((pdir / "page.json").read_text()).get("colours") or {}
    except (OSError, ValueError):
        colours = {}
    write(pdir, colours)


def cmd_page(args) -> int:
    from lab.cli import project_dir
    pdir = project_dir(args.project)
    if not pdir.is_dir():
        raise FileNotFoundError(f"No project {args.project!r} at {pdir}.")
    out = write(pdir, out=args.out)
    print(f"Wrote {out}")
    if args.open:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())
    return 0


def register(sub) -> None:
    s = sub.add_parser("page", help="build a read-only HTML page of the project (needs you, questions, notebook)")
    s.add_argument("--out", help="where to write it (default: projects/<project>/page.html, next to the photos)")
    s.add_argument("--open", action="store_true", help="open it in the browser")
    s.set_defaults(fn=cmd_page)
