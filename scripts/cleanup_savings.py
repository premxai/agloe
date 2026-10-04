"""Cleanup savings: when a bad tip enters a swarm, how many outputs must you re-check?

Uses the planted-tip lab worlds (W2 = tip appears mid-run, W2E = tip is there from the start). The hidden read log says which
outputs the bad tip really reached (a chain of copying back to the planted post) and which outputs are wrong. Each method
produces a "re-check these" list from what an investigator could see; we score every list against the hidden truth.

Methods:
  everyone      re-run all outputs (the only safe choice with no tracing)
  after_tip     re-check every output submitted after the bad tip was posted (the natural time-based rule)
  earliest      follow the earliest visible writer of each copied link back to the tip (best simple edit-log rule here)
  latest        follow the latest visible writer
  tags          follow the secret code in the link where it survived
  tags+backup   the code where it survived, the earliest-writer rule where it did not

Usage: python -m scripts.cleanup_savings  -> data/lab/cleanup_savings.json (aggregates only)
"""
from __future__ import annotations

import json
from pathlib import Path

from experiments.lab.analyze_lab import closure, first_valued, load_cells, pooled
from experiments.mini_swarm.analyze import investigator, truth_copies
from experiments.mini_swarm.world import RUMOR_AUTHOR, STALE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "lab" / "cleanup_savings.json"
METHODS = ("everyone", "after_tip", "tags", "tags+backup", "earliest", "latest")


def cell_cleanup(w: dict) -> dict:
    succ = first_valued(w)
    tr = truth_copies(w, succ, prefer_exact=True)
    rows = investigator(w, tr).pop("rows")
    subs = {s["agent"]: s for s in w["submissions"]}
    outputs = set(subs)
    stale = {a for a, s in subs.items() if s["answer"] == STALE}
    truth_par = {a: t["parent"] for a, t in tr.items() if t["copied"] and t["parent"]}
    reached = closure(truth_par, RUMOR_AUTHOR) & outputs
    tip_t = min((x["t"] for x in w["writes"] if x["author"] == RUMOR_AUTHOR), default=0)
    par = {
        "tags": {r["agent"]: r["tag_parent"] for r in rows if r["tag_parent"]},
        "earliest": {r["agent"]: r["earliest"] for r in rows if r["earliest"]},
        "latest": {r["agent"]: r["latest"] for r in rows if r["latest"]},
        "tags+backup": {r["agent"]: (r["tag_parent"] or r["earliest"]) for r in rows if (r["tag_parent"] or r["earliest"])},
    }
    flagged = {"everyone": set(outputs), "after_tip": {a for a, s in subs.items() if s["t"] > tip_t}}
    for k, p in par.items():
        flagged[k] = closure(p, RUMOR_AUTHOR) & outputs
    cell = {"outputs": len(outputs), "reached": len(reached), "stale": len(stale), "stale_not_reached": len(stale - reached)}
    for k in METHODS:
        f = flagged[k]
        cell[k] = {"flagged": len(f), "caught": len(f & reached), "bad_found": len(f & stale)}
    return cell


def aggregate(cells: list[dict]) -> dict:
    out = {"runs": len(cells), "outputs": sum(c["outputs"] for c in cells), "reached": sum(c["reached"] for c in cells),
           "stale": sum(c["stale"] for c in cells), "stale_not_reached": sum(c["stale_not_reached"] for c in cells), "methods": {}}
    for k in METHODS:
        out["methods"][k] = {
            "flagged_share": pooled([(c[k]["flagged"], c["outputs"]) for c in cells]),      # effort: share of outputs to re-check
            "reached_found": pooled([(c[k]["caught"], c["reached"]) for c in cells]),       # recall of the outputs the tip reached
            "precision": pooled([(c[k]["caught"], c[k]["flagged"]) for c in cells]),        # share of the list that is truly affected
            "bad_found": pooled([(c[k]["bad_found"], c["stale"]) for c in cells]),          # share of the wrong outputs on the list
        }
    return out


def main() -> None:
    groups: dict[str, list[dict]] = {}
    for s, w in load_cells():
        if s["world"] not in ("W2", "W2E") or not w.get("seed_rumor"):
            continue
        c = cell_cleanup(w)
        c["family"] = s["family"]
        scope = f"{s['world']} {'tags' if s['cond'] != 'none' else 'no tags'}"
        groups.setdefault(scope, []).append(c)
        if s["cond"] != "none":
            groups.setdefault(f"{s['world']} tags {s['family']}", []).append(c)
    res = {k: aggregate(v) for k, v in sorted(groups.items())}
    # a typical single run, for the one-line story: the tagged run closest to the median size of the contamination
    tagged = [c for k, v in groups.items() if k in ("W2 tags", "W2E tags") for c in v if 3 <= c["reached"] < c["outputs"]]
    if tagged:
        tagged.sort(key=lambda c: c["reached"])
        res["example"] = tagged[len(tagged) // 2]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    f = lambda d: "n/a" if d["rate"] is None else f"{d['rate']:.0%} ({d['lo']:.0%}-{d['hi']:.0%})"
    for scope, a in res.items():
        if scope == "example":
            continue
        print(f"\n{scope}: {a['runs']} runs, {a['outputs']} outputs, tip reached {a['reached']}, wrong {a['stale']}")
        print(f"  {'method':12s} {'re-check share':>22s} {'reached found':>22s} {'precision':>22s} {'wrong found':>22s}")
        for k in METHODS:
            m = a["methods"][k]
            print(f"  {k:12s} {f(m['flagged_share']):>22s} {f(m['reached_found']):>22s} {f(m['precision']):>22s} {f(m['bad_found']):>22s}")
    if "example" in res:
        print("\nexample run:", json.dumps(res["example"]))


if __name__ == "__main__":
    main()
