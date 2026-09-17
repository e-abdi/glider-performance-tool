#!/usr/bin/env python3
"""Assemble content/slocum-endurance.qmd from the extracted model.

The page is self-contained: the interpreter (code/endurance_eval.js) and the model JSON
are inlined, so there is nothing to fetch and no Quarto resource to wire up. Re-run this
after code/extract_endurance_model.py.

Usage: python3 code/build_endurance_page.py
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "content" / "data" / "endurance-model.json"
EVAL = REPO / "code" / "endurance_eval.js"
OUT = REPO / "content" / "slocum-endurance.qmd"

# Every control: cell key, label, kind, and options. Labels marked dynamic are rendered
# from the workbook's own label formulas, so they track the mode the way Excel does.
GROUPS = [
    ("Mission", [
        ("P!F6", "Maximum profile depth", "num", {"unit": "m", "step": 10, "min": 1}),
        ("P!F7", "Minimum profile depth", "num", {"unit": "m", "step": 1, "min": 0}),
        ("P!F8", "Horizontal velocity", "num", {"unit": "m/s", "step": 0.01, "min": 0.01}),
        ("P!F9", "Vertical velocity", "num", {"unit": "m/s", "step": 0.01, "min": 0.01}),
        ("P!F11", "Surface on", "sel", {"options": [
            ["N", "Profile count"], ["T", "Elapsed time"], ["D", "Distance"]]}),
        ("P!F12", None, "num", {"label_from": "P!E12", "step": 1, "min": 0}),
        ("P!F13", "Surface time", "num", {"unit": "min", "step": 1, "min": 0}),
        ("P!F14", "Average operating temperature", "num", {"unit": "°C", "step": 1}),
    ]),
    ("Glider configuration", [
        ("P!F17", "Buoyancy pump", "sel", {"options": [
            ["1000", "1000 m pump"], ["200", "200 m pump"]], "numeric": True}),
        ("P!E22", "Glider type", "sel", {"options": [
            ["Coastal", "Coastal"], ["Open Ocean", "Open Ocean"]]}),
        ("P!F19", "Altimeter", "bool", {}),
        ("P!F18", "Pinger", "bool", {}),
        ("P!F20", "FreeWave", "bool", {}),
        ("P!F21", "PTT / Argos", "bool", {}),
    ]),
    ("Battery", [
        ("P!F26", "Chemistry", "sel", {"options": [
            # The workbook also models Lithium C ("Lc") and Tadiran ("t"); both are left
            # off the menu as packs this group does not fly. The model still supports them.
            ["Ld", "Lithium"], ["a", "Alkaline"]]}),
        ("P!E28", "Type", "sel", {"options": [["P", "Primary"], ["R", "Rechargeable"]]}),
        ("P!E29", "Extended energy bay", "bool", {}),
        # The workbook's "Remaining energy (%)" input is deliberately absent: it only scales
        # the bare-glider figures we dropped, and has no effect on K30/K31. Shipping it would
        # be a control that silently does nothing. To make it real, K30 would need to become
        #   ROUND(capacity * F32/100 / K20, 0)
        # which is a change to the workbook's logic, not a port of it.
    ]),
    ("Standard science payload", [
        ("P!F36", "CTD", "frac", {}),
        ("P!F37", "Motherboard", "frac", {}),
        ("P!F39", "Persistor", "frac", {}),
        ("P!F40", "Aanderaa optode", "frac", {}),
        ("P!F41", "Explorer 600 kHz DVL", "frac", {}),
        ("P!F42", "FLBBCD-SLK", "frac", {}),
        ("P!F43", "Biospherical QSP-2150", "frac", {}),
    ]),
    ("Thruster and extra sensors", [
        ("P!K43", "Thruster use (at 7 W)", "num", {"unit": "%", "step": 5, "min": 0, "max": 100}),
        ("P!F50", "UVP6", "frac", {"ah": 1.6}),
        ("P!F51", "EK80", "frac", {"ah": 11.2}),
        # The workbook calls this row "Hydrophone" and charges it a generic 1.6 Ah/day.
        # Renamed on request; the figure is still the workbook's generic one.
        ("P!F52", "JASCO OceanObserver", "frac", {"ah": 1.6}),
        ("P!F53", "eDNA", "frac", {"ah": 6.4}),
    ]),
]

# Where the page should open, for cells whose workbook value is not the configuration this
# group actually flies. Everything not listed here starts on the workbook's own saved value.
PAGE_DEFAULTS = {
    "P!F52": 1,    # JASCO OceanObserver on
    "P!F51": 0,    # EK80 off
    "P!F50": 0,    # UVP6 off
    "P!F53": 0,    # eDNA off
    "P!K43": 0,    # no thruster
}

GEOMETRY = [
    ("P!K6", "Trajectory angle", "°", 1),
    ("P!K7", "Profile duration", "min", 1),
    ("P!K8", "Profile distance", "m", 0),
    ("P!K9", "Profiles between surfacing", "", 1),
    ("P!K10", "Time between surfacing", "min", 1),
    ("P!K11", "Distance between surfacing", "km", 2),
    ("P!K18", "Battery capacity (derated)", "Ah", 0),
]

CSS = """
  #set {
    --surface: #FFFFFF; --surface-2: #F1F6F7; --line: #DAE3E5; --line-strong: #BCCBCE;
    --ink: #1F2C31; --ink-2: #536268; --ink-3: #78888E;
    --accent: #2780E3; --accent-ink: #1B62B0; --accent-soft: #E3EEFB;
    --good: #1A6B4E; --warn: #A33227; --warn-soft: #F8E4E1;
    --sans: "Atkinson Hyperlegible", "Helvetica Neue", Arial, sans-serif;
    --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
    max-width: 1150px; color: var(--ink); font-family: var(--sans); line-height: 1.55;
  }
  body.quarto-dark #set, :root[data-bs-theme="dark"] #set {
    --surface: #212121; --surface-2: #2A2A2A; --line: #3A3A3A; --line-strong: #4E4E4E;
    --ink: #F2F2F2; --ink-2: #BFC6C8; --ink-3: #939A9D;
    --accent: #75AADB; --accent-ink: #9CC6EC; --accent-soft: #23323F;
    --good: #6DC49B; --warn: #E08278; --warn-soft: #3A211E;
  }
  #set * { box-sizing: border-box; }
  #set .lede { color: var(--ink-2); max-width: 74ch; }

  /* ---- results ---- */
  #set .results {
    position: sticky; top: 0; z-index: 5; background: var(--surface);
    border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px;
    margin: 18px 0 26px; box-shadow: 0 6px 18px rgba(31,44,49,.07);
  }
  #set .headline { display: flex; flex-wrap: wrap; gap: 26px 44px; align-items: baseline; }
  #set .big { display: flex; flex-direction: column; gap: 2px; }
  #set .big .v { font-size: 40px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
  #set .big .v small { font-size: 17px; font-weight: 400; color: var(--ink-3); margin-left: 5px; }
  #set .big .k { font-size: 11.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-3); }
  #set .load { display: flex; flex-wrap: wrap; gap: 8px 22px; margin-left: auto; }
  #set .load div { font-size: 12.5px; color: var(--ink-2); }
  #set .load b { font-family: var(--mono); color: var(--ink); font-variant-numeric: tabular-nums; }
  #set .alerts { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
  #set .alert {
    font-size: 13px; color: var(--warn); background: var(--warn-soft);
    border-radius: 6px; padding: 7px 11px;
  }

  /* ---- inputs ---- */
  #set .panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 16px; }
  #set .panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
  #set .panel h3 {
    font-size: 12px; letter-spacing: .07em; text-transform: uppercase; color: var(--ink-3);
    margin: 0 0 10px; font-weight: 700;
  }
  #set .f { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; align-items: center; padding: 5px 0; }
  #set .f + .f { border-top: 1px solid var(--line); }
  #set .f label { font-size: 13.5px; color: var(--ink-2); }
  #set .f .ctl { display: flex; align-items: center; gap: 6px; }
  #set input[type="number"], #set select {
    font: inherit; font-size: 13.5px; font-family: var(--mono); text-align: right;
    width: 92px; padding: 4px 7px; border: 1px solid var(--line-strong);
    border-radius: 6px; background: var(--surface); color: var(--ink);
  }
  #set select { width: 140px; text-align: left; font-family: var(--sans); }
  #set input[type="checkbox"] { width: 17px; height: 17px; accent-color: var(--accent); margin: 0; }
  #set .unit { font-size: 12px; color: var(--ink-3); min-width: 30px; }
  #set input:focus-visible, #set select:focus-visible, #set button:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  #set .ah { font-size: 11px; color: var(--ink-3); font-family: var(--mono); }

  /* ---- geometry ---- */
  #set .geo { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 2px 20px; }
  #set .geo div { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; padding: 5px 0; border-bottom: 1px solid var(--line); }
  #set .geo span:first-child { color: var(--ink-2); }
  #set .geo span:last-child { font-family: var(--mono); font-variant-numeric: tabular-nums; }

  #set .bar { display: flex; gap: 10px; align-items: center; margin: 18px 0 6px; }
  #set button {
    font: inherit; font-size: 13.5px; font-weight: 700; cursor: pointer; border-radius: 7px;
    padding: 7px 15px; border: 1px solid var(--line-strong); background: var(--surface); color: var(--accent-ink);
  }
  #set .check { font-size: 12.5px; color: var(--ink-3); margin-left: auto; font-family: var(--mono); }
  #set .check.ok { color: var(--good); }
  #set footer.src { margin-top: 26px; border-top: 1px solid var(--line); padding-top: 12px; font-size: 12.5px; color: var(--ink-3); }
  #set h2.sec { font-size: 18px; margin: 28px 0 10px; font-weight: 700; }
