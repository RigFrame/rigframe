"""Write the GitHub Pages front page: one row per published boat, with links to its viewer and report.

    python tools/site_index.py PAGES_DIR

Reads PAGES_DIR/boats/<stem>/viewer.json. Pull-request previews (previews/) are left unlisted.
A boat with a notebook study of its own (notebooks/<stem>*.ipynb, longest match) also links that study's
report and companion PDFs on the sample-reports release.
"""
import html
import json
import sys
from pathlib import Path

RELEASE = "https://github.com/rigframe/rigframe/releases/download/sample-reports/"
STUDIES = sorted((p.stem for p in (Path(__file__).resolve().parents[1] / "notebooks").glob("*.ipynb")), key=len, reverse=True)


def study_of(stem):
    """The notebook study a boat file belongs to: morgan-462-ketch-triatic -> morgan-462-ketch."""
    return next((s for s in STUDIES if stem == s or stem.startswith(s + "-")), None)


root = Path(sys.argv[1])
rows = []
for vj in sorted(root.glob("boats/*/viewer.json")):
    b = json.loads(vj.read_text(encoding="utf-8"))["boat"]
    stem = vj.parent.name
    name = b["name"] + (f" ({b['variant']})" if b.get("variant") else "")
    est = f"{b['estimates']} of {b['inputs']}" if b.get("inputs") else ""
    pdfs = []
    if (vj.parent / "REPORT.pdf").exists():
        pdfs.append(f'<a href="boats/{stem}/REPORT.pdf">Report</a>')
    study = study_of(stem)
    if study:
        pdfs += [f'<a href="{RELEASE}{study}-report.pdf">Study report</a>',
                 f'<a href="{RELEASE}{study}-companion.pdf">Companion</a>']
    rows.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(b.get('rig', ''))}</td><td>{est}</td>"
                f'<td><a href="boats/{stem}/viewer.html">3D viewer</a></td>'
                f'<td><a href="boats/{stem}/REPORT.html">Report</a></td>'
                f"<td>{' · '.join(pdfs) or '—'}</td></tr>")

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>rigframe boats</title>
<style>
:root{{--bg:#fbfaf7;--ink:#0b0b0b;--muted:#6b6a65;--line:#d8d7d2;--accent:#2a78d6}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#171716;--ink:#eeede8;--muted:#a3a29b;--line:#3a3a37;--accent:#5b9cf0;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#171716;--ink:#eeede8;--muted:#a3a29b;--line:#3a3a37;--accent:#5b9cf0;color-scheme:dark}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:var(--muted);max-width:70ch}} a{{color:var(--accent)}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
</style></head><body><main>
<h1>rigframe boats</h1>
<p>Sailboat rigs analysed as 3D frames, one per boat file in the
<a href="https://github.com/rigframe/rigframe">rigframe repository</a>. Each is an engineering estimate, not a
rig survey; the estimates column says how many inputs are still estimates.</p>
<p>The viewer and report pages come from boat files, and the full analysis engine isn't in the package yet. The
PDF column links the complete 11 &times; 17 in report and companion from the boat's notebook study, on the
<a href="https://github.com/rigframe/rigframe/releases/tag/sample-reports">sample-reports release</a>. Both Morgan
rows share one study, which runs the triatic and the split backstays side by side.</p>
<div class="wrap"><table><thead><tr><th>Boat</th><th>Rig</th><th>Estimates</th><th>Viewer</th><th>Report</th><th>PDF</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table></div>
</main></body></html>
"""
(root / "index.html").write_text(page, encoding="utf-8")
print(f"wrote {root / 'index.html'}: {len(rows)} boats")
