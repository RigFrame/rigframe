"""Read and check a rigframe boat file (YAML).

    python -m rigframe.boatfile boats/my-boat.yaml [more.yaml ...]

Exits 0 when every file passes, 1 otherwise, and prints each problem in words with the line to fix.
Every value comes back in SI (m, kg, Pa, m^2, m^4, rad, fraction), with its basis kept alongside, so the
engine never sees a unit string and the report can list every estimate.
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import jsonschema
import pint
import yaml

UREG = pint.UnitRegistry()
UNITS = r"mm|cm|m|in|ft|kg|t|lb|%|deg|°|(?:mm|cm|m|in)\^[24]|MPa|GPa|ksi|psi|N\*m|kN\*m|kgf\*m|lbf\*ft|ft\*lbf|kg/m|lb/ft"
NUMBER = re.compile(rf"^\s*(-?)(\d+ \d+/\d+|\d+/\d+|\d+(?:\.\d+)?(?:e-?\d+)?|\.\d+)\s*({UNITS})\s*$")
SI = {"[length]": "m", "[mass]": "kg", "[length] ** 2": "m**2", "[length] ** 4": "m**4",
      "[mass] / [length] / [time] ** 2": "Pa", "[length] ** 2 * [mass] / [time] ** 2": "N*m",
      "[mass] / [length]": "kg/m"}
G_ACC = 9.80665


@dataclass
class Value:
    """One input in SI, with where it came from."""
    si: float | bool | str
    basis: str            # measured | maker | published | estimate
    ref: str = ""
    note: str = ""
    raw: str = ""
    path: str = ""


def _number(text):
    sign, num, unit = NUMBER.match(text).groups()
    if " " in num:                                       # "1 1/4"
        whole, frac = num.split(" ")
        a, b = frac.split("/")
        x = int(whole) + int(a) / int(b)
    elif "/" in num:
        a, b = num.split("/")
        x = int(a) / int(b)
    else:
        x = float(num)
    return (-x if sign else x), unit


def to_si(text: str) -> float:
    """'53.15 ft' -> 16.2001, '3/8 in' -> 0.009525, '20 %' -> 0.20, '15 deg' -> 0.2618, '2430 cm^4' -> 2.43e-05."""
    x, unit = _number(str(text))
    if unit == "%":
        return x / 100.0
    if unit in ("deg", "°"):
        return math.radians(x)
    if unit in ("lb", "lbs"):                            # mass, not force
        unit = "pound"
    q = UREG.Quantity(x, unit.replace("^", "**"))
    dim = str(q.dimensionality)
    if dim not in SI:
        raise ValueError(f"unexpected unit '{unit}' ({dim})")
    return float(q.to(SI[dim]).magnitude)


def _wrap(node, path):
    """A YAML leaf, bare or {value, basis, ref, note}, as a Value. A bare value counts as an estimate."""
    if isinstance(node, dict) and "value" in node and "basis" in node:
        raw, basis, ref, note = node["value"], node["basis"], node.get("ref", ""), node.get("note", "")
    else:
        raw, basis, ref, note = node, "estimate", "", ""
    si = to_si(raw) if isinstance(raw, str) and NUMBER.match(raw) else raw
    return Value(si, basis, ref, note, str(raw), path)


def walk(node, path=""):
    """Turn the whole document into nested dicts and lists of Value."""
    if isinstance(node, dict) and not ("value" in node and "basis" in node):
        return {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
    if isinstance(node, list):
        return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
    return _wrap(node, path)


# ---- checks -----------------------------------------------------------------------------------------

def _schema():
    try:
        text = resources.files("rigframe").joinpath("boat.schema.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        text = (Path(__file__).resolve().parents[2] / "schema" / "boat.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


def _line_of(text, path):
    """Best-effort line number for a schema error path, by finding its last key in the file."""
    keys = [p for p in path if isinstance(p, str)]
    if not keys:
        return None
    pat = re.compile(rf"^\s*-?\s*{re.escape(keys[-1])}\s*:", re.M)
    hits = [text[:m.start()].count("\n") + 1 for m in pat.finditer(text)]
    return hits[0] if len(hits) == 1 else None


def schema_problems(doc, text):
    out = []
    v = jsonschema.Draft202012Validator(_schema())
    for e in sorted(v.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        best = jsonschema.exceptions.best_match([e])
        where = ".".join(str(p) for p in e.absolute_path) or "(top level)"
        line = _line_of(text, list(e.absolute_path))
        msg = best.message
        if best.validator == "pattern":
            units = re.findall(r"\?\(([^()]*)\)\$$", best.validator_value)
            units = ", ".join(u.replace("\\", "") for u in units[0].split("|")) if units else "the documented units"
            msg = f"{best.instance!r} needs a number, a space, then one of: {units}."
        elif "is not valid under any of the given schemas" in msg:
            msg = (f"{best.instance!r} isn't a value this field takes. Numbers need a unit from the list in "
                   "docs/boat-yaml.md ('12 mm', '53.15 ft', '20 %'), or the {value, basis} form.")
        elif "Additional properties are not allowed" in msg:
            extra = set(best.instance) - set(best.schema.get("properties", {})) if isinstance(best.instance, dict) else set()
            if any(" " in str(k) or str(k).endswith(".") for k in extra):
                msg += (" A comma inside { } ends the value, so the rest of a note became a new key."
                        " Put the note in quotes: note: \"..., ...\".")
            else:
                msg += " Check the spelling against docs/boat-yaml.md."
        out.append(f"{where}{f' (line {line})' if line else ''}: {msg}")
    return out


def rig_problems(b):
    """Engineering sense checks the schema can't express."""
    out = []
    masts = {m["id"].si: m for m in b["masts"]}
    I = b["sail_plan"]["I"].si
    rig = b["boat"]["rig"].si
    two = rig.split()[1] in ("ketch", "yawl")
    if two != (len(masts) == 2):
        out.append(f"boat.rig is '{rig}' but there {'is' if len(masts) == 1 else 'are'} {len(masts)} mast(s).")
    if two and not {"PY", "EY"} <= set(b["sail_plan"]):
        out.append("sail_plan: a ketch or yawl needs PY and EY for the mizzen.")
    if "main" not in masts:
        out.append("masts: one mast must have id 'main'.")
    for mid, m in masts.items():
        hz = m["hounds_z"].si if "hounds_z" in m else (I if mid == "main" else None)
        if hz is None:
            out.append(f"masts.{mid}: hounds_z is needed for any mast but the main.")
            continue
        luff = b["sail_plan"]["P"].si if mid == "main" else b["sail_plan"].get("PY", Value(0, "")).si
        if m["gooseneck_z"].si + luff > hz + m["above_hounds"].si + 1e-6:
            out.append(f"masts.{mid}: gooseneck_z + luff ({m['gooseneck_z'].si + luff:.2f} m) puts the head of the sail "
                       f"above the masthead ({hz + m['above_hounds'].si:.2f} m).")
        if m["step"].si == "keel" and ("heel_z" not in m or m["heel_z"].si >= 0):
            out.append(f"masts.{mid}: a keel-stepped mast needs heel_z below the sheer (a negative length).")
        zs = [s["height"].si * hz if s["height"].raw.endswith("%") else s["height"].si for s in m["spreaders"]]
        if zs != sorted(zs) or (zs and not 0 < zs[0] and zs[-1] < hz):
            out.append(f"masts.{mid}.spreaders: list them bottom to top, between the deck and the hounds.")
        sh = m["shrouds"]
        if sh["arrangement"].si == "discontinuous" and len(m["spreaders"]) < 2:
            out.append(f"masts.{mid}.shrouds: discontinuous shrouds need at least two spreader sets.")
        if len(m["spreaders"]) >= 2 and "intermediate" not in sh:
            out.append(f"masts.{mid}.shrouds: two or more spreader sets need an intermediate shroud.")
        if sh["arrangement"].si == "continuous":
            for name in ("cap", "intermediate"):
                if name in sh and "chainplate" not in sh[name]:
                    out.append(f"masts.{mid}.shrouds.{name}: continuous shrouds need a chainplate.")
        lowers = sh.get("lowers", {})
        if "single" in lowers and ({"forward", "aft"} & set(lowers)):
            out.append(f"masts.{mid}.shrouds.lowers: give 'single', or 'forward' and/or 'aft', not both.")
    ids = [s["id"].si for s in b["stays"]]
    for s in b["stays"]:
        for end in ("top", "bottom"):
            e = s[end]
            if "mast" in e and e["mast"].si not in masts:
                out.append(f"stays.{s['id'].si}.{end}: no mast called '{e['mast'].si}'.")
        if "adjusts" in s and s["adjusts"].si not in ids:
            out.append(f"stays.{s['id'].si}.adjusts: no stay called '{s['adjusts'].si}'.")
    kinds = [s["kind"].si for s in b["stays"]]
    if "forestay" not in kinds:
        out.append("stays: there must be a forestay.")
    if not ({"backstay", "triatic"} & set(kinds)):
        out.append("stays: something must hold the main masthead aft: a backstay or a triatic.")
    if "triatic" in kinds and "mizzen_backstay" not in kinds:
        out.append("stays: a triatic needs mizzen backstays to hold it.")
    if two and "triatic" not in kinds and "mizzen_forestay" not in kinds:
        out.append("stays: without a triatic the mizzen needs a mizzen_forestay, or nothing holds its head forward.")
    if "cutter" in rig and "inner_forestay" not in kinds:
        out.append("stays: a cutter needs an inner_forestay (staysail stay).")
    return out


