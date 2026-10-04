"""Swarm Traceability Report Card: point it at any agent swarm's logs, get an honest audit.

INPUT SCHEMA (JSON Lines, one event per line -- anything an agent wrote somewhere others could see):
    {"agent": "agent-7", "time": "2026-06-18T21:06:50Z", "channel": "wiki/StartPage", "content": "...text..."}
  agent    who wrote it                       (aliases: author, speaker, label, user)
  time     ISO-ish timestamp, sortable        (aliases: t, timestamp, created_at, ts)
  channel  where it was written / readable    (aliases: room, page, page_id, location, loc, thread)
  content  the text written (URLs, code, msg) (aliases: text, body, message, msg)
Use one channel for a single shared chat; use page/room ids when agents only see part of the swarm.

WHAT IT REPORTS
  1. Traceability  - of all cases where an agent repeats a distinctive string another agent wrote earlier, how
                     many have a prior writer VISIBLE in the same channel (carrier coverage), and the best possible
                     top-1 attribution accuracy given only these logs (uniform ceiling E[1/m]; 0 when no carrier).
  2. Copy or coincidence - naive "same string = copy" calls vs calls that survive calibration (distinctive token,
                     few users, not schema vocabulary). Everything else is what agents type independently.
  3. "Everyone types this" - the most widely shared strings: shared vocabulary / model focal values, i.e. the
                     strings a naive detector will mistake for collusion.
  4. Recommendation - what to log / tag so the next audit can do better.

This is the generic form of what the paper measured on collusion.wiki and AI Village (RESULTS.md sections B, G, K, L).
It reads logs only; it never fetches any URL found in them.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from backend.analysis.markers import _good, wilson
from backend.analysis.signatures import unquote_n

TOKEN = re.compile(r"[A-Za-z0-9_\-]{12,}")
SCRUB = ("[REDACTED]", "[BLOB_REMOVED]", "[IMAGE_REMOVED]")
MAX_AGENTS = 10          # a string used by more agents than this is shared vocabulary, not a lineage marker
ALIASES = {      # kept identical in frontend/card/card-core.js (parity-tested)
    "agent": ("agent", "author", "speaker", "label", "user", "agent_name", "sender", "actor", "name"),
    "time": ("time", "t", "timestamp", "created_at", "ts"),
    "channel": ("channel", "room", "page", "page_id", "location", "loc", "thread", "session", "session_id", "conversation", "conversation_id"),
    "content": ("content", "text", "body", "message", "msg"),
}

# ---------------------------------------------------------------- token classification (shared with the read-map verifier)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}")
_WAYBACK = re.compile(r"^(\d{14})id_?$")
_SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_CAMEL = re.compile(r"^[a-z]+(?:[A-Z][a-z0-9]*)+$")
VOCAB_CLASSES = {"snake-field", "camel-ident", "wayback-constructed"}
# kept identical in frontend/card/card-core.js (parity-tested)
REC_TAGS = ("Add version-unique, load-bearing tags (canary tokens) to shared artifacts. A decoration copiers can drop is "
            "dropped by some models; a token the link needs to work survives copying (see docs/CANARY.md).")


def shannon(s: str) -> float:
    n = len(s)
    if not n:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def classify_token(tok: str) -> tuple[str, str]:
    """(class, strength). high = cannot plausibly coincide (uuid, high-entropy minted id); low = vocabulary-like."""
    if _UUID.search(tok):
        return "uuid", "high"
    m = _WAYBACK.match(tok)
    if m:
        return ("wayback-constructed", "low") if m.group(1)[8:] == "000000" else ("wayback-capture", "medium")
    if _SNAKE.match(tok):
        return "snake-field", "low"
    if _CAMEL.match(tok):
        return "camel-ident", "low"
    if shannon(tok) >= 3.3 and len(tok) >= 12:
        return "high-entropy", "high"
    return "other", "low"


# ---------------------------------------------------------------- input
def _pick(d: dict, key: str):
    for a in ALIASES[key]:
        if d.get(a) not in (None, ""):
            return d[a]
    return None


def normalize(d: dict) -> dict | None:
    agent, time, content = _pick(d, "agent"), _pick(d, "time"), _pick(d, "content")
    if not agent or not time or content is None:
        return None
    e = {"agent": str(agent), "time": str(time), "channel": str(_pick(d, "channel") or "global"),
         "content": content if isinstance(content, str) else json.dumps(content)}
    for k in ("kind", "source"):             # optional: a read log ("kind": "read", "source": author of what was read) and a flag on bad outputs
        if d.get(k):
            e[k] = str(d[k])
    if d.get("flag"):
        e["flag"] = True
    return e


def load_events(path: str | Path) -> list[dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return parse_events(f.read())


def parse_events(text: str) -> list[dict]:
    """JSON Lines, or one JSON array of objects. Malformed lines and non-object items are skipped."""
    items: list = []
    if text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            items = []
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    out = [e for d in items if isinstance(d, dict) for e in [normalize(d)] if e]
    out.sort(key=lambda e: e["time"])
    return out


def tokens(content: str) -> set[str]:
    text = unquote_n(content, 3)
    for m in SCRUB:
        text = text.replace(m, " ")
    return {t for t in TOKEN.findall(text) if _good(t)}


# ---------------------------------------------------------------- the report
def grade(coverage: float) -> str:
    for g, lo in (("A", 0.9), ("B", 0.7), ("C", 0.5), ("D", 0.25)):
        if coverage >= lo:
            return g
    return "F"


def report_card(events: list[dict], max_agents: int = MAX_AGENTS) -> dict:
    events = [e for e in events if e.get("kind") != "read"]       # reads are evidence for the colony view; they are not things an agent wrote
    agents = sorted({e["agent"] for e in events})
    channels = sorted({e["channel"] for e in events})
    # every (token, agent) first use, and every channel where each agent wrote each token
    first: dict[str, dict[str, dict]] = defaultdict(dict)
    for e in events:
        for t in tokens(e["content"]):
            first[t].setdefault(e["agent"], {"time": e["time"], "channel": e["channel"]})
    writes_by_channel: dict[tuple, list] = defaultdict(list)   # (token, channel) -> [(time, agent)]
    for t, by in first.items():
        for a, r in by.items():
            writes_by_channel[(t, r["channel"])].append((r["time"], a))

    naive, supported, declined = [], [], []
    vocab = []
    for t, by in first.items():
        n = len(by)
        if n < 2:
            continue
        cls, strength = classify_token(t)
        if n > max_agents:
            vocab.append({"token": t, "agents": n, "class": cls})
        order = sorted(by.items(), key=lambda kv: kv[1]["time"])
        ok = n <= max_agents and cls not in VOCAB_CLASSES and (strength == "high" or n <= 3)
        for agent, r in order[1:]:
            earlier = {a for tm, a in writes_by_channel[(t, r["channel"])] if tm < r["time"] and a != agent}
            m = len(earlier)
            row = {"token": t, "class": cls, "adopter": agent, "channel": r["channel"],
                   "agents_using": n, "visible_carriers": m, "p_base": n / max(len(agents), 1)}
            naive.append(row)
            (supported if ok else declined).append(row)

    def trace(rows):
        k = sum(1 for r in rows if r["visible_carriers"] > 0)
        ceil = sum(1 / r["visible_carriers"] for r in rows if r["visible_carriers"] > 0) / len(rows) if rows else 0.0
        return k, ceil

    k_all, ceil_all = trace(naive)
    k_sup, ceil_sup = trace(supported)
    n_all, n_sup = len(naive), len(supported)
    # with no calibrated copy call there is nothing to score: never fall back to the naive matches (that would grade
    # coincidence as traceable)
    cov = k_sup / n_sup if n_sup else 0.0
    vocab.sort(key=lambda v: -v["agents"])
    shared = Counter()
    for t, by in first.items():
        if len(by) >= 3:
            shared[t] = len(by)
    rec = []
    if not n_sup:
        rec.append("No distinctive string is shared between agents (every repeated string is common vocabulary), so copying "
                   "cannot be traced from content at all. Shared artifacts need unique, load-bearing tags before an audit "
                   "can say anything.")
    if n_sup and cov < 0.5:
        rec.append(f"{1 - cov:.0%} of real copies have no visible source in the channel where they reappear: agents read from "
                   "places you do not log. Log item-level reads (who read which page/message, when).")
    if n_all and (n_all - n_sup) / n_all > 0.5:
        rec.append(f"{(n_all - n_sup) / n_all:.0%} of naive 'same string' matches are shared vocabulary or common values. "
                   "Do not treat a shared value as copying without its base rate.")
    rec.append(REC_TAGS)
    return {
        "events": len(events), "agents": len(agents), "channels": len(channels),
        "distinct_shared_strings": sum(1 for by in first.values() if len(by) >= 2),
        "naive_copy_calls": n_all,
        "calibrated_copy_calls": n_sup,
        "declined_as_coincidence": len(declined),
        "carrier_coverage": round(cov, 3),
        "carrier_coverage_ci95": [round(x, 3) for x in wilson(k_sup, n_sup)],
        "best_possible_top1": round(ceil_sup, 3),
        "naive_coverage": round(k_all / n_all, 3) if n_all else 0.0,
        "grade": grade(cov) if n_sup else "N/A",
        "single_channel": len(channels) == 1,
        # a string typed by more than max_agents agents is shared vocabulary whatever its shape (e.g. a dataset field name)
        # ties ordered by name: set iteration order (hash-randomized) must not leak into the output
        "everyone_types_this": [{"string": t[:40], "agents": c,
                                 "class": "shared-vocabulary" if c > max_agents else classify_token(t)[0]}
                                for t, c in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))[:10]],
        "recommendations": rec,
        "_supported": supported, "_declined": declined,
    }


def render(card: dict, title: str = "Swarm") -> str:
    L = []
    L.append("=" * 72)
    L.append(f" AGLOE TRACEABILITY REPORT CARD  -  {title}")
    L.append("=" * 72)
    L.append(f" {card['events']:,} events  |  {card['agents']:,} agents  |  {card['channels']:,} channels")
    L.append("")
    if card["grade"] == "N/A":
        L.append(" TRACEABILITY GRADE: N/A  (no distinctive shared strings: nothing to trace from content)")
    else:
        L.append(f" TRACEABILITY GRADE: {card['grade']}")
        L.append(f"   carrier coverage      {card['carrier_coverage']:.0%}  (CI {card['carrier_coverage_ci95'][0]:.0%}-"
                 f"{card['carrier_coverage_ci95'][1]:.0%})  real copies whose source is visible where they reappear")
        L.append(f"   best possible top-1   {card['best_possible_top1']:.0%}  even a perfect tracer can name the source this often")
        if card["single_channel"]:
            L.append("   (single shared channel: every earlier write is visible, so coverage is an upper bound)")
    L.append("")
    L.append(" COPY OR COINCIDENCE")
    L.append(f"   naive 'same string = copy' calls   {card['naive_copy_calls']:,}")
    L.append(f"   survive calibration                {card['calibrated_copy_calls']:,}")
    L.append(f"   declined as coincidence/vocabulary {card['declined_as_coincidence']:,}")
    L.append("")
    L.append(" EVERYONE TYPES THIS  (strings a naive detector will mistake for collusion)")
    for v in card["everyone_types_this"][:8]:
        L.append(f"   {v['agents']:4d} agents  {v['string']:40s} [{v['class']}]")
    L.append("")
    L.append(" RECOMMENDATIONS")
    for r in card["recommendations"]:
        L.append(f"   - {r}")
    L.append("=" * 72)
    return "\n".join(L)


# ---------------------------------------------------------------- built-in converters (worked examples of the schema)
def events_from_collusion(raw_dir: Path) -> list[dict]:
    """collusion.wiki export -> events: one per revision, content = URLs that revision added, channel = page."""
    from backend.adapters.german_wiki import added_urls, load_revisions
    per = defaultdict(list)
    for r in added_urls(load_revisions(raw_dir)):
        if r["label"] and not r["generated_page"]:
            per[(r["rev_id"], r["label"], r["time"], r["page_id"])].append(r["url"])
    ev = [{"agent": a, "time": t, "channel": p, "content": " ".join(us)} for (_rev, a, t, p), us in per.items()]
    return sorted(ev, key=lambda e: e["time"])


def events_from_ai_village(raw_dir: Path, lo: str, hi: str) -> list[dict]:
    """AI Village chat in [lo, hi] -> events; channel = chat room (one global room before Rooms v1, 2026-02-25)."""
    from backend.adapters.ai_village import load_chat
    return [{"agent": r["agent"], "time": r["t"], "channel": r["room"] or "global", "content": r["content"]}
            for r in load_chat(Path(raw_dir), lo, hi)]


def events_from_lab(world, with_reads: bool = False) -> list[dict]:
    """A lab world.json (dict or path) -> the investigator's view: wiki writes + submissions.

    Every wiki page is readable by every agent, so the whole wiki is one channel; submissions are placed in it too, so
    a submitted link can be matched to the earlier posts it may have come from.

    with_reads=True is the colony view: the same writes and submissions on their own channels (each wiki page, and a
    "submit" desk), plus the lab's HIDDEN read log as `kind: read` events (content = the exact copy served, `source` = the
    author of the chunk it came from), and a `flag` on outputs that carry the stale value. No real investigator has the reads."""
    if not isinstance(world, dict):
        world = json.loads(Path(world).read_text(encoding="utf-8"))
    if not with_reads:
        ev = [{"agent": w["author"], "time": f"{w['t']:09d}", "channel": "wiki", "content": w["text"]} for w in world["writes"]]
        ev += [{"agent": s["agent"], "time": f"{s['t']:09d}", "channel": "wiki",
                "content": " ".join(s.get("urls") or [])} for s in world["submissions"]]
        return sorted(ev, key=lambda e: e["time"])
    from experiments.mini_swarm.world import STALE
    ev = [{"agent": w["author"], "time": f"{w['t']:09d}", "channel": w["page"], "kind": "write", "content": w["text"]} for w in world["writes"]]
    for s in world["submissions"]:
        e = {"agent": s["agent"], "time": f"{s['t']:09d}", "channel": "submit", "kind": "submit", "content": " ".join(s.get("urls") or [])}
        if s.get("answer") == STALE:
            e["flag"] = True
        ev.append(e)
    for r in world.get("reads", []):
        for u in r["urls"]:
            ev.append({"agent": r["reader"], "time": f"{r['t']:09d}", "channel": r["page"], "kind": "read", "source": u["author"], "content": u["served"]})
    return sorted(ev, key=lambda e: (e["time"], e.get("kind") != "read"))        # at the same instant a read comes first


def public(card: dict) -> dict:
    """The card without per-row detail (safe to share: aggregates only)."""
    return {k: v for k, v in card.items() if not k.startswith("_")}