"""Build the GitHub Pages site from the README and the docs, with every published boat as a card.

    python tools/build_site.py PAGES_DIR

Writes, into PAGES_DIR:
- index.html: the front page. Its words come from the top of README.md, its prompt box from
  prompts/make-boat-yaml.md, and its boat cards from PAGES_DIR/boats/<stem>/viewer.json;
- guide.html (README.md), boat-file.html (docs/boat-yaml.md) and prompt.html (prompts/make-boat-yaml.md);
- img/, a copy of docs/img/.

So editing the README edits the site. Links between those files point at their pages; links to any other file
in the repository point at it on GitHub. Pull-request previews (previews/) are left unlisted.
A boat with a notebook study of its own (notebooks/<stem>*.ipynb, longest match) also links that study's report
and companion PDFs on the sample-reports release, and its notebook in Colab.

Needs markdown-it-py and mdit-py-plugins.
"""
import html
import json
import os
import posixpath
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin

REPO = Path(__file__).resolve().parents[1]
GITHUB = "https://github.com/RigFrame/rigframe"
SITE = "https://rigframe.github.io/rigframe/"
RELEASE = GITHUB + "/releases/download/sample-reports/"
COLAB = "https://colab.research.google.com/github/RigFrame/rigframe/blob/main/notebooks/"
STUDIES = sorted((p.stem for p in (REPO / "notebooks").glob("*.ipynb")), key=len, reverse=True)

# Repository files that have a page of their own; every other relative link goes to GitHub.
PAGES = {"README.md": "guide.html", "docs/boat-yaml.md": "boat-file.html", "prompts/make-boat-yaml.md": "prompt.html"}


def study_of(stem):
    """The notebook study a boat file belongs to: morgan-462-ketch-triatic -> morgan-462-ketch."""
    return next((s for s in STUDIES if stem == s or stem.startswith(s + "-")), None)


# ---------------------------------------------------------------- markdown

def rewrite(href, src, here):
    """A link as written in repository file `src`, as it should read on page `here`."""
    if href.startswith(SITE):
        return href[len(SITE):] or "./"
    if re.match(r"[a-z]+:", href) or href.startswith("//"):
        return href
    path, _, frag = href.partition("#")
    if not path:                                   # an anchor in the same file
        page = PAGES.get(src, here)
        return ("" if page == here else page) + "#" + frag
    target = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
    tail = "#" + frag if frag else ""
    if target in PAGES:
        return ("" if PAGES[target] == here else PAGES[target]) + tail
    if target.startswith("docs/img/"):
        return "img/" + target[len("docs/img/"):]
    kind = "tree" if path.endswith("/") or (REPO / target).is_dir() else "blob"
    return f"{GITHUB}/{kind}/main/{target}{tail}"


def markdown(src, here):
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    md.use(anchors_plugin, min_level=2, max_level=3)

    def links(state):
        stack = list(state.tokens)
        while stack:
            t = stack.pop()
            if t.type == "link_open":
                href = rewrite(t.attrGet("href"), src, here)
                t.attrSet("href", href)
                if href.startswith("http") and not href.startswith(SITE):
                    t.attrSet("rel", "noopener")
            elif t.type == "image":
                t.attrSet("src", rewrite(t.attrGet("src"), src, here))
                t.attrSet("loading", "lazy")
            stack.extend(t.children or [])
    md.core.ruler.push("site_links", links)
    return md


def render(text, src, here):
    """HTML and the h2/h3 headings (level, id, text) for the contents sidebar."""
    md = markdown(src, here)
    tokens = md.parse(text)
    toc = [(int(t.tag[1]), t.attrGet("id"), tokens[i + 1].children and
            "".join(c.content for c in tokens[i + 1].children if c.type in ("text", "code_inline")))
           for i, t in enumerate(tokens) if t.type == "heading_open" and t.attrGet("id")]
    body = md.renderer.render(tokens, md.options, {})
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    return body, toc


def inline(text, src="README.md", here="index.html"):
    return markdown(src, here).renderInline(text)


