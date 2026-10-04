// Agloe Colony: drop a swarm's log and watch it as an ant colony. Every agent is an ant, the chambers are the rooms / pages agents work in, trails form as
// agents pick things up from each other, and a click traces an ant back to what it read and forward to everyone downstream of it.
// All of it runs in this page: the file is read locally, nothing is uploaded. The tracing rules live in ../card/card-core.js (parity-tested with the card).
import { colony, loadEvents } from "../card/card-core.js";
import { ONE, ROW, buildMapped, flatten, guessMapping, rawObjects, readFileText } from "../card/input.js";

const $ = (id) => document.getElementById(id);
const cv = $("c"), ctx = cv.getContext("2d");
const LW = 1000, LH = 625;                                          // logical canvas size; the backing store is scaled to the screen
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const C = { ok: "#5be3a0", amber: "#ffb347", bad: "#ff5a68", grey: "#8d8173", ant: "#e8d5b5", text: "#f1e6d6", muted: "#a89782", line: "#2e241b" };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let M = null, meta = null, edges = [], agg = [], incoming = new Map(), outgoing = new Map(), byName = new Map(), chambers = [];
let feedItems = [], feedList = [], fp = 0, ep = 0, crumbs = [], sel = null, follow = null, hover = null, ip = 0, playing = false, last = 0, speed = 1, lastUi = 0;
let tSorted = { trails: [], hidden: [], coin: [], flag: [] };
const opts = { hidden: true, coin: false, show: false };

function setStatus(msg, err = false) { const s = $("status"); s.textContent = msg; s.classList.toggle("err", err); }
const hash = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; };
const ub = (arr, x) => { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= x) lo = m + 1; else hi = m; } return lo; };   // count of items <= x in a sorted array
const maskTok = (t, cls) => (opts.show ? t.slice(0, 30) : `${cls} · ${t.slice(0, 3)}…${t.length} ch`);

// ---------------------------------------------------------------- loading
async function openText(text, name, info) {
  setStatus(`Reading ${name}…`); $("mapper").hidden = true;
  await new Promise((r) => setTimeout(r, 30));
  const events = loadEvents(text);
  if (events.length) return build(events, name, info);
  const objs = rawObjects(text, name);
  if (objs.length) return showMapper(objs, name, info);
  setStatus("No usable events found. Each line needs agent, time and content (see the report card's “What format?”).", true);
}

let pending = null;
function showMapper(objs, name, info) {
  const flats = objs.map((o) => flatten(o)), g = guessMapping(flats);
  if (!g.keys.length) { setStatus("The file has no rows with fields.", true); return; }
  const fill = (id, extra, def) => {
    const sel2 = $(id); sel2.replaceChildren();
    for (const [v, label] of extra) { const o = document.createElement("option"); o.value = v; o.textContent = label; sel2.appendChild(o); }
    for (const k of g.keys) { const o = document.createElement("option"); o.value = k; o.textContent = k; sel2.appendChild(o); }
    sel2.value = def ?? sel2.options[0].value;
  };
  fill("m-agent", [], g.agent); fill("m-time", [[ROW, "(row order)"]], g.time); fill("m-channel", [[ONE, "(one shared channel)"]], g.channel); fill("m-content", [], g.content);
  const show = () => {
    const pick = (f, id) => (f[$(id).value] === undefined ? "" : String(f[$(id).value]).slice(0, 60));
    $("m-preview").textContent = flats.slice(0, 3).map((f) => `agent=${pick(f, "m-agent")} | time=${$("m-time").value === ROW ? "(row order)" : pick(f, "m-time")} | content=${pick(f, "m-content")}`).join("\n");
  };
  for (const id of ["m-agent", "m-time", "m-channel", "m-content"]) $(id).onchange = show;
  show(); pending = { flats, name, info }; $("mapper").hidden = false;
  setStatus(`Found ${flats.length.toLocaleString()} rows in ${name} but not the usual field names. Check the choices below.`);
}
$("m-go").addEventListener("click", () => {
  const events = buildMapped(pending.flats, { agent: $("m-agent").value, time: $("m-time").value, channel: $("m-channel").value, content: $("m-content").value });
  if (!events.length) { setStatus("No rows had all of agent, time and content for those choices.", true); return; }
  $("mapper").hidden = true; build(events, pending.name, pending.info);
});

