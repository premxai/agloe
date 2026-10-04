// Parity test: the JS card must match the Python reference on every fixture.  Run: node frontend/card/parity.test.mjs
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { colony, loadEvents, reportCard } from "./card-core.js";

const here = dirname(fileURLToPath(import.meta.url));
const dirs = [join(here, "fixtures"), join(here, "..", "..", "data", "out", "card_fixtures")].filter(existsSync);
const EXACT = ["events", "agents", "channels", "distinct_shared_strings", "naive_copy_calls", "calibrated_copy_calls",
  "declined_as_coincidence", "grade", "single_channel"];
const NUM = ["carrier_coverage", "best_possible_top1", "naive_coverage"];     // Python round() vs JS round() may differ by 1 ulp of the 3rd digit
const norm = (s) => s.replace(/\d+%/g, "N%");                                  // percentage rounding of exact .5 differs (banker's vs half-up)

let failures = 0, checked = 0;
const fail = (name, msg) => { failures++; console.log(`  FAIL ${name}: ${msg}`); };

for (const dir of dirs) {
  for (const f of readdirSync(dir).filter((x) => x.endsWith(".jsonl"))) {
    const name = f.replace(".jsonl", "");
    const exp = JSON.parse(readFileSync(join(dir, `${name}.expected.json`), "utf8"));
    const evs = loadEvents(readFileSync(join(dir, f), "utf8")), got = reportCard(evs);
    checked++;
    const col = colony(evs.filter((e) => e.kind !== "read")).stats;                // the colony view must count copies exactly as the card does
    if (col.naive !== got.naive_copy_calls || col.supported !== got.calibrated_copy_calls || col.naive - col.supported !== got.declined_as_coincidence)
      fail(name, `colony counts ${col.naive}/${col.supported} vs card ${got.naive_copy_calls}/${got.calibrated_copy_calls}`);
    if (col.supported && Math.abs(col.covered / col.supported - got.carrier_coverage) > 0.0011) fail(name, "colony coverage differs from the card");
    for (const k of EXACT) if (got[k] !== exp[k]) fail(name, `${k}: js ${got[k]} vs py ${exp[k]}`);
    for (const k of NUM) if (Math.abs(got[k] - exp[k]) > 0.0011) fail(name, `${k}: js ${got[k]} vs py ${exp[k]}`);
    exp.carrier_coverage_ci95.forEach((v, i) => { if (Math.abs(got.carrier_coverage_ci95[i] - v) > 0.0011) fail(name, `ci95[${i}]: js ${got.carrier_coverage_ci95[i]} vs py ${v}`); });
    if (JSON.stringify(got.everyone_types_this) !== JSON.stringify(exp.everyone_types_this)) fail(name, "everyone_types_this differs");
    if (JSON.stringify(got.recommendations.map(norm)) !== JSON.stringify(exp.recommendations.map(norm))) fail(name, "recommendations differ");
    console.log(`  ok   ${name.padEnd(30)} grade ${got.grade}  naive ${got.naive_copy_calls} -> calibrated ${got.calibrated_copy_calls}`);
  }
}
if (!checked) { console.log("no fixtures found: run  python -m scripts.make_card_fixtures"); process.exit(2); }
console.log(failures ? `\n${failures} mismatch(es)` : `\nparity OK on ${checked} fixtures`);
process.exit(failures ? 1 : 0);