def blocks(text):
    """Split markdown into blank-line-separated blocks, keeping fenced code together."""
    out, cur, fence = [], [], None
    for line in text.splitlines():
        m = re.match(r"\s*(`{3,}|~{3,})", line)
        if m and (fence is None or m.group(1).startswith(fence)):
            fence = None if fence else m.group(1)
        if not line.strip() and fence is None:
            if cur:
                out.append("\n".join(cur))
            cur = []
        else:
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def readme_parts():
    """The README's opening (shown on the front page) and the rest (the guide)."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    sections = re.split(r"\n---\n", text)
    intro = {"bullets": [], "paras": [], "callouts": []}
    for b in blocks(sections[0]):
        if b.startswith("# "):
            intro["title"] = b[2:].strip()
        elif re.fullmatch(r"\*\*.+\*\*", b.strip()):
            intro["tagline"] = b.strip()[2:-2]
        elif b.startswith("- "):
            intro["bullets"] = [re.sub(r"\s+", " ", i).strip().rstrip(";.") for i in re.split(r"\n- ", b[2:])]
        elif b.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", b)
            intro["image"] = (m.group(1), rewrite(m.group(2), "README.md", "index.html"))
        elif b.startswith("<sub>"):
            intro["caption"] = re.sub(r"</?sub>", "", b).strip()
        elif b.startswith(">"):
            intro["callouts"].append(re.sub(r"^> ?", "", b, flags=re.M))
        else:
            intro["paras"].append(b)
    rest = [s for s in sections[1:] if not s.strip().startswith("## Contents")]
    guide = "\n\n".join("> " + c.replace("\n", "\n> ") for c in intro["callouts"]) + "\n\n" + "\n\n".join(rest)
    ways = next((s for s in rest if s.strip().startswith("## Four ways")), "")
    notebooks = next((s for s in rest if s.strip().startswith("## The notebooks")), "")
    return intro, guide, ways, notebooks


def table_rows(section):
    rows = [r for r in section.splitlines() if r.startswith("|")]
    if len(rows) < 3:
        return [], []
    split = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
    return split(rows[0]), [split(r) for r in rows[2:]]


def capital(md):
    """Upper-case the first letter, past any markdown markers: '**buckling** of' -> '**Buckling** of'."""
    return re.sub(r"^([^A-Za-z]*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), md)


def reflow(text):
    """Join hard-wrapped lines into paragraphs and list items, for display; headings and list starts stay put."""
    out = []
    for line in text.splitlines():
        starts = re.match(r"\s*([-*] |\d+\. |#|```)", line)
        if out and out[-1].strip() and line.strip() and not starts and not out[-1].lstrip().startswith("#"):
            out[-1] += " " + line.strip()
        else:
            out.append(line)
    return "\n".join(out)


def prompt_text():
    text = (REPO / "prompts/make-boat-yaml.md").read_text(encoding="utf-8")
    m = re.search(r"^````text\n(.*?)^````", text, re.S | re.M)
    steps = re.search(r"## How to use it\n\n(.*?)\n\n(?!\s)", text, re.S)
    items = re.split(r"\n\d+\. ", "\n" + steps.group(1))[1:] if steps else []
    return m.group(1).rstrip() if m else "", [re.sub(r"\s+", " ", i) for i in items]


# ---------------------------------------------------------------- boats

def ramp(u):
    """Utilisation 0..0.5+ as a colour, pale sand to rust, readable on light and dark backgrounds."""
    u = max(0.0, min(u / 0.5, 1.0))
    a, b = (0xd8, 0xc8, 0xa4), (0xc0, 0x4a, 0x1a)
    return "#" + "".join(f"{round(x + (y - x) * u):02x}" for x, y in zip(a, b))


def elevation(data):
    """A side view of the rig (bow to the left), every wire coloured by its highest utilisation in any case."""
    geo_key = data["cases"][0]["g"] if data.get("cases") else next(iter(data["geos"]))
    g = data["geos"][geo_key]
    xyz = g["xyz"]
    peak = [0.0] * len(g["wires"])
    for c in data.get("cases", []):
        if c.get("g") != geo_key:
            continue
        for k, (w, res) in enumerate(zip(g["wires"], c["w"])):
            if w[4]:
                peak[k] = max(peak[k], res[0] / w[4])
    xs = [-p[0] for p in xyz]
    zs = [p[2] for p in xyz]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    pad = 0.04 * (z1 - z0)
    vb = f"{x0 - pad:.2f} {-(z1 + pad):.2f} {x1 - x0 + 2 * pad:.2f} {z1 - z0 + 2 * pad:.2f}"
    sw = (z1 - z0) / 180
    seg = lambda i, j: f'x1="{xs[i]:.2f}" y1="{-zs[i]:.2f}" x2="{xs[j]:.2f}" y2="{-zs[j]:.2f}"'
    order = sorted(range(len(g["wires"])), key=lambda k: peak[k])
    lines = [f'<line {seg(g["wires"][k][0], g["wires"][k][1])} stroke="{ramp(peak[k])}" stroke-width="{sw:.3f}"/>'
             for k in order]
    lines += [f'<line {seg(i, j)} stroke="currentColor" stroke-width="{sw * (3 if kind == "mast" else 2):.3f}" '
              f'stroke-linecap="round"/>' for i, j, kind, *_ in g["beams"]]
    lines.append(f'<line x1="{x0 - pad:.2f}" y1="{-z0:.2f}" x2="{x1 + pad:.2f}" y2="{-z0:.2f}" '
                 f'stroke="currentColor" stroke-opacity=".25" stroke-width="{sw:.3f}"/>')
    return (f'<svg class="elev" viewBox="{vb}" preserveAspectRatio="xMidYMax meet" role="img" '
            f'aria-label="Side view of the rig">{"".join(lines)}</svg>')


def boat_cards(root):
    cards = []
    for vj in sorted(root.glob("boats/*/viewer.json")):
        data = json.loads(vj.read_text(encoding="utf-8"))
        b = data["boat"]
        stem = vj.parent.name
        name = html.escape(b["name"])
        variant = f'<span class="variant">{html.escape(b["variant"])}</span>' if b.get("variant") else ""
        est = ""
        if b.get("inputs"):
            share = b["estimates"] / b["inputs"]
            est = (f'<div class="est"><div class="bar"><span style="width:{share * 100:.0f}%"></span></div>'
                   f'<small>{b["estimates"]} of {b["inputs"]} inputs are estimates</small></div>')
        links = [f'<a class="btn small" href="boats/{stem}/viewer.html">3D viewer</a>',
                 f'<a href="boats/{stem}/REPORT.html">Report</a>']
        if (vj.parent / "REPORT.pdf").exists():
            links.append(f'<a href="boats/{stem}/REPORT.pdf">PDF</a>')
        study = study_of(stem)
        if study:
            links += [f'<a href="{RELEASE}{study}-report.pdf">Study PDF</a>',
                      f'<a href="{RELEASE}{study}-companion.pdf">Companion</a>',
                      f'<a href="{COLAB}{study}.ipynb" rel="noopener">Colab</a>']
        links.append(f'<a href="{GITHUB}/blob/main/boats/{stem}.yaml" rel="noopener">YAML</a>')
        try:
            pic = elevation(data)
        except (KeyError, IndexError, ValueError, ZeroDivisionError):
            pic = ""
        cases = len(data.get("cases", []))
        cards.append(f"""<article class="boat">
  <div class="pic">{pic}</div>
  <div class="body">
    <h3>{name} {variant}</h3>
    <p class="muted">{html.escape(b.get("rig", "").capitalize())} &middot; {cases} load cases</p>
    {est}
    <div class="actions">{" ".join(links)}</div>
  </div>
