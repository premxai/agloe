"""Hand-verification harness for the cross-team jumps in the hidden read map (collusion.wiki).

The read map (`backend/analysis/markers.read_map`) flags marker copies whose source page and copier page
belong to different task families ("teams"). A flag is only a *candidate*: a token can recur across teams
because agents independently use the same API field name or construct the same round timestamp -- the very
copy-vs-coincidence trap this project is about. This script applies that discipline to our own findings.

For each candidate it recovers the full token and both URLs, then checks:
  1. different agents        - source.label != copier.label (else it's one agent reusing its own token);
  2. earlier write           - source.time < copier.time (enforced upstream; re-asserted);
  3. token distinctiveness   - corpus-wide spread: # distinct pages / agents / families that contain the
                               token anywhere. A token in many pages/families is shared vocabulary, not a marker;
  4. token class             - uuid / high-entropy (impossible to coincide) vs wayback-timestamp vs
                               snake_or_camel field name (schema vocabulary, independently reproducible);
  5. no nearer carrier       - whether the token appeared earlier on a page in the COPIER's own family
                               (a within-team path that explains the token without any cross-team jump).

Verdict: STRONG (distinctive token, two families, different agents, no nearer same-family carrier),
PLAUSIBLE (survives 1-2 but has a caveat), REJECT (common vocabulary / same agent / nearer carrier).

Usage: python -m scripts.verify_readmap  -> prints the table and writes data/out/readmap_verify.json
No raw wiki text is written out; only token strings (needed to judge distinctiveness) and ids.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from backend.adapters.german_wiki import load_jsonl_gz, load_revisions
from backend.analysis.markers import find_pairs
from backend.analysis.report import classify_token as classify  # noqa: F401 - one shared classifier
from backend.analysis.report import shannon  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "german"


def corpus_index(revs: list[dict], tokens: set[str]) -> dict:
    """token -> {pages, agents, families, revs} it appears in (substring over all revision bodies)."""
    fam = {p["page_id"]: p.get("page_family", "?") for p in load_jsonl_gz(RAW / "pages.jsonl.gz")}
    idx = {t: {"pages": set(), "agents": set(), "families": set(), "revs": set()} for t in tokens}
    low = {t: t.lower() for t in tokens}
    for r in revs:
        body = (r.get("body") or "").lower()
        for t in tokens:
            if low[t] in body:
                d = idx[t]
                d["pages"].add(r["page_id"]); d["agents"].add(r["label"] or "?")
                d["families"].add(fam.get(r["page_id"], "?")); d["revs"].add(r["rev_id"])
    return idx, fam


def main() -> None:
    revs = load_revisions(RAW)
    pairs = find_pairs(revs)
    fampage = {p["page_id"]: p.get("page_family", "?") for p in load_jsonl_gz(RAW / "pages.jsonl.gz")}
    # cross-team candidates (same condition as read_map), but keep FULL token and URLs
    cands = []
    for p in pairs:
        a, b = p["source"]["page"], p["copier"]["page"]
        fa, fb = fampage.get(a, "?"), fampage.get(b, "?")
        if a != b and fa not in ("?", "None") and fb not in ("?", "None") and fa != fb:
            cands.append(p)
    tokens = {p["token"] for p in cands}
    idx, fam = corpus_index(revs, tokens)

    # per-family earliest appearance of each token, to spot a nearer within-team carrier
    tok_fam_first: dict = defaultdict(lambda: defaultdict(list))
    seq = {r["rev_id"]: int(r["seq"]) for r in revs}
    for r in revs:
        low = (r.get("body") or "").lower()
        for t in tokens:
            if t.lower() in low:
                tok_fam_first[t][fam.get(r["page_id"], "?")].append((r["time"], r["page_id"], r["label"] or "?"))

    rows = []
    for p in cands:
        tok = p["token"]
        src, cp = p["source"], p["copier"]
        cls, strength = classify(tok)
        ci = idx[tok]
        n_pages, n_agents, n_fams = len(ci["pages"]), len(ci["agents"]), len(ci["families"])
        diff_agents = src["agent"] != cp["agent"]
        earlier = src["time"] < cp["time"]
        # nearer same-family carrier: token seen in the COPIER's family strictly before the copier wrote it
        cp_fam = fampage.get(cp["page"], "?")
        nearer = any(t < cp["time"] and pg != cp["page"]
                     for t, pg, _lab in tok_fam_first[tok][cp_fam])
        # verdict
        if not diff_agents:
            verdict = "REJECT"; why = "same agent wrote both pages"
        elif not earlier:
            verdict = "REJECT"; why = "source not earlier"
        elif n_fams >= 3 or n_pages > 4:
            verdict = "REJECT"; why = f"common vocabulary (pages={n_pages}, families={n_fams})"
        elif strength == "high" and n_fams == 2 and not nearer:
            verdict = "STRONG"; why = f"{cls}; 2 families; no nearer same-team carrier"
        elif strength == "high":
            verdict = "PLAUSIBLE"; why = f"{cls} but " + ("nearer same-team carrier exists" if nearer else f"{n_fams} families")
        else:
            verdict = "REJECT" if (cls.endswith("field") or cls == "camel-ident" or cls == "wayback-constructed") and n_agents >= 2 \
                else "PLAUSIBLE"
            why = f"{cls} (strength {strength}); pages={n_pages} agents={n_agents}" + (", nearer carrier" if nearer else "")
        rows.append({
            "token": tok, "class": cls, "strength": strength, "verdict": verdict, "why": why,
            "from_family": fampage.get(src["page"]), "to_family": cp_fam,
            "from_page": src["page"], "to_page": cp["page"],
            "source_agent": src["agent"], "copier_agent": cp["agent"],
            "source_rev": src["rev"], "copier_rev": cp["rev"], "similarity": p["similarity"],
            "corpus_pages": n_pages, "corpus_agents": n_agents, "corpus_families": n_fams,
            "different_agents": diff_agents, "nearer_same_family_carrier": nearer,
            "source_url": src["url"], "copier_url": cp["url"],
        })
    order = {"STRONG": 0, "PLAUSIBLE": 1, "REJECT": 2}
    rows.sort(key=lambda r: (order[r["verdict"]], -r["corpus_families"]))
    tally = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("STRONG", "PLAUSIBLE", "REJECT")}
    print(f"candidates={len(rows)}  tally={tally}\n")
    for r in rows:
        print(f"[{r['verdict']:9s}] {r['class']:18s} tok={r['token'][:26]:26s} "
              f"{r['from_family']}->{r['to_family']}  pages={r['corpus_pages']} fams={r['corpus_families']} "
              f"agents={r['corpus_agents']}  diffA={r['different_agents']} near={r['nearer_same_family_carrier']}  | {r['why']}")
    (ROOT / "data" / "out").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "out" / "readmap_verify.json").write_text(
        json.dumps({"tally": tally, "rows": rows}, indent=1, default=str), encoding="utf-8")
    print("\nwrote data/out/readmap_verify.json")


if __name__ == "__main__":
    main()
