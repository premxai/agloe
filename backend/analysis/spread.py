"""Agent-to-agent spread tree for one method.

Each named agent contributes one event: their FIRST adoption of the method. Its parent is
the most recent earlier adopter (different named agent) whose revision added the method on the
same page, i.e. the carrier whose text was on the page the agent was editing. Because every
agent appears once and parents are strictly earlier, the result is a forest (no loops).
Agents with no visible carrier are roots (entered by some channel the logs do not show).
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

from backend.adapters.german_wiki import load_revisions
from backend.analysis.lineage import RAW, SIG_EVENTS


def spread_tree(method_key: str) -> dict:
    seq = {r["rev_id"]: int(r["seq"]) for r in load_revisions(RAW)}
    use = []
    with gzip.open(SIG_EVENTS, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["sig"]["method_key"] == method_key and not r["generated_page"]:
                use.append(r)
    use.sort(key=lambda r: (r["time"], r["rev_id"]))
    by_page = defaultdict(list)          # page -> [(seq, label, row)] one entry per revision
    seen_rev = set()
    for r in use:
        if r["rev_id"] in seen_rev:
            continue
        seen_rev.add(r["rev_id"])
        by_page[r["page_id"]].append((seq[r["rev_id"]], r["label"], r))
    first = {}
    for r in use:
        if r["label"] and r["label"] not in first:
            first[r["label"]] = r
    nodes = {}
    for lab, r in first.items():
        carriers = [x for x in by_page[r["page_id"]] if x[0] < seq[r["rev_id"]] and x[1] and x[1] != lab]
        carrier = carriers[-1] if carriers else None
        nodes[lab] = {
            "agent": lab,
            "time": r["time"],
            "page": r["page_id"],
            "rev_id": r["rev_id"],
            "url": r["url"],
            "batch_size": r["batch_size"],
            "carrier": carrier[1] if carrier else None,
            "carrier_rev_id": carrier[2]["rev_id"] if carrier else None,
            "carrier_time": carrier[2]["time"] if carrier else None,
            "carrier_url": carrier[2]["url"] if carrier else None,
        }
    # a carrier must itself have adopted strictly before; first-adoption time guarantees acyclicity when parent's
    # first adoption <= the carrier revision time. Enforce it.
    for n in nodes.values():
        c = n["carrier"]
        if c and not (nodes[c]["time"] <= n["carrier_time"] and nodes[c]["time"] < n["time"]):
            n["carrier"] = n["carrier_rev_id"] = n["carrier_time"] = n["carrier_url"] = None
    depth = {}
    def d(a):
        if a in depth:
            return depth[a]
        c = nodes[a]["carrier"]
        depth[a] = 0 if not c else d(c) + 1
        return depth[a]
    for a in nodes:
        d(a)
    return {"method_key": method_key, "nodes": nodes, "depth": depth}


if __name__ == "__main__":
    import sys
    from collections import Counter

    t = spread_tree(sys.argv[1])
    n, dep = t["nodes"], t["depth"]
    roots = [a for a in n if not n[a]["carrier"]]
    kids = Counter(x["carrier"] for x in n.values() if x["carrier"])
    print("agents", len(n), "roots", len(roots), "with visible carrier", len(n) - len(roots))
    print("max depth", max(dep.values()), "depth histogram", sorted(Counter(dep.values()).items()))
    print("max fan-out", kids.most_common(3))
    end = max(dep, key=dep.get)
    path = [end]
    while n[path[-1]]["carrier"]:
        path.append(n[path[-1]]["carrier"])
    print("deepest path:")
    for a in path[::-1]:
        x = n[a]
        print("  ", x["time"][5:16], a[:26].ljust(26), "page", x["page"][:38], "batch", x["batch_size"])
