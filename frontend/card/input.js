// Shared log input for the report card and the colony page: JSON Lines, a JSON array, or CSV; guessing which fields are agent / time / channel /
// content when the names differ; and a row-order fallback for logs without timestamps. No DOM here, and nothing leaves the browser.
import { normalize } from "./card-core.js";

export const ROW = "\u0000row", ONE = "\u0000one";               // sentinels: "use row order as time", "one shared channel"

export async function readFileText(file) {
  if (/\.gz$/i.test(file.name)) {
    if (!("DecompressionStream" in window)) throw new Error("This browser cannot open .gz files; gunzip the log first.");
    return await new Response(file.stream().pipeThrough(new DecompressionStream("gzip"))).text();
  }
  return await file.text();
}

export function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
    else if (c !== "\r") cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.some((x) => x !== ""));
  return head ? body.map((r) => Object.fromEntries(head.map((h, i) => [h.trim(), r[i] ?? ""]))) : [];
}

export function rawObjects(text, name) {
  if (/\.csv$/i.test(name)) return parseCsv(text);
  let items = [];
  if (text.trimStart().startsWith("[")) { try { items = JSON.parse(text); } catch { items = []; } }
  else {
    for (const line of text.split("\n")) { const s = line.trim(); if (!s) continue; try { items.push(JSON.parse(s)); } catch { /* skip */ } }
    if (!items.length && text.split("\n", 1)[0].includes(",")) return parseCsv(text);       // a CSV saved without the extension
  }
  return (Array.isArray(items) ? items : []).filter((d) => d && typeof d === "object" && !Array.isArray(d));
}

export function flatten(d, prefix = "", depth = 0, out = {}) {
  for (const [k, v] of Object.entries(d)) {
    if (v && typeof v === "object" && !Array.isArray(v) && depth < 2) flatten(v, `${prefix}${k}.`, depth + 1, out);
    else out[prefix + k] = v;
  }
  return out;
}

const GUESS = { agent: /agent|author|sender|speaker|actor|user|role|name/i, time: /time|date|(^|_)ts$|created|(^|_)at$/i,
  channel: /channel|room|page|thread|session|conversation|topic/i, content: /content|text|body|message|msg|output|result|post/i };
const sortTime = (v) => (/^\d+(\.\d+)?$/.test(String(v)) ? Number(v).toFixed(3).padStart(24, "0") : String(v));   // numeric epochs sort as numbers

// Best guess of the four fields from the keys of the flattened rows: { keys, agent, time, channel, content }.
export function guessMapping(flats) {
  const freq = new Map();
  for (const f of flats.slice(0, 2000)) for (const k of Object.keys(f)) freq.set(k, (freq.get(k) || 0) + 1);
  const keys = [...freq.keys()].sort((a, b) => freq.get(b) - freq.get(a));
  const avgLen = (k) => { let n = 0, s = 0; for (const f of flats.slice(0, 200)) if (typeof f[k] === "string") { n++; s += f[k].length; } return n ? s / n : 0; };
  const leaf = (k) => k.split(".").pop();
  const agent = keys.find((k) => GUESS.agent.test(leaf(k))) ?? keys[0];
  const time = keys.find((k) => k !== agent && GUESS.time.test(leaf(k)));
  const channel = keys.find((k) => ![agent, time].includes(k) && GUESS.channel.test(leaf(k)));
  const rest = keys.filter((k) => ![agent, time, channel].includes(k)).sort((a, b) => avgLen(b) - avgLen(a));          // longest text first
  const content = rest.find((k) => GUESS.content.test(leaf(k))) ?? rest[0] ?? keys[0];
  return { keys, agent, time: time ?? ROW, channel: channel ?? ONE, content };
}

// Rows -> sorted events, for a chosen mapping { agent, time, channel, content } (keys of the flattened rows, or the ROW / ONE sentinels).
export function buildMapped(flats, m) {
  const out = [];
  flats.forEach((d, i) => {
    const e = normalize({ agent: d[m.agent], time: m.time === ROW ? String(i).padStart(12, "0") : sortTime(d[m.time]),
      channel: m.channel === ONE ? "global" : d[m.channel], content: d[m.content] });
    if (e) out.push(e);
  });
  return out.sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}
