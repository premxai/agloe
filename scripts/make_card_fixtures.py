"""Fixtures + expected output for the browser card's parity test (frontend/card/parity.test.mjs).

Python's report card is the reference; the JS port must give the same numbers on the same events.
  frontend/card/fixtures/   synthetic swarm + two lab cells (ours, safe to publish)
  data/out/card_fixtures/   samples of the real datasets (local only, gitignored: collusion.wiki is marked 'do not share')

Usage: python -m scripts.make_card_fixtures
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from backend.analysis import report as R

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "card" / "fixtures"
LOCAL = ROOT / "data" / "out" / "card_fixtures"


def synthetic() -> list[dict]:
    """A small swarm that exercises every branch: copied UUIDs across channels, vocabulary, encoded text, scrub markers."""
    rng = random.Random(7)
    ev, t = [], 0

    def add(agent, channel, content):
        nonlocal t
        t += 1
        ev.append({"agent": agent, "time": f"2026-06-18T10:{t // 60:02d}:{t % 60:02d}Z", "channel": channel, "content": content})
    uuids = [f"{rng.getrandbits(32):08x}-{rng.getrandbits(16):04x}-4{rng.getrandbits(12):03x}-a{rng.getrandbits(12):03x}-{rng.getrandbits(48):012x}"
             for _ in range(4)]
    for i in range(1, 25):
        agent, ch = f"agent-{i:02d}", f"page{i % 3}"
        add(agent, ch, f"check ipeds_tuition_value and countyLegend field, vocabulary everyone types")
        if i % 4 == 0:
            add(agent, ch, f"try https://example.invalid/render?token={uuids[i % 4]}&scope=ua now")
        if i % 6 == 0:
            add(agent, f"page{(i + 1) % 3}", f"same link https%3A%2F%2Fexample.invalid%2Frender%3Ftoken%3D{uuids[i % 4]} copied")
        if i % 5 == 0:
            add(agent, ch, "key [REDACTED] blob [BLOB_REMOVED] and zq7Lk2vT9xRw4mPa minted slug")
        if i % 7 == 0:
            add(agent, ch, f"slug zq7Lk2vT9xRw4mPa reused by {agent} and 20250201000000id_ capture")
    add("agent-30", "page0", "aHR0cDovL2V4YW1wbGUuaW52YWxpZC9hcGk6e30=  this one decodes to a url, so it is common")
    add("agent-31", "page1", {"nested": "object content", "id": "AbCdEf123456GhIj"})
    return ev


def incident_like() -> list[dict]:
    """A swarm shaped like the real incident, built from invented strings only: many agents independently type the same
    vocabulary (so a naive 'same string = copied' detector fires a lot), and the few real copies hop between pages the
    investigator cannot connect (reads were not logged), so only some sources are visible. Expect a low grade (D)."""
    rng = random.Random(11)
    vocab = ["county_median_rent", "rentFormat", "table_row_count", "legendConfig", "survey2019data", "stateCodeLookup"]
    alnum = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def slug() -> str:
        while True:
            s = "".join(rng.choice(alnum) for _ in range(16))
            if R.shannon(s) >= 3.5 and any(c.isdigit() for c in s):
                return s
    agents, pages = [f"agent-{i:02d}" for i in range(1, 61)], [f"wiki/Page-{i:02d}" for i in range(1, 41)]
    chan = {a: pages[i % len(pages)] for i, a in enumerate(agents)}
    ev: list[dict] = []
    t = 0

    def add(agent, channel, content):
        nonlocal t
        t += 1
        ev.append({"agent": agent, "time": f"2026-06-18T10:{t // 60:02d}:{t % 60:02d}Z", "channel": channel, "content": content})
    for a in agents:                                                   # everyone types shared vocabulary on their own page
        add(a, chan[a], "notes: " + ", ".join(rng.sample(vocab, 3)))
    pool = list(agents)
    for j in range(10):                                                # ten real copies chains of three agents each
        src, c1, c2 = rng.sample(pool, 3)
        s = slug()
        add(src, chan[src], f"working link https://relay.invalid/s/{s}/fetch")
        # six chains: the first copier posts on the source's page (source visible); four: both copiers elsewhere (source invisible)
        add(c1, chan[src] if j < 6 else chan[c1], f"using https://relay.invalid/s/{s}/fetch")
        add(c2, chan[c2] if chan[c2] != chan[src] else pages[(pages.index(chan[src]) + 7) % len(pages)], f"same link {s} worked")
    return ev


def write(dirp: Path, name: str, events: list[dict]) -> None:
    dirp.mkdir(parents=True, exist_ok=True)
    (dirp / f"{name}.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    # the browser receives the file text, so the reference is computed from the file, not from the in-memory list
    ev = R.load_events(dirp / f"{name}.jsonl")
    (dirp / f"{name}.expected.json").write_text(json.dumps(R.public(R.report_card(ev)), indent=1), encoding="utf-8")
    print(f"  {name:28s} {len(ev):5d} events -> grade {R.report_card(ev)['grade']}")


def main() -> None:
    write(PUBLIC, "synthetic", synthetic())
    write(PUBLIC, "incident_like", incident_like())
    lab = ROOT / "data" / "lab"
    for cell in ("W1-loadbearing-qwen-n30-s1", "W2-none-qwen-n30-s1"):
        wp = lab / cell / "world.json"
        if wp.exists():
            write(PUBLIC, "lab_" + cell.split("-n30")[0].lower().replace("-", "_"), R.events_from_lab(wp))
    raw = ROOT / "data" / "raw"
    if (raw / "german").exists():
        ev = R.events_from_collusion(raw / "german")
        write(LOCAL, "collusion_sample", ev[:6000])
    if (raw / "ai_village" / "chat_messages.jsonl.gz").exists():
        write(LOCAL, "ai_village_owasp", R.events_from_ai_village(raw / "ai_village", "2026-01-12", "2026-01-16"))


if __name__ == "__main__":
    main()
