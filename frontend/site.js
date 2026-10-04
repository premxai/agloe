// Agloe landing page: renders every chart and number from data/results.json (built by scripts/build_site_data.py).
const $ = (id) => document.getElementById(id);
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const NAMES = { qwen: "Qwen3-235B", deepseek: "DeepSeek-V4", kimi: "Kimi-K3", glm: "GLM-5.2", gptoss: "gpt-oss-120B", nemotron: "Nemotron-3",
  minimax: "MiniMax-M3", hermes: "Hermes-4 (Llama)", gemma: "Gemma-3", qwen35: "Qwen3.5-397B" };
const nm = (f) => NAMES[f] || f;
const tip = $("tip");

function showTip(el, html) {
  const r = el.getBoundingClientRect();
  tip.innerHTML = html; tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = `${Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8)}px`;
  tip.style.top = `${r.top - h - 8 < 8 ? r.bottom + 8 : r.top - h - 8}px`;
}
const hideTip = () => { tip.hidden = true; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// rows: [{label, values:[v|null...], texts?:[..], notes?:[..]}], series: [{name, cls}]  (values are shares in 0..1)
function hbar(el, { title, sub, series, rows, valueName = "Share" }) {
  el.replaceChildren();
  const add = (tag, cls, txt, parent = el) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt != null) n.textContent = txt; parent.appendChild(n); return n; };
  add("p", "ct", title); if (sub) add("p", "cs", sub);
  if (series.length > 1) {
    const lg = add("div", "legend");
    for (const s of series) { const sp = add("span", "", s.name, lg); const i = document.createElement("i"); i.style.background = `var(--${s.cls})`; sp.prepend(i); }
  }
  const wrap = add("div", "rows");
  for (const r of rows) {
    const row = add("div", "row", null, wrap);
    add("div", "lab", r.label, row);
    const plot = add("div", "plot", null, row);
    series.forEach((s, k) => {
      const v = r.values[k];
      const bw = add("div", "bar-w", null, plot);
      if (v == null) { add("span", "val", "no data", bw).style.color = "var(--muted)"; return; }
      const bar = add("div", `bar ${s.cls}`, null, bw);
      bar.style.width = "0"; bar.tabIndex = 0; bar.setAttribute("role", "img");
      const text = r.texts?.[k] ?? pct(v);
      bar.setAttribute("aria-label", `${r.label}${series.length > 1 ? ", " + s.name : ""}: ${text}`);
      setTimeout(() => { bar.style.width = `calc(var(--w) * ${Math.max(0, Math.min(1, v))})`; }, 30);   // same scale as the axis (timer, not rAF: rAF stalls in hidden tabs)
      add("span", "val", text, bw);
      const html = `<b>${esc(r.label)}</b>${series.length > 1 ? `<br>${esc(s.name)}` : ""}<br>${esc(valueName)}: ${esc(text)}${r.notes?.[k] ? `<br><span style="color:var(--muted)">${esc(r.notes[k])}</span>` : ""}`;
      for (const ev of ["mouseenter", "focus"]) bar.addEventListener(ev, () => showTip(bar, html));
      for (const ev of ["mouseleave", "blur"]) bar.addEventListener(ev, hideTip);
    });
  }
  const ax = add("div", "axis"); add("span", "", "", ax);
  const sp = add("span", "ticks", null, ax);                       // each label sits exactly on its gridline
  ["0%", "25%", "50%", "75%", "100%"].forEach((t, k) => { const s = add("span", "", t, sp); s.style.left = `${k * 25}%`; });
  // table-view twin: every value reachable without hover
  const d = add("details", "tv"); add("summary", "", "View as table", d);
  const t = add("table", "t", null, d); const hr = add("tr", "", null, add("thead", "", null, t));
  add("th", "", "Row", hr); for (const s of series) add("th", "", s.name, hr);
  const tb = add("tbody", "", null, t);
  for (const r of rows) { const tr = add("tr", "", null, tb); add("td", "", r.label, tr); series.forEach((s, k) => add("td", "", r.values[k] == null ? "no data" : `${r.texts?.[k] ?? pct(r.values[k])}${r.notes?.[k] ? " (" + r.notes[k] + ")" : ""}`, tr)); }
}

