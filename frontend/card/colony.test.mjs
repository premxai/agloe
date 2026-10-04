// Read-tracing logic of the colony view (synthetic events only).  Run: node frontend/card/colony.test.mjs
import { colony } from "./card-core.js";

let failures = 0;
const check = (name, ok, extra = "") => { if (!ok) { failures++; console.log(`  FAIL ${name} ${extra}`); } else console.log(`  ok   ${name}`); };
const L1 = "https://mirror.invalid/fetch/county_data_file";             // posted twice, so the copy an agent was shown is ambiguous
const S1 = "https://mirror.invalid/s/aaaa1111/fetch/county_data_file";  // a copy with its own token: exact
const ev = (i, agent, channel, kind, content, extra = {}) => ({ agent, time: String(i).padStart(6, "0"), channel, kind, content, ...extra });
const events = [
  ev(1, "agent-01", "Notes", "write", `working link ${L1}`),
  ev(2, "agent-02", "Notes", "write", `working link ${L1}`),
  ev(3, "agent-03", "Notes", "read", L1, { source: "agent-01" }),
  ev(3, "agent-03", "Notes", "read", L1, { source: "agent-02" }),
  ev(4, "agent-03", "submit", "submit", L1),
  ev(5, "agent-04", "Notes", "read", S1, { source: "agent-01" }),
  ev(6, "agent-04", "submit", "submit", S1, { flag: true }),
  ev(7, "agent-05", "submit", "submit", "https://mirror.invalid/s/qqqq9999/fetch/county_data_file"),     // read nothing: worked it out alone
  ev(8, "agent-06", "Notes", "read", L1, { source: "agent-06" }),                                      // reading its own post is not a copy
  ev(9, "agent-06", "submit", "submit", L1),
];
// the most specific read wins, and a dropped tag gives a weaker link instead of none
const BASE = "https://m.invalid/fetch/shared_county_file", TAGGED = BASE + "?_=zz11yy22", OTHER = "https://m.invalid/s/bbbb2222/fetch/shared_county_file";
events.push(
  ev(10, "agent-07", "Notes", "read", BASE, { source: "agent-01" }), ev(10, "agent-07", "Notes", "read", TAGGED, { source: "agent-02" }),
  ev(11, "agent-07", "submit", "submit", `answer via ${TAGGED}`),
  ev(12, "agent-08", "Notes", "read", OTHER, { source: "agent-02" }),
  ev(13, "agent-08", "submit", "submit", "https://m.invalid/fetch/shared_county_file"));              // dropped the token it was served
const c = colony(events);
const by = Object.fromEntries(c.links.map((l) => [l.adopter, l]));
check("longest matching read wins over a shorter tagless link inside it", by["agent-07"] && by["agent-07"].unique && by["agent-07"].sources.join() === "agent-02", JSON.stringify(by["agent-07"]));
check("a dropped tag gives a weak link, not an exact one", by["agent-08"] && by["agent-08"].weak && !by["agent-08"].unique && by["agent-08"].sources.join() === "agent-02", JSON.stringify(by["agent-08"]));

check("ambiguous when identical copies came from two authors", by["agent-03"] && !by["agent-03"].unique && by["agent-03"].sources.join() === "agent-01,agent-02", JSON.stringify(by["agent-03"]));
check("exact when the copy it read is unique", by["agent-04"] && by["agent-04"].unique && by["agent-04"].sources.join() === "agent-01");
check("no link without a matching read", !by["agent-05"]);
check("reading your own post is not a link", !by["agent-06"]);
check("a link is found only once per agent, at its first use", c.links.length === 4 && new Set(c.links.map((l) => l.adopter)).size === 4);
check("the flagged output is counted", c.stats.flagged === 1 && c.agents.find((a) => a.name === "agent-04").flagged);
check("reads are counted as reads, and never change the copy counts", c.stats.reads === 7 && colony(events.filter((e) => e.kind !== "read")).stats.naive === c.stats.naive);
check("a vocabulary-like string in many links is declined, not called a copy", c.copies.length > 0 && c.copies.every((x) => !x.ok) && c.stats.supported === 0);
check("agents appear in the order they first act", c.agents.map((a) => a.name).join() === "agent-01,agent-02,agent-03,agent-04,agent-05,agent-06,agent-07,agent-08");
console.log(failures ? `\n${failures} failure(s)` : "\ncolony OK");
process.exit(failures ? 1 : 0);
