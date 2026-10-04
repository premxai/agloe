"""The Face-Off page computes its headline numbers in the browser from the recorded swarms in frontend/replay/data. If a re-export ever
changed those runs, the story's claims could silently stop being true; these checks keep the data the page relies on honest."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "frontend" / "replay" / "data"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def closure(m, root):
    out = set()
    for a in m:
        seen, cur = set(), a
        while cur in m and cur not in seen:
            seen.add(cur)
            cur = m[cur]
            if cur == root:
                out.add(a)
                break
    return out


def test_spread_scene_shows_the_edit_log_losing_to_the_codes():
    s = load("early_tip_tags")["stats"]
    assert s["tags_correct"] == s["copied"] and s["edit_log_correct"] < 0.3 * s["copied"]      # the contrast the story opens with


def test_cleanup_scene_trace_is_much_shorter_than_the_no_trace_list_and_misses_nothing():
    d = load("cleanup_tip_tags")
    root = d["rumor"]["id"]
    truth, edit, tags = (dict(map(tuple, d["edges"][k])) for k in ("truth", "edit_log", "tags"))
    combined = {**edit, **tags}                                                                  # the code where kept, the edit-log guess where lost
    after_tip = {n["id"] for n in d["nodes"] if n["t"] > d["rumor"]["t"]}
    reached, traced = closure(truth, root), closure(combined, root)
    assert len(traced) < len(after_tip) / 3 and reached <= traced                                # the page says "found N of the N the tip reached"
    assert len(d["nodes"]) == d["stats"]["agents"] == 30


def test_every_replay_swarm_listed_in_the_picker_exists():
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    assert {i["file"] for i in index} >= {"early_tip_tags.json", "cleanup_tip_tags.json", "late_tip_tags.json", "no_tip.json"}
    assert all((DATA / i["file"]).exists() for i in index)