function tiles(res) {
  const t = $("tiles"); t.replaceChildren();
  const mk = (a, b, label) => { const d = document.createElement("div"); d.className = "tile"; d.innerHTML = `<span class="v">${a}<i>→</i>${b}</span><span class="l">${esc(label)}</span>`; t.appendChild(d); };
  if (res.coincidence) mk(res.coincidence.naive_calls.toLocaleString(), res.coincidence.supported_calls.toLocaleString(), "copy calls from “same string = copied”, versus calls that survive calibration");
  if (res.cross_team) mk(res.cross_team.naive, res.cross_team.verified, "cross-team collusion jumps flagged, versus verified by hand");
  if (res.incident) { const d = document.createElement("div"); d.className = "tile"; d.innerHTML = `<span class="v">${pct(res.incident.no_carrier)}</span><span class="l">of ${res.incident.adopters.toLocaleString()} adopters had no visible carrier at all (best possible top-1: ${pct(res.incident.best_top1)})</span>`; t.appendChild(d); }
}

function gatedChart(g) {
  const fams = Object.entries(g).filter(([, v]) => v.W4 && v.W4G).sort((a, b) => (a[1].W4.traceable.rate ?? 0) - (b[1].W4.traceable.rate ?? 0));
  if (!fams.length) { $("gated-block").hidden = true; return; }
  const rows = fams.map(([f, v]) => ({ label: nm(f), values: [v.W4.traceable.rate, v.W4G.traceable.rate],
    notes: [`${v.W4.agents} agents; finished ${pct(v.W4.completed.rate)}; ${v.W4.failed_calls_per_agent} refused calls per agent`,
      `${v.W4G.agents} agents; finished ${pct(v.W4G.completed.rate)}; ${v.W4G.failed_calls_per_agent} refused calls per agent`] }));
  hbar($("chart-gated"), { title: "Share of agents whose output carries a token naming the copy it came from", sub: "Same task and wiki; only the mirror's door differs",
    series: [{ name: "Mirror hands out sessions to anyone", cls: "s1" }, { name: "Sessions only through the wiki (gated)", cls: "s2" }], rows, valueName: "Outputs with a traceable token" });
  const done = (k) => { const a = fams.map(([, v]) => v[k].completed.rate).filter((x) => x != null); return a.length ? [Math.min(...a), Math.max(...a)] : null; };
  const o = done("W4"), c = done("W4G");
  const span = (r) => (r[0] === r[1] ? pct(r[0]) : `${pct(r[0])}–${pct(r[1])}`);
  $("gated-note").textContent = (o && c ? `Agents still finished the task: ${span(o)} without the gate, ${span(c)} with it. ` : "") +
    "With the gate, tracing follows from the access design (close to exact: a token names the copy the agent was served), so this shows the cost, not a discovery: some models spend calls on refused requests before reading the wiki. " +
    "A gate traces who got access through whom. It cannot trace an idea an agent learns from a peer and then acts on through some other legitimate door.";
}

