"""Reproduce the AI Village propagation results from the local raw export.

Reads data/raw/ai_village/{agents,chat_messages}.jsonl.gz (gated; never committed) and writes
aggregate-only results to data/out/ai_village.json. No message or token text is emitted.

Usage: python -m scripts.run_ai_village
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.adapters.ai_village import summary

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ai_village"

# Goal weeks (village-goal windows from village_goals.jsonl.gz). The OWASP week predates Rooms v1
# (2026-02-25) so its chat channel is global/all-visible; the others are room-scoped.
WINDOWS = [
    ("owasp-juice-shop", "2026-01-12", "2026-01-23"),          # pre-rooms: fully-visible channel
    ("rpg-saboteur", "2026-03-05", "2026-03-16"),              # post-rooms
    ("interact-outside-village", "2026-03-23", "2026-03-30"),  # post-rooms
    ("beat-hardest-game", "2026-06-23", "2026-06-29"),         # post-rooms
]


def main() -> None:
    if not (RAW / "chat_messages.jsonl.gz").exists():
        raise SystemExit(f"raw export not found at {RAW} (gated; run the hf download first)")
    out = {}
    for name, lo, hi in WINDOWS:
        s = summary(RAW, lo, hi)
        out[name] = s
        c = s["coincidence"]
        print(f"\n== {name}  {lo}..{hi}  rooms_scoped={s['rooms_scoped']}")
        print(f"   agents={s['agents_in_window']} msgs={s['messages']} markers={s['distinct_markers']} "
              f"adoptions={s['cross_agent_adoptions']}")
        print(f"   carrier-coverage={s['attributable']}/{s['cross_agent_adoptions']}="
              f"{s['attributable_rate']} CI{s['attributable_ci95']}")
        print(f"   same-family share={s['same_family_share_of_attributable']} "
              f"median lag(s)={s['median_lag_s_when_visible']}")
        if c.get("near_simultaneous_pairs"):
            print(f"   coincidence: {c['near_simultaneous_pairs']} pairs<= {c['short_s']}s  "
                  f"obs={c['observed_same_family']} null={c['null_same_family_mean']}{c['null_ci95']} "
                  f"x{c['enrichment']} p={c['p_value']}")
    (ROOT / "data" / "out").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "out" / "ai_village.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/out/ai_village.json")


if __name__ == "__main__":
    main()
