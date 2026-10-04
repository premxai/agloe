"""Method-level lineage DAG for the DSEWiki.

Nodes are methods (see signatures.method_key). A method's *origin* is the first
non-generated revision that added it. Its *parent* is the earlier method with the
smallest layer edit distance, ranked first by what the logs prove about exposure:

  A  the origin revision edited a page whose previous revision already held the parent
  B  the author had earlier edited some page that held the parent (inferred exposure)
  C  parent is close and earlier, but nothing shows the author could have seen it
  D  no earlier method within distance 1.5: root / independent discovery

Models never decide any of this. Ties are kept as `alternates`, not hidden.

Run: python -m backend.analysis.lineage
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from backend.adapters.german_wiki import SOURCE, is_generated, load_revisions
from backend.analysis.signatures import extract_urls, parse_signature

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "german"
SIG_EVENTS = ROOT / "data" / "out" / "sig_events.jsonl.gz"
OUT = ROOT / "data" / "out" / "lineage.json"
MAX_DIST = 1.5
ONE_STEP = 1.0


@lru_cache(maxsize=None)
def _sig(url: str):
    return parse_signature(url)


def _is_node(sig) -> bool:
    """A method is its wrapper chain, whatever it fetches. Bare URLs only count for official targets."""
    return bool(sig.layers) or sig.target_kind == "official"


def _is_node_row(sig: dict) -> bool:
    return bool(sig["layers"]) or sig["target_kind"] == "official"


def _layer_tokens(method_key: str) -> tuple[str, ...]:
    return () if method_key == "direct" else tuple(method_key.split(" > "))


def _tok_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    sa, sb = a.rsplit("@", 1)[0], b.rsplit("@", 1)[0]
    if sa == sb:
        return 0.5  # same service+style, encoding depth differs
    ha, hb = sa.split("/", 1)[0], sb.split("/", 1)[0]
    return 0.5 if ha == hb else 1.0  # same service, different endpoint style


def layer_distance(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    prev = [float(j) for j in range(len(b) + 1)]
    for i in range(1, len(a) + 1):
        cur = [float(i)] + [0.0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + _tok_cost(a[i - 1], b[j - 1]))
        prev = cur
    return prev[-1]


def describe_change(parent: tuple[str, ...], child: tuple[str, ...]) -> tuple[str, str]:
    """(relation, human description) from the layer difference. Deterministic."""
    if len(child) == len(parent) + 1:
        for i in range(len(child)):
            if child[:i] + child[i + 1:] == parent:
                where = "outermost" if i == 0 else ("innermost" if i == len(child) - 1 else "middle")
                return "extend", f"adds {where} layer {child[i]}"
    if len(child) + 1 == len(parent):
        for i in range(len(parent)):
            if parent[:i] + parent[i + 1:] == child:
                return "simplify", f"drops layer {parent[i]}"
    if len(child) == len(parent):
        diff = [(p, c) for p, c in zip(parent, child) if p != c]
        if len(diff) == 1:
            p, c = diff[0]
            sp, sc = p.rsplit("@", 1), c.rsplit("@", 1)
            if sp[0] == sc[0]:
                return "reencode", f"re-encodes {sp[0]} from depth {sp[1]} to {sc[1]}"
            if sp[0].split("/", 1)[0] == sc[0].split("/", 1)[0]:
                return "restyle", f"switches {sp[0]} to endpoint form {sc[0]}"
            return "substitute", f"swaps {p} for {c}"
    return "rework", f"{' > '.join(parent) or 'direct'}  =>  {' > '.join(child)}"


def _ord(row: dict) -> tuple[str, str]:
    return (row["time"], row["rev_id"])


def build() -> dict:
    revisions = load_revisions(RAW)
    by_page = defaultdict(list)
    for r in revisions:
        by_page[r["page_id"]].append(r)
    prev_of = {}
    for revs in by_page.values():
        revs.sort(key=lambda r: int(r["seq"]))
        for a, b in zip(revs, revs[1:]):
            prev_of[b["rev_id"]] = a

    @lru_cache(maxsize=None)
    def body_index(rev_id: str) -> dict:
        """method_key -> set of resources (target_url) fetched with it, for a revision's full body."""
        out = defaultdict(set)
        for u in extract_urls(rev_by_id[rev_id]["body"]):
            s = _sig(u)
            if s and _is_node(s):
                out[s.method_key].add(s.target_url)
        return out

    def body_methods(rev_id: str) -> frozenset:
        return frozenset(body_index(rev_id))

    rev_by_id = {r["rev_id"]: r for r in revisions}

    rows = []
    with gzip.open(SIG_EVENTS, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if _is_node_row(r["sig"]) and not r["generated_page"]:
                rows.append(r)
    rows.sort(key=_ord)

    # --- origins and adoptions
    origin: dict[str, dict] = {}
    uses: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        m = r["sig"]["method_key"]
        uses[m].append(r)
        origin.setdefault(m, r)
    methods_in_rev = defaultdict(set)  # rev_id -> methods it adds
    for r in rows:
        methods_in_rev[r["rev_id"]].add(r["sig"]["method_key"])
    origin_revs = {o["rev_id"] for o in origin.values()}

    # --- exposure history of each (non-blank) agent, snapshotted at each origin revision
    seen: dict[str, set] = defaultdict(set)
    exposure_at: dict[str, frozenset] = {}
    for r in revisions:
        lab = r["label"]
        prev = prev_of.get(r["rev_id"])
        if lab and r["rev_id"] in origin_revs:
            exposure_at[r["rev_id"]] = frozenset(seen[lab])
        if lab:
            if prev:
                seen[lab] |= body_methods(prev["rev_id"])
            seen[lab] |= body_methods(r["rev_id"])

    # --- parent selection
    order = {m: i for i, m in enumerate(sorted(origin, key=lambda m: _ord(origin[m])))}
    nodes, edges = {}, []
    for m, o in origin.items():
        layers = _layer_tokens(m)
        nodes[m] = {
            "method_key": m,
            "family_key": o["sig"]["family_key"],
            "layers": list(layers),
            "origin": {k: o[k] for k in ("rev_id", "page_id", "label", "time", "url", "batch_size", "time_grade")},
            "n_adoptions": len(uses[m]),
            "n_agents": len({u["label"] for u in uses[m] if u["label"]}),
            "n_blank": sum(1 for u in uses[m] if not u["label"]),
        }
    for m, o in sorted(origin.items(), key=lambda kv: _ord(kv[1])):
        child = _layer_tokens(m)
        state_idx = body_index(prev_of[o["rev_id"]]["rev_id"]) if o["rev_id"] in prev_of else {}
        state = frozenset(state_idx)
        child_res = {u["sig"]["target_url"] for u in uses[m] if u["rev_id"] == o["rev_id"]}
        child_hosts = {t.split("/", 1)[0] for t in child_res}
        expo = exposure_at.get(o["rev_id"], frozenset())
        cands = []
        for p, po in origin.items():
            if p == m:
                continue
            visible_now = p in state                          # tier A basis
            if _ord(po) >= _ord(o):                            # acyclic by construction
                continue
            # without page evidence the clock must be strictly earlier (same-second order is ambiguous)
            if not visible_now and po["time"] >= o["time"]:
                continue
            d = layer_distance(_layer_tokens(p), child)
            if d > MAX_DIST:
                continue
            level = 0 if (visible_now and d <= ONE_STEP) else 1 if (p in expo and d <= ONE_STEP) else 2
            # does the parent's URL on the page fetch the same resource? (same goal, changed route)
            res = 0
            if visible_now:
                pres = state_idx[p]
                res = 2 if child_res & pres else 1 if child_hosts & {t.split("/", 1)[0] for t in pres} else 0
            cands.append((level, -res, d, -order[p], p))
        if not cands:
            nodes[m]["parent"] = None
            nodes[m]["tier"] = "D"
            nodes[m]["relation"] = "independent"
            continue
        cands.sort()
        best_level, best_res, best_d = cands[0][0], -cands[0][1], cands[0][2]
        tied = [c for c in cands if c[0] == best_level and -c[1] == best_res and c[2] == best_d]
        primary = tied[0][4]  # most recently introduced among equals
        rel, desc = describe_change(_layer_tokens(primary), child)
        tier = "ABC"[best_level]
        # secondary influence: the added layer already existed as its own earlier method
        secondary = []
        if rel == "extend":
            added = desc.split("layer ", 1)[1]
            if added in origin and _ord(origin[added]) < _ord(o) and added != primary:
                secondary.append(added)
        state_url = next(
            (u for u in extract_urls(prev_of[o["rev_id"]]["body"]) if (_sig(u) and _sig(u).method_key == primary)),
            None,
        ) if (o["rev_id"] in prev_of and primary in state) else None
        nodes[m].update(
            {
                "parent": primary,
                "tier": tier,
                "relation": rel,
                "change": desc,
                "distance": best_d,
                "same_resource": best_res == 2,
                "same_host": best_res >= 1,
                "alternates": [c[4] for c in tied[1:6]],
                "n_alternates": len(tied) - 1,
                "secondary_parents": secondary,
                "evidence": {
                    "child_rev_id": o["rev_id"],
                    "child_page": o["page_id"],
                    "child_label": o["label"],
                    "child_time": o["time"],
                    "child_url": o["url"],
                    "prev_rev_id": o["prev_rev_id"],
                    "prev_label": o["prev_label"],
                    "parent_in_prev_state": primary in state,
                    "parent_url_in_prev_state": state_url,
                    "author_exposed_earlier": primary in expo,
                    "parent_origin_rev_id": origin[primary]["rev_id"],
                    "parent_origin_label": origin[primary]["label"],
                    "parent_origin_time": origin[primary]["time"],
                    "parent_origin_url": origin[primary]["url"],
                },
            }
        )
        edges.append({"child": m, "parent": primary, "tier": tier, "relation": rel})
    return {"source": SOURCE, "n_methods": len(nodes), "nodes": nodes, "edges": edges}


def main() -> None:
    result = build()
    OUT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    nodes = result["nodes"].values()
    from collections import Counter

    print("methods", len(result["nodes"]), "edges", len(result["edges"]))
    print("tiers", dict(Counter(n["tier"] for n in nodes)))
    print("relations", dict(Counter(n["relation"] for n in nodes)))
    print("->", OUT)


if __name__ == "__main__":
    main()
