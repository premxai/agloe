"""Self-excitation of adoptions, controlled for overall swarm activity.

Model: adoption intensity  lambda(t) = mu0 * A(t)/mean(A) + alpha * sum_i beta * exp(-beta (t - t_i)).
A(t) is how many edits the whole swarm made around t, so a burst that simply tracks "more agents were awake" is
absorbed by the baseline instead of being read as agents triggering each other.  alpha is the branching ratio:
expected number of later adoptions directly triggered by one adoption.  alpha near 1 means a self-sustaining
cascade; alpha near 0 means adoptions were driven from outside.

Limits: A(t) includes the adopters' own edits, and common outside triggers (a shared prompt, a scheduled start)
are indistinguishable from imitation.  Treat alpha as an upper-leaning estimate of imitation, not proof of it.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
from scipy.optimize import minimize

TS = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def activity_baseline(edit_times: list[float], t0: float, T: float, bin_s: float = 600.0):
    """Edits per bin over [t0, t0+T], normalised to mean 1 (never zero, so the likelihood stays finite)."""
    nb = int(np.ceil(T / bin_s))
    a = np.zeros(nb)
    for x in edit_times:
        k = int((x - t0) // bin_s)
        if 0 <= k < nb:
            a[k] += 1
    a = a + 0.5
    return a / a.mean(), bin_s


def _nll(params, t, T, base, bin_s, alpha_fixed=None):
    mu0, beta = np.exp(params[0]), np.exp(params[1])
    alpha = alpha_fixed if alpha_fixed is not None else np.exp(params[2])
    A, ll = 0.0, 0.0
    for i, ti in enumerate(t):
        if i:
            A = np.exp(-beta * (ti - t[i - 1])) * (1 + A)
        ll += np.log(mu0 * base[min(len(base) - 1, int(ti // bin_s))] + alpha * beta * A)
    comp = mu0 * base.sum() * bin_s * (T / (len(base) * bin_s)) + alpha * np.sum(1 - np.exp(-beta * (T - t)))
    return -(ll - comp)


def fit(times: list[float], edit_times: list[float], controlled: bool = True, grid=None) -> dict:
    t0 = min(times)
    t = np.sort(np.array(times) - t0)
    T = float(t[-1] + 60)
    if controlled:
        base, bin_s = activity_baseline(edit_times, t0, T)
    else:
        base, bin_s = np.ones(int(np.ceil(T / 600.0))), 600.0
    starts = [(1e-3, 1e-2, 0.5), (5e-4, 2e-3, 0.8), (2e-3, 5e-2, 0.3), (2e-4, 5e-4, 0.9)]
    best = None
    for s in starts:
        r = minimize(_nll, np.log(s), args=(t, T, base, bin_s), method="Nelder-Mead", options={"maxiter": 3000, "xatol": 1e-6, "fatol": 1e-9})
        if best is None or r.fun < best.fun:
            best = r
    mu0, beta, alpha = np.exp(best.x)
    # profile likelihood for alpha: 95% interval where the log-likelihood is within 1.92 of the maximum
    grid = np.linspace(0.0, 1.5, 31) if grid is None else grid
    prof = []
    for a in grid:
        rr = min((minimize(_nll, np.log(s[:2]), args=(t, T, base, bin_s, a), method="Nelder-Mead", options={"maxiter": 1500}) for s in starts[:2]), key=lambda r: r.fun)
        prof.append(-rr.fun)
    prof = np.array(prof)
    ok = grid[prof >= prof.max() - 1.92]
    return {"alpha": float(alpha), "alpha_ci95": [float(ok.min()), float(ok.max())], "mu0_per_h": float(mu0 * 3600),
            "decay_minutes": float(1 / beta / 60), "n": len(t), "nll": float(best.fun),
            "loglik_gain_vs_no_excitation": float(prof.max() - prof[0])}
