// Agloe Face-Off: one swarm, two investigators, as a self-playing story on one 16:9 canvas (project it, or record it with "Make a clip").
// Static page; every number comes from the recorded lab runs in data/ (scripts/export_lab_replay.py). Nothing is fetched except those files.
const W = 1280, H = 720, R = 200, KX = 1.34;      // the radial tree is stretched sideways to fill the wide panels
const cv = document.getElementById("c"), ctx = cv.getContext("2d");
const $ = (id) => document.getElementById(id);
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
const pct = (x) => `${Math.round(x * 100)}%`;
let C = {};

// ---------------------------------------------------------------- the story: two recorded runs, then an end card
const SCENES = [
  { file: "early_tip_tags.json", kind: "spread", phases: [["intro", 3.4], ["infect", 9], ["blame", 12], ["verdict", 6.5]] },
  { file: "cleanup_tip_tags.json", kind: "cleanup", phases: [["intro", 3.2], ["infect", 5], ["recheck", 7.5], ["verdict", 6.5]] },
];
const END_S = 4.5;
let S = [], timeline = [], TOTAL = 0, tl = 0, playing = false, lastNow = 0, recording = false;

const closure = (m, root) => {                       // agents whose chain of parents reaches `root` (cycle-safe)
  const out = new Set();
  for (const a of m.keys()) { const seen = new Set(); let cur = a; while (m.has(cur) && !seen.has(cur)) { seen.add(cur); cur = m.get(cur); if (cur === root) { out.add(a); break; } } }
  return out;
};

function layoutTree(s) {                             // radial tree of who really copied from whom; same positions in both panels
  const kids = new Map();
  for (const [c, p] of s.truth) { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(c); }
  const hasKids = (id) => kids.has(id), root = s.root;
  const tops = [...(root ? kids.get(root) || [] : [])];
  for (const n of s.nodes) if (n.id !== root && !s.truth.has(n.id) && hasKids(n.id) && !tops.includes(n.id)) tops.push(n.id);
  const lone = s.nodes.filter((n) => n.id !== root && !s.truth.has(n.id) && !hasKids(n.id)).map((n) => n.id);
  const leaves = new Map(), guard = new Set();
  const cnt = (id) => { if (leaves.has(id)) return leaves.get(id); if (guard.has(id)) return 1; guard.add(id); const k = kids.get(id) || []; const v = k.length ? k.reduce((a, c) => a + cnt(c), 0) : 1; leaves.set(id, v); return v; };
  const total = tops.reduce((a, t) => a + cnt(t), 0) || 1;
  let maxD = 1;
  const depthOf = (id, d, seen = new Set()) => { maxD = Math.max(maxD, d); if (seen.has(id)) return; seen.add(id); for (const c of kids.get(id) || []) depthOf(c, d + 1, seen); };
  tops.forEach((t) => depthOf(t, 1));
  const gap = (R - 14) / maxD, pos = new Map();
  if (root) pos.set(root, { x: 0, y: 0 }); else pos.set("__centre", { x: 0, y: 0 });
  const a0 = lone.length ? Math.PI / 2 + 0.62 : -Math.PI / 2, span = lone.length ? 2 * Math.PI - 1.24 : 2 * Math.PI;
  let acc = 0;
  const place = (id, d, from, to, seen = new Set()) => {
    if (seen.has(id)) return; seen.add(id);
    const a = (from + to) / 2;
    pos.set(id, { x: Math.cos(a) * d * gap * KX, y: Math.sin(a) * d * gap });
    const k = kids.get(id) || []; let f = from; const tot = k.reduce((q, c) => q + cnt(c), 0) || 1;
    for (const c of k) { const w = (to - from) * (cnt(c) / tot); place(c, d + 1, f, f + w, seen); f += w; }
  };
  for (const t of tops) { const w = span * (cnt(t) / total); place(t, 1, a0 + acc, a0 + acc + w); acc += w; }
  lone.forEach((id, i) => {                          // agents that found it alone sit in the bottom sector, unconnected
    const a = Math.PI / 2 + (lone.length > 1 ? (i / (lone.length - 1) - 0.5) * 0.9 : 0), r = R * (i % 2 ? 0.8 : 0.93);
    pos.set(id, { x: Math.cos(a) * r * KX, y: Math.sin(a) * r });
  });
  s.pos = pos;
}

