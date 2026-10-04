"""Whole-dataset AI Village aggregation: pooled rates by regime, per-window spread, and where a showcased week sits (synthetic rows only)."""
from __future__ import annotations

from backend.adapters.ai_village import spread_records
from scripts import run_ai_village_full as full


def _row(start, rooms, adoptions, covered):
    return {"start": start, "rooms": rooms, "messages": 10, "agents": 3, "adoptions": adoptions, "covered": covered}


ROWS = [_row("2026-01-01", False, 200, 200), _row("2026-01-08", False, 150, 150),
        _row("2026-03-01", True, 200, 190), _row("2026-03-08", True, 100, 85), _row("2026-03-15", True, 300, 297), _row("2026-03-22", True, 50, 10)]


def test_pooled_rates_are_weighted_by_copies_and_split_by_regime():
    out = full.aggregate(ROWS)
    assert out["pre_rooms"]["rate"] == 1.0 and out["pre_rooms"]["windows"] == 2
    post = out["room_scoped"]
    assert post["adoptions"] == 650 and post["covered"] == 582 and post["rate"] == round(582 / 650, 3)
    assert post["windows_used_for_spread"] == 3 and post["window_min"] == 0.85 and post["window_max"] == 0.99     # the 50-copy window is not used


def test_showcased_week_is_placed_in_its_regime():
    out = full.aggregate(ROWS, [{"name": "low", "rooms": True, "rate": 0.85}, {"name": "typical", "rooms": True, "rate": 0.99}])
    pct = {s["name"]: s["percentile_in_regime"] for s in out["showcased"]}
    assert pct["low"] < pct["typical"] == 1.0


def test_window_row_counts_visible_carriers_with_the_adapter():
    chat = [{"id": f"m{i}", "agent": a, "agent_id": a, "family": "f", "room": "r", "t": f"2026-01-0{i + 1} 10:00:00.000000", "content": txt}
            for i, (a, txt) in enumerate([("a", "see build-artifact_9f3k2x7q1z"), ("b", "using build-artifact_9f3k2x7q1z too")])]
    row = full.window_row(chat, "2026-01-01")
    assert (row["adoptions"], row["covered"], row["rooms"]) == (len(spread_records(chat, rooms=False)), 1, False)
