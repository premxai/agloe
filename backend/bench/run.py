"""Run the simulation benchmark and write data/out/bench_results.json (+ markdown tables on stdout).

Run: python -m backend.bench.run [--seeds 20]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from backend.bench.em import EMTracer
from backend.bench.methods import METHODS, Index, make_oracle
from backend.bench.metrics import bayes_ceiling, evaluate
from backend.sim.world import SimConfig, simulate

OUT = Path(__file__).resolve().parents[2] / "data" / "out" / "bench_results.json"
BASE = SimConfig(n_agents=300, n_pages=25, steps=9000)


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def run_config(cfg: SimConfig, seeds: int, with_reads: bool = False) -> dict:
    """Pool events over seeds; report event-weighted metrics with Wilson CIs."""
    agg = defaultdict(lambda: defaultdict(float))
    ceil_hits = ceil_n = blind_hits = 0.0
    tiers = defaultdict(lambda: defaultdict(float))
    calib = defaultdict(lambda: [0, 0]); fitted = defaultdict(float)
    for s in range(seeds):
        w = simulate(replace(cfg, seed=s))
        ix = Index(w)
        c = bayes_ceiling(w, ix, use_reads=with_reads)
        cb = bayes_ceiling(w, ix, use_reads=with_reads, content=False)
        ceil_hits += c["ceiling"] * c["n"]; ceil_n += c["n"]; blind_hits += cb["ceiling"] * c["n"]
        methods = dict(METHODS)
        methods["oracle"] = make_oracle(w, use_reads=with_reads, seed=s)
        em = EMTracer(w); methods["em"] = em
        for k, v in em.params().items():
            fitted[k] += v / seeds
        for e in w.obs:
            if w.truth[e.id] is not None and e.id in em.pred and e.read_item is None:
                cid, pr = em.pred[e.id]; b = min(9, int(pr * 10)); calib[b][0] += 1; calib[b][1] += int(cid == w.truth[e.id])
        for name, m in methods.items():
            r = evaluate(w, ix, m)
            a = agg[name]
            a["n"] += r["n"]; a["top1"] += r["top1"] * r["n"]; a["top3"] += r["top3"] * r["n"]
            a["variant_ok"] += r["variant_ok"] * r["n"]; a["answered"] += r["coverage"] * r["n"]
            if name == "em":
                for t, k in r["tier_n"].items():
                    tiers["em_" + t]["n"] += k; tiers["em_" + t]["ok"] += r["tier_precision"][t] * k; tiers["em_" + t]["var"] += r["tier_variant_ok"][t]
            if name == "ours":
                for t, k in r["tier_n"].items():
                    tiers[t]["n"] += k; tiers[t]["ok"] += r["tier_precision"][t] * k; tiers[t]["var"] += r["tier_variant_ok"][t]
    out = {"events": int(ceil_n), "ceiling": ceil_hits / ceil_n, "ceiling_blind": blind_hits / ceil_n, "methods": {}, "tiers": {}}
    for name, a in agg.items():
        lo, hi = wilson(a["top1"], int(a["n"]))
        out["methods"][name] = {"top1": a["top1"] / a["n"], "ci": [lo, hi], "top3": a["top3"] / a["n"],
                                "variant_ok": a["variant_ok"] / a["n"], "coverage": a["answered"] / a["n"]}
    out["fitted"] = dict(fitted)
    tot = sum(v[0] for v in calib.values())
    out["calibration"] = [{"bin": f"{b/10:.1f}-{(b+1)/10:.1f}", "n": calib[b][0], "predicted": (b + 0.5) / 10, "observed": calib[b][1] / calib[b][0]} for b in sorted(calib) if calib[b][0]]
    out["ece"] = sum(abs(c["observed"] - c["predicted"]) * c["n"] for c in out["calibration"]) / tot if tot else 0.0
    for t, v in tiers.items():
        lo, hi = wilson(v["ok"], int(v["n"]))
        vlo, vhi = wilson(v["var"], int(v["n"]))
        out["tiers"][t] = {"n": int(v["n"]), "precision": v["ok"] / v["n"], "ci": [lo, hi],
                           "variant_precision": v["var"] / v["n"], "variant_ci": [vlo, vhi]}
    return out


def robustness(res: dict, seeds: int) -> None:
    print("\n## 6. Copy rules the tracer was not built for, and the real-board setting (85% of sources off-page)\n")
    print("| copy rule | off-page share | Bayes ceiling | heuristic tracer | model-based tracer | model-based / ceiling | learned off-page share |")
    print("|---|---|---|---|---|---|---|")
    res["robustness"] = {}
    for copy in ("uniform", "recency", "homophily", "window"):
        for off in (0.25, 0.85):
            r = run_config(replace(BASE, copy=copy, offpage=off), seeds); res["robustness"][f"{copy}@{off}"] = r
            m = r["methods"]
            print(f"| {copy} | {off:.2f} | {r['ceiling']:.3f} | {m['ours']['top1']:.3f} | {m['em']['top1']:.3f} | {m['em']['top1']/r['ceiling']:.2f} | {r['fitted']['theta']:.2f} |")


def trap_streets_and_convergence(res: dict, seeds: int) -> None:
    from backend.bench.convergence import rates, score
    print("\n## 7. Trap streets: tags stamped by the board (uniform copying, 25% off-page)\n")
    base_c = run_config(BASE, seeds)["ceiling"]
    print(f"no tags: Bayes ceiling C0 = {base_c:.3f}\n")
    print("| tag design | tag survival s | Bayes ceiling | formula s+(1-s)C0 | model-based tracer | heuristic |")
    print("|---|---|---|---|---|---|")
    res["trap_streets"] = {"C0": base_c, "cells": {}}
    for scope in ("version", "static", "page"):
        for s_keep in (0.1, 0.33, 0.6, 0.9):
            r = run_config(replace(BASE, tag_scope=scope, tag_keep=s_keep), seeds)
            pred = s_keep + (1 - s_keep) * base_c if scope == "version" else None
            res["trap_streets"]["cells"][f"{scope}@{s_keep}"] = {**{k: r[k] for k in ("ceiling", "events")}, "em": r["methods"]["em"]["top1"], "ours": r["methods"]["ours"]["top1"], "formula": pred}
            ps = f"{pred:.3f}" if pred is not None else "-"
            print(f"| {scope} | {s_keep:.2f} | {r['ceiling']:.3f} | {ps} | {r['methods']['em']['top1']:.3f} | {r['methods']['ours']['top1']:.3f} |")
    print("\n## 8. Copy or rediscovery? (same behaviour written again; inert value kept 40% of the time when copied)\n")
    print("| how alike 'random' picks are (zipf) | events | identical-output screen: false accusations | naive value match: false accusations | calibrated: false accusations | calibrated recall | AUC |")
    print("|---|---|---|---|---|---|---|")
    res["convergence"] = {}
    cbase = replace(BASE, invent_rate=0.01, rediscover=0.5, n_values=50, value_keep=0.4)
    for z in (0.0, 1.0, 1.5, 2.0):
        rows = []
        for sd in range(seeds):
            w = simulate(replace(cbase, value_zipf=z, seed=sd)); em = EMTracer(w)
            rows += score(w, em.keep)["rows"]
        r = rates(rows, 10.0); res["convergence"][str(z)] = r
        print(f"| {z:.1f} | {r['events']} | {r['identical']['false_call_rate']:.2f} | {r['naive']['false_call_rate']:.3f} | {r['calibrated']['false_call_rate']:.3f} | {r['calibrated']['recall']:.2f} | {r['auc_calibrated']:.2f} |")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--only", choices=["all", "robustness", "tags"], default="all")
    args = ap.parse_args(); seeds = args.seeds
    if args.only == "tags":
        res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        trap_streets_and_convergence(res, seeds); OUT.write_text(json.dumps(res, indent=1), encoding="utf-8"); return
    if args.only == "robustness":
        res = json.loads(OUT.read_text(encoding="utf-8")); robustness(res, seeds); OUT.write_text(json.dumps(res, indent=1), encoding="utf-8"); return
    res = {"base": BASE.__dict__, "seeds": seeds, "copy_models": {}, "reads_item": {}, "reads_page": {}, "offpage": {}}
    print(f"# Simulation benchmark ({seeds} seeds per cell; ~{BASE.steps} steps, {BASE.n_agents} agents)\n")

    print("## 1. Methods vs the Bayes ceiling (no reads logged)\n")
    names = ["random", "earliest", "latest", "most_similar", "ours", "em", "oracle"]
    print("| copy model | Bayes ceiling | ceiling if content ignored | " + " | ".join(names) + " |"); print("|" + "---|" * (len(names) + 3))
    for copy in ("uniform", "recency", "popular"):
        r = run_config(replace(BASE, copy=copy), seeds); res["copy_models"][copy] = r
        print(f"| {copy} | {r['ceiling']:.3f} | {r['ceiling_blind']:.3f} | " + " | ".join(f"{r['methods'][n]['top1']:.3f}" for n in names) + " |")

    print("\n## 2. Value of logging reads (uniform copying, ours uses reads when present)\n")
    print("| rho | ceiling(with reads) | ours | em | ours (ignores reads) | oracle |"); print("|---|---|---|---|---|---|")
    for level in ("item", "page"):
        for rho in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0):
            r = run_config(replace(BASE, rho=rho, read_level=level), seeds, with_reads=True)
            res[f"reads_{level}"][str(rho)] = r
            m = r["methods"]
            print(f"| {level} {rho:.2f} | {r['ceiling']:.3f} | {m['ours']['top1']:.3f} | {m['em']['top1']:.3f} | {m['ours_no_reads']['top1']:.3f} | {m['oracle']['top1']:.3f} |")

    print("\n## 3. Off-page sources (reads happened on pages the edit log does not show)\n")
    print("| off-page share | ceiling | latest | ours (heuristic) | em (learns the copy model) |"); print("|---|---|---|---|---|")
    for off in (0.0, 0.25, 0.5, 0.75):
        r = run_config(replace(BASE, offpage=off), seeds); res["offpage"][str(off)] = r
        print(f"| {off:.2f} | {r['ceiling']:.3f} | {r['methods']['latest']['top1']:.3f} | {r['methods']['ours']['top1']:.3f} | {r['methods']['em']['top1']:.3f} |")

    print("\n## 4. Is the evidence tier honest? (ours, uniform copying, no reads)\n")
    t = res["copy_models"]["uniform"]["tiers"]
    print("| tier | answers | exact source right | 95% CI | right method (variant) | 95% CI |"); print("|---|---|---|---|---|---|")
    for k in ("A", "B", "C"):
        if k in t:
            print(f"| {k} | {t[k]['n']} | {t[k]['precision']:.3f} | {t[k]['ci'][0]:.3f}-{t[k]['ci'][1]:.3f} | {t[k]['variant_precision']:.3f} | {t[k]['variant_ci'][0]:.3f}-{t[k]['variant_ci'][1]:.3f} |")
    print("\n## 5. Can the model-based tracer's probabilities be trusted? (uniform copying, no reads)\n")
    cal = res["copy_models"]["uniform"]
    print("| says | cases | right |"); print("|---|---|---|")
    for c in cal["calibration"]:
        print(f"| {c['bin']} | {c['n']} | {c['observed']:.3f} |")
    print(f"\nexpected calibration error = {cal['ece']:.3f};  learned copy model (mean over seeds): " + ", ".join(f"{k}={v:.2f}" for k, v in cal["fitted"].items()))
    robustness(res, seeds)
    trap_streets_and_convergence(res, seeds)
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
