"""Scoring and the Bayes ceiling for SwarmLineageBench."""
from __future__ import annotations

from collections import Counter, defaultdict

from backend.bench.methods import Index
from backend.sim.world import World, likelihood, source_posterior, value_prior


def value_likelihood(src_value, value, keep: float, prior: list) -> float:
    """P(copier's inert value | it copied a source holding src_value): kept, or a fresh draw from the prior."""
    return keep * (value == src_value) + (1 - keep) * prior[value]


def static_weight(root, f, cand) -> float:
    """How likely candidate f belongs to the lineage named by a static tag.

    A static tag only names the lineage root. Visible members (f is the root or carries the same tag) fit;
    a candidate carrying a different tag cannot; an untagged candidate may be a member that dropped its tag,
    weighted by the root's share among tagged candidates."""
    if f.id == root or f.tag_item == root:
        return 1.0
    if f.tag_item is not None:
        return 0.0
    tagged = [g for g, _ in cand if g.tag_item is not None or g.id == root]
    members = sum(1 for g in tagged if g.tag_item == root or g.id == root)
    return (members + 1) / (len(tagged) + 2)


def tag_filter(cfg, e, cand):
    """Narrow candidates using a surviving board tag (observable on the copier's write)."""
    if cfg.tag_scope == "version" and e.tag_item is not None:
        hit = [(f, w) for f, w in cand if f.id == e.tag_item]
        return hit or cand
    if cfg.tag_scope == "static" and e.tag_item is not None:
        return [(f, w * static_weight(e.tag_item, f, cand)) for f, w in cand]
    if cfg.tag_scope == "page" and e.tag_page is not None:
        hit = [(f, w) for f, w in cand if f.page == e.tag_page]
        return hit or cand
    return cand


def posterior_all(world: World, ix: Index, e, content: bool = True, use_reads: bool = False):
    """Exact posterior over the true parent of adoption `e` given everything an edit log can show.

    Mirrors the generative process: with prob (1-offpage) the source is drawn from the visible on-page carriers,
    otherwise from carriers on other pages; weights follow the copy model; the child's variant adds the
    mutation likelihood (content=True). Returns [(parent_id, prob)].
    """
    cfg = world.cfg
    copies = Counter(world.truth[f.id] for f in world.obs if f.t < e.t and world.truth[f.id] is not None)
    onp = sorted(ix.carriers(e.page, e.t, e.agent), key=lambda f: f.t)
    off = sorted([f for f in world.obs if f.t < e.t and f.page != e.page and f.agent != e.agent], key=lambda f: f.t)
    if not onp:
        p_on, p_off = 0.0, 1.0
    elif not off:
        p_on, p_off = 1.0, 0.0
    else:
        p_on, p_off = 1 - cfg.offpage, cfg.offpage
    cand = []
    for pool, mass in ((onp, p_on), (off, p_off)):
        if not pool or mass == 0:
            continue
        pw = source_posterior(pool, cfg, copies, (e.agent, e.t, world.visits))
        for f, w in zip(pool, pw):
            cand.append((f, mass * w))
    if use_reads and e.read_item is not None:
        return [(e.read_item, 1.0)]
    if use_reads and e.read_page is not None:
        cand = [(f, w) for f, w in cand if f.page == e.read_page]
    cand = tag_filter(cfg, e, cand)
    if content:
        cand = [(f, w * likelihood(f.variant, e.variant, cfg.mutate)) for f, w in cand]
    if content and cfg.n_values and e.value is not None:
        pr = value_prior(cfg)
        cand = [(f, w * value_likelihood(f.value, e.value, cfg.value_keep, pr)) for f, w in cand]
    z = sum(w for _, w in cand)
    return [(f if isinstance(f, int) else f.id, w / z) for f, w in cand] if z > 0 else []


def bayes_ceiling(world: World, ix: Index, use_reads: bool = False, content: bool = True) -> dict:
    """Expected top-1 accuracy of the Bayes-optimal guesser (it knows the copy model) on the logs we can see.

    No method that sees the same logs can beat this in expectation. content=False gives the ceiling for a
    tracer that ignores what the agent wrote (it reduces to E[1/m] under uniform copying with no off-page sources).
    """
    total = hits = 0.0
    for e in world.obs:
        if world.truth[e.id] is None:
            continue
        total += 1
        post = posterior_all(world, ix, e, content=content, use_reads=use_reads)
        if post:
            hits += max(w for _, w in post)
    return {"n": int(total), "ceiling": hits / total if total else 0.0}


def evaluate(world: World, ix: Index, method) -> dict:
    n = top1 = top3 = var_ok = answered = 0
    tier_n, tier_ok, tier_var = Counter(), Counter(), Counter()
    for e in world.obs:
        parent = world.truth[e.id]
        if parent is None:
            continue
        n += 1
        ranked, tier = method(ix, e)
        if not ranked:
            continue
        answered += 1
        tier_n[tier] += 1
        if ranked[0] == parent:
            top1 += 1; tier_ok[tier] += 1
        if parent in ranked[:3]:
            top3 += 1
        if ix.by_id[ranked[0]].variant == ix.by_id[parent].variant:
            var_ok += 1; tier_var[tier] += 1
    return {
        "n": n, "top1": top1 / n if n else 0.0, "top3": top3 / n if n else 0.0,
        "variant_ok": var_ok / n if n else 0.0, "coverage": answered / n if n else 0.0,
        "precision": top1 / answered if answered else 0.0,
        "tier_precision": {t: tier_ok[t] / tier_n[t] for t in tier_n}, "tier_n": dict(tier_n),
        "tier_variant_ok": {t: tier_var[t] for t in tier_n}, "tier_ok": dict(tier_ok),
    }
