"""Markdown report -> 11 x 17 in PDF: pandoc (KaTeX math) to HTML, then Chromium prints it.

    python tools/md_to_tabloid_pdf.py notebooks/output/island-packet-40-1996/REPORT.md [--out report.pdf]

Writes the PDF next to the .md unless --out is given. Images are found relative to the .md, as the
notebooks write them (assets/...). Needs pandoc on PATH, `pip install playwright`, `playwright install
chromium` once, and internet for KaTeX. Prints how many math spans rendered and how many failed.
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

CSS = """body{font:11pt/1.45 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;max-width:none;margin:0 0.2in;color:#111}
h1{font-size:20pt}h2{font-size:15pt;border-bottom:1px solid #ccc;padding-bottom:2px;margin-top:1.4em}h3{font-size:12.5pt}
table{border-collapse:collapse;margin:0.6em 0;font-size:9.5pt;width:auto !important;table-layout:auto}
col{width:auto !important}td:first-child{white-space:nowrap}th,td{border:1px solid #bbb;padding:3px 6px;vertical-align:top}
th{background:#f1efe8}img{max-width:100%}code{font-size:9pt;background:#f4f4f2;padding:0 2px}
p em{color:#444}header,#title-block-header{display:none}"""
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src=\"([^\"]+)\"")


def convert(md: Path, out: Path):
    text = md.read_text(encoding="utf-8")
    if text.startswith("---"):                            # front matter isn't page content
        text = text.split("\n---", 1)[1].split("\n", 1)[1]
    with tempfile.TemporaryDirectory(prefix="md2pdf_") as tmp:
        work = Path(tmp)
        missing = []
        for m in IMAGE.finditer(text):                    # copy each local image to the same relative place
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
        (work / "style.css").write_text(CSS, encoding="utf-8")
        (work / "page.md").write_text(text, encoding="utf-8")
        subprocess.run(["pandoc", "page.md", "-s", "--katex", "-c", "style.css", "--metadata", f"pagetitle={md.stem}",
                        "-f", "markdown+tex_math_dollars-yaml_metadata_block-implicit_figures", "-o", "page.html"],
                       check=True, cwd=work)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto((work / "page.html").as_uri())
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            n_math = page.evaluate("document.querySelectorAll('.katex').length")
            n_err = page.evaluate("document.querySelectorAll('.katex-error').length")
            out.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(out), width="11in", height="17in", print_background=True,
                     margin={"top": "0.5in", "bottom": "0.5in", "left": "0.4in", "right": "0.4in"})
            browser.close()
    print(f"{out}: {n_math} math spans, {n_err} errors" + (f", {len(missing)} missing images: {missing}" if missing else ""))
    return n_err + len(missing)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("md", type=Path)
    ap.add_argument("--out", type=Path, help="the PDF to write (default: next to the .md)")
    a = ap.parse_args()
    md = a.md.resolve()
    raise SystemExit(1 if convert(md, (a.out or md.with_suffix(".pdf")).resolve()) else 0)