</article>""")
    return cards


# ---------------------------------------------------------------- page

LOGO = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5v19M4.5 20.5 12 2.5l7.5 18M7.6 12.5h8.8'
        'M3 21.5h18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>')
GH = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 '
      '6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-'
      '.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95'
      ' 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04'
      ' 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-'
      '.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>')

CSS = """
:root{--bg:#f6f5f1;--surface:#fff;--sunk:#efede7;--ink:#15191f;--muted:#5d646e;--line:#e1ded6;
--accent:#1d5ea8;--accent-ink:#fff;--accent-soft:#e3edf8;--warn:#b7791f;--warn-soft:#fbf1df;--code:#f1efe9;
--hero:radial-gradient(1200px 500px at 85% -10%,#dfe9f5 0,transparent 60%);color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d1015;--surface:#151a21;--sunk:#11151b;
--ink:#e7e5e0;--muted:#9aa2ad;--line:#262d36;--accent:#6aa9f5;--accent-ink:#0b1320;--accent-soft:#16243a;
--warn:#e2a54b;--warn-soft:#2a2113;--code:#11161d;--hero:radial-gradient(1200px 500px at 85% -10%,#16243a 0,transparent 60%);
color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0d1015;--surface:#151a21;--sunk:#11151b;--ink:#e7e5e0;--muted:#9aa2ad;--line:#262d36;
--accent:#6aa9f5;--accent-ink:#0b1320;--accent-soft:#16243a;--warn:#e2a54b;--warn-soft:#2a2113;--code:#11161d;
--hero:radial-gradient(1200px 500px at 85% -10%,#16243a 0,transparent 60%);color-scheme:dark}
*{box-sizing:border-box}
html{scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:2px}
code,pre{font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88em}
:not(pre)>code{background:var(--code);border:1px solid var(--line);border-radius:5px;padding:.08em .35em}
.muted{color:var(--muted)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
/* top bar */
header.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 85%,transparent);
backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;align-items:center;gap:20px;height:58px}
.brand{display:flex;align-items:center;gap:8px;font-weight:700;color:var(--ink);text-decoration:none;letter-spacing:-.01em}
.brand svg{width:22px;height:22px;color:var(--accent)}
nav.links{display:flex;gap:4px;flex:1}
nav.links a{color:var(--muted);text-decoration:none;font-size:14.5px;padding:6px 10px;border-radius:7px}
nav.links a:hover,nav.links a[aria-current]{color:var(--ink);background:var(--sunk)}
.icons{display:flex;gap:6px;margin-left:auto}
.icon{display:inline-grid;place-items:center;width:36px;height:36px;border-radius:8px;border:1px solid var(--line);
background:var(--surface);color:var(--ink);cursor:pointer}
.icon svg{width:17px;height:17px}
/* buttons */
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:var(--accent-ink);text-decoration:none;
font-weight:600;padding:11px 18px;border-radius:9px;border:1px solid var(--accent);font-size:15px}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line)}
.btn.ghost:hover{background:var(--sunk)}
.btn.small{padding:5px 11px;font-size:13.5px;border-radius:7px}
/* hero */
.hero{background:var(--hero)}
.hero .wrap{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:48px;align-items:center;padding-top:64px;padding-bottom:56px}
.eyebrow{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin:0 0 14px}
.hero h1{font-size:clamp(34px,4.6vw,54px);line-height:1.06;letter-spacing:-.025em;margin:0 0 20px;font-weight:750}
.lead{font-size:18.5px;color:var(--muted);margin:0 0 26px;max-width:36em}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.note{font-size:14.5px;color:var(--muted);margin:0}
.frame{position:relative;border-radius:14px;overflow:hidden;border:1px solid var(--line);background:var(--surface);
box-shadow:0 1px 2px rgba(0,0,0,.04),0 18px 50px -20px rgba(16,40,80,.35)}
.frame .bar{display:flex;align-items:center;gap:6px;padding:9px 12px;border-bottom:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.frame .bar i{width:10px;height:10px;border-radius:50%;background:var(--line)}
.frame .bar span{margin-left:8px}
.frame img{display:block;width:100%;height:auto}
.frame iframe{display:block;width:100%;height:min(78vh,720px);border:0;background:#fff}
figure.live{grid-column:1/-1}
.play{position:absolute;left:50%;bottom:22px;transform:translateX(-50%);box-shadow:0 8px 24px -8px rgba(0,0,0,.4)}
figcaption{font-size:13px;color:var(--muted);margin-top:10px}
/* bands and sections */
.callouts{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-bottom:40px;margin-top:-16px}
.callout{background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);border-left:3px solid var(--warn);
border-radius:10px;padding:14px 16px;font-size:14.5px}
.callout p{margin:0}
section.block{padding:56px 0;border-top:1px solid var(--line)}
section.block h2{font-size:clamp(26px,3vw,34px);letter-spacing:-.02em;margin:0 0 8px;line-height:1.15}
section.block>.wrap>p.sub{color:var(--muted);margin:0 0 28px;max-width:46em;font-size:17px}
.grid{display:grid;gap:14px}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px}
.card p{margin:0}
.card .num{font:600 12px/1 "JetBrains Mono",monospace;color:var(--accent);margin-bottom:10px;display:block}
.way h3{font-size:16px;margin:0 0 10px}
.way dl{margin:0;font-size:14px}
.way dt{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-top:10px}
.way dd{margin:2px 0 0}
/* prompt box */
.promptgrid{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:36px;align-items:start}
ol.steps{list-style:none;padding:0;margin:0;counter-reset:s}
ol.steps li{counter-increment:s;position:relative;padding:0 0 18px 44px;font-size:15px}
ol.steps li::before{content:counter(s,decimal-leading-zero);position:absolute;left:0;top:0;font:600 12px/1 "JetBrains Mono",monospace;
color:var(--accent);background:var(--accent-soft);border-radius:6px;padding:6px 7px}
.term{border:1px solid var(--line);border-radius:12px;background:var(--code);overflow:hidden}
.term .bar{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid var(--line);
font-size:12.5px;color:var(--muted);background:var(--surface)}
.term pre{margin:0;padding:16px 18px;white-space:pre-wrap;font-size:13px;line-height:1.55;max-height:300px;overflow:hidden;position:relative}
.term.open pre{max-height:none}
.term:not(.open) pre::after{content:"";position:absolute;inset:auto 0 0 0;height:90px;background:linear-gradient(transparent,var(--code))}
.term .more{display:block;width:100%;border:0;border-top:1px solid var(--line);background:var(--surface);color:var(--accent);
padding:9px;font:inherit;font-size:14px;cursor:pointer}
.copy{font:inherit;font-size:12.5px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:6px;padding:3px 10px;cursor:pointer}
/* boats */
.boats{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.boat{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.boat .pic{height:200px;padding:14px 14px 0;background:linear-gradient(var(--sunk),var(--surface));color:var(--ink);display:flex;justify-content:center}
.elev{width:100%;height:100%}
.boat .body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;flex:1}
.boat h3{margin:0;font-size:17px}
.boat p{margin:0;font-size:14px}
.variant{font-size:12px;font-weight:600;color:var(--accent);background:var(--accent-soft);padding:2px 8px;border-radius:999px;vertical-align:2px}
.est small{color:var(--muted);font-size:12.5px}
.est .bar{height:5px;border-radius:9px;background:var(--accent-soft);overflow:hidden;margin:4px 0 2px}
.est .bar span{display:block;height:100%;background:var(--warn)}
.actions{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin-top:auto;padding-top:6px;font-size:13.5px}
.legend{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--muted);margin:-12px 0 22px}
.legend .ramp{width:120px;height:6px;border-radius:9px;background:linear-gradient(90deg,#d8c8a4,#c04a1a)}
/* docs */
.doclayout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:48px;padding-top:36px;padding-bottom:80px}
aside.toc{position:sticky;top:78px;align-self:start;max-height:calc(100vh - 96px);overflow:auto;font-size:13.5px;padding-right:6px}
aside.toc p{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin:0 0 8px}
aside.toc a{display:block;color:var(--muted);text-decoration:none;padding:4px 0 4px 12px;border-left:2px solid var(--line);line-height:1.35}
aside.toc a.l3{padding-left:24px;font-size:13px}
aside.toc a:hover{color:var(--ink)}
aside.toc a.on{color:var(--accent);border-left-color:var(--accent)}
details.mtoc{display:none}
.doc{max-width:780px;min-width:0}
.doc h1{font-size:clamp(30px,4vw,42px);letter-spacing:-.02em;line-height:1.1;margin:0 0 18px}
.doc h2{font-size:26px;letter-spacing:-.015em;margin:52px 0 12px;padding-top:28px;border-top:1px solid var(--line);line-height:1.2}
.doc h3{font-size:19px;margin:32px 0 8px}
.doc hr{display:none}
.doc img{max-width:100%;height:auto;border-radius:10px;border:1px solid var(--line);background:#fff}
.doc p>sub{display:block;font-size:13px;color:var(--muted);margin-top:-6px}
.doc blockquote{margin:16px 0;background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);
border-left:3px solid var(--warn);border-radius:10px;padding:12px 16px;font-size:15px}
.doc blockquote p{margin:0}
.doc pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow:auto;position:relative;line-height:1.5}
.doc pre .copy{position:absolute;top:8px;right:8px;opacity:0;transition:opacity .15s}
.doc pre:hover .copy,.doc pre .copy:focus{opacity:1}
.table-wrap{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
.doc table{border-collapse:collapse;width:100%;font-size:14.5px}
.doc th,.doc td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
.doc tr:last-child td{border-bottom:0}
.doc th{background:var(--sunk);font-size:13px}
.doc li{margin:4px 0}
.doc :not(pre)>code{overflow-wrap:anywhere}
.header-anchor{opacity:0;margin-left:6px;text-decoration:none;color:var(--muted)}
h2:hover .header-anchor,h3:hover .header-anchor{opacity:1}
footer{border-top:1px solid var(--line);padding:28px 0 40px;font-size:13.5px;color:var(--muted)}
footer .wrap{display:flex;flex-wrap:wrap;gap:8px 24px;justify-content:space-between}
@media (max-width:960px){
 .hero .wrap,.promptgrid{grid-template-columns:1fr;gap:32px}
 .hero .wrap{padding-top:40px}
 .g3,.g4{grid-template-columns:repeat(2,minmax(0,1fr))}
 .doclayout{grid-template-columns:1fr;gap:0}
 aside.toc{display:none}
 details.mtoc{display:block;margin-bottom:20px;border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:10px 14px;font-size:14px}
 details.mtoc a{display:block;padding:3px 0;text-decoration:none}
 details.mtoc a.l3{padding-left:14px}
}
@media (max-width:720px){
 header.top .wrap{flex-wrap:wrap;height:auto;padding-top:9px;padding-bottom:6px;gap:6px 12px}
 nav.links{order:3;flex-basis:100%;overflow-x:auto;white-space:nowrap;margin:0 -6px;scrollbar-width:none}
 nav.links a{padding:4px 8px;font-size:14px}
 html{scroll-padding-top:110px}
 aside.toc{top:110px}
 .g3,.g4,.g2,.callouts{grid-template-columns:1fr}
 .frame iframe{height:70vh}
}
"""

JS = """
(function(){
 var root=document.documentElement,key='rigframe-theme';
 try{var t=localStorage.getItem(key);if(t)root.dataset.theme=t;}catch(e){}
 var b=document.getElementById('theme');
 if(b)b.addEventListener('click',function(){
  var dark=root.dataset.theme?root.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme=dark?'light':'dark';try{localStorage.setItem(key,root.dataset.theme);}catch(e){}
 });
 function copy(btn,text){
  var done=function(){var o=btn.textContent;btn.textContent='Copied';setTimeout(function(){btn.textContent=o;},1400);};
  if(navigator.clipboard)navigator.clipboard.writeText(text).then(done,function(){});
 }
 document.querySelectorAll('.doc pre').forEach(function(pre){
  var btn=document.createElement('button');btn.className='copy';btn.type='button';btn.textContent='Copy';
  btn.addEventListener('click',function(){copy(btn,pre.querySelector('code').innerText);});pre.appendChild(btn);
 });
 document.querySelectorAll('[data-copy]').forEach(function(btn){
  btn.addEventListener('click',function(){copy(btn,document.getElementById(btn.dataset.copy).value);});
 });
 document.querySelectorAll('.term .more').forEach(function(m){
  m.addEventListener('click',function(){var t=m.closest('.term');t.classList.toggle('open');
   m.textContent=t.classList.contains('open')?'Show less':'Show the whole prompt';});
 });
 var play=document.getElementById('play');
 if(play)play.addEventListener('click',function(e){
  e.preventDefault();var f=document.createElement('iframe');f.src=play.getAttribute('href');f.title='3D rig viewer';
  var host=document.getElementById('shot');host.closest('figure').classList.add('live');host.replaceWith(f);play.remove();
 });
 var links=[].slice.call(document.querySelectorAll('aside.toc a'));
 if(links.length&&'IntersectionObserver'in window){
  var map={};links.forEach(function(a){map[a.hash.slice(1)]=a;});
  var io=new IntersectionObserver(function(es){es.forEach(function(e){
   if(e.isIntersecting){links.forEach(function(a){a.classList.remove('on');});var a=map[e.target.id];if(a)a.classList.add('on');}
  });},{rootMargin:'-70px 0px -70% 0px'});
  Object.keys(map).forEach(function(id){var h=document.getElementById(id);if(h)io.observe(h);});
 }
})();
"""

NAV = [("guide.html", "Guide"), ("index.html#boats", "Boats"), ("boat-file.html", "Boat file"),
       ("prompt.html", "AI prompt"), ("index.html#notebooks", "Notebooks")]


def page(title, description, body, here):
    nav = "".join(f'<a href="{h}"{" aria-current=page" if h == here else ""}>{t}</a>' for h, t in NAV)
    built = os.environ.get("GITHUB_SHA", "")[:7]
    stamp = f"Built {date.today():%Y-%m-%d}" + (f' from <a href="{GITHUB}/commit/{built}">{built}</a>' if built else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(description)}">
<meta property="og:image" content="{SITE}img/viewer-morgan-462.png">
<link rel="icon" href="data:image/svg+xml,{quote(LOGO.replace('currentColor', '#1d5ea8').replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" '))}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="./">{LOGO}rigframe</a>
<nav class="links">{nav}</nav>
<div class="icons">
<button class="icon" id="theme" type="button" aria-label="Switch light or dark"><svg viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="1.8" d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/></svg></button>
<a class="icon" href="{GITHUB}" aria-label="rigframe on GitHub" rel="noopener">{GH}</a>
</div></div></header>
{body}
<footer><div class="wrap">
<span>rigframe is MIT-licensed. An engineering estimate, not a rig survey.</span>
<span>{stamp} &middot; <a href="{GITHUB}">GitHub</a> &middot; <a href="{GITHUB}/issues">Issues</a></span>
</div></footer>
<script>{JS}</script>
</body></html>
"""


def doc_page(src, here, title, description):
    text = (REPO / src).read_text(encoding="utf-8")
    body, toc = render(text, src, here)
    return page(title, description, layout(body, toc, src), here)


def layout(body, toc, src):
    items = "".join(f'<a class="l{lvl}" href="#{i}">{html.escape(t)}</a>' for lvl, i, t in toc)
    edit = f'<p style="margin-top:18px"><a href="{GITHUB}/blob/main/{src}">View {src} on GitHub</a></p>'
    return f"""<div class="wrap doclayout">
<aside class="toc"><p>On this page</p>{items}{edit}</aside>
<article class="doc"><details class="mtoc"><summary>On this page</summary>{items}</details>
{body}</article></div>"""


def index_page(root, intro, ways, nb_section):
    prompt, steps = prompt_text()
    cards = boat_cards(root)
    head, rows = table_rows(ways)
    bullets = "".join(f'<div class="card"><span class="num">{k:02d}</span><p>{inline(capital(b))}</p></div>'
                      for k, b in enumerate(intro["bullets"], 1))
    ways_html = "".join(
        f'<div class="card way"><h3>{inline(r[0])}</h3><dl>'
        + "".join(f"<dt>{html.escape(h)}</dt><dd>{inline(c)}</dd>" for h, c in zip(head[1:], r[1:])) + "</dl></div>"
        for r in rows)
    ways_note = next((b for b in blocks(ways) if not b.startswith(("#", "|"))), "")
    callouts = "".join(f'<div class="callout">{markdown("README.md", "index.html").render(c)}</div>'
                       for c in intro["callouts"])
    alt, src = intro.get("image", ("", ""))
    first = next((p.parent.name for p in sorted(root.glob("boats/morgan-462-ketch-triatic/viewer.html"))), None) \
        or next((p.parent.name for p in sorted(root.glob("boats/*/viewer.html"))), None)
    play = f'<a class="btn play" id="play" href="boats/{first}/viewer.html">Open the live 3D viewer</a>' if first else ""
    paras = intro["paras"]
    step_items = "".join(f"<li>{inline(s, 'prompts/make-boat-yaml.md')}</li>" for s in steps)
    rigs = {m.group(1): r[1] for r in table_rows(nb_section)[1] if (m := re.search(r"\[`?([\w-]+)`?\]", r[0]))}
    notebooks = [(s, f"{COLAB}{s}.ipynb") for s in sorted(STUDIES)]
    nb_cards = "".join(
        f'<div class="card"><h3 style="margin:0 0 6px;font-size:16px"><code>{s}</code></h3>'
        f'<p class="muted" style="font-size:14px;margin-bottom:12px">{inline(rigs.get(s, ""))}</p>'
        f'<p class="actions" style="padding:0"><a class="btn small" href="{u}" rel="noopener">Open in Colab</a>'
        f'<a href="{RELEASE}{s}-report.pdf">Report PDF</a><a href="{RELEASE}{s}-companion.pdf">Companion PDF</a></p></div>'
        for s, u in notebooks)
    body = f"""
<section class="hero"><div class="wrap">
 <div>
  <p class="eyebrow">Sailboat standing rigs &middot; 3D frame analysis</p>
  <h1>{inline(intro.get("tagline", "rigframe"))}</h1>
  <p class="lead">{inline(paras[0].rstrip(":") + ".") if paras else ""}</p>
  <div class="cta">
   <a class="btn" href="#boats">See the example boats</a>
   <a class="btn ghost" href="guide.html#step-1-make-your-boat-file">Add your boat</a>
   <a class="btn ghost" href="#notebooks">Run a notebook</a>
  </div>
  <p class="note">{inline(paras[1]) if len(paras) > 1 else ""}</p>
 </div>
 <figure style="margin:0">
  <div class="frame"><div class="bar"><i></i><i></i><i></i><span>viewer.html &middot; works offline</span></div>
   <img id="shot" src="{src}" alt="{html.escape(alt)}" width="1600" height="1000">{play}</div>
  <figcaption>{inline(intro.get("caption", ""))}</figcaption>
 </figure>
</div>
<div class="wrap callouts">{callouts}</div>
</section>

<section class="block"><div class="wrap">
 <h2>What the report holds</h2>
 <p class="sub">One report per boat, written to share with the owner, the rigger or the surveyor.</p>
 <div class="grid g3">{bullets}</div>
</div></section>

<section class="block" id="prompt"><div class="wrap promptgrid">
 <div>
  <h2>Have an AI assistant draft your boat file</h2>
  <p class="sub" style="margin-bottom:24px">Getting the numbers together is the hard part. Paste this prompt into an AI
  assistant with web search turned on. It reads this repository's rules, looks up your boat, and asks you only what it
  can't find.</p>
  <ol class="steps">{step_items}</ol>
  <p><a href="prompt.html">Read the prompt page</a> &middot; <a href="boat-file.html">Every field in the boat file</a></p>
 </div>
 <div class="term"><div class="bar"><span>Paste into Claude, ChatGPT or Gemini</span><button class="copy" type="button" data-copy="prompt-text">Copy prompt</button></div>
  <pre>{html.escape(reflow(prompt))}</pre><textarea id="prompt-text" hidden>{html.escape(prompt)}</textarea><button class="more" type="button">Show the whole prompt</button></div>
</div></section>

<section class="block" id="boats"><div class="wrap">
 <h2>Example boats</h2>
 <p class="sub">Each rig is drawn from its side, with every wire coloured by the highest share of its breaking load it
 reaches in any load case. Open the 3D viewer to turn it round and hover over any member. The study PDFs are the full
 11 &times; 17 in reports from each boat's notebook.</p>
 <div class="legend"><span>Lightly loaded</span><span class="ramp"></span><span>50% of breaking load or more</span></div>
 <div class="boats">{"".join(cards) or '<p class="muted">No boats published yet.</p>'}</div>
</div></section>

<section class="block" id="ways"><div class="wrap">
 <h2>Four ways to get a report</h2>
 <p class="sub">{inline(ways_note)}</p>
 <div class="grid g4">{ways_html}</div>
 <p style="margin-top:22px"><a class="btn ghost" href="guide.html">Read the full guide</a></p>
</div></section>

<section class="block" id="notebooks"><div class="wrap">
 <h2>The notebooks: the full analysis today</h2>
 <p class="sub">Each notebook holds one boat's whole analysis and runs on its own, in Google Colab or on your computer.
 Edit its <code>RigParams</code> cell for your own boat. <a href="guide.html#the-notebooks-the-full-analysis-today">How to run them</a>.</p>
 <div class="grid g3">{nb_cards}</div>
</div></section>
"""
    title = f"{intro.get('title', 'rigframe')}: {intro.get('tagline', '')}".rstrip(": ")
    return page(title, intro.get("tagline", ""), body, "index.html")


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    intro, guide, ways, notebooks = readme_parts()
    (root / "index.html").write_text(index_page(root, intro, ways, notebooks), encoding="utf-8")
    body, toc = render("# Guide\n\n" + guide, "README.md", "guide.html")
    (root / "guide.html").write_text(page("rigframe guide", "How to make a boat file, get a report and read it.",
                                          layout(body, toc, "README.md"), "guide.html"), encoding="utf-8")
    (root / "boat-file.html").write_text(doc_page("docs/boat-yaml.md", "boat-file.html", "The boat file · rigframe",
                                                  "Every field in a rigframe boat file, its units and where to find it."),
                                         encoding="utf-8")
    (root / "prompt.html").write_text(doc_page("prompts/make-boat-yaml.md", "prompt.html", "AI prompt · rigframe",
                                               "A prompt that has an AI assistant research a boat and draft its file."),
                                      encoding="utf-8")
    shutil.copytree(REPO / "docs/img", root / "img", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.py"))
    print(f"wrote {root}: index, guide, boat-file, prompt; {len(list(root.glob('boats/*/viewer.json')))} boats")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
