#!/usr/bin/env node
/*
 * Validate the Seaglider endurance model against every logged dive, then refresh the page.
 *
 * 1. Runs code/seaglider_model.js on each dive in content/data/seaglider-dives.csv, using
 *    only what a pilot would plan with (depth, vertical speed, surface time, MAX_BUOY, SM_CC,
 *    data volume, sensor settings), and compares the prediction with the energy the glider
 *    logged for that dive. Exits non-zero if any mission's total is off by more than
 *    TOLERANCE, so a refit that breaks the model cannot quietly reach the page.
 * 2. Rewrites only the block between the SEAGLIDER-DATA markers in
 *    content/seaglider-endurance.qmd with the model, the validation and the model code.
 *    The rest of the page is hand-maintained; the script refuses to run without the markers.
 *
 * Usage: node code/build_seaglider_page.js          (validate and update the page)
 *        node code/build_seaglider_page.js --check  (validate only)
 */
"use strict";
const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..");
const MODEL = path.join(REPO, "content/data/seaglider-model.json");
const DIVES = path.join(REPO, "content/data/seaglider-dives.csv");
const PAGE = path.join(REPO, "content/seaglider-endurance.qmd");
const CODE = path.join(REPO, "code/seaglider_model.js");
const BEGIN = "<!-- SEAGLIDER-DATA:BEGIN -->";
const END = "<!-- SEAGLIDER-DATA:END -->";
const TOLERANCE = 0.25; // largest allowed |model/logged - 1| for a mission's total energy

const SeagliderModel = require(CODE);
const model = JSON.parse(fs.readFileSync(MODEL, "utf8"));

function parseCsv(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line) continue;
    const out = [];
    let cur = "", q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (q) {
        if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') q = false;
        else cur += c;
      } else if (c === '"') q = true;
      else if (c === ",") { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    rows.push(out);
  }
  const head = rows.shift();
  return rows.map((r) => {
    const o = {};
    head.forEach((h, i) => {
      const v = r[i];
      o[h] = v === "" || v === undefined ? null : isNaN(+v) ? v : +v;
    });
    return o;
  });
}

const n = (v) => (v == null ? 0 : v);

// The science sensors as they appear in the log, and the model's key for each.
const SCI_LOG = { SBE_CT: "SBE_CT", CONTOPT: "CONTOPT", WL_ECO: "WL_blue_red_Chl_old_fw" };
const LOGGERS = { PAM: "PAM", UVP: "UVP", ESNDR: "ESNDR" };

function loggedAh(d) {
  let ah = 0;
  for (const k of Object.keys(d)) {
    if (k.startsWith("e_")) ah += n(d[k]);
    if (k.startsWith("S_")) ah += n(d[k]) * n(d["I_" + k.slice(2)]) / 3.6e6;
  }
  return ah;
}

function diveConfig(d, mission) {
  const glider = model.gliders[String(d.ID)];
  const diveS = d.dive_min * 60;
  const sensors = String(d.sensors || "").split("|");
  const scicon = sensors.includes("SciCon");
  const science = {};
  let interval = diveS / d.n_eng;
  if (scicon) {
    // The SciCon on SG644 carried the CT, the Contros optode and the SeaOWL.
    ["SBE_CT", "CONTOPT", "SEAOWL"].forEach((k) => (science[k] = { on: true }));
    if (d.S_SciCon > 0 && d.n_sbect > 0) interval = d.S_SciCon / d.n_sbect;
  } else {
    for (const [k, log] of Object.entries(SCI_LOG)) {
      if (sensors.includes(log)) science[k] = { on: true, mA: d["I_" + log] };
    }
  }
  const loggers = [];
  for (const [k, log] of Object.entries(LOGGERS)) {
    if (!sensors.includes(log)) continue;
    loggers.push({
      key: k, label: k, on: n(d["S_" + log]) > 0, mA: n(d["I_" + log]),
      record_above: k === "PAM" ? d.PA_RECORDABOVE : null, duty: 1,
    });
  }
  return {
    glider: String(d.ID),
    depth: d.maxdepth, w: (2 * d.maxdepth) / diveS, surface_min: d.surface_min,
    max_buoy: d.MAX_BUOY, sm_cc: d.SM_CC, kb: n(d.kb_data) + n(d.kb_cap),
    call_ndives: 1, sample_interval: interval, pump_factor: 1,
    glide_ratio: mission.glide_ratio, scicon: scicon, science: science, loggers: loggers,
    battery: { dual: glider.battery.dual, cap24: glider.battery.cap24, cap10: glider.battery.cap10,
               v24: d.v24, v10: d.v10, reserve_pct: 0 },
  };
}