function prep(D, kind) {
  const nodes = [...D.nodes];
  if (D.rumor && !nodes.some((n) => n.id === D.rumor.id)) nodes.push({ id: D.rumor.id, t: D.rumor.t, rumor: true, stale: false, copied: false });
  nodes.sort((a, b) => a.t - b.t);
  const s = { D, kind, nodes, N: nodes.length, truth: new Map(D.edges.truth), edit: new Map(D.edges.edit_log), tags: new Map(D.edges.tags), root: D.rumor ? D.rumor.id : null };
  s.idx = new Map(nodes.map((n, i) => [n.id, i]));
  s.agents = nodes.filter((n) => !n.rumor).length;
  layoutTree(s);
  const cls = (c, p) => (s.truth.get(c) === p ? "ok" : s.truth.has(c) ? "bad" : "ghost");     // right source / wrong source / blames an agent that worked alone
  s.edgesEdit = [...s.edit].map(([c, p]) => ({ c, p, kind: cls(c, p) }));
  s.edgesTags = [...s.tags].map(([c, p]) => ({ c, p, kind: cls(c, p) }));
  if (s.root) {
    s.afterTip = new Set(nodes.filter((n) => !n.rumor && n.t > D.rumor.t).map((n) => n.id));     // the no-trace rule: everything submitted after the tip appeared
    s.reached = closure(s.truth, s.root);                                                         // answer key: outputs the tip really reached
    const combined = new Map(s.tags); for (const [c, p] of s.edit) if (!combined.has(c)) combined.set(c, p);   // the code where kept, the edit-log guess where lost
    s.traced = closure(combined, s.root);
    s.edgesTrace = [...combined].filter(([c]) => s.traced.has(c)).map(([c, p]) => ({ c, p, kind: cls(c, p) }));
    s.caught = [...s.traced].filter((a) => s.reached.has(a)).length;
  }
  return s;
}

function buildTimeline() {
  timeline = []; let t = 0;
  S.forEach((s, si) => { for (const [name, d] of SCENES[si].phases) { timeline.push({ s: si, name, t0: t, t1: t + d, d }); t += d; } });
  timeline.push({ s: -1, name: "end", t0: t, t1: t + END_S, d: END_S }); TOTAL = t + END_S;
}
const segAt = (t) => timeline.find((q) => t < q.t1) || timeline[timeline.length - 1];

// ---------------------------------------------------------------- drawing helpers
function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
function text(str, x, y, size, color, weight = 400, align = "center", base = "alphabetic") { ctx.font = `${weight} ${size}px ${SANS}`; ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = base; ctx.fillText(str, x, y); }
function bez(a, b, pull, u) { const mx = ((a.x + b.x) / 2) * pull, my = ((a.y + b.y) / 2) * pull, k = 1 - u; return { x: k * k * a.x + 2 * k * u * mx + u * u * b.x, y: k * k * a.y + 2 * k * u * my + u * u * b.y }; }
function edgeLine(a, b, pull, prog, color, width, dash) {
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []); ctx.beginPath(); ctx.moveTo(a.x, a.y);
  for (let k = 1; k <= 22; k++) { const q = bez(a, b, pull, (prog * k) / 22); ctx.lineTo(q.x, q.y); }
  ctx.stroke(); ctx.setLineDash([]);
}

function drawNode(s, n, alpha, age, dim = 1) {
  const p = s.pos.get(n.id); if (!p || alpha <= 0) return;
  ctx.save(); ctx.globalAlpha = alpha * dim;
  if (age > 0 && age < 0.9 && dim === 1) {                         // a ripple as the agent finishes
    ctx.globalAlpha = (1 - age / 0.9) * 0.55 * alpha; ctx.strokeStyle = n.stale || n.rumor ? C.bad : C.text; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(p.x, p.y, 8 + age * 26, 0, 7); ctx.stroke(); ctx.globalAlpha = alpha * dim;
  }
  if (n.rumor) {
    ctx.shadowColor = C.bad; ctx.shadowBlur = 18; ctx.fillStyle = C.bad; ctx.translate(p.x, p.y); ctx.rotate(Math.PI / 4); ctx.fillRect(-8, -8, 16, 16);
  } else if (n.stale) {
    ctx.shadowColor = C.bad; ctx.shadowBlur = 12; ctx.fillStyle = C.bad; ctx.beginPath(); ctx.arc(p.x, p.y, 6.5, 0, 7); ctx.fill();
  } else if (n.copied) {
    ctx.fillStyle = C.text; ctx.beginPath(); ctx.arc(p.x, p.y, 6.5, 0, 7); ctx.fill();
  } else {
    ctx.strokeStyle = C.text; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 6, 0, 7); ctx.stroke();
  }
  ctx.restore();
}

