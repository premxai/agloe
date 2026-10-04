"""Colony-view export: the lab's hidden read log becomes `kind: read` events, stale outputs are flagged, and the report card ignores reads."""
from __future__ import annotations

import json

from backend.analysis import report as R
from scripts import export_log

LINK_A = "https://read.alpha-reader.invalid/s/aaaa1111/https://data.countyfacts.invalid/files/county_stats.json"
SERVED_B = "https://read.alpha-reader.invalid/s/zzzz9999/https://data.countyfacts.invalid/files/county_stats.json"
WORLD = {
    "writes": [{"t": 1, "author": "agent-01", "page": "Notes", "version": 1, "text": f"working link {LINK_A}"}],
    "reads": [{"t": 3, "reader": "agent-02", "page": "Notes", "version": 1,
               "urls": [{"chunk": 0, "author": "agent-01", "written": LINK_A, "served": SERVED_B, "tag": "zzzz9999"}]}],
    "submissions": [{"t": 5, "agent": "agent-02", "answer": 1290, "urls": [SERVED_B]}, {"t": 6, "agent": "agent-03", "answer": 1342, "urls": [LINK_A]}],
}


def test_colony_export_adds_reads_pages_and_flags_without_changing_the_plain_view():
    plain = R.events_from_lab(WORLD)
    assert {e["channel"] for e in plain} == {"wiki"} and all("kind" not in e for e in plain)       # the card's view is unchanged
    ev = R.events_from_lab(WORLD, with_reads=True)
    kinds = [e["kind"] for e in ev]
    assert kinds == ["write", "read", "submit", "submit"]
    read = ev[1]
    assert (read["agent"], read["channel"], read["source"], read["content"]) == ("agent-02", "Notes", "agent-01", SERVED_B)
    assert [e.get("flag") for e in ev if e["kind"] == "submit"] == [True, None]                    # only the stale answer is flagged


def test_normalize_keeps_optional_fields_and_the_card_ignores_reads():
    ev = R.parse_events("\n".join(json.dumps(e) for e in R.events_from_lab(WORLD, with_reads=True)))
    assert any(e.get("kind") == "read" and e.get("source") == "agent-01" for e in ev) and any(e.get("flag") for e in ev)
    with_reads = R.report_card(ev)
    without = R.report_card([e for e in ev if e.get("kind") != "read"])
    assert {k: with_reads[k] for k in ("events", "agents", "naive_copy_calls", "calibrated_copy_calls")} == \
           {k: without[k] for k in ("events", "agents", "naive_copy_calls", "calibrated_copy_calls")}


def test_write_jsonl_round_trips(tmp_path):
    ev = R.events_from_lab(WORLD, with_reads=True)
    p = export_log.write_jsonl(ev, tmp_path / "x" / "log.jsonl")
    assert [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] == ev