function validate() {
  const dives = parseCsv(fs.readFileSync(DIVES, "utf8")).filter(
    (d) => d.dive_min > 10 && d.surface_min > 0 && d.surface_min < 240);
  const out = [];
  let worst = 0;
  for (const m of model.missions) {
    const ds = dives.filter((d) => d.ID === m.glider && d.MISSION === m.mission);
    let logged = 0, predicted = 0, predictedLaw = 0, errs = [];
    const comp = {};
    for (const d of ds) {
      const cfg = diveConfig(d, m);
      const law = SeagliderModel.evaluate(model, cfg);
      cfg.pump_factor = m.pump_factor;
      const r = SeagliderModel.evaluate(model, cfg);
      const l = loggedAh(d);
      logged += l; predicted += r.total; predictedLaw += law.total;
      errs.push(Math.abs(r.total / l - 1));
      r.parts.forEach((p) => (comp[p.key] = (comp[p.key] || 0) + p.ah));
    }
    errs.sort((a, b) => a - b);
    const ratio = predicted / logged, ratioLaw = predictedLaw / logged;
    worst = Math.max(worst, Math.abs(ratioLaw - 1));
    out.push({
      glider: m.glider, mission: m.mission, dives: ds.length,
      logged_ah: +logged.toFixed(2), model_ah: +predictedLaw.toFixed(2),
      model_ah_with_factor: +predicted.toFixed(2),
      ratio: +ratioLaw.toFixed(3), ratio_with_factor: +ratio.toFixed(3),
      median_dive_error: +errs[Math.floor(errs.length / 2)].toFixed(3),
    });
  }
  return { rows: out, worst: worst };
}

const v = validate();
console.log("glider mission dives  logged Ah  model Ah  ratio  (with pump factor)  median |dive error|");
for (const r of v.rows) {
  console.log(
    `${r.glider}  ${String(r.mission).padStart(3)}  ${String(r.dives).padStart(5)}  ` +
    `${r.logged_ah.toFixed(1).padStart(9)}  ${r.model_ah.toFixed(1).padStart(8)}  ` +
    `${r.ratio.toFixed(3)}  ${r.ratio_with_factor.toFixed(3).padStart(8)}  ` +
    `${(100 * r.median_dive_error).toFixed(1).padStart(12)}%`);
}
if (v.worst > TOLERANCE) {
  console.error(`FAIL: a mission is off by ${(100 * v.worst).toFixed(0)}% (limit ${100 * TOLERANCE}%)`);
  process.exit(1);
}
console.log(`ok: every mission within ${100 * TOLERANCE}% of its logged energy`);

if (process.argv.includes("--check")) process.exit(0);

const page = fs.readFileSync(PAGE, "utf8");
const a = page.indexOf(BEGIN), b = page.indexOf(END);
if (a < 0 || b < a) {
  console.error(`${path.relative(REPO, PAGE)} has no ${BEGIN} ... ${END} block; refusing to edit it.`);
  process.exit(1);
}
const payload = { ...model, validation: v.rows };
const block = [
  BEGIN,
  "<!-- Written by code/build_seaglider_page.js from content/data/seaglider-model.json and",
  "     code/seaglider_model.js. Edit those and re-run; edits inside this block are overwritten. -->",
  "<script>",
  "window.SEAGLIDER_MODEL = " + JSON.stringify(payload) + ";",
  "</script>",
  "<script>",
  fs.readFileSync(CODE, "utf8").trim(),
  "</script>",
  END,
].join("\n");
fs.writeFileSync(PAGE, page.slice(0, a) + block + page.slice(b + END.length));
console.log(`updated ${path.relative(REPO, PAGE)}`);
