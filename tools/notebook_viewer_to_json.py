"""Turn a rig notebook's standalone viewer (its §14 HTML) into rigframe viewer data, version 1.

    python tools/notebook_viewer_to_json.py NOTEBOOK_VIEWER.html boats/x.yaml tests/reference/x.viewer.json

The notebooks wrote their own HTML with the data inlined as `const D=...;`. This pulls that out and
renames it to the package's format. The result serves two jobs: the reference results the engine must
reproduce (tests/reference/), and sample data for the viewer before the engine exists.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rigframe import __version__                       # noqa: E402
from rigframe.boatfile import estimates, inputs, load_boat   # noqa: E402

SIDE = {"P": "port", "S": "stbd"}
GROUP = {"cap": "cap", "inter": "intermediate", "lower": "aft lower", "lowerA": "aft lower",
         "lowerF": "forward lower", "forestay": "forestay", "backstay": "backstay", "staysail": "staysail stay",
         "staysail_stay": "staysail stay", "triatic": "triatic", "zcap": "mizzen cap", "zlowerA": "mizzen aft lower",
         "zlowerF": "mizzen forward lower", "zbackstay": "mizzen backstay", "zforestay": "mizzen forestay"}


def wire_label(name):
    """cap_V1_P -> 'cap V1 (port)', forestay_s03 -> 'forestay segment 3', zlowerF_D1F_S -> 'mizzen forward lower D1F (stbd)'."""
    parts = name.split("_")
    side = SIDE.get(parts[-1]) if len(parts) > 1 else None
    if side:
        parts = parts[:-1]
    group = parts[0]
    rest = parts[1:]
    if rest and rest[0] == "stay" and group == "staysail":    # staysail_stay
        group, rest = "staysail_stay", rest[1:]
    words = [GROUP.get(group, group.replace("_", " "))]
    for r in rest:
        m = re.fullmatch(r"s(\d+)", r)
        words.append(f"segment {int(m.group(1))}" if m else r)
    return " ".join(words) + (f" ({side})" if side else "")


def beam_label(name, is_mast):
    """mast_M03 -> 'main mast M03', mizzen_M07 -> 'mizzen M07', spreader1_P -> 'spreader 1 (port)'."""
    m = re.fullmatch(r"(mizzen_)?(spreader)(\d)_([PS])", name)
    if m:
        return f"{'mizzen ' if m.group(1) else ''}spreader {m.group(3)} ({SIDE[m.group(4)]})"
    if name.startswith("mast_"):
        return "main mast " + name[5:]
    if name.startswith("mizzen_"):
        return "mizzen " + name[7:]
    return name.replace("_", " ")


def convert(html_path, boat_path):
    text = Path(html_path).read_text(encoding="utf-8")
    D = json.loads(re.search(r"const D=(\{.*?\});\n", text, re.S).group(1))
    boat, probs = load_boat(boat_path)
    assert not probs, probs
    geos = {}
    for k, g in D["geos"].items():
        heads = [{"mast": "main", "node": g["head"]}] + ([{"mast": "mizzen", "node": g["zhead"]}] if "zhead" in g else [])
        geos[k] = {"nodes": g["nodes"], "xyz": g["xyz"], "heads": heads,
                   "beams": [[b[0], b[1], "mast" if b[2] else "spreader", beam_label(b[3], b[2])] for b in g["beams"]],
                   "wires": [[w[0], w[1], wire_label(w[2]), w[3], w[4]] for w in g["wires"]]}
    cases = []
    for c in D["cases"]:
        c = dict(c)
        if c["l"].startswith("Split backstays: "):          # the Morgan notebook ran both arrangements in one page
            c["l"], c["grp"] = c["l"][len("Split backstays: "):], "Split backstays, no triatic"
        elif any(x["l"].startswith("Split backstays: ") for x in D["cases"]):
            c["grp"] = "Triatic"
        cases.append(c)
    b = boat["boat"]
    return {"version": 1,
            "boat": {"name": b["name"].si, "rig": b["rig"].si, "variant": b["variant"].si if "variant" in b else "",
                     "file": "boats/" + Path(boat_path).name,
                     "generated": re.search(r"on (\d{4}-\d{2}-\d{2})", text).group(1) if re.search(r"on (\d{4}-\d{2}-\d{2})", text) else "",
                     "rigframe": __version__, "estimates": len(estimates(boat)), "inputs": len(list(inputs(boat))),
                     "source": f"converted from {Path(html_path).name}"},
            "yield_MPa": D["sy"], "geos": geos, "cases": cases}


def only_group(data, grp):
    """Keep one group's cases (one boat file is one arrangement) and the geometries they use."""
    cases = [dict(c) for c in data["cases"] if c.get("grp") == grp]
    for c in cases:
        c.pop("grp", None)
    used = {c["g"] for c in cases}
    return dict(data, cases=cases, geos={k: v for k, v in data["geos"].items() if k in used})


if __name__ == "__main__":
    src, boat_file, out = sys.argv[1:4]
    data = convert(src, boat_file)
    if len(sys.argv) > 4:                                 # optional: the case group to keep
        data = only_group(data, sys.argv[4])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}: {len(data['cases'])} cases, {len(data['geos'])} geometries")
