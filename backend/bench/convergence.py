"""Copy or rediscovery? The convergence–collusion identifiability problem, on worlds with known answers.

An agent writes a behaviour that someone else already wrote. Did it copy, or find it independently?
Every such event is labelled by the simulator (truth parent = copy, None = rediscovery). Three detectors:

  identical   SWARM's naive screen: same behaviour => copied.
  naive       also needs the inert value to match an earlier writer's value, as if values were uniformly random.
  calibrated  likelihood ratio LR = max_f [k*1(v=v_f) + (1-k)*p(v)] / p(v), where p is the population frequency of the
              value (so a favourite like x=1 counts for little) and k the keep rate learned by the EM tracer.
              Calls 'copied' when LR >= threshold.

Only uses observables (behaviour, value, time, agent); truth is used for scoring alone.
"""
from __future__ import annotations

from collections import Counter

from backend.sim.world import World


def matched_events(world: World) -> list:
    """Events whose behaviour exactly repeats an earlier write by another agent (where convergence can fool us)."""
    out, seen = [], {}
    for e in sorted(world.obs, key=lambda o: o.t):
        prior = seen.get(e.variant, [])
        others = [f for f in prior if f.agent != e.agent]
        if others:
            out.append((e, others))
        seen.setdefault(e.variant, []).append(e)
    return out


def population_freq(world: World):
    vc = Counter(o.value for o in world.obs if o.value is not None)
    tot, distinct = sum(vc.values()), max(world.cfg.n_values, len(vc))
    return lambda v: (vc.get(v, 0) + 0.5) / (tot + 0.5 * distinct)


def score(world: World, keep: float, threshold: float = 10.0) -> dict:
    p = population_freq(world)
    rows = []
    for e, others in matched_events(world):
        copied = world.truth[e.id] is not None
        naive = any(f.value == e.value for f in others)
        lr = max((keep * (f.value == e.value) + (1 - keep) * p(e.value)) / p(e.value) for f in others)
        rows.append((copied, naive, lr))
    return {"rows": rows, "threshold": threshold}


def rates(rows, threshold: float) -> dict:
    cop = [r for r in rows if r[0]]
    red = [r for r in rows if not r[0]]

    def fpr(call):  # rediscoveries wrongly called copies
        return sum(1 for r in red if call(r)) / len(red) if red else 0.0

    def tpr(call):
        return sum(1 for r in cop if call(r)) / len(cop) if cop else 0.0
    ident, naive, cal = (lambda r: True), (lambda r: r[1]), (lambda r: r[2] >= threshold)
    return {
        "events": len(rows), "copies": len(cop), "rediscoveries": len(red),
        "identical": {"false_call_rate": fpr(ident), "recall": tpr(ident)},
        "naive": {"false_call_rate": fpr(naive), "recall": tpr(naive)},
        "calibrated": {"false_call_rate": fpr(cal), "recall": tpr(cal)},
        "auc_calibrated": auc([r[2] for r in cop], [r[2] for r in red]),
    }


def auc(pos: list, neg: list) -> float:
    """Probability a random copy scores above a random rediscovery (ties count half)."""
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        avg = (i + 1 + j) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
