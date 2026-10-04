"""Model-based tracer: learn HOW agents copy from the logs themselves, then answer with probabilities.

For each adoption we consider every earlier carrier. A candidate's prior weight is
    w_i = exp(-lambda * recency_rank_i) * (1 + c_i)^gamma         (recency and popularity preferences)
normalised within its pool (same page / other pages), the pools mixed by theta (share of off-page sources),
times a content likelihood (1-mu)[same behavior] + mu * P(mutation). The parameters (lambda, gamma, theta, mu) are
unknown, so they are estimated by EM using only the observed logs, never the hidden truth:
    E-step  responsibilities pi_ki for every (event, candidate) pair, with c_i the SOFT count of children inferred so far
    M-step  maximise the expected log-likelihood over (lambda, gamma), closed form for theta, 1-D search for mu

The output is a posterior, so we can test calibration: when it says 70%, is it right 70% of the time?
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from backend.bench.methods import Index
from backend.sim.world import World, mutation_kernel


class EMTracer:
    def __init__(self, world: World, iters: int = 6):
        self.world = world
        self.ix = Index(world)
        self.events = sorted(world.obs, key=lambda e: e.t)
        self._prep()
        self.lam, self.gam, self.theta, self.mu, self.keep = 0.0, 0.0, 0.3, 0.3, 0.4
        for _ in range(iters):
            self._estep()
            self._mstep()
        self._estep()
        self.pred = {}
        for k, e in enumerate(self.events):
            if len(self.cand[k]):
                j = int(np.argmax(self.pi[k]))
                self.pred[e.id] = (int(self.cand[k][j]), float(self.pi[k][j]))

    def _prep(self):
        ix = self.ix
        self.cand, self.pool, self.rank, self.same, self.kern = [], [], [], [], []
        self.tmask, self.vsame, self.vprior = [], [], []
        cfg = self.world.cfg
        self.has_values = bool(cfg.n_values)
        if self.has_values:   # population frequency of each inert value (includes copies, so conservative)
            from collections import Counter
            vc = Counter(o.value for o in self.world.obs if o.value is not None)
            tot, distinct = sum(vc.values()), max(cfg.n_values, len(vc))
            self._vfreq = lambda v: (vc.get(v, 0) + 0.5) / (tot + 0.5 * distinct)
        for e in self.events:
            onp = sorted(ix.carriers(e.page, e.t, e.agent), key=lambda f: f.t)
            off = sorted([f for f in self.world.obs if f.t < e.t and f.page != e.page and f.agent != e.agent], key=lambda f: f.t)
            ids, pl, rk, sm, kn = [], [], [], [], []
            for p, pool in ((0, onp), (1, off)):
                n = len(pool)
                for r, f in enumerate(pool):
                    ids.append(f.id); pl.append(p); rk.append(n - 1 - r)
                    sm.append(float(f.variant == e.variant)); kn.append(mutation_kernel(f.variant).get(e.variant, 0.0))
            self.cand.append(np.array(ids)); self.pool.append(np.array(pl)); self.rank.append(np.array(rk, float))
            self.same.append(np.array(sm)); self.kern.append(np.array(kn))
            by = {f.id: f for f in onp + off}
            mask = np.ones(len(ids))
            if cfg.tag_scope == "version" and e.tag_item is not None:
                mask = np.array([1.0 if i == e.tag_item else 0.0 for i in ids])
            elif cfg.tag_scope == "static" and e.tag_item is not None:
                from backend.bench.metrics import static_weight
                cl = [(by[i], 1.0) for i in ids]
                mask = np.array([static_weight(e.tag_item, by[i], cl) for i in ids])
            elif cfg.tag_scope == "page" and e.tag_page is not None:
                mask = np.array([1.0 if by[i].page == e.tag_page else 0.0 for i in ids])
            if len(ids) and mask.sum() == 0:
                mask = np.ones(len(ids))
            self.tmask.append(mask)
            if self.has_values:
                self.vsame.append(np.array([float(by[i].value == e.value) for i in ids]))
                self.vprior.append(np.full(len(ids), self._vfreq(e.value)))
        self.n_on = [int((p == 0).sum()) for p in self.pool]
        self.n_off = [int((p == 1).sum()) for p in self.pool]

    def _prior(self, k, logc):
        """Prior probability of each candidate of event k given current parameters."""
        pl, rk = self.pool[k], self.rank[k]
        if not len(pl):
            return np.array([])
        lw = -self.lam * rk + self.gam * logc
        out = np.zeros(len(pl))
        both = self.n_on[k] > 0 and self.n_off[k] > 0
        for p in (0, 1):
            m = pl == p
            if not m.any():
                continue
            mass = (1 - self.theta if p == 0 else self.theta) if both else 1.0
            z = np.exp(lw[m] - lw[m].max())
            out[m] = mass * z / z.sum()
        return out

    def _estep(self):
        c = defaultdict(float)
        self.pi, self.logc = [], []
        for k, e in enumerate(self.events):
            ids = self.cand[k]
            if not len(ids):
                self.pi.append(np.array([])); self.logc.append(np.array([])); continue
            logc = np.log1p(np.array([c[i] for i in ids]))
            prior = self._prior(k, logc)
            lik = ((1 - self.mu) * self.same[k] + self.mu * self.kern[k]) * self.tmask[k]
            if self.has_values:
                lik = lik * (self.keep * self.vsame[k] + (1 - self.keep) * self.vprior[k])
            post = prior * lik
            z = post.sum()
            post = post / z if z > 0 else prior / prior.sum()
            self.pi.append(post); self.logc.append(logc)
            for i, q in zip(ids, post):
                c[i] += q

    def _mstep(self):
        ev = np.concatenate([np.full(len(p), k) for k, p in enumerate(self.pi)]); n = len(self.events)
        pool = np.concatenate(self.pool).astype(int); rank = np.concatenate(self.rank); logc = np.concatenate(self.logc)
        pi = np.concatenate(self.pi); same = np.concatenate(self.same); kern = np.concatenate(self.kern)
        grp = ev.astype(int) * 2 + pool

        def nll(x):
            lam, gam = x
            lw = -lam * rank + gam * logc
            m = np.full(2 * n, -np.inf); np.maximum.at(m, grp, lw)
            z = np.bincount(grp, np.exp(lw - m[grp]), 2 * n)
            return -np.sum(pi * (lw - m[grp] - np.log(z[grp])))
        r = minimize(nll, [self.lam, self.gam], method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 200})
        self.lam, self.gam = float(np.clip(r.x[0], 0, 8)), float(np.clip(r.x[1], -1, 4))
        both = [k for k in range(n) if self.n_on[k] and self.n_off[k]]
        if both:
            off_mass = sum(self.pi[k][self.pool[k] == 1].sum() for k in both)
            tot = sum(self.pi[k].sum() for k in both)
            self.theta = float(np.clip(off_mass / tot, 0.01, 0.99))
        res = minimize_scalar(lambda mu: -np.sum(pi * np.log((1 - mu) * same + mu * kern + 1e-12)), bounds=(0.01, 0.99), method="bounded")
        self.mu = float(res.x)
        if self.has_values:
            vs, vp = np.concatenate(self.vsame), np.concatenate(self.vprior)
            rk = minimize_scalar(lambda q: -np.sum(pi * np.log(q * vs + (1 - q) * vp + 1e-12)), bounds=(0.01, 0.99), method="bounded")
            self.keep = float(rk.x)

    # method interface used by the benchmark
    def __call__(self, ix, e):
        if e.read_item is not None:
            return [e.read_item], "A"
        if self.world.cfg.tag_scope == "version" and e.tag_item is not None:
            return [e.tag_item], "A"
        got = self.pred.get(e.id)
        if not got:
            return [], "D"
        cid, p = got
        k = self._index[e.id]
        order = np.argsort(-self.pi[k])[:5]
        return [int(self.cand[k][j]) for j in order], ("A" if p >= 0.6 else "B" if p >= 0.3 else "C")

    @property
    def _index(self):
        if not hasattr(self, "_idx"):
            self._idx = {e.id: k for k, e in enumerate(self.events)}
        return self._idx

    def params(self):
        out = {"lambda": self.lam, "gamma": self.gam, "theta": self.theta, "mu": self.mu}
        if self.has_values:
            out["value_keep"] = self.keep
        return out
