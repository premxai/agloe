"""AI Village (aidigestorg/ai-village) -> propagation records for the Agloe audit.

The AI Village is the *opposite* data regime from collusion.wiki: agents pass tips through a shared,
fully-logged chat channel, so when one agent repeats a distinctive string another posted earlier, the
carrier is almost always visible in the log. This adapter measures that -- content-agnostically.

A "marker" here is a rare, distinctive token (an invented identifier, a specific path/flag, a payload
fragment) that shows up in >=2 and <=MAX_AGENTS agents' chat messages. We never inspect what the token
*means*; we only record who used it first and whether a prior cross-agent use was visible to each later
adopter. Token text is never emitted -- only a short salted hash, for joining rows across runs.

Visibility model (from CHANGELOG):
  * before 2026-02-25 ("Rooms v1") every agent saw all chat -> a prior post by anyone is visible;
  * from 2026-02-25 chat is room-scoped -> a prior post is visible only if the adopter was in that room.
To keep the headline defensible, `summary(..., require_rooms=False)` uses a pre-rooms window where
visibility = "any earlier post", and the room-scoped path is used only when a window crosses the cutover.

Terms: research use only; no raw content is written out, only aggregates and hashed token ids.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from backend.analysis.markers import _good, wilson

ROOMS_CUTOVER = "2026-02-25"          # Rooms v1: chat becomes room-scoped
SCRUB = ("[REDACTED]", "[BLOB_REMOVED]", "[IMAGE_REMOVED]")
TOKEN = re.compile(r"[A-Za-z0-9_\-/.]{12,}")
MAX_AGENTS = 10                       # a token used by more agents than this is boilerplate, not lineage
_SALT = "agloe-av"                    # only to make hashed ids non-reversible in published output


def _fam(model_string: str) -> str:
    """Coarse provider family from the model string (for homophily / cross-model tests)."""
    s = (model_string or "").lower()
    s = s.split("::", 1)[-1]          # strip claude-code:: scaffolding prefix
    if s.startswith("claude") or "anthropic" in s:
        return "anthropic"
    if s.startswith(("gpt", "o1", "o3", "o4")) or "openai" in s:
        return "openai"
    if s.startswith("gemini") or "google" in s:
        return "google"
    if s.startswith("grok"):
        return "xai"
    if s.startswith("deepseek") or "deepseek" in s:
        return "deepseek"
    if s.startswith(("kimi", "z-ai", "glm", "moonshot")):
        return "other-oss"
    if s.startswith(("meta/", "muse")) or "llama" in s:
        return "meta"
    if s.startswith("tinker"):
        return "finetune"
    return "other"


def tok_id(t: str) -> str:
    return hashlib.sha1((_SALT + t.lower()).encode()).hexdigest()[:10]


def load_jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def load_agents(raw_dir: Path) -> dict:
    """agent_id -> {name, model_string, family}."""
    out = {}
    for r in load_jsonl_gz(Path(raw_dir) / "agents.jsonl.gz"):
        out[r["id"]] = {"name": r["name"], "model_string": r.get("model_string") or "",
                        "family": _fam(r.get("model_string") or "")}
    return out


def load_chat(raw_dir: Path, lo: str, hi: str, agents: dict | None = None) -> list[dict]:
    """Agent chat messages with created_at date in [lo, hi] (YYYY-MM-DD), sorted by time.

    User/human messages are dropped (not part of agent-to-agent propagation)."""
    agents = agents or load_agents(raw_dir)
    rows = []
    for r in load_jsonl_gz(Path(raw_dir) / "chat_messages.jsonl.gz"):
        if r.get("speaker_type") != "agent":
            continue
        d = r["created_at"][:10]
        if not (lo <= d <= hi):
            continue
        a = agents.get(r.get("agent_speaker_id"))
        if not a:
            continue
        rows.append({"id": r["id"], "agent": a["name"], "agent_id": r["agent_speaker_id"],
                     "family": a["family"], "room": r.get("room_id"), "t": r["created_at"],
                     "content": r.get("content") or ""})
    rows.sort(key=lambda r: (r["t"], r["id"]))
    return rows


def _mask_scrub(s: str) -> str:
    for m in SCRUB:
        s = s.replace(m, " ")
    return s


def message_tokens(content: str) -> set[str]:
    """Distinctive tokens in a chat message (scrub markers removed, boilerplate filtered)."""
    text = _mask_scrub(content)
    out = set()
    for t in TOKEN.findall(text):
        t = t.strip("/.-")
        if len(t) < 12:
            continue
        # reuse the collusion.wiki distinctiveness test (skips hex/digits/dictionary/base64-json/common headers)
        core = t.replace("/", "_").replace(".", "_")
        if _good(core):
            out.add(t)
    return out


def first_uses(chat: list[dict]) -> dict:
    """token -> {agent -> first record} (first time each agent used the token)."""
    first: dict[str, dict] = defaultdict(dict)
    for r in chat:
        for t in message_tokens(r["content"]):
            first[t].setdefault(r["agent"], {"agent": r["agent"], "family": r["family"],
                                             "t": r["t"], "room": r["room"], "msg": r["id"]})
    return first


def spread_records(chat: list[dict], rooms: bool) -> list[dict]:
    """One record per (token, later-adopter): was a prior cross-agent use visible?

    rooms=False  -> pre-cutover: any earlier post by another agent is visible.
    rooms=True   -> an earlier post is visible only if the adopter also posted in that room in the window
                    (a conservative proxy for room membership from chat alone).
    """
    # which rooms each agent posted in (proxy for room visibility when rooms=True)
    agent_rooms: dict[str, set] = defaultdict(set)
    if rooms:
        for r in chat:
            agent_rooms[r["agent"]].add(r["room"])
    first = first_uses(chat)
    recs = []
    for tok, by_agent in first.items():
        if not (2 <= len(by_agent) <= MAX_AGENTS):
            continue
        order = sorted(by_agent.values(), key=lambda x: x["t"])
        src = order[0]
        for cp in order[1:]:
            earlier = [w for w in order if w["t"] < cp["t"] and w["agent"] != cp["agent"]]
            if rooms:
                visible = [w for w in earlier if w["room"] in agent_rooms[cp["agent"]]]
            else:
                visible = earlier
            lag = None
            if visible:
                last = max(visible, key=lambda w: w["t"])
                lag = _lag_seconds(last["t"], cp["t"])
            recs.append({
                "token_id": tok_id(tok), "adopter": cp["agent"], "adopter_family": cp["family"],
                "source": src["agent"], "source_family": src["family"],
                "visible_carrier": bool(visible), "n_visible": len(visible),
                "same_family_source": cp["family"] == src["family"],
                "lag_s": lag,
            })
    return recs


def _lag_seconds(t0: str, t1: str) -> float:
    import datetime as dt
    f = "%Y-%m-%d %H:%M:%S.%f"
    try:
        return (dt.datetime.strptime(t1[:26], f) - dt.datetime.strptime(t0[:26], f)).total_seconds()
    except ValueError:
        return float("nan")


def coincidence_test(chat: list[dict], short_s: float = 120.0, seed: int = 0, iters: int = 2000) -> dict:
    """Do same-model agents independently emit the same distinctive token more than chance?

    We take unordered agent pairs that first-use the same distinctive token within `short_s` seconds of
    each other -- too close for a deliberate read-then-post, so plausibly independent convergence. The null
    shuffles each agent's family label among the agents active in the window (fixing family sizes) and
    recomputes the same-family share of those near-simultaneous pairs. Observed >> null => coincidence
    clusters within model family, so naive string-matching would over-link same-model agents.
    """
    import random

    first = first_uses(chat)
    agents_active = sorted({r["agent"] for r in chat})
    fam_of = {}
    for r in chat:
        fam_of.setdefault(r["agent"], r["family"])
    pairs = []                                   # (agent_a, agent_b) near-simultaneous co-emitters
    for tok, by_agent in first.items():
        if not (2 <= len(by_agent) <= MAX_AGENTS):
            continue
        us = sorted(by_agent.values(), key=lambda x: x["t"])
        for i in range(len(us)):
            for j in range(i + 1, len(us)):
                lag = _lag_seconds(us[i]["t"], us[j]["t"])
                if lag == lag and lag <= short_s:
                    pairs.append((us[i]["agent"], us[j]["agent"]))
    n = len(pairs)
    if not n:
        return {"near_simultaneous_pairs": 0}
    obs = sum(fam_of[a] == fam_of[b] for a, b in pairs) / n
    rng = random.Random(seed)
    null = []
    fams = [fam_of[a] for a in agents_active]
    for _ in range(iters):
        shuf = fams[:]
        rng.shuffle(shuf)
        m = dict(zip(agents_active, shuf))
        null.append(sum(m[a] == m[b] for a, b in pairs) / n)
    null.sort()
    exp = sum(null) / len(null)
    ge = sum(1 for x in null if x >= obs)
    return {
        "near_simultaneous_pairs": n, "short_s": short_s,
        "observed_same_family": round(obs, 3),
        "null_same_family_mean": round(exp, 3),
        "null_ci95": [round(null[int(0.025 * iters)], 3), round(null[int(0.975 * iters)], 3)],
        "enrichment": round(obs / exp, 2) if exp else None,
        "p_value": round((ge + 1) / (iters + 1), 4),
    }


def summary(raw_dir: Path, lo: str, hi: str, require_rooms: bool | None = None) -> dict:
    """Aggregate propagation result for a window. No token or message text in the output."""
    agents = load_agents(raw_dir)
    chat = load_chat(raw_dir, lo, hi, agents)
    rooms = (lo >= ROOMS_CUTOVER) if require_rooms is None else require_rooms
    recs = spread_records(chat, rooms=rooms)
    n = len(recs)
    att = sum(r["visible_carrier"] for r in recs)
    fams = sorted({r["adopter_family"] for r in recs})
    by_family = {}
    for fam in fams:
        rs = [r for r in recs if r["adopter_family"] == fam]
        k = sum(r["visible_carrier"] for r in rs)
        by_family[fam] = {"adoptions": len(rs), "attributable": k,
                          "rate": round(k / len(rs), 3) if rs else 0.0}
    same = [r for r in recs if r["visible_carrier"] and r["same_family_source"]]
    lags = sorted(r["lag_s"] for r in recs if r["visible_carrier"] and r["lag_s"] == r["lag_s"])
    med = lags[len(lags) // 2] if lags else None
    return {
        "window": [lo, hi], "rooms_scoped": rooms,
        "agents_in_window": len({r["agent"] for r in chat}),
        "messages": len(chat),
        "distinct_markers": len({r["token_id"] for r in recs}),
        "cross_agent_adoptions": n,
        "attributable": att,
        "attributable_rate": round(att / n, 3) if n else 0.0,
        "attributable_ci95": [round(x, 3) for x in wilson(att, n)],
        "same_family_share_of_attributable": round(len(same) / att, 3) if att else 0.0,
        "median_lag_s_when_visible": med,
        "by_adopter_family": by_family,
        "coincidence": coincidence_test(chat),
    }
