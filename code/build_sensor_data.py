#!/usr/bin/env python3
"""Turn the glider/PAM workbook into the sensor and PAM data the selection page uses.

Reads two sheets of output/Copy of Glider_Acoustic_System_info.xlsx:

  "Other glider sensors"     what each science sensor measures and which glider
                             families it is integrated on
  "Passive Acoustic system"  the PAM recorders, their specs and documented
                             glider integrations

and writes content/data/sensors.json, then injects it into
content/glider-selection.qmd between the SENSOR-DATA markers.

    python3 code/build_sensor_data.py

The injection only ever rewrites the marked block. content/glider-selection.qmd is
hand-maintained by several people — nothing else in it is touched, and the script
refuses to run if the markers are missing.

The workbook is read-only here. It is never written, because it carries a threaded
Excel comment that openpyxl drops on save.
"""

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = REPO / "output" / "Copy of Glider_Acoustic_System_info.xlsx"
JSON_OUT = REPO / "content" / "data" / "sensors.json"
QMD = REPO / "content" / "glider-selection.qmd"
BEGIN, END = "<!-- SENSOR-DATA:BEGIN -->", "<!-- SENSOR-DATA:END -->"

# The sheet records integration per glider *family*; the page's cards are specific
# models. One column can therefore light up more than one card.
FAMILY_COLS = {
    "Slocum (driver)": ["slocum-g3", "slocum-sentinel"],
    "Seaglider / SGX": ["seaglider-m1", "seaglider-sgx"],
    "SeaExplorer": ["seaexplorer-1000", "seaexplorer-200"],
    "Spray / Spray2": ["spray", "spray2"],
    "Other gliders": [],  # resolved from the cell text below
}

# Cell text that narrows a family column to one model, or names a glider outright in
# the free-text "Other gliders" column. Patterns, not plain substrings: "Spray2
# standard" must not also count as a plain Spray. Anything unmatched is reported at
# the end rather than dropped in silence.
TEXT_TO_GLIDER = [
    (r"spray\s*2", ["spray2"]),
    (r"spray(?!\s*2)", ["spray"]),
    (r"ocean\s*scout", ["oceanscout"]),
    (r"sentinel|redwing", ["slocum-sentinel"]),
    (r"sgx", ["seaglider-sgx"]),
    (r"seaglider", ["seaglider-m1", "seaglider-sgx"]),
    (r"seaexplorer", ["seaexplorer-1000", "seaexplorer-200"]),
    (r"slocum", ["slocum-g3", "slocum-sentinel"]),
]

# PAM models the selection page already knows by key. Keeping the keys means the
# glider cards' own `pam: [...]` lists keep working; the specs below come from the
# sheet. A model missing here gets a slug and is matched to gliders by its
# integration text alone.
PAM_KEYS = {
    "dmon2": "dmon2",
    "wispr3": "wispr3",
    "oceanobserver": "observer",
    "amarg4": "amar",
    "auris": "auris",
    "oceanscoutpam": "osPam",
    "seagliderpampackagewisprv1": "sgPam",
    "pmarxl": "pmar",
    "porpoise": "porpoise",
}


def clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def slug(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def gliders_from_text(text, default_ids):
    """Which glider cards a cell refers to: the column's family, narrowed by its text."""
    if not text:
        return []
    low = text.lower()
    named = []
    for pattern, ids in TEXT_TO_GLIDER:
        if re.search(pattern, low):
            for i in ids:
                if i not in named:
                    named.append(i)
    if not default_ids:
        return named  # the free-text column: the text is all there is
    # A family column: the text only narrows the family, never adds to it.
    narrowed = [i for i in named if i in default_ids]
    return narrowed or default_ids


def read_sensors(book, unmatched):
    rows = book.parse("Other glider sensors")
    out = []
    for _, r in rows.iterrows():
        model, param = clean(r["Model"]), clean(r["Parameter(s)"])
        if not model or not param:
            continue  # the sheet uses blank rows as separators
        by_glider = {}
        for col, family in FAMILY_COLS.items():
            cell = clean(r.get(col))
            if not cell:
                continue
            ids = gliders_from_text(cell, family)
            if not ids and col == "Other gliders":
                unmatched.append(f"sensor {model!r}: 'Other gliders' = {cell!r}")
            for i in ids:
                by_glider[i] = cell
        out.append({
            "id": f"{slug(r['Manufacturer'])}-{slug(model)}"[:60],
            "category": clean(r["Category"]) or "Other",
            "parameter": param,
            "maker": clean(r["Manufacturer"]) or "",
            "model": model,
            "gliders": by_glider,
            "usage": clean(r.get("Typical usage")),
            "notes": clean(r.get("Operational notes")),
            "sop": clean(r.get("Best practice / SOP")),
            "website": clean(r.get("Website")),
        })
    return out


def read_pam(book, unmatched):
    """One entry per recorder. Rows below an entry with no model continue it —
    the sheet uses them for a model's extra bandwidth and target lines."""
    rows = book.parse("Passive Acoustic system")
    out = []
    for _, r in rows.iterrows():
        model = clean(r["Model"])
        if model:
            key = PAM_KEYS.get(slug(model), slug(model)[:24])
            integ = clean(r.get("Glider integrations (documented)"))
            ids = gliders_from_text(integ, []) if integ else []
            if integ and not ids:
                unmatched.append(f"PAM {model!r}: integrations = {integ!r}")
            out.append({
                "key": key,
                "maker": clean(r["Manufacturer"]) or "",
                "model": model,
                "memory": clean(r.get("Memory capacity")),
                "channels": clean(r.get("Hydrophones #")),
                "bandwidth": [b for b in [clean(r.get("Bandwidth"))] if b],
                "duty": clean(r.get("Duty Cycle")),
                "detector": clean(r.get("Detector/Classifier")),
                "realtime": clean(r.get("Real time option")),
                "target": [t for t in [clean(r.get("Target"))] if t],
                "sampleRate": clean(r.get("Sample rate / bit depth")),
                "power": clean(r.get("Power")),
                "size": clean(r.get("Size / weight / depth rating")),
                "integrations": integ,
                "gliders": ids,
            })
        elif out:
            # A continuation row: keep whichever extra lines it carries.
            for field, col in (("bandwidth", "Bandwidth"), ("target", "Target")):
                v = clean(r.get(col))
                if v and v not in out[-1][field]:
                    out[-1][field].append(v)
    return out


def build(xlsx):
    book = pd.ExcelFile(xlsx)
    unmatched = []
    sensors = read_sensors(book, unmatched)
    pam = read_pam(book, unmatched)

    # Categories in sheet order, because the sheet groups them the way a reader
    # thinks about them (CTD first, then the things hung off the payload bay).
    categories = []
    for s in sensors:
        head = s["category"].split(" / ")[0]
        if head in categories:
            s["category"] = head
        elif s["category"] not in categories:
            categories.append(s["category"])

    return {
        "generated": date.today().isoformat(),
        "source": xlsx.name,
        "categories": categories,
        "sensors": sensors,
        "pam": pam,
    }, unmatched


def inject(data):
    if not QMD.exists():
        return False
    text = QMD.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{QMD} has no SENSOR-DATA markers — refusing to guess where the data goes")
    block = (f"{BEGIN}\n<script id=\"sensor-data\" type=\"application/json\">\n"
             f"{json.dumps(data, separators=(',', ':'))}\n</script>\n{END}")
    QMD.write_text(re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block,
                          text, flags=re.S))
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    args = p.parse_args()

    data, unmatched = build(args.xlsx)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {JSON_OUT.relative_to(REPO)} ({len(data['sensors'])} sensors in "
          f"{len(data['categories'])} categories, {len(data['pam'])} PAM systems)")
    print(f"{'injected into' if inject(data) else 'no page yet at'} {QMD.relative_to(REPO)}")
    for u in unmatched:
        print(f"  no glider matched: {u}")


if __name__ == "__main__":
    main()
