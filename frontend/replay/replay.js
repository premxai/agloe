// Agloe Swarm Replay: an arc diagram of one lab swarm, seen three ways. Static; data from scripts/export_lab_replay.py.
const $ = (id) => document.getElementById(id);
const cv = $("c"), ctx = cv.getContext("2d");
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const pct = (x) => (x == null || isNaN(x) ? "–" : `${Math.round(x * 100)}%`);

let D = null, view = "truth", sel = null, T = 1, playing = false, last = 0, hit = [];
const ORDER = []; let pos = new Map(), truthMap = new Map();

async function load(file) {
  D = await (await fetch("data/" + file)).json();
  const nodes = [...D.nodes];
  if (D.rumor && !nodes.some((n) => n.id === D.rumor.id)) nodes.push({ id: D.rumor.id, t: D.rumor.t, rumor: true, answer: null });
  nodes.sort((a, b) => a.t - b.t);
  ORDER.length = 0; ORDER.push(...nodes);
  truthMap = new Map(D.edges.truth);
  sel = null; T = 1; $("scrub").value = 1000; setView(view); resize();
}

function edges(v) {
  const list = D.edges[v] || [];
  return list.map(([c, p]) => {
    const correct = truthMap.get(c) === p;
    const independent = !truthMap.has(c);
    return { c, p, kind: v === "truth" ? "ok" : correct ? "ok" : independent ? "ghost" : "bad" };
  });
}

function stats(v) {
  const s = D.stats, n = s.copied;
  if (v === "truth") return [["Agents", s.agents, `${n} copied a teammate's link, ${s.independent} found it alone`],
    ["Copied from a teammate", pct(n / s.agents), "the hidden read log says who"],
    ["Stale outputs", s.stale_outputs, D.rumor ? "agents that adopted the planted bad tip" : "no bad tip in this swarm"]];
  if (v === "edit_log") return [["Sources named correctly", `${s.edit_log_correct} / ${n}`, `${pct(s.edit_log_correct / n)} of copies traced from the edit log alone`],
    ["False accusations", s.edit_log_false_accusations, "agents that worked alone but are blamed on someone"],
    ["Wrong sources", s.edit_log_accusations - s.edit_log_correct - s.edit_log_false_accusations, "copies pinned on the wrong teammate"]];
  return [["Sources named correctly", `${s.tags_correct} / ${n}`, `${pct(s.tags_correct / n)} traced exactly with canary tags`],
    ["Tags that survived copying", `${s.tags_kept} / ${n}`, "the tag rides inside the link the agent needs"],
    ["False accusations", 0, "no tag means no accusation"]];
}

const explain = (v) => ({
  truth: "This is what really happened. In real swarms nobody has this: reads are rarely logged, so the arcs have to be inferred.",
  edit_log: `Without reads, an investigator can only blame a teammate who wrote the same link. Here the rule is “blame the ${D.heuristic} one”, the better of the two simple rules for this swarm. Red arcs are wrong; dashed arcs blame agents that never copied anyone.`,
  tags: "Each page view is served with its own load-bearing token inside the link. An agent that copies the link carries the token, so the arc is exact. No guessing.",
}[v]);

function setView(v) {
  view = v;
  for (const b of document.querySelectorAll("[data-view]")) b.setAttribute("aria-selected", String(b.dataset.view === v));
  const st = stats(v);
  ["1", "2", "3"].forEach((k, i) => { $("s" + k + "l").textContent = st[i][0]; $("s" + k).textContent = st[i][1]; $("s" + k + "h").textContent = st[i][2]; });
  $("explain").textContent = explain(v);
  draw();
}