function labCharts(lab) {
  const H3 = lab.H3, rate = H3.adoption_rate || {};
  const fpRows = Object.entries(rate).filter(([f]) => f !== "gemma").sort((a, b) => b[1] - a[1])
    .map(([f, v]) => ({ label: nm(f), values: [v], notes: [`top value: ${(H3.top_values[f]?.[0] || ["none", 0]).join(" × ")}`] }));
  hbar($("chart-fp"), { title: "Share of agents that add a cache-buster value to the URL", sub: "30 independent agents per model, three runs each, no wiki", series: [{ name: "Agents", cls: "s1" }], rows: fpRows, valueName: "Agents adding a value" });
  const tops = {}; for (const [f, v] of Object.entries(H3.top_values || {})) if (v[0]) (tops[v[0][0]] ||= []).push(nm(f));
  const shared = Object.entries(tops).filter(([, fs]) => fs.length > 1).map(([val, fs]) => `${val} (${fs.join(", ")})`);
  const fa = lab.fingerprint_attribution;
  $("fp-note").textContent = (shared.length ? `Several models reach for the same value: ${shared.join("; ")}. ` : "") +
    (fa?.accuracy != null ? `A simple classifier names a model's family from its behaviour alone ${pct(fa.accuracy)} of the time (chance ${pct(fa.chance)}).` : "");

  const h1 = Object.entries(lab.H1.by_family).filter(([, v]) => v.loadbearing.rate != null || v.inert.rate != null);
  const tagRows = h1.sort((a, b) => (b[1].loadbearing.rate ?? -1) - (a[1].loadbearing.rate ?? -1)).map(([f, v]) => ({
    label: nm(f), values: [v.inert.rate, v.loadbearing.rate],
    notes: [v.inert.rate == null ? "" : `${v.inert.den} copiers, ${v.inert.seeds} runs, range ${pct(v.inert.lo)}–${pct(v.inert.hi)}`, v.loadbearing.rate == null ? "" : `${v.loadbearing.den} copiers, ${v.loadbearing.seeds} runs, range ${pct(v.loadbearing.lo)}–${pct(v.loadbearing.hi)}`] }));
  hbar($("chart-tags"), { title: "Share of copiers whose submission still carries the tag", sub: "Wiki worlds, per model family", series: [{ name: "Inert tag (decoration)", cls: "s1" }, { name: "Load-bearing token", cls: "s2" }], rows: tagRows, valueName: "Tag survived" });

  const attrRows = Object.entries(lab.H2.by_family || {}).filter(([, v]) => (v.with_tags.den || 0) >= 20 && v.with_tags.rate != null)
    .sort((a, b) => (b[1].lift_points.rate ?? 0) - (a[1].lift_points.rate ?? 0)).map(([f, v]) => ({
      label: nm(f), values: [v.edit_log_only.rate, v.with_tags.rate],
      notes: ["best of earliest / latest / uniform", `${v.with_tags.den} copies, ${v.with_tags.seeds} runs; lift ${v.lift_points.rate == null ? "n/a" : (v.lift_points.rate * 100 >= 0 ? "+" : "") + Math.round(v.lift_points.rate * 100)} points`] }));
  hbar($("chart-attr"), { title: "Share of copies whose source is named correctly, by model", sub: "Edit log only (the best simple rule for each run) versus the tag where it survived and the same rule where it did not", series: [{ name: "Edit log only (best simple rule)", cls: "s1" }, { name: "With canary tags", cls: "s2" }], rows: attrRows, valueName: "Named correctly" });
  gatedChart(lab.gated || {});
  const lbs = h1.map(([, v]) => v.loadbearing.rate).filter((x) => x != null), ins = h1.map(([, v]) => v.inert.rate).filter((x) => x != null);
  if (lbs.length) $("tag-note").textContent = `Across ${h1.length} model families, load-bearing tokens survived in ${pct(Math.min(...lbs))}–${pct(Math.max(...lbs))} of copies and inert tags in ${pct(Math.min(...ins))}–${pct(Math.max(...ins))}. ` +
    "A token is only as good as the copier's habit of keeping it: some agents fetch a fresh session instead of reusing the one in the wiki.";
}