// ---------------------------------------------------------------- the model -> trails, chambers, ants
function build(events, name, info) {
  M = colony(events);
  if (!M.agents.length) { setStatus("No agents found in that log.", true); return; }
  meta = { name, info, events: events.length };
  byName = new Map(M.agents.map((a, i) => [a.name, a])); M.agents.forEach((a, i) => { a.ph = hash(a.name) * 6.28; a.idx = i; });
  // trails: exact reads, one-of-several reads, strings picked up from a visible earlier user, hidden sources, and coincidences
  edges = [];
  for (const l of M.links) {
    if (l.unique) edges.push({ from: l.sources[0], to: l.adopter, kind: "exact", i: l.i });
    else for (const s of l.sources) edges.push({ from: s, to: l.adopter, kind: "amb", i: l.i });
  }
  for (const c of M.copies) {
    if (!c.ok) edges.push({ from: c.firstUser, to: c.adopter, kind: "coin", i: c.i, token: c.token });
    else if (c.carriers.length) for (const s of c.carriers) edges.push({ from: s, to: c.adopter, kind: "tok", i: c.i, token: c.token });
    else edges.push({ from: c.firstUser, to: c.adopter, kind: "hid", i: c.i, token: c.token });
  }
  edges.sort((a, b) => a.i - b.i);
  incoming = new Map(); outgoing = new Map();
  for (const e of edges) { if (!incoming.has(e.to)) incoming.set(e.to, []); incoming.get(e.to).push(e); if (!outgoing.has(e.from)) outgoing.set(e.from, []); outgoing.get(e.from).push(e); }
  const g = new Map();
  for (const e of edges) { const k = `${e.from}|${e.to}|${e.kind}`; if (!g.has(k)) g.set(k, { from: e.from, to: e.to, kind: e.kind, is: [], tokens: new Set() }); const a = g.get(k); a.is.push(e.i); if (e.token) a.tokens.add(e.token); }
  agg = [...g.values()];
  // first flagged event per agent, for the feed and the counters
  const flagAt = new Map(); events.forEach((e, i) => { if (e.flag && !flagAt.has(e.agent)) flagAt.set(e.agent, i); });
  const noIn = (a) => !(incoming.get(a.name) || []).some((e) => e.kind !== "coin");
  tSorted = {
    exact: M.links.filter((l) => l.unique).map((l) => l.i).sort((a, b) => a - b), none: M.agents.filter(noIn).map((a) => a.first).sort((a, b) => a - b),
    trails: [...M.links.map((l) => l.i), ...M.copies.filter((c) => c.ok).map((c) => c.i)].sort((a, b) => a - b),
    hidden: M.copies.filter((c) => c.ok && !c.carriers.length).map((c) => c.i).sort((a, b) => a - b),
    coin: M.copies.filter((c) => !c.ok).map((c) => c.i).sort((a, b) => a - b), flag: [...flagAt.values()].sort((a, b) => a - b),
  };
  feedItems = [                                                  // text is built when shown, so the "show the strings" switch takes effect at once
    ...M.links.map((l) => ({ i: l.i, kind: l.unique ? "exact" : "amb", html: () => l.unique
      ? `<span class="tag">exact</span><b>${esc(l.adopter)}</b> used what it read from <b>${esc(l.sources[0])}</b>`
      : `<span class="tag">${l.weak ? "copy unknown" : "one of several"}</span><b>${esc(l.adopter)}</b> ${l.weak ? "used the same link as one it read, but not the copy it was served, from" : "read identical copies from"} ${l.sources.slice(0, 3).map((s) => `<b>${esc(s)}</b>`).join(", ")}${l.sources.length > 3 ? "…" : ""}` })),
    ...M.copies.filter((c) => c.ok).map((c) => ({ i: c.i, kind: c.carriers.length ? "tok" : "hid", html: () => c.carriers.length
      ? `<span class="tag">picked up</span><b>${esc(c.adopter)}</b> used ${esc(maskTok(c.token, c.cls))}, already used by <b>${esc(c.carriers[0])}</b>${c.carriers.length > 1 ? ` +${c.carriers.length - 1}` : ""} in ${esc(c.channel)}`
      : `<span class="tag">hidden</span><b>${esc(c.adopter)}</b> used ${esc(maskTok(c.token, c.cls))}; first seen by <b>${esc(c.firstUser)}</b> in another room, source not visible` })),
    ...[...flagAt].map(([a, i]) => ({ i, kind: "flag", html: () => `<span class="tag">flagged</span><b>${esc(a)}</b> produced a flagged output` })),
  ].sort((a, b) => a.i - b.i);
  layout(); renderSide(); renderCriteria();
  $("colony").hidden = false; resetPlayback(0);
  const total = M.stats.events;
  setStatus(`${meta.name}: ${total.toLocaleString()} events, ${M.agents.length} agents${M.hasReads ? `, ${M.stats.reads.toLocaleString()} reads` : " (no read log)"}. Nothing was uploaded.`);
  $("blurb").textContent = info?.look || (M.hasReads ? "This log has a read log, so trails go to what each agent actually read." : "No read log: trails are inferred from strings agents share, like a real investigator would have to.");
  $("colony").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

function layout() {
  const home = new Map(); for (const a of M.agents) home.set(a.home, (home.get(a.home) || 0) + 1);
  const top = [...home].sort((a, b) => b[1] - a[1]).slice(0, 9).map((e) => e[0]), other = home.size > top.length;
  const names = other ? [...top, "(other rooms)"] : top, K = names.length;
  chambers = names.map((nm, k) => {
    const ang = -Math.PI / 2 + (k / K) * 2 * Math.PI, rx = K <= 2 ? 250 : 330, ry = K <= 2 ? 80 : 205;
    const n = nm === "(other rooms)" ? [...home].filter(([c]) => !top.includes(c)).reduce((s, [, v]) => s + v, 0) : home.get(nm);
    const rmax = K === 1 ? 285 : K <= 2 ? 215 : K <= 4 ? 160 : 108;
    return { name: nm, n, x: K === 1 ? LW / 2 : LW / 2 + Math.cos(ang) * rx, y: K === 1 ? LH / 2 : LH / 2 + Math.sin(ang) * ry, r: Math.min(rmax, 60 + Math.sqrt(n) * 38) };
  });
  const chamberOf = (h) => chambers.find((c) => c.name === h) || chambers[chambers.length - 1];
  for (const a of M.agents) { const c = chamberOf(a.home), ang = hash(a.name + "a") * 6.28, rr = Math.sqrt(hash(a.name + "r")) * c.r * 0.8; a.cx = c.x; a.cy = c.y; a.x = c.x + Math.cos(ang) * rr; a.y = c.y + Math.sin(ang) * rr; }
  const E = edges.filter((e) => e.kind !== "coin" && e.kind !== "hid" && byName.has(e.from) && byName.has(e.to)), n = M.agents.length, iters = n > 300 ? 70 : 230;
  for (let it = 0; it < iters; it++) {
    for (const a of M.agents) { a.fx = (a.cx - a.x) * 0.005; a.fy = (a.cy - a.y) * 0.005; }
    const gap = Math.max(34, Math.min(78, 560 / Math.sqrt(n)));                  // fewer ants, more room each
    for (let p = 0; p < n; p++) for (let q = p + 1; q < n; q++) {
      const a = M.agents[p], b = M.agents[q], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
      if (d2 < gap * gap) { const d = Math.sqrt(d2) || 0.5, f = (gap - d) * 0.07; a.fx += (dx / d) * f; a.fy += (dy / d) * f; b.fx -= (dx / d) * f; b.fy -= (dy / d) * f; }
    }
    for (const e of E) { const a = byName.get(e.from), b = byName.get(e.to), dx = b.x - a.x, dy = b.y - a.y; a.fx += dx * 0.0009; a.fy += dy * 0.0009; b.fx -= dx * 0.0009; b.fy -= dy * 0.0009; }
    for (const a of M.agents) { a.x = clamp(a.x + a.fx, 26, LW - 26); a.y = clamp(a.y + a.fy, 30, LH - 30); }
  }
}

// ---------------------------------------------------------------- tracing from the model
function traceBack(name) {
  const chain = [{ name, via: null }], seen = new Set([name]); let cur = name;
  for (;;) {
    const inc = (incoming.get(cur) || []).filter((e) => e.kind !== "coin");
    if (!inc.length) break;
    const pick = inc.find((e) => e.kind === "exact") || inc.find((e) => e.kind === "tok") || inc.find((e) => e.kind === "amb") || inc[0];
    if (seen.has(pick.from)) { chain.push({ name: pick.from, via: pick.kind, loop: true }); break; }
    chain.push({ name: pick.from, via: pick.kind }); seen.add(pick.from); cur = pick.from;
    if (pick.kind === "hid") break;
  }
  return chain;
}
function downstream(name) {                                       // everyone reachable by following visible trails forward (hidden sources are not guessed at)
  const out = new Set(), q = [name];
  while (q.length) for (const e of outgoing.get(q.shift()) || []) if (e.kind !== "coin" && e.kind !== "hid" && !out.has(e.to) && e.to !== name) { out.add(e.to); q.push(e.to); }
  return out;
}

// ---------------------------------------------------------------- the side panel
function renderSide() {
  const sp = M.agents.map((a) => ({ name: a.name, n: downstream(a.name).size })).filter((x) => x.n > 0).sort((a, b) => b.n - a.n).slice(0, 6);
  $("spreaders").replaceChildren(...(sp.length ? sp : [{ none: true }]).map((x) => {
    const li = document.createElement("li");
    if (x.none) { li.textContent = "No trails to follow forward in this log."; li.style.cursor = "default"; li.className = "muted"; return li; }
    li.innerHTML = `<span>${esc(x.name)}</span><small>${x.n} downstream</small>`; li.addEventListener("click", () => select(x.name)); return li;
  }));
  const toks = M.tokens.slice(0, 10);
  $("strings").replaceChildren(...(toks.length ? toks : [{ none: true }]).map((t) => {
    const li = document.createElement("li");
    if (t.none) { li.textContent = "No string is used by two or more agents."; li.style.cursor = "default"; li.className = "muted"; return li; }
    li.dataset.token = t.token; li.innerHTML = `<span class="mono">${esc(maskTok(t.token, t.cls))}</span><small>${t.n} agents · ${t.ok ? "copy" : "vocabulary"}</small>`;
    li.addEventListener("click", () => { follow = follow === t.token ? null : t.token; sel = null; renderSel(); markFollow(); }); return li;
  }));
  renderSel(); renderCounters(true);
}
function markFollow() { for (const li of $("strings").children) li.classList.toggle("on", li.dataset.token === follow); }

function renderCounters(force) {
  const now = performance.now(); if (!force && now - lastUi < 120) return; lastUi = now;
  const x = Math.floor(ip), vis = M.agents.filter((a) => a.first <= x).length;
  const cells = [["events", `${x.toLocaleString()} / ${M.stats.events.toLocaleString()}`], ["ants", `${vis} / ${M.agents.length}`], ["trails found", ub(tSorted.trails, x)],
    ["of them exact", ub(tSorted.exact, x)], ["ants with no trail", ub(tSorted.none, x)], ["hidden sources", ub(tSorted.hidden, x)],
    ["coincidences declined", ub(tSorted.coin, x)], ["flagged outputs", ub(tSorted.flag, x)]];
  $("counters").innerHTML = cells.map(([l, v]) => `<div class="c"><b>${v}</b><span>${l}</span></div>`).join("");
  $("clock").textContent = `${x.toLocaleString()} / ${M.stats.events.toLocaleString()}`;
  $("scrub").value = Math.round((ip / Math.max(1, M.stats.events)) * 1000);
}

function renderFeed() {
  $("feed").innerHTML = feedList.slice().reverse().map((f) => `<li class="${f.kind}">${f.html()}</li>`).join("") || `<li class="muted">Waiting for the first trail…</li>`;
}

function select(name) { sel = sel === name ? null : name; follow = null; markFollow(); renderSel(); }
function renderSel() {
  const box = $("sel");
  if (!sel) { box.className = "sel muted"; box.textContent = "Click an ant to trace it back, and to see who is downstream of it."; return; }
  const a = byName.get(sel), chain = traceBack(sel), down = downstream(sel), link = M.links.find((l) => l.adopter === sel);
  const ev = M.copies.filter((c) => c.ok && c.adopter === sel);
  const via = { exact: "exact read", tok: "same string, same room", amb: "one of several identical copies", hid: "source hidden" };
  const lines = [];
  if (link) lines.push(`<p class="${link.unique ? "ok" : "warn"}">${link.unique ? "Used what it read from" : link.weak ? "Used the same link as one it read, but not the copy it was served (code dropped or replaced), so the copy is unknown: one of" : "Used one of several identical copies read from"} <b>${esc(link.sources.join(", "))}</b>.</p>`);
  else if (M.hasReads && a.nreads) lines.push(`<p class="bad">Nothing it wrote matches anything it read: it found its own way (no trail).</p>`);
  if (ev.length) lines.push(`<p>Strings it picked up:</p><ul>${ev.slice(0, 5).map((c) => `<li>${esc(maskTok(c.token, c.cls))} · ${c.carriers.length ? `already used by ${esc(c.carriers.slice(0, 2).join(", "))}` : `<span class="warn">source not visible</span>`}</li>`).join("")}</ul>`);
  const trail = chain.length > 1 ? `<p><b>Trace back:</b> ${chain.map((c) => esc(c.name)).join(" ← ")}</p><p class="muted small">evidence, hop by hop: ${chain.slice(1).map((c) => via[c.via]).join(" → ")}</p>` : `<p class="muted">No trail leads into this ant: it is an origin, or its source is not in the log.</p>`;
  box.className = "sel";
  box.innerHTML = `<h4>${esc(sel)}${a.flagged ? ` <span class="bad">· flagged output</span>` : ""}</h4><p class="muted">${a.events} events · home: ${esc(a.home)} · first seen at event ${a.first + 1}</p>${lines.join("")}${trail}` +
    `<p><b>Downstream:</b> ${down.size ? `${down.size} agent${down.size > 1 ? "s" : ""} to re-check if this ant is wrong: ${[...down].slice(0, 12).map(esc).join(", ")}${down.size > 12 ? "…" : ""}` : "nobody picked anything up from this ant."}</p>` +
    (chain.some((c) => c.via === "hid") ? `<p class="warn small">The chain stops at a hidden source: the log cannot say where it read it.</p>` : "");
}

function renderCriteria() {
  const b = $("criteria-body"), c = meta.info?.criteria;
  const rows = c ? [["World", `${c.world}: ${c.world_what}`], ["Tags", `${c.tags}: ${c.tags_what}`], ["Model", c.model], ["Agents", c.agents + (c.seed !== undefined ? ` · seed ${c.seed} · up to ${c.max_calls_per_agent} tool calls each` : "")],
    ["Truth", c.truth], ...(c.run ? [["Run", c.run]] : [])] : [["Your file", `${meta.name}: ${meta.events.toLocaleString()} events, ${M.agents.length} agents, ${M.channels.length} channels, ${M.hasReads ? "with" : "without"} a read log`],
    ["Truth", M.hasReads ? "the read events in your log (what each agent was shown)" : "none: copying is inferred from shared strings, so some sources stay hidden"]];
  b.innerHTML = `<dl class="crit">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` +
    `<p class="small muted">Pooled results across all our runs, the hypotheses we stated in advance and what happened to each: <a href="../#method">How we tested</a> and the <a href="../paper/agloe.html">paper</a>.</p>`;
}

// ---------------------------------------------------------------- playback
function totalEv() { return M.stats.events; }
function resetPlayback(at) {
  ip = at; crumbs = []; fp = ub(feedItems.map((f) => f.i), ip); ep = ub(edges.map((e) => e.i), ip);
  feedList = feedItems.slice(Math.max(0, fp - 14), fp); renderFeed(); renderCounters(true);
  const q = new URLSearchParams(location.search);
  playing = !(reduce || q.get("autoplay") === "0" || at > 0); last = performance.now(); $("play").textContent = playing ? "Pause" : at >= totalEv() ? "Replay" : "Play";
}
function setPlaying(on) { if (on && ip >= totalEv() - 0.5) { resetPlayback(0); } playing = on; last = performance.now(); $("play").textContent = on ? "Pause" : "Play"; }
$("play").addEventListener("click", () => setPlaying(!playing));
$("speed").addEventListener("change", (e) => (speed = Number(e.target.value)));
$("scrub").addEventListener("input", (e) => { ip = (e.target.value / 1000) * totalEv(); playing = false; $("play").textContent = "Play"; crumbs = []; fp = ub(feedItems.map((f) => f.i), ip); ep = ub(edges.map((x) => x.i), ip); feedList = feedItems.slice(Math.max(0, fp - 14), fp); renderFeed(); renderCounters(true); });
for (const [id, k] of [["t-hidden", "hidden"], ["t-coin", "coin"], ["t-show", "show"]]) $(id).addEventListener("change", (e) => { opts[k] = e.target.checked; if (k === "show" && M) { renderSide(); markFollow(); renderFeed(); } });
addEventListener("keydown", (e) => { if (!M || e.target.matches("input, select, textarea")) return; if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); } });