// one panel: its edges and nodes for the current phase. side 0 = left investigator, 1 = right investigator
function panel(side, s, phase, p, dur) {
  const x0 = side ? 652 : 24, y0 = 96, w = 604, h = 478, cx = x0 + w / 2, cy = y0 + h / 2 + 2;
  ctx.fillStyle = "#0d0907"; rr(x0, y0, w, h, 14); ctx.fill(); ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.stroke();
  ctx.save(); rr(x0, y0, w, h, 14); ctx.clip(); ctx.translate(cx, cy);
  ctx.strokeStyle = "rgba(255,255,255,.045)"; ctx.lineWidth = 1;
  for (let k = 1; k <= 4; k++) { ctx.beginPath(); ctx.ellipse(0, 0, (R * k * KX) / 4, (R * k) / 4, 0, 0, 7); ctx.stroke(); }
  const N = s.N, early = phase === "intro" || phase === "infect";
  const f = (i) => (i / Math.max(1, N - 1)) * 0.9;                                  // when node i finishes, as a fraction of the infect phase
  const alphaOf = (i) => (phase === "intro" ? (i === 0 && s.root && s.idx.get(s.root) === 0 ? 1 : 0) : phase === "infect" ? clamp((p - f(i)) / 0.04) : 1);
  const ageOf = (i) => (phase === "infect" ? (p - f(i)) * dur : 9);
  let dimSet = null;                                                                // nodes faded out in the clean-up scene's right panel
  const recheck = s.kind === "cleanup" && (phase === "recheck" || phase === "verdict");
  if (recheck && side === 1) dimSet = s.traced;
  const dimOf = (n) => (dimSet && !n.rumor && !dimSet.has(n.id) ? 1 - 0.78 * ease(phase === "recheck" ? (p - 0.08) / 0.2 : 1) : 1);

  // edges
  const blame = s.kind === "spread" && (phase === "blame" || phase === "verdict");
  const list = side ? s.edgesTags : s.edgesEdit;
  if (blame) {
    for (const e of list) {
      const a = s.pos.get(e.p), b = s.pos.get(e.c); if (!a || !b) continue;
      const i = s.idx.get(e.c), fa = (i / Math.max(1, N - 1)) * 0.85, pr = phase === "verdict" ? 1 : clamp((p - fa) / 0.13);
      if (pr <= 0) continue;
      const wrong = e.kind !== "ok", col = side ? C.ok : wrong ? C.bad : C.ok;
      ctx.globalAlpha = wrong ? 0.8 : 0.9;
      edgeLine(a, b, wrong ? 0.28 : 1, pr, col, side ? 2.2 : wrong ? 1.6 : 2.2, e.kind === "ghost" ? [5, 5] : null);
      if (side && pr < 1) { const q = bez(a, b, 1, pr); ctx.save(); ctx.translate(q.x, q.y); ctx.rotate(Math.PI / 4); ctx.fillStyle = C.amber; ctx.shadowColor = C.amber; ctx.shadowBlur = 10; ctx.fillRect(-4, -4, 8, 8); ctx.restore(); }   // the token riding the link
      ctx.globalAlpha = 1;
      if (!side && wrong && phase === "blame") {                                    // a cross on every wrong guess, fading
        const age = (p - fa - 0.13) * dur; if (age > 0 && age < 1.2) { text("✗", b.x, b.y - 13, 17, C.bad, 700); }
      }
    }
  }
  if (recheck && side === 1) {                                                     // follow the trace: edges from the tip down to the agents it reached
    const rank = [...s.traced].sort((a, b) => s.idx.get(a) - s.idx.get(b));
    for (const e of s.edgesTrace) {
      const a = s.pos.get(e.p), b = s.pos.get(e.c); if (!a || !b) continue;
      const r = rank.indexOf(e.c), fa = 0.12 + (r / Math.max(1, rank.length - 1)) * 0.55, pr = phase === "verdict" ? 1 : clamp((p - fa) / 0.14);
      if (pr > 0) { ctx.globalAlpha = 0.95; edgeLine(a, b, e.kind === "ok" ? 1 : 0.3, pr, e.kind === "ok" ? C.ok : C.bad, 2.6, e.kind === "ghost" ? [5, 5] : null); ctx.globalAlpha = 1; }
    }
  }
  // nodes
  s.nodes.forEach((n, i) => drawNode(s, n, alphaOf(i), ageOf(i), dimOf(n)));
  if (recheck && side === 0) {                                                     // no trace: re-check everything submitted after the tip appeared
    const rank = s.nodes.filter((n) => s.afterTip.has(n.id));
    rank.forEach((n, r) => {
      const pp = s.pos.get(n.id), fa = 0.1 + (r / Math.max(1, rank.length - 1)) * 0.6, a = phase === "verdict" ? 1 : ease((p - fa) / 0.08);
      if (a <= 0) return; ctx.globalAlpha = a; ctx.strokeStyle = C.amber; ctx.lineWidth = 2.2; ctx.beginPath(); ctx.arc(pp.x, pp.y, 11.5, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
    });
  }
  if (recheck && side === 1) {
    for (const id of s.traced) { const pp = s.pos.get(id); if (!pp) continue; ctx.strokeStyle = C.ok; ctx.lineWidth = 2.2; ctx.globalAlpha = phase === "verdict" ? 1 : ease((p - 0.2) / 0.3); ctx.beginPath(); ctx.arc(pp.x, pp.y, 11.5, 0, 7); ctx.stroke(); ctx.globalAlpha = 1; }
  }
  if (s.root && alphaOf(s.idx.get(s.root)) > 0) text("bad tip", 0, 24, 12, C.muted, 600);
  if (recheck && side === 1 && phase === "verdict") {                              // what the trace buys: the rest have no link to the tip
    ctx.globalAlpha = ease(p / 0.2); text(`the other ${s.agents - s.traced.size} outputs have no link to the tip`, 0, h / 2 - 16, 15, C.ok, 600); ctx.globalAlpha = 1;
  }
  ctx.restore();
  return { x0, w, cx };
}

// ---------------------------------------------------------------- numbers under the panels, computed from the same frame state
function scoreboard(side, s, phase, p) {
  const cx = side ? 954 : 326, N = s.N, agents = s.agents;
  let label = "", big = "", sub = "", color = C.text, size = 46;
  if (s.kind === "spread") {
    if (phase === "intro" || phase === "infect") {
      const done = phase === "intro" ? 0 : s.nodes.filter((n, i) => !n.rumor && n.stale && clamp((p - (i / Math.max(1, N - 1)) * 0.9) / 0.04) > 0).length;
      label = "adopted the bad tip"; big = `${done} / ${agents}`; color = C.bad; sub = side ? "the same records, a different investigator" : "the same records, a different investigator";
    } else {
      const copies = s.D.stats.copied, list = side ? s.edgesTags : s.edgesEdit;
      let ok = 0, wrong = 0;
      for (const e of list) { const i = s.idx.get(e.c), fa = (i / Math.max(1, N - 1)) * 0.85, done = phase === "verdict" || (p - fa) / 0.13 >= 1; if (done) { if (e.kind === "ok") ok++; else wrong++; } }
      label = "sources named correctly"; color = side ? C.ok : C.bad;
      if (phase === "blame") { big = `${ok} / ${copies}`; sub = side ? "each code names the exact copy" : `${wrong} wrong guesses so far`; }
      else { big = pct(ok / copies); size = 54; sub = side ? `${ok} of ${copies}, every code names its copy` : `${ok} of ${copies}; ${wrong} wrong guesses`; }
    }
  } else {
    const after = s.afterTip.size, tr = s.traced.size;
    if (phase === "intro" || phase === "infect") {
      const stale = s.nodes.filter((n, i) => n.stale && clamp((p - (i / Math.max(1, N - 1)) * 0.9) / 0.04) > 0 && phase === "infect").length;
      label = "outputs that used the bad tip"; big = `${stale}`; color = C.bad; sub = `of ${agents} agents`;
    } else {
      label = "outputs to re-check"; color = side ? C.ok : C.amber;
      const rank = side ? [...s.traced].sort((a, b) => s.idx.get(a) - s.idx.get(b)) : s.nodes.filter((n) => s.afterTip.has(n.id)).map((n) => n.id);
      const shown = phase === "verdict" ? rank.length : rank.filter((_, r) => (side ? 0.12 + (r / Math.max(1, rank.length - 1)) * 0.55 : 0.1 + (r / Math.max(1, rank.length - 1)) * 0.6) <= p).length;
      big = String(shown); if (phase === "verdict") size = 54;
      sub = side ? (phase === "verdict" ? `found ${s.caught} of the ${s.reached.size} the tip reached` : "following the codes") : (phase === "verdict" ? "everything submitted after the tip appeared" : "no trace: re-check everyone after the tip");
    }
  }
  text(label.toUpperCase(), cx, 598, 13, C.muted, 600);
  text(big, cx, 598 + size, size, color, 800);
  text(sub, cx, 598 + size + 22, 15, C.muted, 400);
}

// a short hook before each run: three lines, one after the other, then they clear
const HOOKS = {
  spread: (s) => ["One bad tip.", `${s.agents} AI agents.`, "Who passed it on?"],
  cleanup: () => ["Another run.", "A late tip.", "Most agents never used it."],
};
function hook(s, p) {
  const lines = HOOKS[s.kind](s), out = 1 - ease((p - 0.82) / 0.18);
  ctx.save(); ctx.fillStyle = `rgba(11,8,6,${0.78 * out})`; ctx.fillRect(24, 96, W - 48, 478);
  lines.forEach((ln, i) => { const a = ease((p - i * 0.24) / 0.14) * out; ctx.globalAlpha = a; text(ln, W / 2, 262 + i * 76, i === 2 ? 56 : 62, i === 2 ? C.amber : C.text, 800); });
  ctx.restore();
}

const CAPTIONS = {
  spread: { intro: "A bad tip is planted in a wiki shared by 30 AI agents.", infect: "Agents read the wiki and pass the link on. The mistake spreads.", blame: "Same records, two investigators. Who passed it to whom?", verdict: (s) => `Edit log alone: ${s.D.stats.edit_log_correct} of ${s.D.stats.copied}. With trap streets: ${s.D.stats.tags_correct} of ${s.D.stats.copied}.` },
  cleanup: { intro: "Another run: a late tip, and most agents never used it.", infect: "The tip appears mid-run. Only some agents act on it.", recheck: "Which outputs do we have to re-check?", verdict: (s) => `Re-check ${s.afterTip.size} outputs, or just ${s.traced.size}. The trace found ${s.caught} of the ${s.reached.size} affected.` },
};
const TITLES = {
  spread: [["The detective", "edit log only: who wrote the same link"], ["Trap streets", "a secret code in every link"]],
  cleanup: [["No trace", "re-check everything after the tip"], ["Follow the trace", "the code where kept, earliest writer where lost"]],
};

function draw() {
  const dpr = cv.width / W;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  const seg = segAt(tl), p = clamp((tl - seg.t0) / seg.d);
  const si = seg.s < 0 ? S.length - 1 : seg.s, s = S[si], phase = seg.s < 0 ? "verdict" : seg.name, pp = seg.s < 0 ? 1 : p;
  if (!s) return;
  const [[lt, ls], [rt, rs]] = TITLES[s.kind];
  text(`RUN ${si + 1} OF ${S.length} · ${s.kind === "spread" ? "THE TIP SPREADS" : "THE CLEAN-UP"}`, W / 2, 24, 13, C.amber, 700);
  text(lt, 326, 58, 27, C.text, 700); text(ls, 326, 81, 15, C.muted, 400);
  text(rt, 954, 58, 27, C.text, 700); text(rs, 954, 81, 15, C.muted, 400);
  panel(0, s, phase, pp, seg.d); panel(1, s, phase, pp, seg.d);
  scoreboard(0, s, phase, pp); scoreboard(1, s, phase, pp);
  if (seg.s >= 0 && phase === "intro") hook(s, pp);
  const cap = CAPTIONS[s.kind][phase]; const line = typeof cap === "function" ? cap(s) : cap;
  const fade = seg.s < 0 ? 0 : ease(p / 0.08);
  if (seg.s >= 0) { ctx.globalAlpha = 0.25 + 0.75 * fade; text(line, W / 2, 706, 25, C.text, 600); ctx.globalAlpha = 1; }
  if (seg.s < 0) {                                                                 // end card
    const a = ease(p / 0.25);
    ctx.fillStyle = `rgba(11,8,6,${0.92 * a})`; ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = a; text("Agloe", W / 2, 300, 96, C.amber, 800); text("trap streets for AI agent swarms", W / 2, 362, 34, C.text, 600);
    text("Read the past honestly, make the future traceable.", W / 2, 416, 22, C.muted, 400);
    text("Paper Towns · AI Swarm Dynamics Hackathon", W / 2, 470, 16, C.muted, 400); ctx.globalAlpha = 1;
  }
  $("scrub").value = Math.round((tl / TOTAL) * 1000); $("clock").textContent = `${Math.floor(tl)}s / ${Math.round(TOTAL)}s`;
}

// ---------------------------------------------------------------- the clock: timer-driven so it also runs in throttled or recorded tabs
function step() {
  const now = performance.now();
  if (playing) { tl = Math.min(TOTAL, tl + (now - lastNow) / 1000); if (tl >= TOTAL) { playing = false; $("play").textContent = "Replay"; } }
  lastNow = now; draw();
}
function setPlaying(on) {
  if (on && tl >= TOTAL - 0.05) tl = 0;
  playing = on; lastNow = performance.now(); $("play").textContent = on ? "Pause" : tl >= TOTAL ? "Replay" : "Play";
}
$("play").addEventListener("click", () => setPlaying(!playing));
$("scrub").addEventListener("input", (e) => { tl = (e.target.value / 1000) * TOTAL; setPlaying(false); draw(); });
addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
  if (e.code === "ArrowRight") { tl = Math.min(TOTAL, tl + 2); draw(); }
  if (e.code === "ArrowLeft") { tl = Math.max(0, tl - 2); draw(); }
});

