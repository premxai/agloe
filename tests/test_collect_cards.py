"""Collecting shared report cards: strings from the logs never leave the card, and swarms are anonymised by default."""
from __future__ import annotations

import json

from scripts import collect_cards

CARD = {"grade": "B", "events": 2058, "agents": 13, "channels": 3, "naive_copy_calls": 659, "calibrated_copy_calls": 277,
        "declined_as_coincidence": 382, "carrier_coverage": 0.82, "best_possible_top1": 0.68, "single_channel": False,
        "everyone_types_this": [{"string": "SECRET-TOKEN-FROM-THE-LOGS", "agents": 5, "class": "uuid"},
                                {"string": "another_log_string", "agents": 4, "class": "uuid"}],
        "recommendations": ["free text that mentions a team"]}


def test_clean_keeps_counts_and_drops_free_text():
    row = collect_cards.clean(CARD, "Swarm A")
    blob = json.dumps(row)
    assert "SECRET" not in blob and "another_log_string" not in blob and "free text" not in blob
    assert row["shared_by_class"] == {"uuid": 2} and row["calibrated_copy_calls"] == 277 and row["grade"] == "B"


def test_clean_rejects_things_that_are_not_cards():
    assert collect_cards.clean({"grade": "A"}, "x") is None and collect_cards.clean([], "x") is None


def test_collect_anonymises_unless_names_are_allowed(tmp_path):
    (tmp_path / "team_foo.json").write_text(json.dumps(CARD), encoding="utf-8")
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    (tmp_path / "other.json").write_text(json.dumps({"hello": 1}), encoding="utf-8")
    rows = collect_cards.collect(tmp_path, use_names=False)
    assert [r["swarm"] for r in rows] == ["Swarm A"]
    assert [r["swarm"] for r in collect_cards.collect(tmp_path, use_names=True)] == ["team_foo"]
    assert "| Swarm A |" in collect_cards.markdown(rows) and "82%" in collect_cards.markdown(rows)
