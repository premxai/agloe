"""Agloe-Bench export + scorer on a scripted lab world (no network)."""
from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import asdict
from pathlib import Path

from experiments.mini_swarm.world import ANSWER, TARGET, World
from scripts.export_bench import export

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agloe_score", ROOT / "bench_release" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

HOST = "read.alpha-reader.invalid"


def _session_url(w: World, agent: str) -> str:
    out = w.fetch(agent, f"https://{HOST}/")
    tok = re.search(r"/s/([a-z0-9]+)/", out).group(1)
    url = f"https://{HOST}/s/{tok}/{TARGET}"
    assert str(ANSWER) in w.fetch(agent, url)
    return url


def _scripted_world() -> World:
    """agent-01 and agent-02 solve alone and post; agent-03 reads the notes and copies the OLDER post (agent-01's)."""
    w = World(condition="loadbearing", board=True, seed=11)
    for ag in ("agent-01", "agent-02"):
        u = _session_url(w, ag)
        w.write_page(ag, "Notes", f"works: {u}")
        w.submit(ag, ANSWER, [u])
    page = w.read_page("agent-03", "Notes")
    chunk = re.search(r"\[edit \d+ by agent-01\]\n(.*?)(?:\n\n\[edit|\Z)", page, re.S).group(1)
    copied = re.search(r"https?://\S+", chunk).group(0)
    assert str(ANSWER) in w.fetch("agent-03", copied)
    w.submit("agent-03", ANSWER, [copied])
    return w


def _lab(tmp_path) -> Path:
    w = _scripted_world()
    d = tmp_path / "lab" / "W1-loadbearing-qwen-n3-s1"
    d.mkdir(parents=True)
    state = {k: v for k, v in asdict(w).items() if k != "pages"}
    state["pages"] = {p: [asdict(c) for c in cs] for p, cs in w.pages.items()}
    (d / "world.json").write_text(json.dumps(state, default=str), encoding="utf-8")
    (d / "run.json").write_text(json.dumps({"cell": d.name, "world": "W1", "cond": "loadbearing", "family": "qwen", "n": 3,
                                            "seed": 1, "statuses": {"submitted": 3}}), encoding="utf-8")
    return tmp_path / "lab"


def test_export_writes_input_key_registry_and_ceiling(tmp_path):
    out = tmp_path / "bench"
    assert export(_lab(tmp_path), out) == 1
    cid = "W1-loadbearing-qwen-n3-s1"
    log = [json.loads(x) for x in (out / "edit_log" / f"{cid}.jsonl").read_text().splitlines()]
    truth = {r["agent"]: r for r in map(json.loads, (out / "truth" / f"{cid}.jsonl").read_text().splitlines())}
    assert {e["kind"] for e in log} == {"write", "submit"} and all("routes" in e for e in log)
    assert "parent" not in log[0] and "copied" not in log[0]                  # the key never leaks into the input
    assert truth["agent-03"]["copied"] and truth["agent-03"]["parent"] == "agent-01"
    assert not truth["agent-01"]["copied"] and not truth["agent-02"]["copied"]
    reg = json.loads((out / "registry" / f"{cid}.json").read_text())
    assert reg["tokens"] and all(v["reader"] for v in reg["tokens"].values())
    ceil = json.loads((out / "ceiling" / f"{cid}.json").read_text())
    assert ceil["copiers"] == 1 and ceil["uniform_ceiling"] == 0.5          # two earlier posters, one copier


def test_tags_recover_the_older_source_that_latest_writer_misses(tmp_path):
    out = tmp_path / "bench"
    export(_lab(tmp_path), out)
    cid = "W1-loadbearing-qwen-n3-s1"
    log = score.read_jsonl(out / "edit_log" / f"{cid}.jsonl")
    truth = score.read_jsonl(out / "truth" / f"{cid}.jsonl")
    reg = json.loads((out / "registry" / f"{cid}.json").read_text())
    ceil = json.loads((out / "ceiling" / f"{cid}.json").read_text())
    res = {}
    for m in ("latest", "earliest", "tags"):
        c = score.cell_counts(truth, score.baseline(m, log, reg), ceil, rumor=False)
        res[m] = c["hit"] / c["n_copy"]
    assert res["latest"] == 0.0 and res["earliest"] == 1.0 and res["tags"] == 1.0
    s = score.summarize([score.cell_counts(truth, score.baseline("tags", log, reg), ceil, False)], iters=50)
    assert s["top1"]["value"] == 1.0 and s["vs_uniform_ceiling"] == 2.0       # beats the uniform ceiling: tags add information


def test_missing_predictions_count_as_independent():
    truth = [{"agent": "a", "copied": True, "parent": "b"}, {"agent": "c", "copied": False, "parent": None}]
    c = score.cell_counts(truth, {}, {"uniform_ceiling": 0.5, "copiers": 1}, rumor=False)
    assert c["hit"] == 0 and c["accused_copy"] == 0 and c["accused_indep"] == 0