// ---------------------------------------------------------------- Make a clip: plays the whole story once and downloads it as a video
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function makeClip() {
  if (!window.MediaRecorder || !cv.captureStream) { alert("This browser cannot record video from a canvas. Try Chrome or Edge."); return; }
  const btn = $("clip"), old = btn.textContent; btn.disabled = true; btn.textContent = "Recording…";
  const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const rec = new MediaRecorder(cv.captureStream(30), mime ? { mimeType: mime, videoBitsPerSecond: 6_000_000 } : undefined), chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  tl = 0; setPlaying(true); rec.start();
  while (tl < TOTAL) await sleep(100);
  await sleep(400); rec.stop(); await done;
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(chunks, { type: mime || "video/webm" })); a.download = "agloe-face-off.webm"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000); btn.disabled = false; btn.textContent = old;
}
$("clip").addEventListener("click", makeClip);

// ---------------------------------------------------------------- facts as text (the same numbers as the animation)
function facts() {
  const a = S[0], b = S[1], st = a.D.stats, box = $("facts"); box.replaceChildren();
  const add = (cls, lbl, num, hint) => { const d = document.createElement("div"); d.className = "stat " + cls; for (const [c, t] of [["lbl", lbl], ["num", num], ["hint", hint]]) { const e = document.createElement("span"); e.className = c; e.textContent = t; d.appendChild(e); } box.appendChild(d); };
  add("bad", "Run 1 · edit log alone", `${st.edit_log_correct} / ${st.copied}`, `sources named correctly (${pct(st.edit_log_correct / st.copied)}); the rest are wrong guesses`);
  add("good", "Run 1 · trap streets", `${st.tags_correct} / ${st.copied}`, `sources named correctly (${pct(st.tags_correct / st.copied)}); the code in the link names its copy`);
  add("bad", "Run 2 · no trace", String(b.afterTip.size), `outputs to re-check: everything submitted after the tip appeared (of ${b.agents})`);
  add("good", "Run 2 · follow the trace", String(b.traced.size), `outputs to re-check; found ${b.caught} of the ${b.reached.size} the tip reached`);
}

(async () => {
  C = { bg: css("--bg") || "#0b0806", text: css("--text"), muted: css("--muted"), amber: css("--amber"), ok: css("--ok"), bad: css("--bad"), line: css("--line") };
  const dpr = Math.min(2, devicePixelRatio || 1); cv.width = W * dpr; cv.height = H * dpr;
  S = await Promise.all(SCENES.map(async (sc) => prep(await (await fetch("data/" + sc.file)).json(), sc.kind)));
  buildTimeline(); facts();
  const q = new URLSearchParams(location.search), t = parseFloat(q.get("t"));
  if (!isNaN(t)) { tl = clamp(t, 0, TOTAL); playing = false; $("play").textContent = "Play"; }
  else if (reduce || q.get("autoplay") === "0") { tl = TOTAL * 0.43; $("play").textContent = "Play"; }          // reduced motion: a still frame of the verdict
  else setPlaying(true);
  window.__faceoff = { seek: (x) => { tl = clamp(x, 0, TOTAL); playing = false; draw(); }, total: () => TOTAL, timeline: () => timeline, state: () => ({ tl, playing }) };
  setInterval(step, 33); draw();
})();