function resize() {
  const r = cv.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

// hops from the origin in a view: follow that view's parent links (cycle-safe)
function depths(v) {
  const m = new Map((D.edges[v] || []).map(([c, p]) => [c, p])), out = new Map();
  for (const a of ORDER) { let d = 0, cur = a.id; const seen = new Set(); while (m.has(cur) && !seen.has(cur)) { seen.add(cur); cur = m.get(cur); d++; } out.set(a.id, d); }
  return out;
}
let maxDepth = 1;
function layout(W, H) {
  const m = 30, n = ORDER.length, dep = depths(view);
  maxDepth = Math.max(1, ...["truth", "edit_log", "tags"].map((v) => Math.max(...depths(v).values())));   // same height scale in every view
  const dy = Math.min(48, (H - 70) / (maxDepth + 0.4)), base = H - 28;
  pos = new Map(ORDER.map((a, i) => [a.id, { x: m + (n > 1 ? (i / (n - 1)) * (W - 2 * m) : 0), y: base - dep.get(a.id) * dy, i, d: dep.get(a.id), base, dy }]));
}

function chain(v, id) {
  const m = new Map((D.edges[v] || []).map(([c, p]) => [c, p])), out = [id], seen = new Set([id]);
  while (m.has(out[out.length - 1]) && !seen.has(m.get(out[out.length - 1]))) { const nx = m.get(out[out.length - 1]); out.push(nx); seen.add(nx); }
  return out;
}

function draw() {
  if (!D) return;
  const W = cv.clientWidth, H = cv.clientHeight;
  ctx.clearRect(0, 0, W, H);
  layout(W, H);
  const cur = Math.round(T * (ORDER.length - 1));
  const ch = sel ? new Set(chain(view, sel)) : null;
  const colors = { ok: css("--ok"), bad: css("--bad"), ghost: css("--bad") };       // green = correct source, red = wrong
  // arcs
  const arcs = edges(view).filter((e) => pos.has(e.c) && pos.has(e.p) && pos.get(e.c).i <= cur && pos.get(e.p).i <= cur);
  // depth guides: one hairline per hop level, so the height of the cascade can be read off
  const any = pos.values().next().value;
  if (any) {
    ctx.font = "11px " + css("--mono"); ctx.textBaseline = "middle";
    for (let k = 0; k <= maxDepth; k++) {
      const y = any.base - k * any.dy;
      ctx.strokeStyle = css("--line"); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(34, y); ctx.lineTo(W - 12, y); ctx.stroke();
      if (k % 2 === 0 || maxDepth < 6) { ctx.fillStyle = css("--muted"); ctx.textAlign = "left"; ctx.fillText(String(k), 8, y); }
    }
    ctx.fillStyle = css("--muted"); ctx.textAlign = "right"; ctx.fillText("hops from the origin ↑", W - 14, 12);
  }
  for (const e of arcs) {
    const a = pos.get(e.p), b = pos.get(e.c), bow = Math.min(36, Math.abs(b.x - a.x) * 0.1);
    const on = !ch || (ch.has(e.c) && ch.has(e.p));
    ctx.globalAlpha = on ? 0.85 : 0.1; ctx.lineWidth = ch && on ? 2.6 : 1.3;
    ctx.strokeStyle = colors[e.kind]; ctx.setLineDash(e.kind === "ghost" ? [4, 4] : []);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo((a.x + b.x) / 2, (a.y + b.y) / 2 - bow, b.x, b.y); ctx.stroke();
  }
  ctx.setLineDash([]); ctx.globalAlpha = 1;
  hit = [];
  for (const a of ORDER) {
    const p = pos.get(a.id); if (p.i > cur) continue;
    const dim = ch && !ch.has(a.id), r = a.rumor ? 8 : 6.5;
    ctx.globalAlpha = dim ? 0.25 : 1;
    if (a.rumor) { ctx.fillStyle = css("--stale"); ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(Math.PI / 4); ctx.fillRect(-r * .8, -r * .8, r * 1.6, r * 1.6); ctx.restore(); }
    else {
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 7);
      if (a.stale) { ctx.fillStyle = css("--stale"); ctx.fill(); }
      else if (a.copied) { ctx.fillStyle = css("--text"); ctx.fill(); }
      else { ctx.strokeStyle = css("--text"); ctx.lineWidth = 2; ctx.stroke(); }
    }
    if (a.id === sel) { ctx.strokeStyle = css("--amber"); ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(p.x, p.y, r + 5, 0, 7); ctx.stroke(); }
    hit.push({ id: a.id, x: p.x, y: p.y, r: r + 6 });
  }
  ctx.globalAlpha = 1;
  const t = ORDER[cur]; $("clock").textContent = t ? `${cur + 1} / ${ORDER.length}` : "";
  if (clip.on) drawClipOverlay(W, H);
}

