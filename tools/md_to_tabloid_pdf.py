"""Markdown report -> 11 x 17 in PDF, typeset by LaTeX (default) or printed by Chromium.

    python tools/md_to_tabloid_pdf.py notebooks/output/island-packet-40-1996/REPORT.md [--out report.pdf]
    python tools/md_to_tabloid_pdf.py REPORT.md --engine chromium

LaTeX (default): pandoc -> XeLaTeX, in CMU Serif (Computer Modern with Greek, superscripts and symbols) with
real LaTeX math. Needs pandoc, a TeX distribution with XeLaTeX and the CMU fonts (MiKTeX installs them on
demand; Ubuntu: texlive-xetex, texlive-latex-extra, fonts-cmu) and rsvg-convert for the SVG figures
(Ubuntu: librsvg2-bin). Reports any character the font lacks.

Chromium: pandoc -> HTML with KaTeX, printed by Playwright's Chromium. Needs `pip install playwright`,
`playwright install chromium` once, and internet for KaTeX.

Writes the PDF next to the .md unless --out is given. Images are found relative to the .md (assets/...).
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src=\"([^\"]+)\"")
READER = "markdown+tex_math_dollars+gfm_auto_identifiers-yaml_metadata_block-implicit_figures"

# Traffic-light emoji in comparison tables become coloured dots that any font can draw
DOTS = {"✅": "2E7D32", "\U0001F7E2": "2E7D32", "\U0001F7E1": "C99A00", "\U0001F7E0": "E07B00", "\U0001F534": "C62828"}
SYMBOLS = {"≈": r"\ensuremath{\approx}", **{s: rf"\ensuremath{{^{{{d}}}}}" for s, d in zip("⁰⁴⁵⁶⁷⁸⁹", "0456789")}}
LATEX_HEADER = r"""
\usepackage{xcolor}
\usepackage{etoolbox}
\AtBeginEnvironment{longtable}{\small}
\setlength{\emergencystretch}{3em}
"""

CSS = """body{font:11pt/1.45 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;max-width:none;margin:0 0.2in;color:#111}
h1{font-size:20pt}h2{font-size:15pt;border-bottom:1px solid #ccc;padding-bottom:2px;margin-top:1.4em}h3{font-size:12.5pt}
table{border-collapse:collapse;margin:0.6em 0;font-size:9.5pt;width:auto !important;table-layout:auto}
col{width:auto !important}td:first-child{white-space:nowrap}th,td{border:1px solid #bbb;padding:3px 6px;vertical-align:top}
th{background:#f1efe8}img{max-width:100%}code{font-size:9pt;background:#f4f4f2;padding:0 2px}
p em{color:#444}header,#title-block-header{display:none}"""


def stage(md: Path, work: Path):
    """Copy the page and every local image it uses into work/. Returns (text, missing image refs)."""
    text = md.read_text(encoding="utf-8")
    if text.startswith("---"):                            # front matter isn't page content
        text = text.split("\n---", 1)[1].split("\n", 1)[1]
    missing = []
    for m in IMAGE.finditer(text):
        ref = m.group(1) or m.group(2)
        if re.match(r"[a-z]+:", ref):
            continue
        src = (md.parent / ref).resolve()
        if not src.exists():
            missing.append(ref)
            continue
        dst = work / ref
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    return text, missing


SEP = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def size_columns(text):
    """Pandoc gives a wide pipe table's columns widths in proportion to the dashes under each header. The
    notebooks write |---| for every column, so make each column's dashes as long as its longest entry."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and SEP.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            rows = [cells(lines[k]) for k in [i, *range(i + 2, j)]]
            seps = cells(lines[i + 1])
            n = len(seps)
            width = [3] * n
            for row in rows:
                for c, cell in enumerate(row[:n]):
                    shown = re.sub(r"\*\*|`|\\[a-z]+\{|[{}$]", "", cell)
                    width[c] = max(width[c], min(len(shown), 70))
            new = []
            for c, s in enumerate(seps):
                left, right = s.startswith(":"), s.endswith(":")
                new.append((":" if left else "") + "-" * width[c] + (":" if right else ""))
            lines[i + 1] = "|" + "|".join(new) + "|"
            i = j
        else:
            i += 1
    return "\n".join(lines)


def latex(md: Path, out: Path, work: Path):
    text, missing = stage(md, work)
    text = size_columns(text)
    for ch, colour in DOTS.items():
        text = text.replace(ch, rf"\textcolor[HTML]{{{colour}}}{{\large$\bullet$}}")
    for ch, tex in SYMBOLS.items():                      # characters CMU Serif doesn't have
        text = text.replace(ch, tex)
    (work / "page.md").write_text(text, encoding="utf-8")
    (work / "header.tex").write_text(LATEX_HEADER, encoding="utf-8")
    r = subprocess.run(["pandoc", "page.md", "-o", "page.pdf", "-f", READER, "--pdf-engine=xelatex",
                        "-H", "header.tex", "-V", "geometry:paperwidth=11in", "-V", "geometry:paperheight=17in",
                        "-V", "geometry:margin=0.75in", "-V", "fontsize=11pt", "-V", "mainfont=CMU Serif",
                        "-V", "sansfont=CMU Sans Serif", "-V", "monofont=CMU Typewriter Text",
                        "-V", "colorlinks=true", "-V", "linkcolor=blue!50!black", "-V", "urlcolor=blue!50!black",
                        "--metadata", f"pagetitle={md.stem}"],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"pandoc/XeLaTeX failed on {md}:\n{r.stderr[-3000:]}")
    lacking = sorted(set(re.findall(r"Missing character: There is no (\S+)", r.stderr)))
    unresolved = len(re.findall(r"Hyper reference `[^']*' on", r.stderr))
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(work / "page.pdf", out)
    notes = []
    if lacking:
        notes.append(f"font lacks {' '.join(lacking)}")
    if unresolved:
        notes.append(f"{unresolved} internal links unresolved")
    if missing:
        notes.append(f"{len(missing)} missing images: {missing}")
    print(f"{out}: typeset by XeLaTeX" + (", " + "; ".join(notes) if notes else ", clean"))
    return len(lacking) + len(missing)


def chromium(md: Path, out: Path, work: Path):
    from playwright.sync_api import sync_playwright
    text, missing = stage(md, work)
    (work / "style.css").write_text(CSS, encoding="utf-8")
    (work / "page.md").write_text(text, encoding="utf-8")
    subprocess.run(["pandoc", "page.md", "-s", "--katex", "-c", "style.css", "--metadata", f"pagetitle={md.stem}",
                    "-f", READER, "-o", "page.html"], check=True, cwd=work)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto((work / "page.html").as_uri())
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        n_err = page.evaluate("document.querySelectorAll('.katex-error').length")
        out.parent.mkdir(parents=True, exist_ok=True)
        page.pdf(path=str(out), width="11in", height="17in", print_background=True,
                 margin={"top": "0.5in", "bottom": "0.5in", "left": "0.4in", "right": "0.4in"})
        browser.close()
    print(f"{out}: printed by Chromium, {n_err} math errors" + (f", missing images: {missing}" if missing else ""))
    return n_err + len(missing)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("md", type=Path)
    ap.add_argument("--out", type=Path, help="the PDF to write (default: next to the .md)")
    ap.add_argument("--engine", choices=("latex", "chromium"), default="latex")
    a = ap.parse_args()
    md = a.md.resolve()
    with tempfile.TemporaryDirectory(prefix="md2pdf_") as tmp:
        bad = (latex if a.engine == "latex" else chromium)(md, (a.out or md.with_suffix(".pdf")).resolve(), Path(tmp))
    raise SystemExit(1 if bad else 0)
