"""The branching-ratio estimator must (a) recover a known alpha and (b) not mistake an activity wave for imitation."""
import numpy as np

from backend.analysis.hawkes import fit


def _simulate(alpha, beta, mu0, base, bin_s, rng):
    T = len(base) * bin_s
    imm = []
    for k, b in enumerate(base):                       # inhomogeneous Poisson immigrants
        n = rng.poisson(mu0 * b * bin_s)
        imm += list(k * bin_s + rng.uniform(0, bin_s, n))
    out, frontier = list(imm), list(imm)
    while frontier:
        nxt = []
        for t in frontier:
            for _ in range(rng.poisson(alpha)):
                c = t + rng.exponential(1 / beta)
                if c < T:
                    nxt.append(c)
        out += nxt; frontier = nxt
    return np.sort(np.array(out)), T


def _activity_edits(base, bin_s, rng):
    edits = []
    for k, b in enumerate(base):
        edits += list(k * bin_s + rng.uniform(0, bin_s, int(400 * b)))
    return edits


def test_recovers_known_alpha_and_ignores_activity_waves():
    rng = np.random.default_rng(4)
    bin_s = 600.0
    base = np.concatenate([np.full(6, 0.4), np.full(6, 2.2), np.full(6, 0.6)]); base = base / base.mean()
    edits = _activity_edits(base, bin_s, rng)
    # (b) no imitation at all, only an activity wave
    t0, T = _simulate(0.0, 1 / 300, 0.012, base, bin_s, rng)
    r0 = fit(list(t0 + 1e9), [e + 1e9 for e in edits], controlled=False)
    c0 = fit(list(t0 + 1e9), [e + 1e9 for e in edits], controlled=True)
    assert r0["alpha"] > 0.3, "uncontrolled fit should be fooled by the wave (that is why we control)"
    assert c0["alpha"] < 0.25 and c0["alpha_ci95"][0] <= 0.1
    # (a) true alpha 0.6
    t1, _ = _simulate(0.6, 1 / 300, 0.006, base, bin_s, rng)
    c1 = fit(list(t1 + 1e9), [e + 1e9 for e in edits], controlled=True)
    assert c1["alpha_ci95"][0] <= 0.6 <= c1["alpha_ci95"][1], c1