LAYOUT = (".step", ".arrangement")     # choices that change the model's shape


def inputs(node):
    """Every engineering input: the numbers, plus the layout choices that change the model's shape."""
    if isinstance(node, Value):
        if (isinstance(node.si, float) or node.path.endswith(LAYOUT)) and not node.path.startswith(
                ("load_cases", "analysis")):
            yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from inputs(v)
    elif isinstance(node, list):
        for v in node:
            yield from inputs(v)


def estimates(boat):
    """Every input still marked estimate: what the report asks the owner to measure or confirm."""
    return [v for v in inputs(boat) if v.basis == "estimate"
            and not v.path.endswith((".pretension", ".section.E"))   # a tuning target and a material constant
            and v.si != 0.0]                                          # the origin and the centreline


def load_boat(path):
    """(boat as nested Values, list of problems). Problems empty means the file is good to run."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        return None, [f"{where}this isn't valid YAML ({getattr(e, 'problem', e)}). Check the indentation: "
                      "two spaces per level, no tabs."]
    probs = schema_problems(doc, text)
    if probs:
        return None, probs
    boat = walk(doc)
    return boat, rig_problems(boat)


def main(argv=None):
    paths = argv if argv is not None else sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    bad = 0
    for p in paths:
        boat, probs = load_boat(p)
        if probs:
            bad += 1
            print(f"FAIL  {p}")
            for msg in probs:
                print(f"      - {msg}")
            continue
        est = estimates(boat)
        n = len(list(inputs(boat)))
        print(f"OK    {p}: {boat['boat']['name'].si}, {boat['boat']['rig'].si}, "
              f"{len(boat['masts'])} mast(s), {len(boat['stays'])} stays; {len(est)} of {n} inputs are estimates")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
