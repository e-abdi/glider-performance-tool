/* Prove that moving the external payload out of the workbook changed no arithmetic.
 *
 * The workbook hardcodes five terms inside one formula:
 *
 *   K20 = (K43/100*11.2) + (F50*1.6) + (F51*11.2) + (F52*1.6) + (F53*6.4) + K19
 *
 * The page instead reads them from content/data/extra-sensors.csv and adds them to K19.
 * For the five the workbook knows about, the two must agree exactly. This drives both
 * over randomised mission configurations and compares K20, K30 and K31.
 *
 * It also guards the swap itself: if someone edits a row in the CSV so it no longer
 * matches the workbook's coefficient, that shows up here as a mismatch rather than as a
 * quietly different endurance. Rows the workbook has no term for (anything added later)
 * are reported and skipped, since there is nothing to compare them against.
 *
 * Usage: node code/check_extra_sensors.js
 */
const fs = require("fs");
const path = require("path");
const { Model } = require("./endurance_eval.js");

const root = path.join(__dirname, "..");
const model = JSON.parse(fs.readFileSync(
  path.join(root, "content", "data", "endurance-model.json"), "utf8"));

// --- read the CSV the page is built from -------------------------------------------
function parseCsv(text) {
  const rows = [];
  let field = "", row = [], quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift().map((h) => h.trim());
  return rows.filter((r) => r.some((v) => v.trim() !== ""))
    .map((r) => Object.fromEntries(head.map((h, i) => [h, (r[i] || "").trim()])));
}

const sensors = parseCsv(fs.readFileSync(
  path.join(root, "content", "data", "extra-sensors.csv"), "utf8"))
  .map((r) => ({ name: r.name, ah: parseFloat(r.ah_per_day), kind: r.kind || "fraction" }));

// Which workbook cell each CSV row stands in for, so the same setting drives both sides.
const MAPPED = {
  "Thruster": { cell: "P!K43", kind: "percent", ah: 11.2 },
  "UVP6": { cell: "P!F50", kind: "fraction", ah: 1.6 },
  "EK80": { cell: "P!F51", kind: "fraction", ah: 11.2 },
  // The workbook's single "Hydrophone" row is the single-channel configuration; the
  // 5-channel one is measured, has no workbook equivalent, and is reported as an addition.
  "JASCO OceanObserver (1 channel)": { cell: "P!F52", kind: "fraction", ah: 1.6 },
  "eDNA": { cell: "P!F53", kind: "fraction", ah: 6.4 }
};

const unmapped = sensors.filter((s) => !(s.name in MAPPED));
const recosted = sensors.filter((s) => s.name in MAPPED &&
  (s.ah !== MAPPED[s.name].ah || s.kind !== MAPPED[s.name].kind));

// --- drive both paths over random configurations -----------------------------------
let seed = 20260917;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const pick = (a) => a[Math.floor(rnd() * a.length)];

const m = new Model(model.cells);
const RUNS = 500;
let worst = 0, worstAt = "", fails = 0;

for (let i = 0; i < RUNS; i++) {
  const pump = pick([200, 1000]);
  const base = {
    "P!F17": pump,
    "P!F6": pump === 200 ? pick([50, 100, 150, 180]) : pick([100, 200, 400, 600, 800, 950]),
    "P!F7": pick([1, 2, 5, 10]),
    "P!F8": 0.15 + rnd() * 0.2,
    "P!F9": 0.05 + rnd() * 0.11,
    "P!F13": pick([5, 10, 15, 25, 40]),
    "P!F14": pick([0, 4, 8, 12, 18, 25]),
    "P!E22": pick(["Coastal", "Open Ocean"]),
    "P!F18": pick([0, 1]), "P!F19": pick([0, 1]),
    "P!F20": pick([0, 1]), "P!F21": pick([0, 1]),
    "P!F26": pick(["Ld", "a"]),
    "P!E28": pick(["P", "R"]), "P!E29": pick([0, 1]),
    "P!F11": "N", "P!F12": pick([2, 4, 6, 8, 12])
  };
  ["P!F36", "P!F37", "P!F39", "P!F40", "P!F41", "P!F42", "P!F43"]
    .forEach((c) => { base[c] = pick([0, 0.5, 1]); });

  // one random setting per mapped sensor, applied identically to both sides
  const setting = {};
  for (const name in MAPPED) {
    setting[name] = MAPPED[name].kind === "percent" ? pick([0, 25, 50, 75, 100]) : pick([0, 0.5, 1]);
  }

  // workbook path: its own K20 formula, fed through its own cells
  const wbInputs = Object.assign({}, base);
  for (const name in MAPPED) wbInputs[MAPPED[name].cell] = setting[name];
  m.reset(wbInputs);
  const wb = { k20: m.get("P!K20"), days: m.get("P!K30"), km: m.get("P!K31") };

  // page path: workbook terms zeroed, CSV payload added to K19, K20 overridden
  const pageInputs = Object.assign({}, base);
  for (const name in MAPPED) pageInputs[MAPPED[name].cell] = 0;
  m.reset(pageInputs);
  const k19 = m.get("P!K19");
  let load = 0;
  sensors.forEach((s) => {
    if (!(s.name in MAPPED)) return;
    const v = setting[s.name];
    load += s.ah * (s.kind === "percent" ? v / 100 : v);
  });
  m.reset(Object.assign({}, pageInputs, { "P!K20": k19 + load }));
  const pg = { k20: k19 + load, days: m.get("P!K30"), km: m.get("P!K31") };

  for (const key of ["k20", "days", "km"]) {
    const rel = Math.abs(pg[key] - wb[key]) / Math.max(1, Math.abs(wb[key]));
    if (rel > worst) { worst = rel; worstAt = `run ${i} ${key}: page=${pg[key]} workbook=${wb[key]}`; }
    if (rel > 1e-9) {
      fails++;
      if (fails <= 5) console.log(`MISMATCH run ${i} ${key}: page=${pg[key]} workbook=${wb[key]}`);
    }
  }
}

console.log(`${RUNS} random configurations x 3 outputs = ${RUNS * 3} comparisons`);
console.log(`mismatches: ${fails}`);
console.log(`worst relative difference: ${worst.toExponential(2)}${worst ? "  (" + worstAt + ")" : ""}`);

if (recosted.length) {
  console.log("\nre-costed against the workbook (intentional edits show up here):");
  recosted.forEach((s) => console.log(
    `  ${s.name}: csv ${s.ah} Ah/day ${s.kind}, workbook ${MAPPED[s.name].ah} ${MAPPED[s.name].kind}`));
}
if (unmapped.length) {
  console.log("\nadded beyond the workbook (nothing to compare against):");
  unmapped.forEach((s) => console.log(`  ${s.name}: ${s.ah} Ah/day ${s.kind}`));
}

process.exit(fails ? 1 : 0);
