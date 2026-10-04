"""Report card tests on synthetic swarms (no raw data, no network)."""
from __future__ import annotations

import gzip
import json

from backend.analysis import report as R

UUID_TOK = "9c1f4b72-6a0e-4d58-b3a1-7e25d0c4f918"
MINTED = "zq7Lk2vT9xRw4mPa"          # high-entropy invented token


def _ev(agent, t, channel, content):
    return {"agent": agent, "time": f"2026-06-18T10:{t:02d}:00Z", "channel": channel, "content": content}


def test_aliases_normalize_and_gzip_loads(tmp_path):
    rows = [{"author": "a1", "timestamp": "2026-01-01T00:00:01Z", "room": "r1", "text": f"x {UUID_TOK}"},
            {"speaker": "a2", "created_at": "2026-01-01T00:00:02Z", "page": "r1", "body": f"y {UUID_TOK}"},
            {"user": "a3", "t": "2026-01-01T00:00:03Z", "message": "no channel given"}]
    p = tmp_path / "logs.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    ev = R.load_events(p)
    assert [e["agent"] for e in ev] == ["a1", "a2", "a3"]
    assert ev[0]["channel"] == "r1" and ev[2]["channel"] == "global"


def test_json_array_new_aliases_and_bad_lines():
    arr = json.dumps([{"sender": "a1", "created_at": "2026-01-01T00:00:01Z", "session": "s1", "text": f"x {UUID_TOK}"},
                      {"actor": "a2", "ts": "2026-01-01T00:00:02Z", "conversation_id": "s1", "msg": f"y {UUID_TOK}"}, 7, "junk"])
    ev = R.parse_events(arr)
    assert [e["agent"] for e in ev] == ["a1", "a2"] and {e["channel"] for e in ev} == {"s1"}
    jl = '{"agent":"a","time":"2026-01-01","content":"ok"}\nnot json at all\n[1,2]\n{"agent":"b","time":"2026-01-02","content":"ok2"}\n'
    assert [e["agent"] for e in R.parse_events(jl)] == ["a", "b"]           # malformed and non-object lines are skipped
    assert R.parse_events("[1,") == [] and R.parse_events("") == []


def test_grade_thresholds():
    assert [R.grade(x) for x in (0.95, 0.75, 0.55, 0.3, 0.1)] == ["A", "B", "C", "D", "F"]


def test_classifier_separates_markers_from_vocabulary():
    assert R.classify_token(UUID_TOK)[1] == "high"
    assert R.classify_token(MINTED)[1] == "high"
    assert R.classify_token("ipeds_tuition")[0] in R.VOCAB_CLASSES
    assert R.classify_token("20250201000000id_")[0] in R.VOCAB_CLASSES


def test_same_channel_carrier_is_traceable_cross_channel_is_not():
    ev = [_ev("a1", 1, "pageA", f"see {UUID_TOK}"),
          _ev("a2", 2, "pageA", f"copied {UUID_TOK}"),            # carrier a1 visible on pageA
          _ev("a3", 3, "pageB", f"copied {UUID_TOK}")]            # read elsewhere: no visible carrier on pageB
    card = R.report_card(ev)
    assert card["calibrated_copy_calls"] == 2
    assert card["carrier_coverage"] == 0.5
    assert card["best_possible_top1"] == 0.5                       # a2: 1/1, a3: 0
    assert not card["single_channel"]


def test_vocabulary_matches_are_declined_as_coincidence():
    ev = [_ev(f"a{i}", i, "global", "query ipeds_tuition_value field") for i in range(1, 6)]
    card = R.report_card(ev)
    assert card["naive_copy_calls"] == 4
    assert card["calibrated_copy_calls"] == 0 and card["declined_as_coincidence"] == 4
    assert card["grade"] == "N/A"                                  # never grade coincidence as traceable
    assert any("base rate" in r for r in card["recommendations"])
    assert any("No distinctive string" in r for r in card["recommendations"])
    assert "N/A" in R.render(card, "t")


def test_widely_shared_strings_are_vocabulary_not_markers():
    ev = [_ev(f"a{i:02d}", i, "global", f"tok {MINTED}") for i in range(1, 14)]   # 13 agents > MAX_AGENTS
    card = R.report_card(ev)
    assert card["calibrated_copy_calls"] == 0
    assert card["everyone_types_this"][0]["agents"] == 13


def test_public_card_has_no_row_detail_and_renders():
    ev = [_ev("a1", 1, "global", f"see {UUID_TOK}"), _ev("a2", 2, "global", f"copied {UUID_TOK}")]
    card = R.report_card(ev)
    pub = R.public(card)
    assert not any(k.startswith("_") for k in pub)
    assert card["single_channel"] and card["grade"] == "A"
    text = R.render(card, "test")
    assert "TRACEABILITY GRADE: A" in text and "upper bound" in text


def test_events_from_lab_world_dict():
    world = {"writes": [{"t": 3, "author": "agent-01", "page": "Tips", "text": f"use https://x.invalid/{MINTED}"}],
             "submissions": [{"t": 9, "agent": "agent-02", "urls": [f"https://x.invalid/{MINTED}"]}]}
    ev = R.events_from_lab(world)
    assert [e["agent"] for e in ev] == ["agent-01", "agent-02"] and {e["channel"] for e in ev} == {"wiki"}
    card = R.report_card(ev)
    assert card["calibrated_copy_calls"] == 1 and card["carrier_coverage"] == 1.0

