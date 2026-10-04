"""Inference methods for SwarmLineageBench. Each sees ONLY `world.obs` and `world.visits`, never `world.truth`.

A method returns, per adoption event, a ranked list of candidate parent ids and an evidence tier
(A direct / B supported / C possible / D abstain). An empty list means "I cannot tell".
"""
from __future__ import annotations

import random
from bisect import bisect_left
from collections import defaultdict

from backend.analysis.lineage import layer_distance
from backend.sim.world import World

Pred = tuple[list[int], str]


class Index:
    def __init__(self, world: World):
        self.world = world
        self.by_page = defaultdict(list)
        for e in sorted(world.obs, key=lambda e: e.t):
            self.by_page[e.page].append(e)
        self.times = {p: [e.t for e in lst] for p, lst in self.by_page.items()}
        self.by_id = {e.id: e for e in world.obs}

    def carriers(self, page: int, t: int, exclude_agent: int) -> list:
        lst = self.by_page.get(page, [])
        k = bisect_left(self.times.get(page, []), t)
        return [f for f in lst[:k] if f.agent != exclude_agent]

    def exposure(self, e) -> list:
        """Carriers on pages this agent edited earlier, as they stood at that moment (not on e's own page)."""
        seen = {}
        for t, pg in self.world.visits[e.agent]:
            if t >= e.t:
                break
            if pg == e.page:
                continue
            for f in self.carriers(pg, t, e.agent):
                seen[f.id] = f
        return list(seen.values())


def earliest(ix: Index, e) -> Pred:
    c = ix.carriers(e.page, e.t, e.agent)
    return ([min(c, key=lambda f: f.t).id], "C") if c else ([], "D")


def latest(ix: Index, e) -> Pred:
    c = ix.carriers(e.page, e.t, e.agent)
    return ([max(c, key=lambda f: f.t).id], "C") if c else ([], "D")


def random_pick(ix: Index, e, rng=random.Random(1)) -> Pred:
    c = ix.carriers(e.page, e.t, e.agent)
    return ([rng.choice(c).id], "C") if c else ([], "D")


def most_similar(ix: Index, e) -> Pred:
    c = ix.carriers(e.page, e.t, e.agent)
    if not c:
        return [], "D"
    best = min(c, key=lambda f: (layer_distance(f.variant, e.variant), -f.t))
    return [best.id], "C"


def _ranked(cands, e):
    """Same ranking rule as the real tracer: evidence level, then edit distance, then recency."""
    out = []
    for level, f in cands:
        d = layer_distance(f.variant, e.variant)
        if d <= 1.5:
            out.append(((level if d <= 1.0 else 2), d, -f.t, f.id))
    out.sort()
    return out


def ours(ix: Index, e, use_reads: bool = True) -> Pred:
    if use_reads and e.read_item is not None:
        return [e.read_item], "A"
    cfg = ix.world.cfg
    if cfg.tag_scope == "version" and e.tag_item is not None:
        return [e.tag_item], "A"
    if use_reads and e.read_page is not None:
        pool = [(0, f) for f in ix.carriers(e.read_page, e.t, e.agent)]
    elif cfg.tag_scope == "page" and e.tag_page is not None:
        pool = [(0, f) for f in ix.carriers(e.tag_page, e.t, e.agent)]
    elif cfg.tag_scope == "static" and e.tag_item is not None:
        members = [f for f in ix.world.obs if f.t < e.t and f.agent != e.agent and (f.id == e.tag_item or f.tag_item == e.tag_item)]
        pool = [(0, f) for f in members]
    else:
        onp = ix.carriers(e.page, e.t, e.agent)
        ids = {f.id for f in onp}
        pool = [(0, f) for f in onp] + [(1, f) for f in ix.exposure(e) if f.id not in ids]
    r = _ranked(pool, e)
    if not r:
        return [], "D"
    return [x[3] for x in r[:5]], "ABC"[r[0][0]]


def ours_no_reads(ix: Index, e) -> Pred:
    return ours(ix, e, use_reads=False)


METHODS = {
    "random": random_pick,
    "earliest": earliest,
    "latest": latest,
    "most_similar": most_similar,
    "ours_no_reads": ours_no_reads,
    "ours": ours,
}


def make_oracle(world: World, use_reads: bool = False, content: bool = True, seed: int = 7):
    """Bayes-optimal guess (posterior mode, random tie-break). It knows the copy and mutation model, so it is not
    a usable method: it exists to measure, empirically, the best any method could do on these logs."""
    import random as _r
    from backend.bench.metrics import posterior_all
    rng = _r.Random(seed)

    def oracle(ix: Index, e) -> Pred:
        post = posterior_all(world, ix, e, content=content, use_reads=use_reads)
        if not post:
            return [], "D"
        top = max(w for _, w in post)
        best = [i for i, w in post if abs(w - top) < 1e-12]
        return [rng.choice(best)], "A"
    return oracle
