"""Export Agloe-Bench from the lab runs: what a tracer sees, and the hidden answer key it is scored against.

  bench_release/
    manifest.json            cells: id, world, condition, family, n, seed
    edit_log/<cell>.jsonl    INPUT. the investigator's view: wiki writes + submissions (time-ordered, with URL routes)
    truth/<cell>.jsonl       HIDDEN KEY. per agent: copied from whom (from the read log) or independent; stale-output flag
    registry/<cell>.json     OPERATOR-SIDE INFO for the tag track only: tag/token -> the served copy it names
    ceiling/<cell>.json      best accuracy any tracer can reach from the edit log alone (uniform ceiling)
    score.py, README.md      (static files, in the repo)

Only our own offline lab runs are exported (no transcripts, no third-party logs). Agent names are lab labels (agent-NN).
Usage: python -m scripts.export_bench [--lab data/lab] [--out bench_release]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from experiments.lab.analyze_lab import first_valued, load_cells
from experiments.mini_swarm.analyze import investigator, route, truth_copies
from experiments.mini_swarm.world import STALE

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"https?://[^\s<>\"'`)\]]+")


def edit_log(w: dict) -> list[dict]:
    ev = [{"t": x["t"], "kind": "write", "agent": x["author"], "page": x["page"], "text": x["text"],
           "routes": sorted({route(u) for u in URL.findall(x["text"])})} for x in w["writes"]]
    ev += [{"t": s["t"], "kind": "submit", "agent": s["agent"], "answer": s["answer"], "urls": s.get("urls", []),
            "routes": sorted({route(u) for u in s.get("urls", [])})} for s in w["submissions"]]
    return sorted(ev, key=lambda e: (e["t"], e["kind"]))


def truth(w: dict) -> list[dict]:
    succ = first_valued(w)
    tr = truth_copies(w, succ, prefer_exact=True)
    answers = {s["agent"]: s["answer"] for s in w["submissions"]}
    rows = []
    for a in sorted(set(succ) | set(answers)):
        t = tr.get(a)
        rows.append({"agent": a, "copied": bool(t and t["copied"]), "parent": t["parent"] if t else None,
                     "route": t["route"] if t else None, "answered_stale": answers.get(a) == STALE})
    return rows


def registry(w: dict) -> dict:
    wiki_tokens = {k: {x: v[x] for x in ("reader", "page", "version", "author") if x in v}
                   for k, v in w.get("tokens", {}).items() if v.get("minted_by") == "wiki"}
    tags = {k: {x: v[x] for x in ("reader", "page", "version", "author") if x in v} for k, v in w.get("tags", {}).items()}
    return {"tokens": wiki_tokens, "tags": tags}


def ceiling(w: dict) -> dict:
    succ = first_valued(w)
    inv = investigator(w, truth_copies(w, succ, prefer_exact=True))
    return {"copiers": inv["copiers"], "uniform_ceiling": round(inv["edit_log_only_uniform_expectation"], 4),
            "latest_writer": round(inv["edit_log_only_latest"], 4)}


def export(lab: Path, out: Path) -> int:
    for d in ("edit_log", "truth", "registry", "ceiling"):
        (out / d).mkdir(parents=True, exist_ok=True)
    manifest = []
    for summary, w in load_cells(lab):
        if summary["world"] in ("FP", "W4", "W4G"):        # fingerprint runs have no wiki; the access-control worlds are a separate experiment
            continue
        cid = summary["cell"]
        (out / "edit_log" / f"{cid}.jsonl").write_text("\n".join(json.dumps(e) for e in edit_log(w)) + "\n", encoding="utf-8")
        (out / "truth" / f"{cid}.jsonl").write_text("\n".join(json.dumps(r) for r in truth(w)) + "\n", encoding="utf-8")
        (out / "registry" / f"{cid}.json").write_text(json.dumps(registry(w)), encoding="utf-8")
        (out / "ceiling" / f"{cid}.json").write_text(json.dumps(ceiling(w)), encoding="utf-8")
        manifest.append({k: summary[k] for k in ("cell", "world", "cond", "family", "n", "seed")})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return len(manifest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default=str(ROOT / "data" / "lab"))
    ap.add_argument("--out", default=str(ROOT / "bench_release"))
    a = ap.parse_args()
    n = export(Path(a.lab), Path(a.out))
    print(f"exported {n} cells -> {a.out}")


if __name__ == "__main__":
    main()
