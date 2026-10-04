"""AI Village carrier coverage over the WHOLE chat, in 7-day windows (aggregate-only output).

run_ai_village.py reports four hand-picked weeks. This script covers every week of agent chat, so the picture does not depend on which
weeks we chose: for each window, the share of cross-agent copies whose earlier author was visible in the log where the copy happened
(before Rooms v1 the whole chat is visible; after it, only rooms the adopter also posted in), pooled by regime.

Reads data/raw/ai_village/{agents,chat_messages}.jsonl.gz (gated; never committed). Writes data/out/ai_village_full.json: counts and
rates only, no message or token text.

Usage: python -m scripts.run_ai_village_full
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from backend.adapters.ai_village import ROOMS_CUTOVER, load_agents, load_chat, spread_records
from backend.analysis.markers import wilson

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "ai_village"
OUT = ROOT / "data" / "out" / "ai_village_full.json"
MIN_ADOPTIONS = 100          # windows with fewer copy events are listed but not used for the per-window spread
SHOWCASED = [                # the four weeks run_ai_village.py reports, so the reader can see where they sit
    ("owasp-juice-shop", "2026-01-12", "2026-01-23"), ("rpg-saboteur", "2026-03-05", "2026-03-16"),
    ("interact-outside-village", "2026-03-23", "2026-03-30"), ("beat-hardest-game", "2026-06-23", "2026-06-29")]


def window_row(msgs: list[dict], start: str) -> dict:
    rooms = start >= ROOMS_CUTOVER
    recs = spread_records(msgs, rooms=rooms)
    return {"start": start, "rooms": rooms, "messages": len(msgs), "agents": len({m["agent"] for m in msgs}),
            "adoptions": len(recs), "covered": sum(r["visible_carrier"] for r in recs)}


def weekly_rows(chat: list[dict]) -> list[dict]:
    start = dt.date.fromisoformat(chat[0]["t"][:10])
    weeks: dict[int, list[dict]] = defaultdict(list)
    for r in chat:
        weeks[(dt.date.fromisoformat(r["t"][:10]) - start).days // 7].append(r)
    return [window_row(m, (start + dt.timedelta(days=7 * w)).isoformat()) for w, m in sorted(weeks.items())]


def pooled(rows: list[dict]) -> dict:
    n, k = sum(r["adoptions"] for r in rows), sum(r["covered"] for r in rows)
    out = {"windows": len(rows), "adoptions": n, "covered": k, "rate": round(k / n, 3) if n else None,
           "ci95": [round(x, 3) for x in wilson(k, n)] if n else None}
    rates = sorted(r["covered"] / r["adoptions"] for r in rows if r["adoptions"] >= MIN_ADOPTIONS)
    out["windows_used_for_spread"] = len(rates)
    if rates:
        out.update(window_min=round(rates[0], 3), window_median=round(rates[len(rates) // 2], 3), window_max=round(rates[-1], 3))
    return out


def percentile(rate: float, rows: list[dict]) -> float | None:
    """Share of the regime's windows (with enough copy events) whose coverage is at or below `rate`."""
    rates = [r["covered"] / r["adoptions"] for r in rows if r["adoptions"] >= MIN_ADOPTIONS]
    return round(sum(x <= rate for x in rates) / len(rates), 2) if rates else None


def aggregate(rows: list[dict], showcased: list[dict] | None = None) -> dict:
    pre, post = [r for r in rows if not r["rooms"]], [r for r in rows if r["rooms"]]
    out = {"rooms_cutover": ROOMS_CUTOVER, "window_days": 7, "min_adoptions_for_spread": MIN_ADOPTIONS,
           "pre_rooms": pooled(pre), "room_scoped": pooled(post), "windows": rows}
    if showcased:
        out["showcased"] = [{**s, "percentile_in_regime": percentile(s["rate"], post if s["rooms"] else pre)} for s in showcased]
    return out


def main() -> None:
    if not (RAW / "chat_messages.jsonl.gz").exists():
        raise SystemExit(f"raw export not found at {RAW} (gated; run the hf download first)")
    agents = load_agents(RAW)
    chat = load_chat(RAW, "2000-01-01", "2100-01-01", agents)
    rows = weekly_rows(chat)
    shown = []
    for name, lo, hi in SHOWCASED:
        w = window_row([m for m in chat if lo <= m["t"][:10] <= hi], lo)
        shown.append({"name": name, "start": lo, "end": hi, "rooms": w["rooms"], "adoptions": w["adoptions"],
                      "rate": round(w["covered"] / w["adoptions"], 3) if w["adoptions"] else None})
    res = aggregate(rows, shown)
    res["messages"], res["agents"], res["first_day"], res["last_day"] = len(chat), len(agents), chat[0]["t"][:10], chat[-1]["t"][:10]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for label in ("pre_rooms", "room_scoped"):
        p = res[label]
        print(f"{label:12s} {p['windows']:3d} windows, {p['adoptions']:6d} copies, coverage {p['rate']} CI{p['ci95']}  "
              f"per-window (n>={MIN_ADOPTIONS}) min {p.get('window_min')} median {p.get('window_median')} max {p.get('window_max')}")
    for s in res["showcased"]:
        print(f"  showcased {s['name']:26s} {s['rate']}  (percentile {s['percentile_in_regime']} within its regime)")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