// ---------------------------------------------------------------- clip: record the three views with captions
const clip = { on: false, cap: "", sub: "", end: false };
function drawClipOverlay(W, H) {
  ctx.save();
  if (clip.end) {
    ctx.fillStyle = "rgba(11,8,6,.92)"; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = css("--amber"); ctx.font = `700 ${Math.max(22, W * 0.05)}px ${css("--sans")}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("Agloe", W / 2, H * 0.36);
    ctx.fillStyle = css("--text"); ctx.font = `600 ${Math.max(15, W * 0.024)}px ${css("--sans")}`;
    ctx.fillText("trap streets for AI agent swarms", W / 2, H * 0.5);
    ctx.fillStyle = css("--muted"); ctx.font = `${Math.max(12, W * 0.018)}px ${css("--sans")}`;
    ctx.fillText("Read the past honestly, make the future traceable.", W / 2, H * 0.62);
  } else {
    const pad = 14, fs = Math.max(16, W * 0.026);
    ctx.font = `700 ${fs}px ${css("--sans")}`; const w1 = ctx.measureText(clip.cap).width;
    ctx.fillStyle = "rgba(11,8,6,.82)"; ctx.fillRect(pad - 8, pad - 6, Math.max(w1, 220) + 24, clip.sub ? fs * 2.6 : fs * 1.7);
    ctx.fillStyle = css("--amber"); ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillText(clip.cap, pad + 4, pad);
    if (clip.sub) { ctx.fillStyle = css("--text"); ctx.font = `${fs * 0.72}px ${css("--sans")}`; ctx.fillText(clip.sub, pad + 4, pad + fs * 1.25); }
  }
  ctx.restore();
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function makeClip() {
  if (!window.MediaRecorder || !cv.captureStream) { alert("This browser cannot record video from a canvas. Try Chrome or Edge."); return; }
  const btn = $("clip"), old = btn.textContent; btn.disabled = true; btn.textContent = "Recording…";
  const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const rec = new MediaRecorder(cv.captureStream(30), mime ? { mimeType: mime, videoBitsPerSecond: 4_000_000 } : undefined), chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  const s = D.stats, n = s.copied;
  const steps = [
    { view: "truth", cap: "What really happened", sub: `${s.agents} AI agents${D.rumor ? ", one planted bad tip" : ""}: ${s.stale_outputs ? `${s.stale_outputs} adopt it` : "they share working links"}`, ms: 7000, play: true },
    { view: "edit_log", cap: "What the edit log says", sub: `${s.edit_log_correct} of ${n} sources named correctly`, ms: 5000 },
    { view: "tags", cap: "With canary tags", sub: `${s.tags_correct} of ${n} sources named correctly`, ms: 5000 },
  ];
  const keepView = view, keepT = T; sel = null; clip.on = true; rec.start();
  const frame = setInterval(draw, 33);                       // timer-driven so recording works even when the tab is throttled
  for (const st of steps) {
    clip.cap = st.cap; clip.sub = st.sub; setView(st.view);
    if (st.play) { const t0 = performance.now(); T = 0; while (performance.now() - t0 < st.ms) { T = Math.min(1, (performance.now() - t0) / (st.ms * 0.8)); await sleep(33); } T = 1; }
    else { T = 1; await sleep(st.ms); }
  }
  clip.end = true; await sleep(2200);
  clearInterval(frame); rec.stop(); await done; clip.on = false; clip.end = false; setView(keepView); T = keepT; draw();
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(chunks, { type: mime || "video/webm" })); a.download = "agloe-swarm-replay.webm"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000); btn.disabled = false; btn.textContent = old;
}
$("clip").addEventListener("click", makeClip);

function tipFor(a) {
  const n = ORDER.find((x) => x.id === a);
  if (!n) return "";
  if (n.rumor) return `${n.id}: the planted bad tip (a link to a stale mirror)`;
  const tp = truthMap.get(n.id), g = (D.edges.edit_log.find(([c]) => c === n.id) || [])[1], tg = (D.edges.tags.find(([c]) => c === n.id) || [])[1];
  const chainTxt = chain(view, a).join(" → ");
  return `${n.id} (${n.family}) answered ${n.answer ?? "–"}${n.stale ? " (stale)" : ""}\n` +
    `truth: ${tp ? "copied " + tp : "worked alone"} · edit log blames: ${g ?? "nobody"} · tag says: ${tg ?? "no tag"}\n` +
    `chain (${view.replace("_", " ")}): ${chainTxt}`;
}

cv.addEventListener("click", (e) => {
  const r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  const h = hit.find((q) => Math.hypot(q.x - x, q.y - y) <= q.r);
  sel = h ? (h.id === sel ? null : h.id) : null;
  const tip = $("tip"); tip.hidden = !sel; if (sel) { tip.textContent = tipFor(sel); tip.style.whiteSpace = "pre-wrap"; }
  draw();
});
for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => { setView(b.dataset.view); if (sel) $("tip").textContent = tipFor(sel); });
$("scrub").addEventListener("input", (e) => { T = e.target.value / 1000; playing = false; $("play").textContent = "Play"; draw(); });
$("play").addEventListener("click", () => {
  if (reduce) { T = 1; $("scrub").value = 1000; draw(); return; }
  playing = !playing; $("play").textContent = playing ? "Pause" : "Play";
  if (playing) { if (T >= 1) T = 0; last = performance.now(); requestAnimationFrame(tick); }
});
function tick(now) {
  if (!playing) return;
  T = Math.min(1, T + (now - last) / 9000); last = now; $("scrub").value = Math.round(T * 1000); draw();
  if (T >= 1) { playing = false; $("play").textContent = "Play"; return; }
  requestAnimationFrame(tick);
}
$("pick").addEventListener("change", (e) => load(e.target.value));
addEventListener("resize", resize);

(async () => {
  const idx = await (await fetch("data/index.json")).json();
  $("pick").replaceChildren(...idx.map((i) => Object.assign(document.createElement("option"), { value: i.file, textContent: i.title })));
  const want = new URLSearchParams(location.search).get("swarm");
  if (want && idx.some((i) => i.file === want)) $("pick").value = want;
  await load($("pick").value);
})();
