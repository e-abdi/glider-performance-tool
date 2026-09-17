#!/usr/bin/env python3
"""Extract the Slocum Endurance Tool's calculation into JSON for the web page.

The workbook is Teledyne Webb Research's endurance tool. Rather than re-implement its
model by hand — 712 formulas over 335 component constants, which is a lot of places to
mistype a number — this pulls the *formulas themselves* out and ships them as data. The
page evaluates them with a small interpreter, so the arithmetic stays Excel's.

Only the cells that `K30`/`K31` actually depend on are extracted (the transitive closure
of the endurance chain), which leaves out the workbook's unused data-transmission and
bare-glider-endurance branches.

Every cell's last-computed value is carried along as `cached`, giving the JS side an exact
regression oracle: `node check_endurance_model.js` recomputes all of them and compares.

Usage:  python3 code/extract_endurance_model.py
Writes: content/data/endurance-model.json
"""
import json
import re
from pathlib import Path

import openpyxl

WORKBOOK = Path("output/Slocum Endurance Tool.xlsx")
OUT = Path("content/data/endurance-model.json")

# Short sheet keys keep the JSON (and every formula we rewrite) compact.
SHEETS = {"Glider Parameters": "P", "Glider Model": "M"}

# The endurance chain Ehsan wrote on top of the model, plus the mission geometry that
# lets you sanity-check the inputs, plus the cells that carry the sheet's own dynamic
# labels and error messages.
#
# The workbook's bare-glider figures ('Glider Model'!Q7-Q10, and the K12-K17 block that
# displays them) are deliberately NOT roots: they leave out the external sensors, so
# they answer a different question and differ by ~5x. Same for the data-transmission
# branch (Y4/Y5), which the endurance prediction does not use.
ROOTS = [("Glider Parameters", a) for a in (
    "K6", "K7", "K8", "K9", "K10", "K11",      # mission geometry
    "K18", "K19", "K20", "K30", "K31",         # battery capacity, load, endurance
    "E12", "E27",                              # labels that depend on the mode chosen
    "F5", "E30", "H18", "H24",                 # validation messages
)]

STRING_LITERAL = re.compile(r'"[^"]*"')
REF = re.compile(
    r"(?:'([^']+)'!|([A-Za-z_][A-Za-z0-9_]*)!)?"      # optional sheet prefix
    r"(\$?[A-Z]{1,2}\$?[0-9]+)"                        # anchor cell
    r"(?::(\$?[A-Z]{1,2}\$?[0-9]+))?"                  # optional range end
)
A1 = re.compile(r"([A-Z]+)([0-9]+)")


def col_to_num(col):
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_refs(formula, home):
    """Yield (sheet, addr) for every cell a formula reads, expanding ranges.

    String literals are blanked first — "Error! Profile Too Deep!" otherwise looks
    like a sheet-qualified reference.
    """
    body = STRING_LITERAL.sub('""', formula)
    for m in REF.finditer(body):
        sheet = (m.group(1) or m.group(2) or home)
        if sheet not in SHEETS:
            sheet = home
        start = m.group(3).replace("$", "")
        end = m.group(4)
        if not end:
            yield sheet, start
            continue
        end = end.replace("$", "")
        c1, r1 = A1.match(start).groups()
        c2, r2 = A1.match(end).groups()
        for c in range(min(col_to_num(c1), col_to_num(c2)), max(col_to_num(c1), col_to_num(c2)) + 1):
            for r in range(min(int(r1), int(r2)), max(int(r1), int(r2)) + 1):
                yield sheet, f"{num_to_col(c)}{r}"


def qualify(formula, home):
    """Rewrite every reference to the short `SheetKey!ADDR` form, so the JS
    interpreter never has to track a 'current sheet'."""
    out, last = [], 0
    body = STRING_LITERAL.sub(lambda m: " " * len(m.group(0)), formula)
    for m in REF.finditer(body):
        sheet = (m.group(1) or m.group(2) or home)
        if sheet not in SHEETS:
            sheet = home
        start, end = m.group(3).replace("$", ""), m.group(4)
        ref = f"{SHEETS[sheet]}!{start}" + (f":{end.replace('$', '')}" if end else "")
        out.append(formula[last:m.start()])
        out.append(ref)
        last = m.end()
    out.append(formula[last:])
    return "".join(out)


def main():
    wb = openpyxl.load_workbook(WORKBOOK)
    wv = openpyxl.load_workbook(WORKBOOK, data_only=True)

    cells, cached, seen = {}, {}, set()
    stack = list(ROOTS)
    while stack:
        sheet, addr = stack.pop()
        if (sheet, addr) in seen:
            continue
        seen.add((sheet, addr))
        key = f"{SHEETS[sheet]}!{addr}"

        raw = wb[sheet][addr].value
        value = wv[sheet][addr].value
        if isinstance(value, (int, float)):
            cached[key] = value

        if isinstance(raw, str) and raw.startswith("="):
            # Keep the leading "=" so the interpreter can tell a formula from a text
            # cell with certainty, and fail loudly instead of guessing.
            cells[key] = "=" + qualify(raw[1:].strip(), sheet)
            stack.extend(parse_refs(raw[1:], sheet))
        elif raw is None:
            cells[key] = 0          # Excel reads an empty cell as 0 in arithmetic
        else:
            cells[key] = raw

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": WORKBOOK.name,
        "note": "Extracted from the Teledyne Webb Research Slocum Endurance Tool. "
                "Formulas are Excel's, evaluated in the browser.",
        "sheets": SHEETS,
        "cells": cells,
        "cached": cached,
    }, indent=0, sort_keys=True), encoding="utf8")

    formulas = sum(1 for v in cells.values() if isinstance(v, str))
    print(f"{len(cells)} cells ({formulas} formulas, {len(cells) - formulas} constants)")
    print(f"{len(cached)} cached values for validation")
    print(f"-> {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
