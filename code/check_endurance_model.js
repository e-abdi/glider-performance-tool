/* Recompute every extracted cell and compare against the value Excel last stored in it.
 *
 * This is the whole safety net for the endurance page: if the interpreter or the
 * extraction drifts from the workbook, it shows up here rather than as a plausible-looking
 * wrong number of days.
 *
 * Usage: node code/check_endurance_model.js
 */
const fs = require("fs");
const path = require("path");
const { Model } = require("./endurance_eval.js");

const model = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "content", "data", "endurance-model.json"), "utf8"));

const m = new Model(model.cells);
m.reset();

const TOL = 1e-9;
let ok = 0;
const bad = [];
const errors = [];

for (const [key, want] of Object.entries(model.cached)) {
  let got;
  try {
    got = m.get(key);
  } catch (e) {
    errors.push(`${key}: ${e.message}`);
    continue;
  }
  const g = typeof got === "boolean" ? (got ? 1 : 0) : got;
  if (typeof g !== "number" || !isFinite(g)) {
    errors.push(`${key}: got ${JSON.stringify(got)}, want ${want}`);
    continue;
  }
  const scale = Math.max(1, Math.abs(want));
  if (Math.abs(g - want) / scale <= TOL) ok++;
  else bad.push({ key, want, got: g, diff: g - want });
}

console.log(`matched   ${ok} / ${Object.keys(model.cached).length}`);
console.log(`mismatched ${bad.length}`);
console.log(`errored    ${errors.length}`);

if (bad.length) {
  console.log("\nworst mismatches:");
  bad.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 15)
    .forEach((d) => console.log(`  ${d.key}: got ${d.got}  want ${d.want}  (${d.diff})`));
}
if (errors.length) {
  console.log("\nerrors:");
  errors.slice(0, 15).forEach((e) => console.log("  " + e));
}

// The four numbers the page actually reports.
console.log("\nheadline outputs:");
[["P!K19", "Ah/day, glider + standard sensors"],
 ["P!K20", "Ah/day, total incl. thruster + extra sensors"],
 ["P!K30", "Endurance (days)"],
 ["P!K31", "Approx. distance (km)"]].forEach(([k, label]) => {
  console.log(`  ${label.padEnd(46)} ${k} = ${m.get(k)}   (Excel: ${model.cached[k]})`);
});

process.exit(bad.length || errors.length ? 1 : 0);