"""


def control_html(key, label, kind, opt):
    cid = "i_" + key.replace("!", "_")
    lab = f'<label for="{cid}" data-label-for="{opt["label_from"]}">…</label>' if opt.get("label_from") \
        else f'<label for="{cid}">{label}</label>'
    ah = f'<span class="ah">{opt["ah"]} Ah/d</span>' if opt.get("ah") else ""
    if kind == "bool":
        ctl = f'<input type="checkbox" id="{cid}" data-cell="{key}" data-kind="bool">'
    elif kind == "sel":
        opts = "".join(f'<option value="{v}">{t}</option>' for v, t in opt["options"])
        num = ' data-numeric="1"' if opt.get("numeric") else ""
        ctl = f'<select id="{cid}" data-cell="{key}" data-kind="sel"{num}>{opts}</select>'
    elif kind == "frac":
        ctl = (f'{ah}<input type="number" id="{cid}" data-cell="{key}" data-kind="num" '
               f'min="0" max="1" step="0.1" style="width:70px">')
    else:
        attrs = "".join(f' {a}="{opt[a]}"' for a in ("min", "max", "step") if a in opt)
        unit = f'<span class="unit">{opt["unit"]}</span>' if opt.get("unit") else ""
        ctl = f'<input type="number" id="{cid}" data-cell="{key}" data-kind="num"{attrs}>{unit}'
    return f'        <div class="f">{lab}<div class="ctl">{ctl}</div></div>'


def main():
    model = json.loads(MODEL.read_text(encoding="utf8"))

    panels = []
    for title, fields in GROUPS:
        rows = "\n".join(control_html(*f) for f in fields)
        panels.append(f'      <section class="panel">\n        <h3>{title}</h3>\n{rows}\n      </section>')
    panels_html = "\n".join(panels)

    geo_html = "\n".join(
        f'        <div><span>{lab}</span><span id="g_{k.replace("!", "_")}">–</span></div>'
        for k, lab, _u, _d in GEOMETRY)

    spec = {
        "geometry": [[k, u, d] for k, _l, u, d in GEOMETRY],
        "alerts": ["P!F5", "P!E30", "P!H18", "P!H24"],
        "labels": {"P!F12": "P!E12"},
        "defaults": PAGE_DEFAULTS,
    }

    body = f"""<div id="set">

  <p class="lede">Predicts how long a Slocum will last on a given mission, from Teledyne Webb
  Research's <b>Slocum Endurance Tool</b> (revision C, 2012&#8209;10&#8209;19). The workbook's
  formulas are evaluated here as-is rather than reimplemented, so the numbers are Excel's:
  all {len(model["cached"])} cells the model computes are checked against the workbook's own
  stored results.</p>

  <div class="results">
    <div class="headline">
      <div class="big"><span class="v" id="o_days">–</span><span class="k">Endurance (days)</span></div>
      <div class="big"><span class="v" id="o_km">–</span><span class="k">Approximate distance (km)</span></div>
      <div class="load">
        <div>Glider + standard sensors <b id="o_k19">–</b> Ah/day</div>
        <div>Total with thruster + extras <b id="o_k20">–</b> Ah/day</div>
      </div>
    </div>
    <div class="alerts" id="alerts"></div>
  </div>

  <h2 class="sec">Mission and configuration</h2>
  <div class="panels">
{panels_html}
  </div>

  <h2 class="sec">Mission geometry</h2>
  <div class="geo">
{geo_html}
  </div>

  <div class="bar">
    <button id="reset">Reset to defaults</button>
    <span class="check" id="check">–</span>
  </div>

  <footer class="src">
    <p>Endurance is battery capacity by chemistry and bay
    (550 / 800 Ah primary, 215 / 300 Ah rechargeable) divided by total Ah per day, where the
    glider-and-standard-sensor load comes from the workbook's component power model and the
    thruster, UVP6, EK80, hydrophone and eDNA loads are added on top. Distance assumes 20 km/day.</p>
    <p>The workbook also reports a bare-glider endurance from the same power model. It is not
    shown here: it excludes the external sensors, so on these defaults it reads about five times
    longer and answers a different question.</p>
  </footer>
