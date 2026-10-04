// Agloe Traceability Report Card: the pure logic, a faithful port of backend/analysis/report.py.
// No DOM, no network. Used by card.js (browser) and parity.test.mjs (node), which checks it against the Python output.

export const MAX_AGENTS = 10;
const ALIASES = {
  agent: ["agent", "author", "speaker", "label", "user", "agent_name", "sender", "actor", "name"],
  time: ["time", "t", "timestamp", "created_at", "ts"],
  channel: ["channel", "room", "page", "page_id", "location", "loc", "thread", "session", "session_id", "conversation", "conversation_id"],
  content: ["content", "text", "body", "message", "msg"],
};
const SCRUB = ["[REDACTED]", "[BLOB_REMOVED]", "[IMAGE_REMOVED]"];
const COMMON = ["content-type", "application", "authorization", "user-agent", "accept", "bearer", "mozilla", "charset",
  "access-control", "cache-control", "text/html", "x-requested"];
const B64_MARKERS = ["application/json", "content-type", "text/", "http", '{"', "[{"];
const UUID = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}/;
const WAYBACK = /^(\d{14})id_?$/;
const SNAKE = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;
const CAMEL = /^[a-z]+(?:[A-Z][a-z0-9]*)+$/;
const VOCAB_CLASSES = new Set(["snake-field", "camel-ident", "wayback-constructed"]);
export const REC_TAGS = "Add version-unique, load-bearing tags (canary tokens) to shared artifacts. A decoration copiers can drop is " +
  "dropped by some models; a token the link needs to work survives copying (see docs/CANARY.md).";

// ---------------------------------------------------------------- text helpers
export function unquote(s) {
  return s.replace(/(?:%[0-9a-fA-F]{2})+/g, (run) => {
    const bytes = new Uint8Array(run.length / 3);
    for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(run.slice(i * 3 + 1, i * 3 + 3), 16);
    return new TextDecoder("utf-8").decode(bytes);
  });
}
const unquoteN = (s, n) => { for (let i = 0; i < n; i++) s = unquote(s); return s; };

function isCommon(t) {
  const low = t.toLowerCase();
  if (COMMON.some((c) => low.startsWith(c) || low.includes(c))) return true;
  try {
    const pad = t + "=".repeat((4 - (t.length % 4)) % 4);
    const bin = atob(pad.replace(/-/g, "+").replace(/_/g, "/"));
    for (let i = 0; i < bin.length; i++) { const c = bin.charCodeAt(i); if (c < 32 || c > 126) return false; }
    const lowDec = bin.toLowerCase();
    return B64_MARKERS.some((c) => lowDec.includes(c));
  } catch { return false; }
}

function isGood(t) {
  if (isCommon(t)) return false;
  if (/^[0-9a-fA-F]{24,}$/.test(t) || /^\d+$/.test(t)) return false;
  if (new Set(t).size < 7) return false;
  return /\d/.test(t) || (/[A-Z]/.test(t) && /[a-z]/.test(t)) || t.includes("_");
}

export function tokens(content) {
  let text = unquoteN(content, 3);
  for (const m of SCRUB) text = text.split(m).join(" ");
  const out = new Set();
  for (const t of text.match(/[A-Za-z0-9_\-]{12,}/g) || []) if (isGood(t)) out.add(t);
  return out;
}

export function shannon(s) {
  const n = s.length;
  if (!n) return 0;
  const c = new Map();
  for (const ch of s) c.set(ch, (c.get(ch) || 0) + 1);
  let h = 0;
  for (const v of c.values()) h -= (v / n) * Math.log2(v / n);
  return h;
}

export function classifyToken(tok) {
  if (UUID.test(tok)) return ["uuid", "high"];
  const m = WAYBACK.exec(tok);
  if (m) return m[1].slice(8) === "000000" ? ["wayback-constructed", "low"] : ["wayback-capture", "medium"];
  if (SNAKE.test(tok)) return ["snake-field", "low"];
  if (CAMEL.test(tok)) return ["camel-ident", "low"];
  if (shannon(tok) >= 3.3 && tok.length >= 12) return ["high-entropy", "high"];
  return ["other", "low"];
}

export function wilson(k, n, z = 1.96) {
  if (!n) return [0, 0];
  const p = k / n, d = 1 + (z * z) / n, c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [c - h, c + h];
}

export function grade(coverage) {
  for (const [g, lo] of [["A", 0.9], ["B", 0.7], ["C", 0.5], ["D", 0.25]]) if (coverage >= lo) return g;
  return "F";
}

// ---------------------------------------------------------------- input
function pick(d, key) {
  for (const a of ALIASES[key]) if (d[a] !== undefined && d[a] !== null && d[a] !== "") return d[a];
  return null;
}

export function normalize(d) {
  const agent = pick(d, "agent"), time = pick(d, "time"), content = pick(d, "content");
  if (!agent || !time || content === null) return null;
  const e = { agent: String(agent), time: String(time), channel: String(pick(d, "channel") || "global"),
    content: typeof content === "string" ? content : JSON.stringify(content) };
  if (d.kind) e.kind = String(d.kind);            // optional: a read log ("kind": "read", "source": author of what was read) ...
  if (d.source) e.source = String(d.source);
  if (d.flag) e.flag = true;                      // ... and a flag on outputs known to be bad
  return e;
}