function advance(prev, now) {
  while (ep < edges.length && edges[ep].i <= ip) { const e = edges[ep++]; if (e.i > prev && e.kind !== "coin" && crumbs.length < 60) crumbs.push({ from: e.from, to: e.to, kind: e.kind, t0: now }); }
  let changed = false;
  while (fp < feedItems.length && feedItems[fp].i <= ip) { if (feedItems[fp].i > prev) { feedList.push(feedItems[fp]); changed = true; } fp++; }
  if (feedList.length > 14) feedList = feedList.slice(-14);
  if (changed) renderFeed();
}

// ---------------------------------------------------------------- drawing
function bez(a, b, bend, u) { const mx = (a.x + b.x) / 2 - (b.y - a.y) * bend, my = (a.y + b.y) / 2 + (b.x - a.x) * bend, k = 1 - u; return { x: k * k * a.x + 2 * k * u * mx + u * u * b.x, y: k * k * a.y + 2 * k * u * my + u * u * b.y }; }
function pos(a, t) { return { x: a.x + Math.sin(t * 0.0006 + a.ph) * 2.6, y: a.y + Math.cos(t * 0.0007 + a.ph * 1.3) * 2.2 }; }
function ant(x, y, ang, s, fill, leg) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang); ctx.scale(s, s); ctx.strokeStyle = fill; ctx.fillStyle = fill; ctx.lineWidth = 1.1;
  for (let k = -1; k <= 1; k++) { const sw = Math.sin(leg + k * 2.1) * 1.6; ctx.beginPath(); ctx.moveTo(k * 3.2, 0); ctx.lineTo(k * 3.2 + sw, -6.4); ctx.moveTo(k * 3.2, 0); ctx.lineTo(k * 3.2 - sw, 6.4); ctx.stroke(); }
  for (const [ex, rx, ry] of [[-6, 4.6, 3.2], [0, 3, 2.4], [5, 2.6, 2.2]]) { ctx.beginPath(); ctx.ellipse(ex, 0, rx, ry, 0, 0, 7); ctx.fill(); }
  ctx.beginPath(); ctx.moveTo(6.5, -1); ctx.lineTo(10, -4.2); ctx.moveTo(6.5, 1); ctx.lineTo(10, 4.2); ctx.stroke(); ctx.restore();
}
function label(txt, x, y, color = C.text, size = 11) { ctx.font = `600 ${size}px system-ui, sans-serif`; const w = ctx.measureText(txt).width; ctx.fillStyle = "rgba(11,8,6,.82)"; ctx.fillRect(x - w / 2 - 4, y - size, w + 8, size + 5); ctx.fillStyle = color; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic"; ctx.fillText(txt, x, y); }

function draw(now) {
  const dpr = cv.width / LW; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, LW, LH);
  const g = ctx.createRadialGradient(LW / 2, LH / 2, 40, LW / 2, LH / 2, LW * 0.7); g.addColorStop(0, "#1a120c"); g.addColorStop(1, "#070403"); ctx.fillStyle = g; ctx.fillRect(0, 0, LW, LH);
  for (const c of chambers) {                                                  // the rooms / pages: chambers in the soil
    ctx.fillStyle = "rgba(60,40,24,.28)"; ctx.strokeStyle = "rgba(120,86,52,.35)"; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.ellipse(c.x, c.y, c.r * 1.12, c.r * 0.86, 0, 0, 7); ctx.fill(); ctx.stroke();
    ctx.font = "600 11px system-ui, sans-serif"; ctx.fillStyle = "rgba(190,160,120,.75)"; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    const nm = c.name.length > 22 ? c.name.slice(0, 21) + "…" : c.name; ctx.fillText(`${nm} · ${c.n}`, c.x, c.y - c.r * 0.86 - 6);
  }
  const x = ip, P = new Map(M.agents.filter((a) => a.first <= x).map((a) => [a.name, pos(a, now)]));
  const back = sel ? traceBack(sel) : null, backSet = back ? new Set(back.map((b) => b.name)) : null, down = sel ? downstream(sel) : null;
  const dim = sel || follow ? 0.14 : 0;
  // trails
  for (const t of agg) {
    if ((t.kind === "coin" && !opts.coin) || (t.kind === "hid" && !opts.hidden)) continue;
    const n = ub(t.is, x); if (!n) continue; const a = P.get(t.from), b = P.get(t.to); if (!a || !b) continue;
    const onSel = sel && ((backSet.has(t.from) && backSet.has(t.to)) || (t.from === sel && down.has(t.to)) || (down.has(t.from) && down.has(t.to)));
    const onFollow = follow && t.tokens.has(follow);
    const recent = x - t.is[n - 1] < 18, dense = agg.length > 150; let alpha = onSel || onFollow ? 0.95 : (sel || follow) ? dim : t.kind === "coin" ? 0.14 : recent ? 0.9 : dense ? 0.22 : 0.42;
    ctx.globalAlpha = alpha; ctx.lineWidth = (onSel || onFollow ? 2.2 : dense ? 0.7 : 1) + Math.log2(1 + n) * (dense ? 0.45 : 0.7);
    ctx.strokeStyle = t.kind === "exact" ? C.ok : t.kind === "coin" || t.kind === "hid" ? C.grey : C.amber; ctx.setLineDash(t.kind === "amb" ? [6, 4] : t.kind === "hid" ? [2, 5] : t.kind === "coin" ? [2, 3] : []);
    const bend = (hash(t.from + t.to) - 0.5) * 0.4; ctx.beginPath(); ctx.moveTo(a.x, a.y);
    for (let k = 1; k <= 18; k++) { const q = bez(a, b, bend, k / 18); ctx.lineTo(q.x, q.y); } ctx.stroke(); ctx.setLineDash([]);
    if (t.kind === "hid") { const m = bez(a, b, bend, 0.5); ctx.globalAlpha = Math.min(1, alpha + 0.2); label("?", m.x, m.y + 4, C.grey, 12); }
  }
  ctx.globalAlpha = 1;
  // crumbs travelling along trails
  crumbs = crumbs.filter((c) => now - c.t0 < 900);
  for (const c of crumbs) {
    const a = P.get(c.from), b = P.get(c.to); if (!a || !b) continue; const u = (now - c.t0) / 900, q = bez(a, b, (hash(c.from + c.to) - 0.5) * 0.4, u);
    ctx.save(); ctx.translate(q.x, q.y); ctx.rotate(Math.PI / 4); ctx.fillStyle = c.kind === "exact" ? C.ok : C.amber; ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 12; ctx.globalAlpha = 1 - u * 0.4; ctx.fillRect(-3.5, -3.5, 7, 7); ctx.restore();
  }
  // ants
  hitList = [];
  for (const a of M.agents) {
    const p = P.get(a.name); if (!p) continue;
    const fade = clamp((x - a.first) / 3 + 0.2), isFlag = a.flagged, inChain = backSet && backSet.has(a.name), inDown = down && down.has(a.name), isSel = a.name === sel;
    const usedTok = follow && (M.copies.some((c) => c.token === follow && (c.adopter === a.name || c.firstUser === a.name)));
    let alpha = fade; if ((sel && !isSel && !inChain && !inDown) || (follow && !usedTok)) alpha *= 0.28;
    const ang = Math.atan2(Math.cos(now * 0.0007 + a.ph * 1.3), Math.sin(now * 0.0006 + a.ph)) + (a.ph - 3);
    ctx.globalAlpha = alpha; ant(p.x, p.y, ang, 1.35, isFlag ? C.bad : C.ant, now * 0.012 + a.ph);
    if (isFlag) { ctx.shadowColor = C.bad; ctx.shadowBlur = 14; ctx.fillStyle = C.bad; ctx.beginPath(); ctx.arc(p.x, p.y, 2.2, 0, 7); ctx.fill(); ctx.shadowBlur = 0; }
    const noTrail = !(incoming.get(a.name) || []).some((e) => e.kind !== "coin");
    if (noTrail) { ctx.strokeStyle = "#c9b79c"; ctx.lineWidth = 1.7; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.arc(p.x, p.y, 16, 0, 7); ctx.stroke(); ctx.setLineDash([]); }
    if (inChain) { ctx.strokeStyle = C.ok; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 15, 0, 7); ctx.stroke(); }
    if (inDown) { ctx.strokeStyle = C.bad; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 15, 0, 7); ctx.stroke(); }
    if (isSel) { ctx.strokeStyle = C.amber; ctx.lineWidth = 2.6; ctx.beginPath(); ctx.arc(p.x, p.y, 18, 0, 7); ctx.stroke(); }
    if (usedTok) { ctx.strokeStyle = C.amber; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 15, 0, 7); ctx.stroke(); }
    ctx.globalAlpha = 1;
    hitList.push({ name: a.name, x: p.x, y: p.y });
    if (isSel || inChain || a.name === hover) label(a.name, p.x, p.y - 20, isSel ? C.amber : C.text);
  }
}
let hitList = [];