</div>"""

    qmd = f"""---
title: "Slocum Endurance Calculation"
page-layout: full
toc: false
format:
  html:
    include-in-header:
      text: |
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap">
---

```{{=html}}
<style>{CSS}</style>

{body}

<script>
{EVAL.read_text(encoding="utf8").strip()}
</script>

<script>
const MODEL = {json.dumps(model, separators=(",", ":"))};
const SPEC = {json.dumps(spec, separators=(",", ":"))};
{UI}
</script>
```
"""
    OUT.write_text(qmd, encoding="utf8")
    print(f"-> {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")


UI = r"""
(function () {
  "use strict";
  const model = new EnduranceEval.Model(MODEL.cells);
  const controls = Array.from(document.querySelectorAll("#set [data-cell]"));
  const fmt = (v, d) => (typeof v === "number" && isFinite(v))
    ? v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
    : "–";

  // Each control starts on the workbook's own saved value, except where SPEC.defaults
  // overrides it with the payload this group actually flies.
  const defaults = {};
  controls.forEach((el) => {
    const k = el.dataset.cell;
    defaults[k] = k in SPEC.defaults ? SPEC.defaults[k] : MODEL.cells[k];
  });

  function setControl(el, value) {
    if (el.dataset.kind === "bool") el.checked = Number(value) !== 0;
    else if (el.dataset.kind === "sel") el.value = String(value);
    else el.value = value;
  }

  function readInputs() {
    const out = {};
    controls.forEach((el) => {
      const k = el.dataset.cell;
      if (el.dataset.kind === "bool") out[k] = el.checked ? 1 : 0;
      else if (el.dataset.kind === "sel") out[k] = el.dataset.numeric ? Number(el.value) : el.value;
      else {
        const n = parseFloat(el.value);
        out[k] = isNaN(n) ? 0 : n;
      }
    });
    return out;
  }

  function render() {
    const inputs = readInputs();
    let r;
    try {
      model.reset(inputs);
      r = {
        days: model.get("P!K30"), km: model.get("P!K31"),
        k19: model.get("P!K19"), k20: model.get("P!K20")
      };
    } catch (e) {
      document.getElementById("alerts").innerHTML =
        '<div class="alert">' + e.message + "</div>";
      ["o_days", "o_km", "o_k19", "o_k20"].forEach((id) => {
        document.getElementById(id).textContent = "–";
      });
      return;
    }

    document.getElementById("o_days").innerHTML = fmt(r.days, 0) + " <small>days</small>";
    document.getElementById("o_km").innerHTML = fmt(r.km, 0) + " <small>km</small>";
    document.getElementById("o_k19").textContent = fmt(r.k19, 2);
    document.getElementById("o_k20").textContent = fmt(r.k20, 2);

    SPEC.geometry.forEach(([key, unit, dp]) => {
      const el = document.getElementById("g_" + key.replace("!", "_"));
      let v;
      try { v = model.get(key); } catch (e) { v = null; }
      el.textContent = fmt(v, dp) + (unit ? " " + unit : "");
    });

    // Labels the workbook itself computes, so the wording tracks the mode.
    Object.entries(SPEC.labels).forEach(([cell, from]) => {
      const el = document.querySelector('[data-label-for="' + from + '"]');
      if (!el) return;
      let t;
      try { t = model.get(from); } catch (e) { t = ""; }
      el.textContent = String(t || "").replace(/:$/, "");
    });

    const alerts = SPEC.alerts.map((k) => {
      try { const v = model.get(k); return typeof v === "string" ? v.trim() : ""; }
      catch (e) { return ""; }
    }).filter(Boolean);
    document.getElementById("alerts").innerHTML =
      alerts.map((a) => '<div class="alert">' + a + "</div>").join("");
  }

  // Confirm on load that the interpreter still reproduces the workbook, and say so.
  function selfCheck() {
    model.reset();
    let ok = 0, total = 0, bad = 0;
    for (const key in MODEL.cached) {
      total++;
      let got;
      try { got = model.get(key); } catch (e) { bad++; continue; }
      const want = MODEL.cached[key];
      const g = typeof got === "boolean" ? (got ? 1 : 0) : got;
      if (typeof g === "number" && Math.abs(g - want) / Math.max(1, Math.abs(want)) <= 1e-9) ok++;
      else bad++;
    }
    const el = document.getElementById("check");
    el.textContent = bad === 0
      ? "✓ matches the workbook on all " + total + " computed cells"
      : bad + " of " + total + " cells differ from the workbook";
    el.classList.toggle("ok", bad === 0);
  }

  controls.forEach((el) => {
    setControl(el, defaults[el.dataset.cell]);
    el.addEventListener("input", render);
    el.addEventListener("change", render);
  });
  document.getElementById("reset").addEventListener("click", () => {
    controls.forEach((el) => setControl(el, defaults[el.dataset.cell]));
    render();
  });

  selfCheck();
  render();
})();
"""

if __name__ == "__main__":
    main()
