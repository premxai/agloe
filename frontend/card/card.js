// Agloe report card UI. The only network use is the optional "sample" buttons (same-origin static files);
// a file you drop or choose is read locally and never sent anywhere.
import { loadEvents, reportCard } from "./card-core.js";
import { ONE, ROW, buildMapped, flatten, guessMapping, rawObjects, readFileText } from "./input.js";

const $ = (id) => document.getElementById(id);
const pct = (x) => `${Math.round(x * 100)}%`;
let current = null;

function setStatus(msg, err = false) { const s = $("status"); s.textContent = msg; s.classList.toggle("err", err); }

// ---------------------------------------------------------------- other shapes: CSV, differently named fields (all local)
let pending = null;
function showMapper(objects, name) {
  const flats = objects.map((o) => flatten(o));
  const g = guessMapping(flats);
  if (!g.keys.length) { setStatus("No usable events found: the file has no rows with fields (see “What format?”).", true); return; }
  const fill = (id, extra, def) => {
    const sel = $(id); sel.replaceChildren();
    for (const [v, label] of extra) { const o = document.createElement("option"); o.value = v; o.textContent = label; sel.appendChild(o); }
    for (const k of g.keys) { const o = document.createElement("option"); o.value = k; o.textContent = k; sel.appendChild(o); }
    sel.value = def ?? sel.options[0].value;
  };
  fill("m-agent", [], g.agent);
  fill("m-time", [[ROW, "(row order: rows are already in time order)"]], g.time);
  fill("m-channel", [[ONE, "(one shared channel)"]], g.channel);
  fill("m-content", [], g.content);
  const show = () => {
    const pick = (f, id) => (f[$(id).value] === undefined ? "" : String(f[$(id).value]).slice(0, 60));
    $("m-preview").textContent = flats.slice(0, 3).map((f) => `agent=${pick(f, "m-agent")} | time=${$("m-time").value === ROW ? "(row order)" : pick(f, "m-time")} | content=${pick(f, "m-content")}`).join("\n");
  };
  for (const id of ["m-agent", "m-time", "m-channel", "m-content"]) $(id).onchange = show;
  show();
  pending = { flats, name };
  $("mapper").hidden = false;
  setStatus(`Found ${flats.length.toLocaleString()} rows in ${name} but not the usual field names. Check the choices below.`);
}

async function runCard(events, name) {
  setStatus(`Analysing ${events.length.toLocaleString()} events…`);
  await new Promise((r) => setTimeout(r, 30));
  current = { card: reportCard(events), name };
  render(current.card, name);
  setStatus(`Done: ${events.length.toLocaleString()} events from ${name}. Nothing was uploaded.`);
}

async function analyze(text, name) {
  setStatus(`Reading ${name}…`);
  $("mapper").hidden = true;
  await new Promise((r) => setTimeout(r, 30));              // let the status paint before the synchronous work
  const events = loadEvents(text);
  if (events.length) return runCard(events, name);
  const objects = rawObjects(text, name);                   // not in the usual shape: offer the field mapper instead of giving up
  if (objects.length) return showMapper(objects, name);
  setStatus("No usable events found. Each line needs agent, time and content (see “What format?”).", true);
}