// ---------------------------------------------------------------- the clock (timer-driven: also runs in throttled or recorded tabs)
function frame() {
  if (!M) return;
  const now = performance.now(), dt = (now - last) / 1000; last = now;
  if (playing) {
    const total = totalEv(), prev = ip, rate = Math.max(6, Math.min(400, total / 45)) * speed;
    ip = Math.min(total, ip + rate * dt); advance(prev, now);
    if (ip >= total) { playing = false; $("play").textContent = "Replay"; }
  }
  draw(now); renderCounters(false);
}
setInterval(frame, 33);

// ---------------------------------------------------------------- pointer
function nearest(ev) {
  const r = cv.getBoundingClientRect(), x = ((ev.clientX - r.left) / r.width) * LW, y = ((ev.clientY - r.top) / r.height) * LH;
  let best = null, bd = 18; for (const h of hitList) { const d = Math.hypot(h.x - x, h.y - y); if (d < bd) { bd = d; best = h; } }
  return { best, x: ev.clientX - r.left, y: ev.clientY - r.top };
}
cv.addEventListener("click", (ev) => { const n = nearest(ev); if (n.best) select(n.best.name); else { sel = null; follow = null; markFollow(); renderSel(); } });
cv.addEventListener("mousemove", (ev) => {
  const n = nearest(ev); hover = n.best ? n.best.name : null; const tip = $("tip");
  if (hover) { const a = byName.get(hover); tip.hidden = false; tip.textContent = `${hover} · ${a.events} events · ${a.home}`; tip.style.left = `${Math.min(n.x + 12, cv.clientWidth - 200)}px`; tip.style.top = `${n.y + 12}px`; } else tip.hidden = true;
});
cv.addEventListener("mouseleave", () => { hover = null; $("tip").hidden = true; });

