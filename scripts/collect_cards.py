"""Collect report cards that other teams chose to share (the JSON from the card's "Copy card as JSON" button).

Teams run the card in their own browser and send only that JSON (counts and rates). This script turns a folder of them into
  - a markdown table for the submission write-up ("real results from using the tool"), and
  - frontend/data/team_cards.json, which the site shows as "Cards from other swarms" when it exists.

Privacy: swarms are anonymised ("Swarm A", "Swarm B", ...) unless you pass --names and the team agreed to be named. The
"most-shared strings" in a card are text from the team's logs: they are never copied out of the card by this script.

Usage:  python -m scripts.collect_cards shared_cards/            # a folder of *.json files
        python -m scripts.collect_cards shared_cards/ --names    # use each file's name as the swarm name (with the team's OK)
"""
from __future__ import annotations

import argparse
import json
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "frontend" / "data" / "team_cards.json"
REQUIRED = ("grade", "events", "agents", "channels", "naive_copy_calls", "calibrated_copy_calls", "carrier_coverage", "best_possible_top1")


def clean(card: dict, name: str) -> dict | None:
    """Keep only counts, rates and the grade; drop every free-text field (strings from the logs, recommendations)."""
    if not isinstance(card, dict) or any(k not in card for k in REQUIRED):
        return None
    row = {"swarm": name, "grade": str(card["grade"]), "events": int(card["events"]), "agents": int(card["agents"]), "channels": int(card["channels"]),
           "naive_copy_calls": int(card["naive_copy_calls"]), "calibrated_copy_calls": int(card["calibrated_copy_calls"]),
           "declined_as_coincidence": int(card.get("declined_as_coincidence", card["naive_copy_calls"] - card["calibrated_copy_calls"])),
           "carrier_coverage": float(card["carrier_coverage"]), "best_possible_top1": float(card["best_possible_top1"]),
           "single_channel": bool(card.get("single_channel", False))}
    shared = card.get("everyone_types_this") or []
    row["shared_by_class"] = {}
    for v in shared:                                    # classes only, never the strings
        c = str(v.get("class", "other"))
        row["shared_by_class"][c] = row["shared_by_class"].get(c, 0) + 1
    return row


def collect(folder: Path, use_names: bool) -> list[dict]:
    rows = []
    for p in sorted(folder.glob("*.json")):
        try:
            card = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            print(f"skipped {p.name}: not valid JSON")
            continue
        i = len(rows)                                   # letters go to accepted cards only
        name = p.stem if use_names else f"Swarm {string.ascii_uppercase[i % 26]}{'' if i < 26 else i // 26}"
        row = clean(card, name)
        if row is None:
            print(f"skipped {p.name}: not a report card (missing fields)")
            continue
        rows.append(row)
    return rows


def markdown(rows: list[dict]) -> str:
    pc = lambda x: f"{x * 100:.0f}%"
    head = "| swarm | events | agents | grade | carrier coverage | best possible top-1 | naive → calibrated copy calls |\n|---|---|---|---|---|---|---|\n"
    return head + "\n".join(
        f"| {r['swarm']} | {r['events']:,} | {r['agents']} | {r['grade']} | {'n/a' if r['grade'] == 'N/A' else pc(r['carrier_coverage'])} | "
        f"{'n/a' if r['grade'] == 'N/A' else pc(r['best_possible_top1'])} | {r['naive_copy_calls']:,} → {r['calibrated_copy_calls']:,} |" for r in rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--names", action="store_true", help="show file names as swarm names (only with the team's agreement)")
    a = ap.parse_args()
    rows = collect(Path(a.folder), a.names)
    if not rows:
        raise SystemExit("no usable cards found")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({"cards": rows}, indent=1), encoding="utf-8")
    print(markdown(rows))
    print(f"\n{len(rows)} cards -> {DEST}")


if __name__ == "__main__":
    main()
