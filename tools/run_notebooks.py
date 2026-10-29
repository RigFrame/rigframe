"""Run notebooks top to bottom, in place, with this Python's own kernel, and check their results.

    python tools/run_notebooks.py notebooks/*.ipynb [--require-opensees]

Prints each notebook's check line ("33 PASS, 0 FAIL, 0 SKIP") and whether the OpenSees cross-check ran.
Exits 1 if a cell raised, a check failed, or (with --require-opensees) OpenSees was skipped.
"""
import argparse
import re
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


def output_text(nb):
    parts = []
    for cell in nb.cells:
        for out in cell.get("outputs", []):
            for item in (out.get("text"), out.get("data", {}).get("text/plain")):
                parts.append("".join(item) if isinstance(item, list) else (item or ""))
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("notebooks", nargs="+", type=Path)
    ap.add_argument("--require-opensees", action="store_true", help="fail if the OpenSees cross-check was skipped")
    a = ap.parse_args()
    bad = 0
    for path in a.notebooks:
        nb = nbformat.read(path, as_version=4)
        t0 = time.time()
        error = None
        try:
            NotebookClient(nb, timeout=1800, kernel_name="python3",
                           resources={"metadata": {"path": str(path.parent.resolve())}}).execute()
        except CellExecutionError as e:
            error = str(e).strip().splitlines()[-1][:400]
        nbformat.write(nb, path)
        text = output_text(nb)
        checks = (re.findall(r"\d+ PASS, \d+ FAIL, \d+ SKIP", text) or ["no check line found"])[-1]
        opensees = (re.findall(r"OpenSees cross-check: [^\n]*", text) or ["OpenSees: not reported"])[-1]
        failed = error or not re.match(r"\d+ PASS, 0 FAIL", checks) or (a.require_opensees and "SKIP" in opensees)
        bad += bool(failed)
        print(f"{'FAIL' if failed else 'OK  '}  {path.name}: {checks}; {opensees}; {time.time() - t0:.0f} s"
              + (f"\n      {error}" if error else ""), flush=True)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
