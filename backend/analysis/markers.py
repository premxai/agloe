"""Real-data validation set from rare "marker" strings (the genetic-marker idea).

A marker is a string an agent invented (a custom path id, a filter, a payload) that later reappears in other agents'
edits.  The first writer is then almost certainly the source, so these pairs are near-ground-truth for real copying.

Guards against false pairs:
  * only the WRAPPER side of a URL is searched; the part that names the outside document is removed, because two
    agents can find the same real document independently;
  * pure hex / digits / dictionary-like strings are skipped (hashes of shared content, ordinary words);
  * the copier's whole URL must resemble the source's URL (difflib ratio), not just share the token;
  * markers written by more than MAX_AGENTS agents are boilerplate, not lineage.
Still a proxy: a chain a -> b -> c is credited to a for c if b never wrote the token on a visible page.
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import unquote

from backend.analysis.signatures import extract_urls, parse_signature, unquote_n

MAX_AGENTS = 7
MIN_SIM = 0.6
TOKEN = re.compile(r"[A-Za-z0-9_\-]{12,}")


COMMON = ("content-type", "application", "authorization", "user-agent", "accept", "bearer", "mozilla", "charset",
          "access-control", "cache-control", "text/html", "x-requested", "eyjzb3vyy2uioij")  # eyJzb3VyY2UiOiJ = base64 '{"source":"'


def _is_common(t: str) -> bool:
    low = t.lower()
    if any(low.startswith(c) or c in low for c in COMMON[:-1]):
        return True
    try:
        import base64
        pad = t + "=" * (-len(t) % 4)
        dec = base64.urlsafe_b64decode(pad).decode("ascii")
        return dec.isprintable() and any(c in dec.lower() for c in ("application/json", "content-type", "text/", "http", "{\"", "[{"))
    except Exception:
        return False


def _good(t: str) -> bool:
    if _is_common(t):
        return False
    if re.fullmatch(r"[0-9a-fA-F]{24,}", t) or t.isdigit():
        return False
    if len(set(t)) < 7:
        return False
    return bool(re.search(r"\d", t) or re.search(r"[A-Z]", t) and re.search(r"[a-z]", t) or "_" in t)


def wrapper_tokens(url: str, wrapper_only: bool = True) -> set[str]:
    sig = parse_signature(url)
    if not sig or not sig.layers:
        return set()
    text = unquote_n(url, 4)
    tgt = sig.target_url.split("/", 1)
    if tgt and wrapper_only:
        text = re.sub(re.escape(sig.target_url), " ", text, flags=re.I)
        text = re.sub(re.escape("www." + sig.target_url), " ", text, flags=re.I)
    return {t for t in TOKEN.findall(text) if _good(t)}


def find_pairs(revisions: list[dict], wrapper_only: bool = True, min_sim: float = MIN_SIM) -> list[dict]:
    """revisions sorted by time. Returns copy events with a near-known source agent."""
    by_page = defaultdict(list)
    for r in revisions:
        by_page[r["page_id"]].append(r)
    for v in by_page.values():
        v.sort(key=lambda r: int(r["seq"]))
    seq = {r["rev_id"]: int(r["seq"]) for r in revisions}
    idx = {r["rev_id"]: (by_page[r["page_id"]], by_page[r["page_id"]].index(r)) for r in revisions}
    first = defaultdict(dict)    # token -> agent -> record of that agent's first write
    for r in revisions:
        lab = r["label"]
        if not lab:
            continue
        pg, i = idx[r["rev_id"]]
        prev = pg[i - 1]["body"] if i else ""
        added = set(extract_urls(r["body"])) - set(extract_urls(prev))
        per_tok = {}
        for u in added:
            for t in wrapper_tokens(u, wrapper_only):
                per_tok.setdefault(t, u)
        for t, u in per_tok.items():
            first[t].setdefault(lab, {"agent": lab, "time": r["time"], "page": r["page_id"], "seq": seq[r["rev_id"]], "rev": r["rev_id"], "url": u})
    pairs = []
    writers_by_page = defaultdict(list)          # page -> [(seq, agent, time)] every logged edit, for visibility
    for r in revisions:
        if r["label"]:
            writers_by_page[r["page_id"]].append((seq[r["rev_id"]], r["label"], r["time"]))
    for tok, d in first.items():
        if not (2 <= len(d) <= MAX_AGENTS):
            continue
        order = sorted(d.values(), key=lambda x: x["time"])
        src = order[0]
        for cp in order[1:]:
            if cp["time"] <= src["time"]:
                continue
            sim = SequenceMatcher(None, unquote_n(src["url"], 3), unquote_n(cp["url"], 3)).ratio()
            if sim < min_sim:
                continue
            # who could the copier see on its own page right before writing?  distinct earlier editors, latest first
            seen, ranked = set(), []
            for s, a, t in sorted(writers_by_page[cp["page"]], reverse=True):
                if s < cp["seq"] and a != cp["agent"] and a not in seen:
                    seen.add(a); ranked.append(a)
            onpage = src["agent"] in seen
            earlier = [w["agent"] for w in order if w["time"] < cp["time"] and w["agent"] != cp["agent"]]
            any_visible = any(a in seen for a in earlier)   # generous: an intermediate copier on the page also counts
            pairs.append({
                "token": tok, "source": src, "copier": cp, "similarity": round(sim, 3),
                "source_visible_on_page": onpage,
                "any_writer_visible": any_visible,
                "visible_editors": len(ranked),
                "recency_rank": ranked.index(src["agent"]) if onpage else None,
                "lag_s": None,
            })
    return pairs


def wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (c - h, c + h)


def fit_recency(pairs: list[dict]) -> dict:
    """MLE of lambda in P(source = editor at recency rank r) ∝ exp(-lambda r) among the m visible editors."""
    import numpy as np
    from scipy.optimize import minimize_scalar

    obs = [(p["recency_rank"], p["visible_editors"]) for p in pairs if p["source_visible_on_page"]]
    if not obs:
        return {}

    def nll(lam):
        s = 0.0
        for r, m in obs:
            ks = np.arange(m)
            s -= -lam * r - np.log(np.exp(-lam * ks).sum())
        return s
    res = minimize_scalar(nll, bounds=(0, 6), method="bounded")
    grid = np.linspace(0, 3, 61); ll = np.array([-nll(g) for g in grid])
    ok = grid[ll >= ll.max() - 1.92]
    uniform = float(np.mean([1 / m for _, m in obs]))
    latest = float(np.mean([1 if r == 0 else 0 for r, _ in obs]))
    return {"lambda": float(res.x), "ci95": [float(ok.min()), float(ok.max())], "n": len(obs),
            "accuracy_if_uniform": uniform, "accuracy_latest_editor": latest}


def read_map(pairs: list[dict], page_family: dict[str, str]) -> dict:
    """Hidden read map: for each marker copy, the page the copier edited vs the page its source wrote on.

    `page_family` maps page_id -> task family from the export (e.g. relay-coordination, datausa-...).
    An edge is cross-team when both pages have a task family and they differ.
    """
    from collections import Counter

    edges = Counter(); cross = []
    for p in pairs:
        a, b = p["source"]["page"], p["copier"]["page"]
        fa, fb = page_family.get(a, "?"), page_family.get(b, "?")
        edges[(a, b)] += 1
        if a != b and fa not in ("?", "None") and fb not in ("?", "None") and fa != fb:
            cross.append({"from": a, "to": b, "from_family": fa, "to_family": fb, "token": p["token"][:24],
                          "source_rev": p["source"]["rev"], "copier_rev": p["copier"]["rev"]})
    n = len(pairs)
    off = sum(1 for p in pairs if p["source"]["page"] != p["copier"]["page"])
    fam_flow = Counter((page_family.get(p["source"]["page"], "?"), page_family.get(p["copier"]["page"], "?")) for p in pairs)
    return {"copies": n, "off_page": off, "off_page_share": off / n if n else 0.0,
            "source_pages": Counter(p["source"]["page"] for p in pairs).most_common(8),
            "family_flows": [(a, b, c) for (a, b), c in fam_flow.most_common(12)],
            "cross_team": cross}