export function loadEvents(text) {          // JSON Lines, or one JSON array of objects; malformed lines are skipped
  let items = [];
  if (text.trimStart().startsWith("[")) {
    try { items = JSON.parse(text); } catch { items = []; }
  } else {
    for (const line of text.split("\n")) {
      const s = line.trim();
      if (!s) continue;
      try { items.push(JSON.parse(s)); } catch { /* skip */ }
    }
  }
  const out = [];
  for (const d of Array.isArray(items) ? items : []) {
    const e = d && typeof d === "object" && !Array.isArray(d) ? normalize(d) : null;
    if (e) out.push(e);
  }
  return out.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}

// ---------------------------------------------------------------- the report
const round3 = (x) => Math.round(x * 1000) / 1000;
const pct = (x) => `${Math.round(x * 100)}%`;

export function reportCard(all, maxAgents = MAX_AGENTS) {
  const events = all.filter((e) => e.kind !== "read");           // reads are evidence for the colony view; they are not things an agent wrote
  const agents = new Set(events.map((e) => e.agent));
  const channels = new Set(events.map((e) => e.channel));
  const first = new Map();                                   // token -> Map(agent -> {time, channel})
  for (const e of events) {
    for (const t of tokens(e.content)) {
      if (!first.has(t)) first.set(t, new Map());
      const by = first.get(t);
      if (!by.has(e.agent)) by.set(e.agent, { time: e.time, channel: e.channel });
    }
  }
  const wbc = new Map();                                     // "token\0channel" -> [[time, agent]]
  for (const [t, by] of first) for (const [a, r] of by) {
    const k = `${t}\u0000${r.channel}`;
    if (!wbc.has(k)) wbc.set(k, []);
    wbc.get(k).push([r.time, a]);
  }
  const supported = [], declined = [];
  let nNaive = 0;
  for (const [t, by] of first) {
    const n = by.size;
    if (n < 2) continue;
    const [cls, strength] = classifyToken(t);
    const order = [...by.entries()].sort((x, y) => (x[1].time < y[1].time ? -1 : x[1].time > y[1].time ? 1 : 0));
    const ok = n <= maxAgents && !VOCAB_CLASSES.has(cls) && (strength === "high" || n <= 3);
    for (const [agent, r] of order.slice(1)) {
      const earlier = new Set();
      for (const [tm, a] of wbc.get(`${t}\u0000${r.channel}`)) if (tm < r.time && a !== agent) earlier.add(a);
      const row = { visible_carriers: earlier.size };
      nNaive++;
      (ok ? supported : declined).push(row);
    }
  }
  const trace = (rows) => {
    const k = rows.filter((r) => r.visible_carriers > 0).length;
    const ceil = rows.length ? rows.filter((r) => r.visible_carriers > 0).reduce((s, r) => s + 1 / r.visible_carriers, 0) / rows.length : 0;
    return [k, ceil];
  };
  const kAll = trace([...supported, ...declined])[0];
  const [kSup, ceilSup] = trace(supported);
  const nSup = supported.length;
  const cov = nSup ? kSup / nSup : 0;
  const shared = [];
  for (const [t, by] of first) if (by.size >= 3) shared.push([t, by.size]);
  shared.sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));   // ties by name (same rule as Python)
  const rec = [];
  if (!nSup) rec.push("No distinctive string is shared between agents (every repeated string is common vocabulary), so copying " +
    "cannot be traced from content at all. Shared artifacts need unique, load-bearing tags before an audit can say anything.");
  if (nSup && cov < 0.5) rec.push(`${pct(1 - cov)} of real copies have no visible source in the channel where they reappear: agents read from ` +
    "places you do not log. Log item-level reads (who read which page/message, when).");
  if (nNaive && (nNaive - nSup) / nNaive > 0.5) rec.push(`${pct((nNaive - nSup) / nNaive)} of naive 'same string' matches are shared vocabulary or common values. ` +
    "Do not treat a shared value as copying without its base rate.");
  rec.push(REC_TAGS);
  return {
    events: events.length, agents: agents.size, channels: channels.size,
    distinct_shared_strings: [...first.values()].filter((by) => by.size >= 2).length,
    naive_copy_calls: nNaive,
    calibrated_copy_calls: nSup,
    declined_as_coincidence: declined.length,
    carrier_coverage: round3(cov),
    carrier_coverage_ci95: wilson(kSup, nSup).map(round3),
    best_possible_top1: round3(ceilSup),
    naive_coverage: nNaive ? round3(kAll / nNaive) : 0,
    grade: nSup ? grade(cov) : "N/A",
    single_channel: channels.size === 1,
    everyone_types_this: shared.slice(0, 10).map(([t, c]) => ({ string: t.slice(0, 40), agents: c,
      class: c > maxAgents ? "shared-vocabulary" : classifyToken(t)[0] })),
    recommendations: rec,
  };
}

