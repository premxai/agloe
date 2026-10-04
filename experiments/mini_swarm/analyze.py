"""Analyze saved mini-swarm runs. Everything is rebuilt from data/mini_swarm/<arm>-seed<k>/world.json - no API calls.

Truth (answer key) comes from the read log: an agent COPIED a route if, before its first successful fetch with that
route, it was served a wiki link using the same route; its parent is the author of that link. Otherwise the route
was found independently (rediscovery).

The investigator sees only the edit log: wiki writes and submissions. Without tags it can only guess among earlier
wiki authors who posted the same route. With tags, a surviving tag in the submitted URL names the served copy.

Usage: python -m experiments.mini_swarm.analyze [--runs data/mini_swarm]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
PARAM = re.compile(r"[?&]([A-Za-z_][\w\-]{0,20})=([^&#\s]*)")
TOKEN = re.compile(r"/s/([a-z0-9]{6,12})/")


def route(url: str) -> str:
    """Behaviour = which mirror and which URL form, ignoring tokens, tags and cache-buster values."""
    u = unquote(url or "")
    host = u.split("/")[2] if u.count("/") >= 2 else ""
    sess = "+session" if TOKEN.search(url or "") else ""
    if host.startswith("read.alpha"):
        return "alpha" + sess
    if host.startswith("beta-proxy"):
        return "beta:" + ("encoded" if "%3A%2F%2F" in (url or "").upper() else "raw") + sess
    if host.startswith("gamma"):
        return "gamma" + sess
    if host.startswith("delta"):
        tail = (url or "").split("county_stats.json", 1)[-1]
        names = sorted({n for n, _ in PARAM.findall(tail) if n != "_"})
        return "delta" + ("+bust:" + ",".join(names) if names else "") + sess
    return "other:" + host


def arbitrary_values(url: str) -> list[tuple[str, str]]:
    """Cache-buster style values an agent chose (excluding the wiki's own '_' tag)."""
    tail = (url or "").split("county_stats.json", 1)[-1]
    return [(n.lower(), v) for n, v in PARAM.findall(tail) if n not in ("_", "url", "src")]


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def first_success(w: dict) -> dict:
    out = {}
    for f in w["fetches"]:
        if f.get("ok") and f["agent"] not in out:
            out[f["agent"]] = f
    return out


def truth_copies(w: dict, succ: dict | None = None, prefer_exact: bool = False) -> dict:
    """agent -> {'route','copied': bool,'parent','served_tag','exact'} using the hidden read log.

    `succ` maps agent -> the fetch that counts as its outcome (default: first fetch that returned the true answer).
    With `prefer_exact`, the source is the served copy whose text the agent reproduced exactly (a per-copy tag or token
    makes that unique and physically certain), falling back to the most recent read; the default picks the most recent
    read first, which mislabels agents that read a page more than once. When several served copies are byte-identical
    (untagged worlds) the exact match is ambiguous and the earliest such copy is returned: do not score attribution
    accuracy there."""
    succ = first_success(w) if succ is None else succ
    res = {}
    for agent, f in succ.items():
        r = route(f["url"])
        seen = [(rd["t"], u) for rd in w["reads"] if rd["reader"] == agent and rd["t"] < f["t"] for u in rd["urls"]
                if route(u["served"]) == r]
        if seen:
            key = (lambda x: (x[1]["served"] == f["url"], x[0])) if prefer_exact else (lambda x: (x[0], x[1]["served"] == f["url"]))
            t, u = max(seen, key=key)
            res[agent] = {"route": r, "copied": True, "parent": u["author"], "served_tag": u["tag"], "exact": u["served"] == f["url"], "t": f["t"]}
        else:
            res[agent] = {"route": r, "copied": False, "parent": None, "served_tag": None, "exact": False, "t": f["t"]}
    return res


def investigator(w: dict, truth: dict) -> dict:
    """Edit-log-only attribution for copiers, then with tags. Returns accuracy stats."""
    subs = {s["agent"]: s for s in w["submissions"]}
    chunks = [{"t": x["t"], "author": x["author"], "routes": {route(u) for u in re.findall(r"https?://\S+", x["text"])}} for x in w["writes"]]
    tags, toks = w.get("tags", {}), w.get("tokens", {})
    rows = []
    for agent, tr in truth.items():
        if not tr["copied"]:
            continue
        sub = subs.get(agent)
        urls = (sub or {}).get("urls", [])
        t_sub = (sub or {}).get("t", 10 ** 9)
        cands = [c for c in chunks if c["t"] < t_sub and c["author"] != agent and tr["route"] in c["routes"]]
        authors = [c["author"] for c in sorted(cands, key=lambda c: c["t"])]
        latest = authors[-1] if authors else None
        earliest = authors[0] if authors else None
        m = len(set(authors))
        uniform = (1.0 / m) if (m and tr["parent"] in authors) else 0.0
        tagged = None
        for u in urls:
            for n, v in PARAM.findall(u):
                if n == "_" and v in tags:
                    tagged = tags[v]
            for tok in TOKEN.findall(u):
                if toks.get(tok, {}).get("minted_by") == "wiki":
                    tagged = toks[tok]
        kept = bool(tagged) and tagged.get("reader") == agent
        guess_tags = tagged["author"] if tagged else latest
        rows.append({"agent": agent, "parent": tr["parent"], "m": m, "latest_ok": latest == tr["parent"], "uniform": uniform,
                     "tag_kept": kept, "tag_ok": guess_tags == tr["parent"], "submitted": bool(sub),
                     "tag_parent": tagged["author"] if (tagged and kept) else None, "latest": latest,
                     "earliest": earliest, "earliest_ok": earliest == tr["parent"]})
    n = len(rows)
    s = sum(r["tag_kept"] for r in rows)
    c0_latest = sum(r["latest_ok"] for r in rows) / n if n else 0.0
    c0_uniform = sum(r["uniform"] for r in rows) / n if n else 0.0
    acc_tags = sum(r["tag_ok"] for r in rows) / n if n else 0.0
    s_rate = s / n if n else 0.0
    return {"copiers": n, "edit_log_only_latest": c0_latest, "edit_log_only_uniform_expectation": c0_uniform,
            "tag_survival": s_rate, "tag_survival_ci": wilson(s, n), "with_tags_accuracy": acc_tags,
            "predicted_with_tags": s_rate + (1 - s_rate) * c0_latest, "rows": rows}


def choices(w: dict) -> dict:
    """What each agent independently chose: final route and any arbitrary values in its URLs."""
    per = {}
    for f in w["fetches"]:
        d = per.setdefault(f["agent"], {"routes": [], "values": []})
        d["routes"].append(route(f["url"])); d["values"] += arbitrary_values(f["url"])
    return per


def collision(values_a: list, values_b: list | None = None) -> float:
    """Probability two distinct agents' chosen values coincide (same arm if b is None, else cross-arm)."""
    if values_b is None:
        pairs = [(i, j) for i in range(len(values_a)) for j in range(i + 1, len(values_a))]
        return sum(values_a[i] == values_a[j] for i, j in pairs) / len(pairs) if pairs else float("nan")
    pairs = [(a, b) for a in values_a for b in values_b]
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", default=str(ROOT / "data" / "mini_swarm"))
    a = ap.parse_args()
    runs = {p.name: json.loads((p / "world.json").read_text(encoding="utf-8")) for p in sorted(Path(a.runs).glob("*-seed*")) if (p / "world.json").exists()}
    report = {}
    first_vals = {}
    for name, w in runs.items():
        arm = name.split("-")[0]
        ch = choices(w)
        fv = [v[0] for v in (d["values"] for d in ch.values()) if v]          # first arbitrary value per agent
        first_vals.setdefault(arm, []).extend(fv)
        succ = first_success(w)
        rep = {"agents": len(ch), "solved": len(succ),
               "final_routes": Counter(route(f["url"]) for f in succ.values()).most_common(),
               "values_top": Counter(f"{n}={v}" for n, v in fv).most_common(8),
               "same_model_value_collision": collision(fv)}
        if w.get("board"):
            tr = truth_copies(w)
            inv = investigator(w, tr)
            inv.pop("rows")
            rep.update({"copied": sum(t["copied"] for t in tr.values()), "independent": sum(not t["copied"] for t in tr.values()),
                        "wiki_writes": len(w["writes"]), **inv})
        report[name] = rep
    if "A0" in first_vals and "A1" in first_vals:
        report["cross_model_value_collision_A0_vs_A1"] = collision(first_vals["A0"], first_vals["A1"])
    print(json.dumps(report, indent=1, default=str))
    out = ROOT / "data" / "mini_swarm" / "analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