function render(c, name) {
  $("result").hidden = false;
  const g = $("grade");
  g.textContent = c.grade; g.className = "grade " + (c.grade === "N/A" ? "NA" : c.grade);
  const na = c.grade === "N/A";
  $("headline").textContent = na ? "Nothing to trace from content"
    : `${pct(c.carrier_coverage)} of real copies have a visible source`;
  $("summary").textContent = na
    ? "No distinctive string is shared between your agents (every repeated string is common vocabulary), so copying cannot be traced from the logs. Tag shared artifacts first."
    : `Even a perfect tracer would name the true source for at most ${pct(c.best_possible_top1)} of copies from these logs.` +
      (c.single_channel ? " (One shared channel: every earlier write is visible, so coverage is an upper bound.)" : "");
  $("meta").textContent = `${name} · ${c.events.toLocaleString()} events · ${c.agents.toLocaleString()} agents · ${c.channels.toLocaleString()} channels`;
  $("t-cov").textContent = na ? "–" : pct(c.carrier_coverage);
  $("b-cov").style.width = na ? "0" : pct(c.carrier_coverage);
  $("t-top").textContent = na ? "–" : pct(c.best_possible_top1);
  $("b-top").style.width = na ? "0" : pct(c.best_possible_top1);
  $("t-naive").textContent = `${c.naive_copy_calls.toLocaleString()} → ${c.calibrated_copy_calls.toLocaleString()}`;
  const tot = Math.max(1, c.naive_copy_calls);
  $("b-sup").style.width = pct(c.calibrated_copy_calls / tot); $("b-dec").style.width = pct(c.declined_as_coincidence / tot);
  $("h-naive").textContent = `naive “same string = copy” calls → calls that survive calibration (${c.declined_as_coincidence.toLocaleString()} declined as coincidence)`;
  const tb = $("shared").tBodies[0]; tb.replaceChildren();
  for (const v of c.everyone_types_this) {
    const tr = document.createElement("tr");
    for (const [txt, cls] of [[v.string, "mono"], [String(v.agents), "r"], [v.class, ""]]) {
      const td = document.createElement("td"); td.textContent = txt; if (cls) td.className = cls; tr.appendChild(td);
    }
    tb.appendChild(tr);
  }
  if (!c.everyone_types_this.length) { const tr = document.createElement("tr"); const td = document.createElement("td"); td.colSpan = 3; td.textContent = "No string is used by 3 or more agents."; td.className = "muted"; tr.appendChild(td); tb.appendChild(tr); }
  const ul = $("recs"); ul.replaceChildren();
  for (const r of c.recommendations) { const li = document.createElement("li"); li.textContent = r; ul.appendChild(li); }
  $("result").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

function summaryText(c, name) {
  return `Agloe Traceability Report Card — ${name}\nGrade ${c.grade}: ${c.events.toLocaleString()} events, ${c.agents.toLocaleString()} agents.\n` +
    (c.grade === "N/A" ? "No distinctive shared strings: nothing traceable from content.\n"
      : `Carrier coverage ${pct(c.carrier_coverage)}; best possible top-1 ${pct(c.best_possible_top1)}.\n`) +
    `Naive copy calls ${c.naive_copy_calls.toLocaleString()} → ${c.calibrated_copy_calls.toLocaleString()} after calibration.\n` +
    c.recommendations.map((r) => `- ${r}`).join("\n");
}

async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); const old = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = old), 1400); }
  catch { setStatus("Could not access the clipboard; select and copy manually.", true); }
}

async function handleFile(file) {
  try { await analyze(await readFileText(file), file.name); } catch (e) { setStatus(String(e.message || e), true); }
}

const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) handleFile(f); });
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } });
$("file").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) handleFile(f); });
for (const b of document.querySelectorAll("[data-sample]")) {
  b.addEventListener("click", async () => {
    try { const r = await fetch("fixtures/" + b.dataset.sample); if (!r.ok) throw new Error("sample not found"); await analyze(await r.text(), b.textContent); }
    catch (e) { setStatus(String(e.message || e), true); }
  });
}
function shareCard(c, withStrings) {                       // text taken from the logs stays out of a shared card unless the user opts in
  const card = JSON.parse(JSON.stringify(c));
  if (!withStrings) card.everyone_types_this = c.everyone_types_this.map((v) => ({ string: "(withheld)", agents: v.agents, class: v.class }));
  return card;
}
$("m-go").addEventListener("click", () => {
  const events = buildMapped(pending.flats, { agent: $("m-agent").value, time: $("m-time").value, channel: $("m-channel").value, content: $("m-content").value });
  if (!events.length) { setStatus("No rows had all of agent, time and content for those choices. Try other fields.", true); return; }
  $("mapper").hidden = true;
  runCard(events, pending.name);
});
$("copy-json").addEventListener("click", (e) => current && copy(JSON.stringify(shareCard(current.card, $("inc-strings").checked), null, 1), e.currentTarget));
$("copy-text").addEventListener("click", (e) => current && copy(summaryText(current.card, current.name), e.currentTarget));
$("again").addEventListener("click", () => { $("result").hidden = true; $("mapper").hidden = true; current = null; pending = null; $("file").value = ""; setStatus(""); window.scrollTo({ top: 0 }); });
