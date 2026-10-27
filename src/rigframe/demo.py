"""Stand-in for the analysis engine, so the GitHub workflow can be bench-tested end to end before it exists.

`rigframe run` lands here until the engine does. It checks the boat file, then writes a report folder:

- boat.yaml, a copy of the input;
- REPORT.html and SUMMARY.md, with the list of estimates to measure (real: it comes from the boat file);
- for the four example boats only, viewer.html and viewer.json, **replayed** from the notebook studies'
  stored results in tests/reference/. They don't change when the boat file changes.

Every page says DEMO at the top. Any other boat gets the estimates and a note that the engine isn't in yet.
"""
from __future__ import annotations

import html
import json
import shutil
import time
from pathlib import Path

from . import __version__
from .boatfile import estimates, inputs, load_boat
from .viewer import write_viewer

REFERENCE = Path(__file__).resolve().parents[2] / "tests" / "reference"


def headline(data):
    """One row per case: governing wire, its SF, peak mast stress and its share of yield."""
    rows = []
    for c in data["cases"]:
        g = data["geos"][c["g"]]
        wires = [(w[4] / r[0], w[2]) for w, r in zip(g["wires"], c["w"]) if r[0] >= 0.5]
        sf, wire = min(wires)
        mast = max(r[0] for b, r in zip(g["beams"], c["b"]) if b[2] == "mast")
        rows.append({"case": c["l"], "solver": c["s"], "wire": wire, "sf": sf, "mast": mast,
                     "util": mast / data["yield_MPa"]})
    return rows


def run(boat_file, out, plotly="inline"):
    boat_file, out = Path(boat_file), Path(out)
    boat, probs = load_boat(boat_file)
    if probs:
        print(f"FAIL  {boat_file}")
        for p in probs:
            print(f"      - {p}")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(boat_file, out / "boat.yaml")
    b = boat["boat"]
    name = b["name"].si + (f" ({b['variant'].si})" if "variant" in b else "")
    est = estimates(boat)
    n_in = len(list(inputs(boat)))
    ref = REFERENCE / f"{boat_file.stem}.viewer.json"
    rows = []
    if ref.exists():
        data = json.loads(ref.read_text(encoding="utf-8"))
        data["boat"].update({"file": f"boats/{boat_file.name}", "generated": time.strftime("%Y-%m-%d"),
                             "rigframe": f"{__version__} DEMO", "estimates": len(est), "inputs": n_in})
        (out / "viewer.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        write_viewer(data, out / "viewer.html", plotly=plotly)
        rows = headline(data)
        status = ("DEMO: these results are replayed from the notebook study of this boat, stored in "
                  f"tests/reference/{ref.name}. They don't change when the boat file changes. The list of "
                  "estimates below does come from this boat file.")
    else:
        status = ("DEMO: the analysis engine isn't in this version of rigframe yet, so there are no results "
                  "for this boat. The boat file passed every check, and the list of estimates below comes from it.")

    # SUMMARY.md: what the Actions run page shows
    md = [f"## {name}", "", f"> **{status}**", ""]
    if rows:
        md += ["| Case | Governing wire | SF | Peak mast stress |", "|---|---|---:|---:|"]
        md += [f"| {r['case']} | {r['wire']} | {r['sf']:.2f} | {r['mast']:.0f} MPa ({r['util']:.0%}) |" for r in rows]
        md.append("")
    md.append(f"**{len(est)} of {n_in} inputs are estimates.**")
    (out / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # REPORT.html: a plain stand-in for the real report
    e = html.escape
    case_rows = "".join(f"<tr><td>{e(r['case'])}</td><td>{e(r['solver'])}</td><td>{e(r['wire'])}</td>"
                        f"<td class=n>{r['sf']:.2f}</td><td class=n>{r['mast']:.0f} MPa · {r['util']:.0%}</td></tr>"
                        for r in rows)
    est_rows = "".join(f"<tr><td><code>{e(v.path)}</code></td><td>{e(v.raw)}</td><td>{e(v.note)}</td></tr>" for v in est)
    viewer_link = '<p><a href="viewer.html">Open the 3D viewer</a></p>' if rows else ""
    cases = (f"<h2>All cases at a glance</h2><div class=w><table><thead><tr><th>Case</th><th>Solver</th>"
             f"<th>Governing wire</th><th>SF</th><th>Peak mast stress</th></tr></thead><tbody>{case_rows}</tbody>"
             f"</table></div>") if rows else ""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(name)}: rig report (demo)</title>
<style>
:root{{--bg:#fbfaf7;--ink:#0b0b0b;--muted:#6b6a65;--line:#d8d7d2;--accent:#2a78d6;--warn:#8a4b00;--warn-bg:#fbefd9}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#171716;--ink:#eeede8;--muted:#a3a29b;--line:#3a3a37;--accent:#5b9cf0;--warn:#f2c27a;--warn-bg:#3a2c14;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#171716;--ink:#eeede8;--muted:#a3a29b;--line:#3a3a37;--accent:#5b9cf0;--warn:#f2c27a;--warn-bg:#3a2c14;color-scheme:dark}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}} a{{color:var(--accent)}} h1{{font-size:22px;margin:0 0 6px}}
h2{{font-size:17px;margin:24px 0 8px}} .warn{{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px}}
.w{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}} .n{{text-align:right;font-variant-numeric:tabular-nums}}
th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
</style></head><body><main>
<h1>{e(name)}: rig report</h1>
<p class=warn><b>{e(status)}</b></p>
<p>An engineering estimate, not a rig survey. From <code>boats/{e(boat_file.name)}</code>, rigframe {__version__},
{time.strftime("%Y-%m-%d")}.</p>
{viewer_link}
<h2>Estimates: what to measure ({len(est)} of {n_in} inputs)</h2>
<div class=w><table><thead><tr><th>Input</th><th>Value used</th><th>Note</th></tr></thead><tbody>{est_rows}</tbody></table></div>
{cases}
</main></body></html>"""
    (out / "REPORT.html").write_text(page, encoding="utf-8")
    print(f"DEMO  {boat_file} -> {out}: {'viewer replayed from ' + ref.name if rows else 'no results (engine not built)'}, "
          f"{len(est)} estimates listed")
    return 0