// ---------------------------------------------------------------- inputs: a dropped file, or one of our recorded runs
async function handleFile(file) { try { await openText(await readFileText(file), file.name, null); } catch (e) { setStatus(String(e.message || e), true); } }
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) handleFile(f); });
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } });
$("file").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) handleFile(f); });
let samples = [];
async function openSample(file) {
  const s = samples.find((x) => x.file === file); if (!s) return;
  try { const r = await fetch("samples/" + s.file); if (!r.ok) throw new Error("sample not found"); await openText(await r.text(), s.title, s); } catch (e) { setStatus(String(e.message || e), true); }
}
$("load-sample").addEventListener("click", () => openSample($("sample").value));
window.__colony = { select: (n) => select(n), seek: (f) => { resetPlayback(clamp(f, 0, 1) * totalEv()); playing = false; $("play").textContent = "Play"; }, model: () => M, state: () => ({ ip, playing, sel, follow }) };   // for tests and screenshots

(async () => {
  const dpr = Math.min(2, devicePixelRatio || 1); cv.width = LW * dpr; cv.height = LH * dpr;
  try { samples = await (await fetch("samples/index.json")).json(); } catch { samples = []; }
  $("sample").replaceChildren(...samples.map((s) => Object.assign(document.createElement("option"), { value: s.file, textContent: s.title })));
  const q = new URLSearchParams(location.search), want = q.get("sample");
  if (want && samples.some((s) => s.file === want)) { $("sample").value = want; await openSample(want); const t = parseFloat(q.get("t")); if (!isNaN(t) && M) { resetPlayback(clamp(t, 0, 1) * totalEv()); playing = false; $("play").textContent = "Play"; } }
})();
