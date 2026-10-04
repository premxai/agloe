"""SwarmLineageBench simulator: agents edit shared pages and copy a behavior from carriers.

The simulator emits two separate things:
  * `World.obs`   what an investigator could see (agent, time, page, variant, optional read log)
  * `World.truth` the hidden true parent of every adoption (None for independent invention)

Everything an inference method may use lives in `obs`. `truth` is only for scoring.

Variants are tuples of wrapper-layer tokens in the same "service/style@depth" shape the real pipeline
uses, so the real distance function (`layer_distance`) is reused unchanged.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

N_SERVICES = 14


@dataclass(frozen=True)
class SimConfig:
    n_agents: int = 150
    n_pages: int = 30
    steps: int = 5000
    zipf: float = 1.0            # page popularity skew (hub concentration)
    adopt_rate: float = 0.06     # chance an agent adopts when it visits a page
    invent_rate: float = 0.002   # chance of independent invention per visit
    offpage: float = 0.25        # chance the true source was read on another page (invisible to edit logs)
    copy: str = "uniform"        # uniform | recency | popular | homophily | window  (the last two are outside the tracer's model family)
    kappa: float = 3.0           # homophily: extra weight per page co-visited with the carrier's agent
    window: int = 400            # window: only carriers written within this many steps are really eligible
    recency_lambda: float = 0.7
    mutate: float = 0.35         # chance a copy is also changed
    rho: float = 0.0             # fraction of adoptions whose read is logged
    read_level: str = "item"     # item: log names the source item; page: log names the source page
    seed: int = 0
    # --- copy or coincidence: an inert value on every write, and independent rediscovery (all off by default) ---
    n_values: int = 0            # >0: each write carries an inert value drawn from a focal (Zipf) prior
    value_zipf: float = 1.2      # how hard 'random' choices pile onto a few favourites (model monoculture)
    value_keep: float = 0.4      # a copier keeps its source's value with this probability, else draws afresh
    rediscover: float = 0.0      # an invention reproduces an existing behaviour (convergence) with this probability
    # --- trap streets: tags stamped by the board on served items ---
    tag_scope: str = "none"      # none | version (unique per served version) | static (one per lineage) | page
    tag_keep: float = 0.6        # s: a tag on the copied item survives the copy with this probability
    tau: float = 1.0             # share of sources that sit on the tagged surface


@dataclass
class Obs:
    id: int
    t: int
    agent: int
    page: int
    variant: tuple
    read_item: int | None = None
    read_page: int | None = None
    value: int | None = None      # inert value written alongside (observable)
    tag_item: int | None = None   # tag carried over from the copied item: version -> that item, static -> lineage root
    tag_page: int | None = None   # page-scope tag: the page the copied item was served from


_prior_cache: dict[tuple, list] = {}


def value_prior(cfg: "SimConfig") -> list[float]:
    """Focal prior over inert values: value k is chosen with probability proportional to 1/(k+1)^zipf."""
    key = (cfg.n_values, cfg.value_zipf)
    if key not in _prior_cache:
        w = [1.0 / (k + 1) ** cfg.value_zipf for k in range(cfg.n_values)]
        s = sum(w); _prior_cache[key] = [x / s for x in w]
    return _prior_cache[key]


@dataclass
class World:
    cfg: SimConfig
    obs: list[Obs] = field(default_factory=list)
    truth: dict[int, int | None] = field(default_factory=dict)       # event id -> true parent id
    visits: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # agent -> [(t, page)] logged edits
    onpage_at_adoption: dict[int, int] = field(default_factory=dict)  # event id -> m visible on-page carriers


def _tok(svc: int, depth: int) -> str:
    return f"s{svc}/x@{depth}"


def _mutate(variant: tuple, rng: random.Random) -> tuple:
    v = list(variant)
    op = rng.choice(["extend", "substitute", "reencode"]) if v else "extend"
    if op == "extend" and len(v) < 4:
        v.insert(rng.randrange(len(v) + 1), _tok(rng.randrange(N_SERVICES), rng.randrange(3)))
    elif op == "substitute" and v:
        i = rng.randrange(len(v)); v[i] = _tok(rng.randrange(N_SERVICES), int(v[i].rsplit("@", 1)[1]))
    elif v:
        i = rng.randrange(len(v)); svc = v[i].split("/", 1)[0][1:]; v[i] = _tok(int(svc), rng.randrange(3))
    return tuple(v)


def _pages_before(visits: dict, agent: int, t: int) -> set:
    return {pg for tt, pg in visits[agent] if tt < t}


def _weights(pool: list[Obs], cfg: SimConfig, copies: Counter, ctx=None) -> list[float]:
    """Copy preference. ctx = (copying agent, time, visits) for rules that depend on who is copying."""
    n = len(pool)
    if cfg.copy == "uniform":
        return [1.0] * n
    if cfg.copy == "recency":   # pool is sorted oldest -> newest
        return [math.exp(-cfg.recency_lambda * (n - 1 - i)) for i in range(n)]
    if cfg.copy == "popular":
        return [1.0 + copies[e.id] for e in pool]
    if cfg.copy == "homophily":  # prefer carriers by agents who edited the same pages as me
        agent, t, visits = ctx
        mine = _pages_before(visits, agent, t)
        cache: dict[int, int] = {}
        out = []
        for e in pool:
            if e.agent not in cache:
                cache[e.agent] = len(mine & _pages_before(visits, e.agent, t))
            out.append(1.0 + cfg.kappa * cache[e.agent])
        return out
    if cfg.copy == "window":     # hard recency cutoff
        agent, t, visits = ctx
        return [1.0 if t - e.t <= cfg.window else 1e-3 for e in pool]
    raise ValueError(cfg.copy)


def source_posterior(pool: list[Obs], cfg: SimConfig, copies: Counter, ctx=None) -> list[float]:
    w = _weights(pool, cfg, copies, ctx); s = sum(w)
    return [x / s for x in w]


def simulate(cfg: SimConfig) -> World:
    rng = random.Random(cfg.seed)
    page_w = [1.0 / (i + 1) ** cfg.zipf for i in range(cfg.n_pages)]
    w = World(cfg)
    by_page: dict[int, list[Obs]] = defaultdict(list)
    adopted: set[int] = set()
    copies: Counter = Counter()
    w.visits = {a: [] for a in range(cfg.n_agents)}

    prior = value_prior(cfg) if cfg.n_values else None
    root: dict[int, int] = {}

    def draw_value():
        return rng.choices(range(cfg.n_values), prior)[0]

    def emit(t, a, pg, variant, parent, src_page, onpage_m):
        e = Obs(len(w.obs), t, a, pg, variant)
        if parent is not None and rng.random() < cfg.rho:
            if cfg.read_level == "item":
                e.read_item = parent
            else:
                e.read_page = src_page
        if cfg.n_values:  # inert value: inherited from the source with prob value_keep, else a fresh 'random' pick
            src_val = w.obs[parent].value if parent is not None else None
            e.value = src_val if (parent is not None and rng.random() < cfg.value_keep) else draw_value()
        root[e.id] = root[parent] if parent is not None else e.id
        if cfg.tag_scope != "none" and parent is not None:
            if rng.random() < cfg.tau and rng.random() < cfg.tag_keep:
                if cfg.tag_scope == "version":
                    e.tag_item = parent
                elif cfg.tag_scope == "static":
                    e.tag_item = root[parent]
                else:
                    e.tag_page = src_page
        w.obs.append(e); w.truth[e.id] = parent; by_page[pg].append(e); adopted.add(a)
        if parent is not None:
            copies[parent] += 1
            w.onpage_at_adoption[e.id] = onpage_m
        return e

    # one seed invention so something can spread
    emit(0, rng.randrange(cfg.n_agents), rng.choices(range(cfg.n_pages), page_w)[0], (_tok(rng.randrange(N_SERVICES), 1),), None, None, 0)
    for t in range(1, cfg.steps + 1):
        a = rng.randrange(cfg.n_agents)
        pg = rng.choices(range(cfg.n_pages), page_w)[0]
        w.visits[a].append((t, pg))                      # every visit is a logged edit
        if a in adopted:
            continue
        onpage = [e for e in by_page[pg] if e.agent != a]
        if rng.random() < cfg.adopt_rate and w.obs:
            use_off = rng.random() < cfg.offpage or not onpage
            pool = [e for e in w.obs if e.page != pg and e.agent != a] if use_off else onpage
            pool = pool or onpage
            if pool:
                pool = sorted(pool, key=lambda e: e.t)
                src = rng.choices(pool, _weights(pool, cfg, copies, (a, t, w.visits)))[0]
                variant = _mutate(src.variant, rng) if rng.random() < cfg.mutate else src.variant
                emit(t, a, pg, variant, src.id, src.page, len(onpage))
                continue
        if rng.random() < cfg.invent_rate:
            if cfg.rediscover and w.obs and rng.random() < cfg.rediscover:
                variant = rng.choice(w.obs).variant          # convergence: same behaviour, found independently
            else:
                variant = (_tok(rng.randrange(N_SERVICES), rng.randrange(3)),)
            emit(t, a, pg, variant, None, None, 0)
    return w


# ---------- exact likelihood of the mutation process (used by the Bayes oracle) ----------
_kernel_cache: dict[tuple, dict] = {}


def mutation_kernel(v: tuple) -> dict:
    """P(result | parent variant v) for one call of _mutate, enumerated exactly."""
    if v in _kernel_cache:
        return _kernel_cache[v]
    out: dict[tuple, float] = defaultdict(float)
    n = len(v)
    if n == 0:
        ops = {"extend": 1.0}
    elif n < 4:
        ops = {"extend": 1 / 3, "substitute": 1 / 3, "reencode": 1 / 3}
    else:                       # extend at max length falls through to the re-encode branch
        ops = {"substitute": 1 / 3, "reencode": 2 / 3}
    for op, po in ops.items():
        if op == "extend":
            for pos in range(n + 1):
                for svc in range(N_SERVICES):
                    for d in range(3):
                        out[v[:pos] + (_tok(svc, d),) + v[pos:]] += po / (n + 1) / N_SERVICES / 3
        elif op == "substitute":
            for i in range(n):
                depth = int(v[i].rsplit("@", 1)[1])
                for svc in range(N_SERVICES):
                    out[v[:i] + (_tok(svc, depth),) + v[i + 1:]] += po / n / N_SERVICES
        else:
            for i in range(n):
                svc = int(v[i].split("/", 1)[0][1:])
                for d in range(3):
                    out[v[:i] + (_tok(svc, d),) + v[i + 1:]] += po / n / 3
    _kernel_cache[v] = dict(out)
    return _kernel_cache[v]


def likelihood(parent_v: tuple, child_v: tuple, mu: float) -> float:
    """P(child variant | parent variant): exact copy w.p. 1-mu, else one mutation step."""
    return (1 - mu) * (child_v == parent_v) + mu * mutation_kernel(parent_v).get(child_v, 0.0)
