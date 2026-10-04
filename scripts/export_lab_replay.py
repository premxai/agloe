"""Export one lab cell as a replay for frontend/replay: the same swarm seen three ways.

  truth     hidden read log: who each agent actually copied from
  edit_log  what an investigator with only the edit log would conclude (latest earlier writer of the same route)
  tags      what canary tags reveal (the served copy named by a token or tag that survived into the agent's submission)

Usage: python -m scripts.export_lab_replay W2-loadbearing-qwen-n30-s1 [--name rumor_tags]  -> frontend/replay/data/<name>.json
Only our own offline lab runs are exported; agent names are lab labels.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from experiments.lab.analyze_lab import first_valued, fetch_value
from experiments.mini_swarm.analyze import PARAM, TOKEN, route, truth_copies
from experiments.mini_swarm.world import RUMOR_AUTHOR, STALE

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"https?://\S+")


def build(summary: dict, w: dict) -> dict:
    succ = first_valued(w)
    tr = truth_copies(w, succ, prefer_exact=True)
    subs = {s["agent"]: s for s in w["submissions"]}
    chunks = [{"t": x["t"], "author": x["author"], "routes": {route(u) for u in URL.findall(x["text"])}} for x in w["writes"]]
    tags, toks = w.get("tags", {}), w.get("tokens", {})
    fams = summary.get("families", {})
    posters = {x["author"] for x in w["writes"]}
    nodes, e_truth, g_latest, g_earliest, e_tags = [], [], [], [], []
    for agent in sorted(set(succ) | set(subs)):
        t = tr.get(agent, {"route": None, "copied": False, "parent": None})
        sub = subs.get(agent)
        t_sub = sub["t"] if sub else succ[agent]["t"]
        cands = [c for c in chunks if c["t"] < t_sub and c["author"] != agent and t["route"] in c["routes"]]
        guess_latest = cands[-1]["author"] if cands else None
        guess_earliest = cands[0]["author"] if cands else None
        tag_parent = None
        for u in (sub or {}).get("urls", []):
            for n, v in PARAM.findall(u):
                if n == "_" and v in tags and tags[v]["reader"] == agent:
                    tag_parent = tags[v]["author"]
            for tok in TOKEN.findall(u):
                if toks.get(tok, {}).get("minted_by") == "wiki" and toks[tok]["reader"] == agent:
                    tag_parent = toks[tok]["author"]
        answer = sub["answer"] if sub else None
        nodes.append({"id": agent, "t": t_sub, "family": fams.get(agent, "?"), "answer": answer,
                      "stale": answer == STALE, "copied": bool(t["copied"]), "route": t["route"],
                      "posted": agent in posters, "tag_kept": tag_parent is not None})
        if t["copied"] and t["parent"]:
            e_truth.append([agent, t["parent"]])
        if guess_latest:
            g_latest.append([agent, guess_latest])
            g_earliest.append([agent, guess_earliest])
        if tag_parent:
            e_tags.append([agent, tag_parent])
    truth_map = {c: p for c, p in e_truth}
    # the edit-log view uses the better of the two simple rules for this swarm, so tags are never shown against a strawman
    score = lambda g: sum(1 for c, p in g if truth_map.get(c) == p)
    heuristic, e_log = ("earliest", g_earliest) if score(g_earliest) > score(g_latest) else ("latest", g_latest)
    n_copy = len(truth_map)
    stats = {
        "agents": len(nodes), "copied": n_copy, "independent": len(nodes) - n_copy,
        "stale_outputs": sum(n["stale"] for n in nodes),
        "edit_log_correct": sum(1 for c, p in e_log if truth_map.get(c) == p),
        "edit_log_accusations": len(e_log),
        "edit_log_false_accusations": sum(1 for c, _ in e_log if c not in truth_map),
        "tags_correct": sum(1 for c, p in e_tags if truth_map.get(c) == p),
        "tags_kept": len(e_tags),
    }
    rumor = next((x for x in w["writes"] if x["author"] == RUMOR_AUTHOR), None)
    return {"cell": summary["cell"], "world": summary["world"], "cond": summary["cond"], "family": summary["family"],
            "n": summary["n"], "heuristic": heuristic, "rumor": {"id": RUMOR_AUTHOR, "t": rumor["t"]} if rumor else None,
            "nodes": nodes, "edges": {"truth": e_truth, "edit_log": e_log, "tags": e_tags}, "stats": stats}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cell")
    ap.add_argument("--name")
    ap.add_argument("--title", help="label shown in the replay page's picker")
    ap.add_argument("--lab", default=str(ROOT / "data" / "lab"))
    a = ap.parse_args()
    d = Path(a.lab) / a.cell
    out = build(json.loads((d / "run.json").read_text(encoding="utf-8")), json.loads((d / "world.json").read_text(encoding="utf-8")))
    dest = ROOT / "frontend" / "replay" / "data" / f"{a.name or a.cell}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out["title"] = a.title or out["cell"]
    dest.write_text(json.dumps(out), encoding="utf-8")
    # the page lists whatever replays exist
    index = [{"file": p.name, "title": json.loads(p.read_text(encoding="utf-8")).get("title", p.stem)}
             for p in sorted(dest.parent.glob("*.json")) if p.name != "index.json"]
    (dest.parent / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    s = out["stats"]
    print(f"{dest.name}: {s['agents']} agents, {s['copied']} copied, {s['stale_outputs']} stale outputs | edit log {s['edit_log_correct']}/{s['copied']} "
          f"correct, {s['edit_log_false_accusations']} false accusations | tags kept {s['tags_kept']}, correct {s['tags_correct']}")


if __name__ == "__main__":
    main()
