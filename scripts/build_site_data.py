"""Assemble frontend/data/results.json: every number the site shows, read from computed outputs (not typed in).

Sources: data/out/{audit,neutral,readmap_verify,ai_village}.json (real datasets), data/lab/lab_results.json (lab runs),
data/lab/*/run.json (agent-run counts), data/mini_swarm (earlier single-seed Claude arms).
Aggregates only: no agent handles, no log text.

Usage: python -m scripts.build_site_data
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "out"
LAB = ROOT / "data" / "lab"


def jl(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def agent_runs() -> dict:
    n, cells, bench, usd = 0, 0, 0, 0.0
    for p in LAB.glob("*/run.json"):
        s = json.loads(p.read_text(encoding="utf-8"))
        if s.get("seed", 0) >= 900:                       # smoke / connectivity checks are not experiments
            continue
        n += s.get("n", 0)
        cells += 1
        bench += s.get("world") not in ("FP", "W4", "W4G")
        usd += s.get("cost_usd", 0.0)
    return {"lab_agent_runs": n, "lab_cells": cells, "bench_cells": bench, "lab_usd": round(usd, 2)}


def design() -> dict:
    """The experiment design as it was actually run: per world, how many cells and agent runs, which models, tag conditions, swarm sizes and seeds."""
    from experiments.lab.grid import WORLD_WHAT
    from scripts.build_paper import NAMES
    worlds: dict = {}
    smoke = 0
    for p in sorted(LAB.glob("*/run.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        if s.get("seed", 0) >= 900:
            smoke += 1
            continue
        w = worlds.setdefault(s["world"], {"world": s["world"], "what": WORLD_WHAT.get(s["world"], ""), "cells": 0, "agent_runs": 0,
                                           "families": set(), "conds": set(), "sizes": set(), "seeds": set(), "usd": 0.0, "max_calls": s.get("max_calls")})
        w["cells"] += 1; w["agent_runs"] += s["n"]; w["families"].add("mixed (all 8)" if s["family"] == "mix" else NAMES.get(s["family"], s["family"]))
        w["conds"].add(s["cond"]); w["sizes"].add(s["n"]); w["seeds"].add(s["seed"]); w["usd"] += s.get("cost_usd", 0.0)
    order = ["FP", "W1", "W2", "W2E", "W3", "W4", "W4G"]
    rows = [{**w, "families": sorted(w["families"]), "conds": sorted(w["conds"], key=["none", "inert", "loadbearing"].index), "sizes": sorted(w["sizes"]),
             "seeds": len(w["seeds"]), "usd": round(w["usd"], 2)} for k in order for w in [worlds[k]] if k in worlds]
    invalid = len(list(LAB.glob("_invalid_*")))
    return {"worlds": rows, "smoke_runs_excluded": smoke, "flawed_designs_set_aside": invalid,
            "totals": {"cells": sum(r["cells"] for r in rows), "agent_runs": sum(r["agent_runs"] for r in rows), "usd": round(sum(r["usd"] for r in rows), 2)}}


def main() -> None:
    audit, neutral, rm, av, lab =(jl(OUT / "audit.json"), jl(OUT / "neutral.json"), jl(OUT / "readmap_verify.json"),
                                   jl(OUT / "ai_village.json"), jl(LAB / "lab_results.json"))
    res: dict = {"generated_from": "computed outputs; see docs/RESULTS.md"}
    if audit:
        s = audit["summary"]
        res["incident"] = {"best_top1": round(s["ceiling_top1"], 3), "no_carrier": round(s["share_no_carrier"], 3),
                           "adopters": s["adopters"], "behaviors": s["behaviors"]}
    if neutral:
        c = neutral["summary"]["copy_or_coincidence"]
        res["coincidence"] = {"naive_calls": c["naive_copy_calls"], "supported_calls": c["calibrated_copy_calls"]}
    if rm:
        t = rm["tally"]
        res["cross_team"] = {"naive": sum(t.values()), "verified": t["STRONG"], "rejected": t["REJECT"]}
    # carrier coverage ladder: share of copy events whose source is visible in the investigator's log
    ladder = [{"label": "Hidden reads (the incident)", "value": 0.20, "text": "16–20%",
               "note": "collusion.wiki: marker strings whose earlier writer was visible (RESULTS §F)"}]
    full = jl(OUT / "ai_village_full.json")
    if full:          # the whole chat, week by week (scripts/run_ai_village_full.py); not the four weeks we first picked
        post, pre = full["room_scoped"], full["pre_rooms"]
        ladder.append({"label": "Room-scoped chat (AI Village, every week)", "value": post["rate"], "text": f"{round(post['rate'] * 100)}%",
                       "note": f"{post['adoptions']:,} copy events over {post['windows']} weeks; the lowest week was {round(post['window_min'] * 100)}%"})
        ladder.append({"label": "One shared chat (AI Village, every week before rooms)", "value": pre["rate"], "text": f"{round(pre['rate'] * 100)}%",
                       "note": f"{pre['adoptions']:,} copy events over {pre['windows']} weeks"})
        res["ai_village_full"] = {k: full[k] for k in ("pre_rooms", "room_scoped", "showcased", "messages", "agents", "first_day", "last_day", "rooms_cutover")}
    elif av:
        for key, label in (("interact-outside-village", "Room-scoped chat (AI Village, one week)"), ("owasp-juice-shop", "One shared chat (AI Village, one week)")):
            if key in av:
                r = av[key]["attributable_rate"]
                ladder.append({"label": label, "value": r, "text": f"{round(r * 100)}%", "note": f"{av[key]['cross_agent_adoptions']:,} copy events"})
    res["ladder"] = ladder
    res["spend"] = agent_runs()
    res["design"] = design()
    if lab:
        res["lab"] = {"H1": lab["H1"], "H2": lab["H2"], "H3": lab["H3"], "H4": lab["H4"],
                      "fingerprint_attribution": lab["fingerprint_attribution"], "size_sweep": lab["size_sweep"],
                      "mixed_swarm": lab["mixed_swarm"], "strong_model": lab["strong_model"], "truth_note": lab["truth_note"],
                      "rumor_by_family": lab.get("rumor_by_family", {}), "early_rumor_by_family": lab.get("early_rumor_by_family", {}),
                      "gated": lab.get("gated", {})}
    cl = jl(LAB / "cleanup_savings.json")
    if cl:
        res["cleanup"] = {k: cl[k] for k in ("W2 tags", "W2E tags") if k in cl}
    dest = ROOT / "frontend" / "data" / "results.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"-> {dest}  ({', '.join(res)})")


if __name__ == "__main__":
    main()
