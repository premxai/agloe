"""Score a tracer on Agloe-Bench (standard library only).

A tracer reads  edit_log/<cell>.jsonl  (what an investigator has: wiki writes and submissions) and says, for each agent,
which earlier agent it copied from, or "independent". The answer key  truth/<cell>.jsonl  comes from the lab's hidden read
log and is never shown to the tracer.

Predictions: JSON Lines, one per agent:  {"cell": "...", "agent": "agent-07", "source": "agent-03" | "independent",
"confidence": 0.8}   (confidence optional; a missing prediction counts as "independent").

  python score.py --baselines                      # latest / earliest / uniform / conservative / tags
  python score.py --pred my_predictions.jsonl      # your tracer
Options: --bench DIR (default: this folder)  --world W1,W2,W3  --cond none,inert,loadbearing  --family qwen,...

Metrics (cell-level bootstrap 95% CI; agents in one swarm are not independent):
  top1                 copied agents whose source is named correctly
  recall               copied agents the tracer accuses of copying at all
  false_accusation     independent agents the tracer accuses of copying
  vs_uniform_ceiling   top1 divided by E[1/m], the best any tracer can do from the edit log if copiers pick uniformly among
                       identical posts. NOT a hard upper bound: tracers that exploit copier habits or read tags exceed 1.
  contamination P / R  planted-rumor cells: agents reached by the rumor, from the predicted lineage vs the true one
  ece                  calibration of the stated confidence on accusations (only if confidences are given)
Truth caveat: "copied" means "was served that link before using it" (exposure), the standard contagion definition.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

RUMOR_AUTHOR = "agent-00"
TAG = re.compile(r"[?&]_=([A-Za-z0-9]+)")
TOKEN = re.compile(r"/s/([a-z0-9]{6,12})/")


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def closure(parent: dict, root: str) -> set:
    out = set()
    for a in parent:
        cur, seen = a, set()
        while cur in parent and cur not in seen:
            seen.add(cur)
            cur = parent[cur]
            if cur == root:
                out.add(a)
                break
    return out


# ------------------------------------------------------------------ baselines (edit-log view only, except `tags`)
def candidates(log: list[dict], sub: dict) -> list[dict]:
    rs = set(sub["routes"])
    return [e for e in log if e["kind"] == "write" and e["t"] < sub["t"] and e["agent"] != sub["agent"] and rs & set(e["routes"])]


def baseline(name: str, log: list[dict], registry: dict, seed: int = 0) -> dict:
    rng = random.Random(seed)
    preds = {}
    for sub in (e for e in log if e["kind"] == "submit"):
        cands = sorted(candidates(log, sub), key=lambda e: e["t"])
        authors = [e["agent"] for e in cands]
        src, conf = "independent", None
        if name == "latest" and cands:
            src = authors[-1]
        elif name == "earliest" and cands:
            src = authors[0]
        elif name == "uniform" and cands:
            src = rng.choice(authors)
        elif name in ("conservative", "tags"):
            if name == "tags":
                for u in sub["urls"]:
                    for tok, table in [(m, "tags") for m in TAG.findall(u)] + [(m, "tokens") for m in TOKEN.findall(u)]:
                        rec = registry.get(table, {}).get(tok)
                        if rec and rec.get("reader") == sub["agent"]:
                            src, conf = rec["author"], 1.0
            if src == "independent" and len(set(authors)) == 1:
                src = authors[0]
        preds[sub["agent"]] = {"source": src, "confidence": conf}
    return preds


# ------------------------------------------------------------------ scoring
def cell_counts(truth: list[dict], preds: dict, ceiling: dict, rumor: bool) -> dict:
    c = defaultdict(float)
    tpar, ppar = {}, {}
    for r in truth:
        p = preds.get(r["agent"], {"source": "independent", "confidence": None})
        accused = p["source"] != "independent"
        if r["copied"]:
            c["n_copy"] += 1
            c["hit"] += p["source"] == r["parent"]
            c["accused_copy"] += accused
            tpar[r["agent"]] = r["parent"]
        else:
            c["n_indep"] += 1
            c["accused_indep"] += accused
        if accused:
            ppar[r["agent"]] = p["source"]
            if p.get("confidence") is not None:
                c["conf_n"] += 1
                c["conf_sum"] += p["confidence"]
                c["conf_hit"] += (r["copied"] and p["source"] == r["parent"])
    c["ceiling_w"] = ceiling["uniform_ceiling"] * ceiling["copiers"]
    c["ceiling_n"] = ceiling["copiers"]
    if rumor:
        truth_set, pred_set = closure(tpar, RUMOR_AUTHOR), closure(ppar, RUMOR_AUTHOR)
        c["ct_tp"], c["ct_pred"], c["ct_truth"] = len(truth_set & pred_set), len(pred_set), len(truth_set)
    return dict(c)


def ratio(cs: list[dict], num: str, den: str):
    d = sum(c.get(den, 0) for c in cs)
    return sum(c.get(num, 0) for c in cs) / d if d else None


def summarize(cs: list[dict], iters: int = 2000, seed: int = 0) -> dict:
    metrics = {"top1": ("hit", "n_copy"), "recall": ("accused_copy", "n_copy"),
               "false_accusation": ("accused_indep", "n_indep"),
               "contamination_precision": ("ct_tp", "ct_pred"), "contamination_recall": ("ct_tp", "ct_truth")}
    out = {"cells": len(cs)}
    rng = random.Random(seed)
    for name, (a, b) in metrics.items():
        v = ratio(cs, a, b)
        if v is None:
            out[name] = None
            continue
        bs = sorted(x for x in (ratio([cs[rng.randrange(len(cs))] for _ in cs], a, b) for _ in range(iters)) if x is not None)
        out[name] = {"value": round(v, 3), "ci95": [round(bs[int(0.025 * len(bs))], 3), round(bs[int(0.975 * len(bs)) - 1], 3)]}
    ceil = ratio(cs, "ceiling_w", "ceiling_n")
    if ceil and out["top1"]:
        # the uniform-copier ceiling E[1/m]. It is an upper bound only if copiers pick uniformly among identical posts; a tracer
        # that exploits copier habits (e.g. "they copy the first link") or reads tags can exceed it, so a value above 1 is expected.
        out["uniform_ceiling_top1"] = round(ceil, 3)
        out["vs_uniform_ceiling"] = round(out["top1"]["value"] / ceil, 3)
    cn = sum(c.get("conf_n", 0) for c in cs)
    if cn:
        out["ece_accusations"] = round(abs(sum(c.get("conf_sum", 0) for c in cs) / cn - sum(c.get("conf_hit", 0) for c in cs) / cn), 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default=str(Path(__file__).parent))
    ap.add_argument("--pred")
    ap.add_argument("--baselines", action="store_true")
    ap.add_argument("--out", help="write the summaries as JSON")
    for k in ("world", "cond", "family"):
        ap.add_argument(f"--{k}")
    a = ap.parse_args()
    bench = Path(a.bench)
    cells = json.loads((bench / "manifest.json").read_text(encoding="utf-8"))
    for k in ("world", "cond", "family"):
        want = getattr(a, k)
        if want:
            cells = [c for c in cells if c[k] in want.split(",")]
    user = defaultdict(dict)
    if a.pred:
        for r in read_jsonl(Path(a.pred)):
            user[r["cell"]][r["agent"]] = {"source": r["source"], "confidence": r.get("confidence")}
    methods = ["latest", "earliest", "uniform", "conservative", "tags"] if a.baselines else []
    if a.pred:
        methods.append("YOUR PREDICTIONS")
    if not methods:
        ap.error("give --baselines and/or --pred")
    print(f"{len(cells)} cells ({', '.join(sorted({c['world'] for c in cells}))})")
    results = {"cells": len(cells), "filters": {k: getattr(a, k) for k in ("world", "cond", "family")}, "methods": {}}
    for m in methods:
        cs = []
        for c in cells:
            cid = c["cell"]
            log = read_jsonl(bench / "edit_log" / f"{cid}.jsonl")
            truth = read_jsonl(bench / "truth" / f"{cid}.jsonl")
            ceiling = json.loads((bench / "ceiling" / f"{cid}.json").read_text(encoding="utf-8"))
            registry = json.loads((bench / "registry" / f"{cid}.json").read_text(encoding="utf-8"))
            preds = user[cid] if m == "YOUR PREDICTIONS" else baseline(m, log, registry)
            cs.append(cell_counts(truth, preds, ceiling, c["world"] in ("W2", "W3")))
        s = summarize(cs)
        results["methods"][m] = s
        f = lambda k: "n/a" if not s.get(k) else f"{s[k]['value']:.2f} [{s[k]['ci95'][0]:.2f}-{s[k]['ci95'][1]:.2f}]"
        print(f"\n{m:18s} top1 {f('top1')}  recall {f('recall')}  false_accusation {f('false_accusation')}  "
              f"vs_uniform_ceiling {s.get('vs_uniform_ceiling', 'n/a')}  contamination P {f('contamination_precision')} R {f('contamination_recall')}"
              + (f"  ece {s['ece_accusations']}" if "ece_accusations" in s else ""))
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
