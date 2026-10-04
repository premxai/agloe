"""Cross-family coincidence matrix for the Nebius multi-model run (+ the Anthropic A0/A1 arms if present).

For every model family we take each agent's first 'random' value (an arbitrary cache-buster-style param it
chose, e.g. x=1) and compute:
  * within-family collision  = P(two distinct same-family agents chose the identical value);
  * cross-family collision   = P(an agent of family X and one of family Y chose the identical value).
Headline: mean within-family >> mean cross-family  =>  the same 'random' value is a model-family habit, so
naive string-matching over-links same-model agents (the collusion.wiki `x=1` effect, now controlled, multi-model).

Reads data/mini_swarm/{NEB-*-seed*,A0-seed*,A1-seed*}/world.json. No network. -> data/mini_swarm/nebius_analysis.json
"""
from __future__ import annotations

import json
from collections import Counter
from itertools import combinations, product
from pathlib import Path

from experiments.mini_swarm.analyze import arbitrary_values, collision, first_success, route, wilson

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "data" / "mini_swarm"
ANTHRO = {"A0-seed0": "claude-haiku", "A1-seed0": "claude-sonnet"}


def first_values(world: dict) -> list[str]:
    """One 'random' value per agent that chose at least one (first arbitrary param on its fetch URLs)."""
    per: dict[str, list] = {}
    for f in world["fetches"]:
        vals = arbitrary_values(f["url"])
        if vals:
            per.setdefault(f["agent"], []).append(f"{vals[0][0]}={vals[0][1]}")
    return [v[0] for v in per.values() if v]


def load_families() -> dict:
    fam = {}
    for d in sorted(RUNS.glob("*-seed*")):
        name = d.name
        if not (d / "world.json").exists():
            continue
        if name.startswith("NEB-"):
            key = name[4:].rsplit("-seed", 1)[0]
        elif name in ANTHRO:
            key = ANTHRO[name]
        else:
            continue
        w = json.loads((d / "world.json").read_text(encoding="utf-8"))
        fam.setdefault(key, {"values": [], "agents": 0, "solved": 0, "routes": Counter()})
        fam[key]["values"] += first_values(w)
        fam[key]["agents"] += len({f["agent"] for f in w["fetches"]})
        succ = first_success(w)
        fam[key]["solved"] += len(succ)
        fam[key]["routes"] += Counter(route(f["url"]) for f in succ.values())
    return fam


def main() -> None:
    fam = load_families()
    report = {"families": {}, "within_vs_cross": {}, "cross_matrix": {}}
    for k, d in sorted(fam.items()):
        vals = d["values"]
        n = len(vals)
        wc = collision(vals)
        report["families"][k] = {
            "agents": d["agents"], "solved": d["solved"],
            "chose_a_value": n, "value_adoption_rate": round(n / d["agents"], 3) if d["agents"] else 0.0,
            "top_values": Counter(vals).most_common(5),
            "within_family_collision": None if wc != wc else round(wc, 3),
            "top_route": d["routes"].most_common(1)[0] if d["routes"] else None,
        }
    # within vs cross (only families where >=2 agents chose a value, so collision is defined)
    usable = {k: d["values"] for k, d in fam.items() if len(d["values"]) >= 2}
    within = [collision(v) for v in usable.values()]
    within = [x for x in within if x == x]
    cross = []
    for (ka, va), (kb, vb) in combinations(usable.items(), 2):
        c = collision(va, vb)
        report["cross_matrix"][f"{ka}|{kb}"] = round(c, 3) if c == c else None
        if c == c:
            cross.append(c)
    mw = sum(within) / len(within) if within else float("nan")
    mc = sum(cross) / len(cross) if cross else float("nan")
    report["within_vs_cross"] = {
        "families_scored": sorted(usable),
        "mean_within_family_collision": round(mw, 3) if mw == mw else None,
        "mean_cross_family_collision": round(mc, 3) if mc == mc else None,
        "enrichment_within_over_cross": round(mw / mc, 2) if (mc == mc and mc > 0) else None,
    }
    (RUNS / "nebius_analysis.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
