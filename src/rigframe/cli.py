"""rigframe command line.

    rigframe validate boats/my-boat.yaml [...]
    rigframe run boats/my-boat.yaml --out reports/my-boat
"""
from __future__ import annotations

import argparse
import sys

from . import boatfile


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rigframe", description="A sailboat's standing rig as a 3D frame.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check boat files and count the estimates in them")
    v.add_argument("files", nargs="+")
    r = sub.add_parser("run", help="analyse a boat and write its report")
    r.add_argument("file")
    r.add_argument("--out", required=True, help="folder for the report")
    w = sub.add_parser("viewer", help="rebuild the 3D viewer from a report's viewer.json")
    w.add_argument("data", help="viewer.json")
    w.add_argument("out", help="the HTML file to write")
    w.add_argument("--cdn", action="store_true", help="load plotly.js from the internet: a 50 kB file instead of 5 MB")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        return boatfile.main(a.files)
    if a.cmd == "viewer":
        from . import viewer
        return viewer.main([a.data, a.out] + (["--cdn"] if a.cdn else []))
    from . import demo                                   # until the engine lands: see demo.py
    return demo.run(a.file, a.out)


if __name__ == "__main__":
    sys.exit(main())
