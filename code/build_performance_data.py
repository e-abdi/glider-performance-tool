#!/usr/bin/env python3
"""Turn output/glider_performance_summary.xlsx into the data the performance page plots.

The spreadsheet is the calculation; this script only reshapes it. It writes
content/data/performance.json and then injects that JSON into content/performance.qmd
between the PERF-DATA markers, so the page is self-contained (no fetch, no Quarto
resource to wire up).

    python3 code/build_performance_data.py

The injection is surgical: everything outside the two marker comments in the qmd is
left exactly as found, so the page stays safe to hand-edit. Re-run this after
code/build_summary.py regenerates the spreadsheet.

Inputs:
    --xlsx  summary spreadsheet, default output/glider_performance_summary.xlsx
Outputs:
    content/data/performance.json   the page data, also injected into content/performance.qmd
    content/data/glider_performance_summary.csv   the mission-mode table, for download
"""

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = REPO / "output" / "glider_performance_summary.xlsx"
JSON_OUT = REPO / "content" / "data" / "performance.json"
CSV_OUT = REPO / "content" / "data" / "glider_performance_summary.csv"
QMD = REPO / "content" / "performance.qmd"
BEGIN, END = "<!-- PERF-DATA:BEGIN -->", "<!-- PERF-DATA:END -->"

# The rodeo mission modes in the order they were flown, with the short labels the
# x-axis uses. The last three are the mini-repeat of slow/intermediate/fast.
MODES = [
    ("shakedown", "shake"),
    ("fast", "fast"),
    ("slow", "slow"),
    ("intermediate", "inter"),
    ("drift", "drift"),
    ("mini-slow", "m-slow"),
    ("mini-intermediate", "m-inter"),
    ("mini-fast", "m-fast"),
]
MINI_SPLIT = 4.5  # the hairline sits between drift and the mini-repeat block

# Every metric the page can draw a panel for: the spreadsheet column, the key the
# page uses, a label, its unit, and whether it is on screen by default.
# "kind" groups metrics that share a unit family, for the tradeoff axis labels.
METRICS = [
    ("Watts", "watts", "Mean power draw", "W", "energy", True),
    ("W h/dive", "whPerDive", "Energy per dive", "W h", "energy", True),
    ("W h per km", "whPerKm", "Energy per km travelled", "W h/km", "energy", False),
    ("median |vert speed| m/s", "vertSpeed", "Vertical speed", "m/s", "speed", True),
    ("km per hour", "kmPerHour", "Speed over ground", "km/h", "speed", True),
    ("km/dive", "kmPerDive", "Distance per dive", "km", "distance", False),
    ("median dive h", "diveHours", "Dive duration", "h", "time", False),
    ("median max depth m", "maxDepth", "Dive depth", "m", "depth", False),
    ("cc pumped per hour", "ccPerHour", "Buoyancy pump volume", "cc/h", "pump", True),
    ("cc pumped per dive", "ccPerDive", "Pump volume per dive", "cc", "pump", False),
    ("pump moves per hour", "pumpMoves", "Pump adjustments", "per hour", "pump", False),
    ("dives", "dives", "Dives completed in mode", "count", "count", False),
]

# Values the Notes sheet says not to trust. The page draws these dashed and hides
# them by default, rather than dropping them silently or letting them set the scale.
FLAGS = [
    ("belladonna", "vertSpeed",
     "CTD timestamps arrive in bursts (samples under 1 ms apart), so rates computed "
     "between samples are far too high. Shown for completeness only."),
]

# The columns the deployment table shows, in order: (source sheet, column, header).
SUMMARY_COLS = [
    ("Gliders", "platform", "Platform"),
    ("Gliders", "owner", "Owner"),
    ("Gliders", "PAM system", "PAM system"),
    ("Gliders", "deployment days", "Days"),
    ("Gliders", "profiles", "Profiles"),
    ("Gliders", "max depth m", "Max depth (m)"),
    ("Gliders", "Raw Data size (GB)", "Data (GB)"),
    ("Power use", "dives", "Dives"),
    ("Power use", "W h/dive", "W h/dive"),
    ("Power use", "Watts", "Watts"),
    ("Power use", "energy source", "Energy measured by"),
]


