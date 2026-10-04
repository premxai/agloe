"""SwarmLineageBench invariants. These guard the claims the paper makes."""
from dataclasses import replace

import pytest

from backend.bench.methods import METHODS, Index, make_oracle
from backend.bench.metrics import bayes_ceiling, evaluate
from backend.sim.world import SimConfig, likelihood, mutation_kernel, simulate

BASE = SimConfig(n_agents=300, n_pages=25, steps=9000)


def test_truth_is_causally_consistent():
    w = simulate(replace(BASE, rho=0.5, seed=3))
    by_id = {e.id: e for e in w.obs}
    assert len(w.obs) > 50
    for e in w.obs:
        p = w.truth[e.id]
        if p is not None:
            assert by_id[p].t < e.t and by_id[p].agent != e.agent
        if e.read_item is not None:
            assert e.read_item == p


def test_mutation_kernel_is_a_distribution():
    for v in [(), ("s1/x@0",), ("s1/x@0", "s2/x@1", "s3/x@2", "s4/x@0")]:
        assert sum(mutation_kernel(v).values()) == pytest.approx(1.0)
    assert likelihood(("s1/x@0",), ("s1/x@0",), 0.35) > 0.64


@pytest.mark.parametrize("copy", ["uniform", "recency", "popular"])
def test_oracle_matches_bayes_ceiling(copy):
    """Theorem 1, checked by simulation: the best guesser's measured accuracy equals the formula."""
    hit = ceil = n = 0.0
    for seed in range(8):
        w = simulate(replace(BASE, copy=copy, seed=seed)); ix = Index(w)
        c = bayes_ceiling(w, ix); r = evaluate(w, ix, make_oracle(w, seed=seed))
        ceil += c["ceiling"] * c["n"]; hit += r["top1"] * r["n"]; n += c["n"]
    se = (0.5 * 0.5 / n) ** 0.5
    assert abs(hit / n - ceil / n) < 3.5 * se


def test_no_method_beats_the_ceiling():
    for copy in ("uniform", "recency"):
        n = ceil = 0.0
        hits = {k: 0.0 for k in ("earliest", "latest", "most_similar", "ours")}
        for seed in range(8):
            w = simulate(replace(BASE, copy=copy, seed=seed)); ix = Index(w)
            c = bayes_ceiling(w, ix); n += c["n"]; ceil += c["ceiling"] * c["n"]
            for name in hits:
                r = evaluate(w, ix, METHODS[name]); hits[name] += r["top1"] * r["n"]
        for name, h in hits.items():
            assert h / n <= ceil / n + 3.5 * (0.25 / n) ** 0.5, (copy, name)


def test_methods_never_read_the_hidden_truth():
    """Replace truth with garbage: every method must give identical answers."""
    w = simulate(replace(BASE, rho=0.3, seed=5)); ix = Index(w)
    before = {name: [m(ix, e) for e in w.obs] for name, m in METHODS.items() if name != "random"}
    w.truth = {k: -1 for k in w.truth}
    after = {name: [m(ix, e) for e in w.obs] for name, m in METHODS.items() if name != "random"}
    assert before == after


def test_reading_items_beats_reading_pages():
    res = {}
    for level in ("item", "page"):
        n = c = 0.0
        for seed in range(6):
            w = simulate(replace(BASE, rho=1.0, read_level=level, seed=seed)); ix = Index(w)
            r = bayes_ceiling(w, ix, use_reads=True); n += r["n"]; c += r["ceiling"] * r["n"]
        res[level] = c / n
    assert res["item"] > 0.95 and res["item"] > res["page"] + 0.2


def test_more_evidence_means_more_precision():
    a = b = na = nb = 0.0
    for seed in range(10):
        w = simulate(replace(BASE, seed=seed)); ix = Index(w); r = evaluate(w, ix, METHODS["ours"])
        a += r["tier_ok"].get("A", 0); na += r["tier_n"].get("A", 0)
        b += r["tier_ok"].get("B", 0); nb += r["tier_n"].get("B", 0)
    assert na > 200 and nb > 20
    assert a / na > b / nb


def test_model_based_tracer_reaches_the_ceiling_and_is_calibrated():
    from backend.bench.em import EMTracer
    n = hit = ceil = 0.0
    bins = {}
    for seed in range(6):
        w = simulate(replace(BASE, seed=seed)); ix = Index(w)
        em = EMTracer(w)
        r = evaluate(w, ix, em); c = bayes_ceiling(w, ix)
        n += r["n"]; hit += r["top1"] * r["n"]; ceil += c["ceiling"] * c["n"]
        for e in w.obs:
            if w.truth[e.id] is not None and e.id in em.pred:
                cid, p = em.pred[e.id]; b = min(4, int(p * 5)); a = bins.setdefault(b, [0, 0, 0.0])
                a[0] += 1; a[1] += int(cid == w.truth[e.id]); a[2] += p
    assert hit / n > ceil / n - 0.04 and hit / n < ceil / n + 3.5 * (0.25 / n) ** 0.5
    ece = sum(abs(a[1] / a[0] - a[2] / a[0]) * a[0] for a in bins.values()) / sum(a[0] for a in bins.values())
    assert ece < 0.05, ece


