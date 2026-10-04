"""Identifiability audit: how much of "who copied whom" can THESE logs ever answer?

Input is a list of adoptions of one behavior: (agent, time, location, order-within-location).
For each agent's first adoption we count the visible carriers: other named agents who had already written the
same behavior at the same location. Then:

  * no visible carrier      -> the source cannot be named from the logs at all
  * m visible carriers      -> if the agent copied one of them with no preference, the best possible guess is
                               right with probability 1/m  (Theorem 1)
  * item-level read logging -> if a fraction rho of copies had their source item logged, the ceiling becomes
                               rho + (1 - rho) * C0, where C0 is the ceiling without reads  (Theorem 2)

All three are exact for the Bayes-optimal guesser under the stated copy model, and are checked by simulation in
`backend/bench`. The audit reports ceilings under no-preference copying; a recency or popularity preference raises
them (see the simulator), so treat the reported numbers as the conservative case.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Adoption:
    agent: str
    t: str          # ISO time; only used to order first adoptions
    loc: str        # page / channel where it was written
    order: int      # strict order of writes within `loc` (revision sequence number)
    key: str = ""   # behavior identifier


def audit_behavior(rows: list[Adoption], name: str = "") -> dict:
    """Audit one behavior (all rows must share a key). Blank agents are ignored: they cannot be attributed."""
    rows = [r for r in rows if r.agent]
    first: dict[str, Adoption] = {}
    for r in sorted(rows, key=lambda r: (r.t, r.loc, r.order)):
        first.setdefault(r.agent, r)
    by_loc = defaultdict(list)
    for r in rows:
        by_loc[r.loc].append(r)
    ms = []
    for a in first.values():
        carriers = {x.agent for x in by_loc[a.loc] if x.order < a.order and x.agent != a.agent}
        ms.append(len(carriers))
    n = len(ms)
    if n == 0:
        return {"name": name, "adopters": 0}
    zero = sum(1 for m in ms if m == 0)
    vis = [m for m in ms if m > 0]
    c0 = sum(1 / m for m in vis) / n                    # overall top-1 ceiling, unresolved count as misses
    top3 = sum(min(1.0, 3 / m) for m in vis) / n
    return {
        "name": name, "adopters": n, "no_visible_carrier": zero, "share_no_carrier": zero / n,
        "one_carrier": sum(1 for m in ms if m == 1), "two_or_more": sum(1 for m in ms if m >= 2),
        "median_carriers_when_visible": sorted(vis)[len(vis) // 2] if vis else 0,
        "ceiling_top1": c0, "ceiling_top3": top3,
        "ceiling_top1_among_visible": (sum(1 / m for m in vis) / len(vis)) if vis else 0.0,
        "with_reads": {str(rho): rho + (1 - rho) * c0 for rho in (0.1, 0.25, 0.5, 0.75, 1.0)},
    }


def audit_many(rows: list[Adoption], min_adopters: int = 20) -> list[dict]:
    by_key = defaultdict(list)
    for r in rows:
        by_key[r.key].append(r)
    out = [audit_behavior(v, k) for k, v in by_key.items()]
    return sorted([o for o in out if o.get("adopters", 0) >= min_adopters], key=lambda o: -o["adopters"])


def summarize(audits: list[dict]) -> dict:
    """Pool across behaviors: adopter-weighted ceiling and share without a visible source."""
    n = sum(a["adopters"] for a in audits)
    if not n:
        return {}
    return {
        "behaviors": len(audits), "adopters": n,
        "share_no_carrier": sum(a["no_visible_carrier"] for a in audits) / n,
        "ceiling_top1": sum(a["ceiling_top1"] * a["adopters"] for a in audits) / n,
        "ceiling_top3": sum(a["ceiling_top3"] * a["adopters"] for a in audits) / n,
        "median_behavior_ceiling": sorted(a["ceiling_top1"] for a in audits)[len(audits) // 2],
    }