// ---------------------------------------------------------------- the colony view: who picked up what from whom, and what each agent actually read
// `all` must be sorted by time (loadEvents and the field mapper both sort). Token copies use the SAME rules as reportCard (parity-tested), so the
// colony and the card always agree on the counts. If the log has read events (kind "read", content = the exact copy served, source = its author),
// an agent's first later event that contains something it read is an exact (or, for identical copies, ambiguous) link: "this is what it read".
export function colony(all, maxAgents = MAX_AGENTS) {
  const agents = new Map(), channels = new Map(), first = new Map(), reads = new Map();
  all.forEach((e, i) => {
    let a = agents.get(e.agent);
    if (!a) { a = { name: e.agent, first: i, events: 0, nreads: 0, channels: new Map(), wrote: new Map(), flagged: false }; agents.set(e.agent, a); }
    if (e.kind === "read") a.nreads++;
    a.events++; a.channels.set(e.channel, (a.channels.get(e.channel) || 0) + 1); if (e.flag) a.flagged = true;
    if (e.kind !== "read") a.wrote.set(e.channel, (a.wrote.get(e.channel) || 0) + 1);
    channels.set(e.channel, (channels.get(e.channel) || 0) + 1);
    if (e.kind === "read") { if (!reads.has(e.agent)) reads.set(e.agent, []); reads.get(e.agent).push({ i, content: e.content, source: e.source || null }); return; }
    for (const t of tokens(e.content)) {
      if (!first.has(t)) first.set(t, new Map());
      const by = first.get(t);
      if (!by.has(e.agent)) by.set(e.agent, { agent: e.agent, i, time: e.time, channel: e.channel });
    }
  });
  const copies = [], tokenList = [];
  for (const [t, by] of first) {
    const n = by.size; if (n < 2) continue;
    const [cls, strength] = classifyToken(t);
    const users = [...by.values()].sort((x, y) => (x.time < y.time ? -1 : x.time > y.time ? 1 : x.i - y.i));
    const ok = n <= maxAgents && !VOCAB_CLASSES.has(cls) && (strength === "high" || n <= 3);
    tokenList.push({ token: t, cls, n, ok, firstUser: users[0].agent });
    for (const u of users.slice(1)) {
      const carriers = users.filter((w) => w.channel === u.channel && w.time < u.time && w.agent !== u.agent).map((w) => w.agent);
      copies.push({ i: u.i, token: t, cls, ok, adopter: u.agent, channel: u.channel, carriers, firstUser: users[0].agent });
    }
  }
  // A link is the agent's first later event that contains something it read. Tier 1: the exact copy it was served (the most specific match wins, so a
  // shorter tagless link inside a longer tagged one does not count as a second candidate). Tier 2, only if no exact copy matches: the same link with
  // its tag, token or query dropped ("weak": it used what it read, but which copy is unknown).
  const strip = (s) => s.replace(/\/s\/[a-z0-9]{6,12}\//g, "/").replace(/[?#][^\s"'<>)\]]*/g, "");
  const links = [], linked = new Set();
  all.forEach((e, i) => {
    if (e.kind === "read" || linked.has(e.agent) || !reads.has(e.agent)) return;
    const prior = reads.get(e.agent).filter((r) => r.i < i && r.content.length >= 12 && r.source !== e.agent);
    let hit = prior.filter((r) => e.content.includes(r.content)), weak = false;
    if (hit.length) hit = hit.filter((r) => !hit.some((o) => o !== r && o.content.length > r.content.length && o.content.includes(r.content)));
    else {
      const ec = strip(e.content);
      hit = prior.filter((r) => { r.s ??= strip(r.content); return r.s.length >= 12 && ec.includes(r.s); }); weak = hit.length > 0;
    }
    if (!hit.length) return;
    linked.add(e.agent);
    const sources = [...new Set(hit.map((r) => r.source).filter(Boolean))];
    links.push({ i, adopter: e.agent, sources, unique: !weak && sources.length === 1, weak, readAt: Math.max(...hit.map((r) => r.i)), channel: e.channel });
  });
  const list = [...agents.values()].sort((a, b) => a.first - b.first);
  for (const a of list) {                                          // home room: where it wrote most (reads alone do not make a room home); ties go to the busier room
    const m = a.wrote.size ? a.wrote : a.channels;
    a.home = [...m.entries()].sort((x, y) => y[1] - x[1] || channels.get(y[0]) - channels.get(x[0]))[0][0];
  }
  const sup = copies.filter((c) => c.ok);
  return {
    agents: list, channels: [...channels].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n), copies, links,
    tokens: tokenList.sort((a, b) => (b.ok - a.ok) || (b.n - a.n) || (a.token < b.token ? -1 : 1)),
    hasReads: reads.size > 0,
    stats: { events: all.length, reads: [...reads.values()].reduce((s, r) => s + r.length, 0), naive: copies.length, supported: sup.length,
      declined: copies.length - sup.length, covered: sup.filter((c) => c.carriers.length).length, linked: links.length,
      linkedExact: links.filter((l) => l.unique).length, linkedWeak: links.filter((l) => l.weak).length, flagged: list.filter((a) => a.flagged).length },
  };
}