def clean(v):
    """JSON has no NaN: every missing number becomes null, every value a plain type."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp, date)):
        return str(v)
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def build(xlsx):
    book = pd.ExcelFile(xlsx)
    gliders_sheet = book.parse("Gliders")
    power = book.parse("Power use")
    modes = book.parse("Mission modes")
    notes = book.parse("Notes")

    order = list(gliders_sheet.glider)  # build_summary.py already sorted these
    mode_names = [m for m, _ in MODES]

    # series[glider][metric] is one value per mission mode, in flight order, so the
    # page can hand a whole panel to Plotly without reshaping anything.
    series = {}
    for name in order:
        rows = modes[modes.glider == name].set_index("mode")
        series[name] = {
            key: [clean(rows[col].get(m)) if col in rows else None for m in mode_names]
            for col, key, _, _, _, _ in METRICS
        }

    power_by_glider = power.set_index("glider")
    summary = []
    for name in order:
        g = gliders_sheet.set_index("glider").loc[name]
        p = power_by_glider.loc[name] if name in power_by_glider.index else None
        row = {"glider": name}
        for sheet, col, _ in SUMMARY_COLS:
            src = g if sheet == "Gliders" else p
            row[col] = clean(src[col]) if src is not None and col in src else None
        row["hydrophone"] = clean(g["hydrophone"])
        row["battery"] = f"{clean(g['battery type'])}" + (
            f", {clean(g['battery capacity'])}" if clean(g["battery capacity"]) else "")
        summary.append(row)

    volume = []
    for name in order:
        g = gliders_sheet.set_index("glider").loc[name]
        gb = clean(g.get("Raw Data size (GB)"))
        days = clean(g["deployment days"])
        volume.append({
            "glider": name,
            "pam": clean(g["PAM system"]),
            "platform": clean(g["platform"]),
            "gb": gb,
            "days": days,
            "gbPerDay": round(gb / days, 1) if gb and days else None,
        })

    return {
        "generated": date.today().isoformat(),
        "source": xlsx.name,
        "modes": [{"name": n, "short": s} for n, s in MODES],
        "miniSplit": MINI_SPLIT,
        "gliders": order,
        "metrics": [{"key": k, "label": lab, "unit": u, "kind": kind, "default": d}
                    for _, k, lab, u, kind, d in METRICS],
        "series": series,
        "flags": [{"glider": g, "metric": m, "reason": r} for g, m, r in FLAGS],
        "summaryCols": [{"col": c, "header": h} for _, c, h in SUMMARY_COLS],
        "summary": summary,
        "volume": volume,
        "notes": [{"item": clean(i), "note": clean(n)} for i, n in
                  zip(notes["item"], notes["note"])],
    }


def inject(data):
    """Replace the data block in the qmd, leaving every hand-edit around it intact."""
    if not QMD.exists():
        return False
    text = QMD.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{QMD} has no PERF-DATA markers — refusing to guess where the data goes")
    block = (f"{BEGIN}\n<script id=\"perf-data\" type=\"application/json\">\n"
             f"{json.dumps(data, separators=(',', ':'))}\n</script>\n{END}")
    QMD.write_text(re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block,
                          text, flags=re.S))
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    args = p.parse_args()

    data = build(args.xlsx)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.read_excel(args.xlsx, "Mission modes").to_csv(CSV_OUT, index=False)
    JSON_OUT.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {JSON_OUT.relative_to(REPO)} "
          f"({len(data['gliders'])} gliders x {len(data['modes'])} modes x "
          f"{len(data['metrics'])} metrics)")
    print(f"wrote {CSV_OUT.relative_to(REPO)}")
    print(f"{'injected into' if inject(data) else 'no page yet at'} {QMD.relative_to(REPO)}")


if __name__ == "__main__":
    main()