function cleanupChart(cl) {
  const late = cl["W2 tags"], early = cl["W2E tags"];
  if (!late || !early) return;
  const rows = [["everyone", "Re-run everything"], ["after_tip", "Re-check everything after the tip appeared"], ["earliest", "Follow the earliest visible writer"],
    ["tags+backup", "Follow the secret codes (earliest writer where a code was lost)"], ["tags", "Follow the secret codes only"]].map(([k, label]) => {
    const note = (a) => { const m = a.methods[k]; return `finds ${pct(m.reached_found.rate)} of the outputs the tip reached; ${pct(m.precision.rate)} of the list is truly affected`; };
    return { label, values: [late.methods[k].flagged_share.rate, early.methods[k].flagged_share.rate], notes: [note(late), note(early)] };
  });
  hbar($("chart-cleanup"), { title: "Share of outputs you would re-check", sub: "Lower is less work. Tagged runs, all model families",
    series: [{ name: "Tip arrives mid-run", cls: "s1" }, { name: "Tip is there from the start", cls: "s2" }], rows, valueName: "Outputs to re-check" });
  $("cleanup-note").textContent = `Mid-run tip: ${late.runs} runs, ${late.outputs.toLocaleString()} outputs, the tip reached ${late.reached}. Tracing cuts the list from about ${pct(late.methods.after_tip.flagged_share.rate)} of outputs to about ` +
    `${pct(late.methods.earliest.flagged_share.rate)}. A simple earliest-writer rule gets most of that; the codes make the list exact. A tip that is there from the start reached ${pct(early.reached / early.outputs)} of outputs, ` +
    `so nothing saves much work: catch a bad tip early. ${late.stale_not_reached} of ${late.stale} wrong outputs arrived another way (agents trying the stale mirror on their own), which a trace from the tip cannot find.`;
}

// "How we tested": the design table is read from the runs themselves (build_site_data.design), the outcomes from the analysis
function methodSection(res) {
  const d = res.design; if (!d) { $("method").hidden = true; return; }
  const t = document.createElement("table"); t.className = "t";
  const head = t.createTHead().insertRow();
  for (const h of ["World", "What it is", "Models", "Tags", "Swarm size", "Runs", "Agent runs"]) { const th = document.createElement("th"); th.textContent = h; head.appendChild(th); }
  const body = t.createTBody();
  for (const w of d.worlds) {
    const r = body.insertRow(); const fam = w.families.length > 3 ? `${w.families.length} models` : w.families.join(", ");
    [w.world, w.what, fam, w.conds.join(" / "), w.sizes.join(", "), `${w.cells} (${w.seeds} seeds)`, w.agent_runs.toLocaleString()].forEach((v, i) => { const c = r.insertCell(); c.textContent = v; if (i >= 5) c.className = "num"; });
  }
  const tot = body.insertRow(); [`All`, "", "", "", "", d.totals.cells.toLocaleString(), d.totals.agent_runs.toLocaleString()].forEach((v, i) => { const c = tot.insertCell(); c.textContent = v; c.style.fontWeight = 600; if (i >= 5) c.className = "num"; });
  $("design-table").replaceChildren(t);
  $("excl").textContent = `${d.smoke_runs_excluded} connectivity checks (seeds 900 and up) are not counted. Gemma-3 never produced tool calls and was dropped. ${d.flawed_designs_set_aside} flawed world designs were set aside and are described in the paper (section 6).`;
  $("budget").textContent = `Open models only, on one provider (Nebius): about $${d.totals.usd.toFixed(0)} for the analysed runs, under a hard $100 cap in the runner. Nothing was run against anyone's live swarm.`;
  const lab = res.lab; if (!lab) return;
  const fams = Object.entries(lab.H2.by_family).filter(([, v]) => (v.with_tags.den || 0) >= 20 && v.lift_points.rate != null);
  const h2 = fams.filter(([, v]) => v.lift_points.rate >= 0.10).length, h1 = lab.H1;
  const tested = Object.values(h1.by_family).filter((v) => (v.loadbearing.den || 0) >= 10 && (v.inert.den || 0) >= 10);
  const lbKeep = tested.filter((v) => v.loadbearing.rate >= 0.9).length, inertKeep = tested.filter((v) => v.inert.rate > 0.1).length;
  const w2e = lab.H4["W2E|loadbearing"]?.contaminated_attribution_with_tags?.rate, w2 = lab.H4["W2|loadbearing"]?.contaminated_attribution_with_tags?.rate;
  const rows = [
    ["H1", "Load-bearing tokens survive copying in at least 90% of copies, and inert tags in at most 10%.", `Not met: ${h1.families_passing} of ${h1.families_tested} model families met both halves. ${lbKeep} kept the load-bearing token in at least 90% of copies (the models that copy links verbatim), but inert tags survived more than 10% in ${inertKeep}, including those same models; the models that fetch their own session lost both.`],
    ["H2", "Tags beat the best simple edit-log rule by at least 10 points.", `${h2} of ${fams.length} families (lift ranges from ${Math.round(Math.min(...fams.map(([, v]) => v.lift_points.rate)) * 100)} to +${Math.round(Math.max(...fams.map(([, v]) => v.lift_points.rate)) * 100)} points), in proportion to how often the tag survived.`],
    ["H3", "Agents of one model family choose the same \"random\" value more often than agents of different families.", "Not supported among the open models: several families default to the same value."],
    ["H4", "Tags name the source of the bad outputs for at least 80% of them.", `Supported where tags survive: ${w2 != null ? pct(w2) : "n/a"} (late tip) and ${w2e != null ? pct(w2e) : "n/a"} (early tip).`],
    ["H5", "The report card's predicted ceiling matches the measured accuracy within 0.10.", "Dropped, as stated in advance: lab swarms share no distinctive strings, so the card reports N/A for them."],
  ];
  const t2 = document.createElement("table"); t2.className = "t";
  const hh = t2.createTHead().insertRow(); for (const h of ["", "Predicted", "What happened"]) { const th = document.createElement("th"); th.textContent = h; hh.appendChild(th); }
  const b2 = t2.createTBody(); for (const r of rows) { const tr = b2.insertRow(); r.forEach((v, i) => { const c = tr.insertCell(); c.textContent = v; if (i === 0) c.style.fontWeight = 700; }); }
  $("hyp-table").replaceChildren(t2);
}

