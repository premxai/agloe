"""Copy or coincidence? Neutral features, model-specific base rates, and accidental tags.

Arbitrary URL parameters (cache-busters, made-up ids: `?x=1`, `&_=17818045`) do nothing for the request, so they
behave like tags. Two questions:

  1. When a later agent repeats an earlier agent's arbitrary value, is that copying or coincidence?
     A match only proves copying if the value is rare *for this population of agents*. LLM agents share priors
     ("random" picks like 1, 123, 999), so base rates must be estimated from the agents themselves:
     for every URL structure we take the FIRST writer's values. The first writer of a structure cannot have
     copied that structure, so these values approximate independent choices ("first-in-structure choosers").
     Likelihood ratio for a match:  LR = 1 / p_v.   Expected coincidental matches over many comparisons = sum p_v.

  2. When an agent reuses an earlier URL that carried an arbitrary value, how often does the value survive?
     That is the survival rate s a defender-planted tag would have (the 'trap street' ingredient), corrected for
     chance matches:  s = (kept - sum p_v) / (n - sum p_v).

Everything here reads logs only; nothing is fetched.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from backend.analysis.signatures import extract_urls, unquote_n

# Only parameters known to be inert count as neutral: cache-busters and dummies. Everything else (wiki actions,
# API options such as lang/filters/template/strip) can change what is fetched, so equal values prove nothing.
INERT = {"_", "x", "cb", "nocache", "cachebust", "cachebuster", "bust", "buster", "rand", "random", "nonce",
         "foo", "bar", "z", "dummy", "ignore", "unused", "cbust", "ts_", "r"}
PARAM = re.compile(r"[?&]([A-Za-z_][\w\-.]{0,30})=([^&#\s\]\)\"'<>|]*)")
FOCAL = re.compile(r"^(0|1|2|3|7|42|69|123|1234|12345|111|222|333|444|555|666|777|888|999|100|1000|456|789|"
                   r"abc|test|foo|bar|baz|x|y|z|yes|true|1\.0|v1|html|\.html|new|newone|a|b)$", re.I)


@dataclass(frozen=True)
class Write:
    """One URL added by a named agent."""
    agent: str
    t: str
    order: tuple      # (time, rev_id) for a strict global order
    page: str
    url: str


def arbitrary_params(url: str) -> list[tuple[str, str]]:
    """(name, value) pairs of non-functional parameters anywhere in the (decoded) URL."""
    d = unquote_n(url, 3)
    out = []
    for name, val in PARAM.findall(d):
        n = name.lower()
        if n in INERT and val:
            out.append((n, val))
    return out


def structure(url: str) -> str:
    """The URL with arbitrary values blanked: two URLs with the same structure make the same request."""
    d = unquote_n(url, 3)

    def blank(m):
        n = m.group(1).lower()
        return m.group(0)[: m.group(0).index("=") + 1] if n in INERT else m.group(0)
    return PARAM.sub(blank, d)


def high_entropy(v: str) -> bool:
    """A value no two agents are likely to pick independently: long and mixed, or a long digit run (timestamps)."""
    if FOCAL.match(v):
        return False
    return (len(v) >= 8 and bool(re.search(r"\d", v)) and bool(re.search(r"[A-Za-z]", v))) or bool(re.fullmatch(r"\d{7,}(\.\d+)?", v))


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (max(0.0, c - h), min(1.0, c + h))


@dataclass
class BaseRates:
    """p_v per parameter name, estimated from first-in-structure choosers with add-alpha smoothing."""
    counts: dict = field(default_factory=lambda: defaultdict(Counter))
    alpha: float = 0.5

    def fit(self, writes: list[Write]) -> "BaseRates":
        first = {}
        for w in sorted(writes, key=lambda w: w.order):
            ps = arbitrary_params(w.url)
            if ps:
                first.setdefault(structure(w.url), ps)
        for ps in first.values():
            for n, v in ps:
                self.counts[n][v] += 1
        return self

    def p(self, name: str, value: str) -> float:
        c = self.counts.get(name)
        if not c:
            c = Counter({k: v for cc in self.counts.values() for k, v in cc.items()})  # pooled fallback
        total, distinct = sum(c.values()), len(c) + 1
        return (c.get(value, 0) + self.alpha) / (total + self.alpha * distinct)

    def collision(self, name: str) -> float:
        """Renyi-2 collision probability: chance two independent choosers pick the same value."""
        c = self.counts.get(name, Counter())
        tot = sum(c.values())
        return sum((k / tot) ** 2 for k in c.values()) if tot else 0.0


def reuse_events(writes: list[Write], rates: BaseRates) -> list[dict]:
    """Every time an agent writes a structure another agent wrote earlier with arbitrary values."""
    seen = defaultdict(list)          # structure -> earlier writes (other agents filtered at use time)
    events = []
    for w in sorted(writes, key=lambda w: w.order):
        ps = arbitrary_params(w.url)
        st = structure(w.url)
        prior = [x for x in seen[st] if x.agent != w.agent]
        if prior and ps:
            # compare with the most recent earlier version of this structure by another agent
            src = prior[-1]
            sp = dict(arbitrary_params(src.url))
            for n, v in sp.items():
                mine = dict(ps).get(n)
                if mine is None:
                    continue
                any_writer = [x for x in prior if dict(arbitrary_params(x.url)).get(n) == mine]
                events.append({
                    "name": n, "src_value": v, "value": mine, "kept": mine == v,
                    "matched_any_earlier": bool(any_writer),
                    "p_src": rates.p(n, v), "p_value": rates.p(n, mine),
                    "high_entropy": high_entropy(v),
                    "copier": w, "source": src,
                    "earliest_writer_of_value": any_writer[0] if any_writer else None,
                    "candidates_same_structure": len({x.agent for x in prior}),
                })
        seen[st].append(w)
    return events


def summarize(writes: list[Write], lr_threshold: float = 100.0) -> dict:
    rates = BaseRates().fit(writes)
    ev = reuse_events(writes, rates)
    n = len(ev)
    kept = [e for e in ev if e["kept"]]
    chance = sum(e["p_src"] for e in ev)
    s_raw = len(kept) / n if n else 0.0
    s_corr = (len(kept) - chance) / (n - chance) if n > chance else 0.0
    hi = [e for e in ev if e["high_entropy"]]
    hk = sum(1 for e in hi if e["kept"])
    # copy-or-coincidence: naive calls every match a copy; calibrated needs LR = 1/p above threshold
    naive = [e for e in ev if e["matched_any_earlier"]]
    calibrated = [e for e in naive if 1.0 / e["p_value"] >= lr_threshold]
    expected_coincidences = sum(e["p_value"] for e in naive)
    # values shared by >=2 agents, with base rate
    users = defaultdict(set)
    for w in writes:
        for nme, v in arbitrary_params(w.url):
            users[(nme, v)].add(w.agent)
    shared = sorted(((k, len(a)) for k, a in users.items() if len(a) >= 2), key=lambda x: -x[1])
    focal_table = [{"param": k[0], "value": k[1], "agents": a, "p": round(rates.p(*k), 4), "focal": bool(FOCAL.match(k[1]))}
                   for k, a in shared[:25]]
    # survival by what the earlier value looks like: focal / ordinary / random-looking
    by_class = {}
    for cls, pick in (("focal", lambda e: bool(FOCAL.match(e["src_value"]))),
                      ("random_looking", lambda e: e["high_entropy"]),
                      ("other", lambda e: not FOCAL.match(e["src_value"]) and not e["high_entropy"])):
        sub = [e for e in ev if pick(e)]
        k = sum(1 for e in sub if e["kept"])
        by_class[cls] = {"n": len(sub), "kept": k, "rate": k / len(sub) if sub else 0.0, "ci": wilson(k, len(sub))}
    # ambiguity reduction where a high-entropy value was kept
    amb = [(e["candidates_same_structure"], 1) for e in hi if e["kept"]]
    return {
        "writes": len(writes),
        "reuse_events": n,
        "survival": {
            "raw": s_raw, "raw_ci": wilson(len(kept), n),
            "chance_corrected": s_corr,
            "high_entropy": hk / len(hi) if hi else 0.0, "high_entropy_ci": wilson(hk, len(hi)), "high_entropy_n": len(hi),
            "by_class": by_class,
        },
        "copy_or_coincidence": {
            "naive_copy_calls": len(naive), "calibrated_copy_calls": len(calibrated),
            "declined_as_weak_evidence": len(naive) - len(calibrated),
            "expected_coincidences_among_naive": expected_coincidences, "lr_threshold": lr_threshold,
        },
        "collision_by_param": {k: round(rates.collision(k), 4) for k in sorted(rates.counts, key=lambda k: -sum(rates.counts[k].values()))[:8]},
        "shared_values": focal_table,
        "ambiguity": {
            "events": len(amb),
            "median_candidates_without_tag": sorted(a for a, _ in amb)[len(amb) // 2] if amb else 0,
        },
        "_events": ev,
    }