def test_model_based_tracer_never_reads_the_hidden_truth():
    from backend.bench.em import EMTracer
    w = simulate(replace(BASE, seed=2))
    a = EMTracer(w).pred
    w.truth = {k: -1 for k in w.truth}
    assert EMTracer(w).pred == a


def test_theorem_2_reads_formula():
    """ceiling(rho) = rho + (1 - rho) * ceiling(0) when each copy's source item is logged with probability rho."""
    def ceil(rho):
        n = c = 0.0
        for seed in range(8):
            w = simulate(replace(BASE, rho=rho, seed=seed)); ix = Index(w)
            r = bayes_ceiling(w, ix, use_reads=True); n += r["n"]; c += r["ceiling"] * r["n"]
        return c / n
    c0 = ceil(0.0)
    for rho in (0.25, 0.5):
        assert abs(ceil(rho) - (rho + (1 - rho) * c0)) < 0.03


@pytest.mark.parametrize("copy", ["homophily", "window"])
def test_oracle_matches_ceiling_for_rules_outside_the_tracers_family(copy):
    hit = ceil = n = 0.0
    for seed in range(8):
        w = simulate(replace(BASE, copy=copy, seed=seed)); ix = Index(w)
        c = bayes_ceiling(w, ix); r = evaluate(w, ix, make_oracle(w, seed=seed))
        ceil += c["ceiling"] * c["n"]; hit += r["top1"] * r["n"]; n += c["n"]
    assert abs(hit / n - ceil / n) < 3.5 * (0.25 / n) ** 0.5


@pytest.mark.parametrize("copy", ["homophily", "window"])
def test_model_based_tracer_degrades_gracefully_when_the_rule_is_unexpected(copy):
    from backend.bench.em import EMTracer
    hit = ceil = n = 0.0
    for seed in range(6):
        w = simulate(replace(BASE, copy=copy, offpage=0.85, seed=seed)); ix = Index(w)
        em = EMTracer(w); r = evaluate(w, ix, em); c = bayes_ceiling(w, ix)
        hit += r["top1"] * r["n"]; ceil += c["ceiling"] * c["n"]; n += r["n"]
    assert hit / ceil > 0.8


# ---------------------------------------------------------------- trap streets and copy-vs-rediscovery

def _pooled(cfg, seeds, method_name=None):
    n = c = hit = 0.0
    for sd in range(seeds):
        w = simulate(replace(cfg, seed=sd)); ix = Index(w)
        r = bayes_ceiling(w, ix); n += r["n"]; c += r["ceiling"] * r["n"]
        if method_name:
            from backend.bench.em import EMTracer
            m = EMTracer(w) if method_name == "em" else make_oracle(w, seed=sd)
            ev = evaluate(w, ix, m); hit += ev["top1"] * ev["n"]
    return c / n, hit / n if method_name else None


def test_version_tags_follow_the_formula():
    """Prop 3: with version-unique tags surviving with prob s, ceiling = s + (1-s) C0."""
    c0, _ = _pooled(BASE, 6)
    for s in (0.3, 0.6):
        c, _ = _pooled(replace(BASE, tag_scope="version", tag_keep=s), 6)
        assert abs(c - (s + (1 - s) * c0)) < 0.02, (s, c, c0)


def test_tag_design_ranking_version_beats_page_beats_static():
    s = 0.6
    v, _ = _pooled(replace(BASE, tag_scope="version", tag_keep=s), 4)
    p, _ = _pooled(replace(BASE, tag_scope="page", tag_keep=s), 4)
    st, _ = _pooled(replace(BASE, tag_scope="static", tag_keep=s), 4)
    c0, _ = _pooled(BASE, 4)
    assert v > p + 0.15 and p > c0 and st < p and st > c0 - 0.03


def test_oracle_matches_ceiling_with_tags_and_values():
    for cfg in (replace(BASE, tag_scope="static", tag_keep=0.6), replace(BASE, n_values=30, value_keep=0.4)):
        c, o = _pooled(cfg, 6, "oracle")
        assert abs(c - o) < 0.03, (cfg.tag_scope, c, o)


def test_naive_matching_falsely_accuses_more_as_agents_think_alike():
    from backend.bench.convergence import rates, score
    from backend.bench.em import EMTracer
    cb = replace(BASE, invent_rate=0.01, rediscover=0.5, n_values=50, value_keep=0.4)
    out = {}
    for z in (0.0, 2.0):
        rows = []
        for sd in range(4):
            w = simulate(replace(cb, value_zipf=z, seed=sd)); rows += score(w, EMTracer(w).keep)["rows"]
        out[z] = rates(rows, 10.0)
    assert out[2.0]["naive"]["false_call_rate"] > out[0.0]["naive"]["false_call_rate"] + 0.2
    assert out[2.0]["calibrated"]["false_call_rate"] < 0.05
    assert out[2.0]["identical"]["false_call_rate"] == 1.0


def test_new_features_off_by_default_do_not_change_worlds():
    a = simulate(replace(BASE, seed=11)); b = simulate(replace(BASE, seed=11, tag_scope="none", n_values=0, rediscover=0.0))
    assert [(o.t, o.agent, o.variant) for o in a.obs] == [(o.t, o.agent, o.variant) for o in b.obs]
