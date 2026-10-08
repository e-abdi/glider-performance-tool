#!/usr/bin/env python3
"""Turn the Slocum / Seaglider comparison sheet into the data the comparison page uses.

Reads output/direct comparison.ods (columns: Factor, Slocum, Seaglider, -, Comments;
a row with only a Factor cell is a section heading), joins each factor with its edge
topics and note topics (what the pilot note
itself speaks to, which the page highlights) from content/data/comparison-tags.csv, writes content/data/comparison.json,
then injects it into content/direct-comparison.qmd between the COMPARISON-DATA markers.

    python3 code/build_comparison_data.py

The spreadsheet holds the words; the CSV holds the judgement calls (which glider has
the edge, which topics a factor belongs to), so those can be changed from the repo
alone — the spreadsheet is gitignored. Factors missing from the CSV, or CSV rows that
match no factor, are reported rather than dropped in silence.

Standard library only: an .ods is a zip with one XML file in it.
"""

import argparse
import csv
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ODS = REPO / "output" / "direct comparison.ods"
TAGS_CSV = REPO / "content" / "data" / "comparison-tags.csv"
JSON_OUT = REPO / "content" / "data" / "comparison.json"
QMD = REPO / "content" / "direct-comparison.qmd"
BEGIN, END = "<!-- COMPARISON-DATA:BEGIN -->", "<!-- COMPARISON-DATA:END -->"

TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
EDGES = {"slocum", "seaglider", "depends", ""}


def para_text(el):
    """Text of a <text:p>, honouring <text:s c="n"/> runs of spaces and skipping annotations."""
    out = [el.text or ""]
    for child in el:
        tag = child.tag
        if tag == f"{{{TEXT}}}s":
            out.append(" " * int(child.get(f"{{{TEXT}}}c", "1")))
        elif tag in (f"{{{TEXT}}}tab",):
            out.append(" ")
        elif tag == f"{{{TEXT}}}line-break":
            out.append("\n")
        elif tag != f"{{{OFFICE}}}annotation":
            out.append(para_text(child))
        out.append(child.tail or "")
    return "".join(out)


def cell_text(cell):
    paras = [para_text(p) for p in cell.findall(f"{{{TEXT}}}p")]
    return re.sub(r"[ \t]+", " ", "\n".join(paras)).strip()


def read_rows(ods):
    root = ET.fromstring(zipfile.ZipFile(ods).read("content.xml"))
    sheet = next(root.iter(f"{{{TABLE}}}table"))
    for row in sheet.iter(f"{{{TABLE}}}table-row"):
        cells = []
        for c in row:
            if c.tag not in (f"{{{TABLE}}}table-cell", f"{{{TABLE}}}covered-table-cell"):
                continue
            n = int(c.get(f"{{{TABLE}}}number-columns-repeated", "1"))
            cells += [cell_text(c)] * min(n, 8)
            if len(cells) >= 8:
                break
        cells = (cells + [""] * 5)[:5]
        if any(cells):
            yield cells


def key(name):
    return re.sub(r"\s+", " ", name).strip().lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ods", nargs="?", type=Path, default=DEFAULT_ODS)
    args = ap.parse_args()

    tags = {}
    with open(TAGS_CSV, newline="") as f:
        for r in csv.DictReader(f):
            edge = r["edge"].strip().lower()
            if edge not in EDGES:
                sys.exit(f"{TAGS_CSV.name}: '{r['factor']}' has edge '{edge}', expected one of {sorted(EDGES - {''})}")
            topics = [t.strip() for t in r["topics"].split(";") if t.strip()]
            note_topics = [t.strip() for t in (r.get("note_topics") or "").split(";") if t.strip()]
            # A note about a topic puts its factor in that topic too.
            topics += [t for t in note_topics if t not in topics]
            tags[key(r["factor"])] = {"edge": edge, "topics": topics, "note_topics": note_topics}

    rows, section, used = [], "", set()
    rows_iter = read_rows(args.ods)
    next(rows_iter)  # header row
    for factor, slocum, seaglider, _, note in rows_iter:
        if factor and not (slocum or seaglider or note):
            section = re.sub(r"^\d+\.\s*", "", factor)
            continue
        t = tags.get(key(factor))
        if t is None:
            print(f"  no tags for '{factor}' — add it to {TAGS_CSV.name}", file=sys.stderr)
            t = {"edge": "", "topics": [], "note_topics": []}
        else:
            used.add(key(factor))
        rows.append({"section": section, "factor": factor.strip(), "slocum": slocum,
                     "seaglider": seaglider, "note": note, **t})

    for k in tags.keys() - used:
        print(f"  {TAGS_CSV.name} row '{k}' matches no factor in the sheet", file=sys.stderr)

    data = {"source": args.ods.name, "built": date.today().isoformat(), "rows": rows}
    JSON_OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")

    qmd = QMD.read_text()
    if BEGIN not in qmd or END not in qmd:
        sys.exit(f"{QMD.name}: COMPARISON-DATA markers missing, not touching it")
    block = (f"{BEGIN}\n<script>\nwindow.COMPARISON = "
             + json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
             + ";\n</script>\n" + END)
    head, rest = qmd.split(BEGIN, 1)
    QMD.write_text(head + block + rest.split(END, 1)[1])
    print(f"{len(rows)} factors in {len({r['section'] for r in rows})} sections -> {JSON_OUT.relative_to(REPO)} and {QMD.relative_to(REPO)}")


if __name__ == "__main__":
    main()