// Cards other teams chose to share (scripts/collect_cards.py writes data/team_cards.json; the section stays hidden without it)
async function teamCards() {
  let cards;
  try { const r = await fetch("data/team_cards.json"); if (!r.ok) return; cards = (await r.json()).cards; } catch { return; }
  if (!cards?.length) return;
  const wrap = $("team-cards"); wrap.replaceChildren();
  const t = document.createElement("table"); t.className = "t";
  const head = t.createTHead().insertRow();
  for (const h of ["Swarm", "Grade", "Agents", "Events", "Carrier coverage", "Best possible top-1", "Naive → calibrated copy calls"]) { const th = document.createElement("th"); th.textContent = h; head.appendChild(th); }
  const body = t.createTBody();
  for (const c of cards) {
    const na = c.grade === "N/A", row = body.insertRow();
    for (const v of [c.swarm, c.grade, c.agents, c.events.toLocaleString(), na ? "n/a" : pct(c.carrier_coverage), na ? "n/a" : pct(c.best_possible_top1),
      `${c.naive_copy_calls.toLocaleString()} → ${c.calibrated_copy_calls.toLocaleString()}`]) row.insertCell().textContent = String(v);
  }
  wrap.appendChild(t);
  $("teams").hidden = false;
}

(async () => {
  teamCards();
  let res;
  try { res = await (await fetch("data/results.json")).json(); } catch { return; }
  if (res.incident) $("hero-num").textContent = pct(res.incident.best_top1);
  if (res.ladder) hbar($("chart-ladder"), { title: "Share of copy events whose source is visible in the log", sub: "By what was logged", series: [{ name: "Visible source", cls: "s1" }],
    rows: res.ladder.map((r) => ({ label: r.label, values: [r.value], texts: [r.text], notes: [r.note] })), valueName: "Visible" });
  tiles(res);
  methodSection(res);
  if (res.cleanup) cleanupChart(res.cleanup);
  else $("cleanup").hidden = true;
  if (res.lab) { labCharts(res.lab); }
  else for (const id of ["chart-fp", "chart-tags", "chart-attr"]) $(id).textContent = "Lab results are being finalized.";
  if (res.spend?.bench_cells) $("bench-n").textContent = String(res.spend.bench_cells);
})();
