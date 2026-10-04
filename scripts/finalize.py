"""Rebuild every derived artifact from the lab data, in dependency order (no API calls).

  python -m scripts.finalize            # analysis -> site data -> RESULTS (lab) -> bench -> baselines -> replays -> paper + PDF
  python -m scripts.finalize --tests    # ...and then the unit tests and the card parity test

The lab itself is run with `python -m experiments.lab.run_lab --phase ...` (needs NEBIUS_API_KEY).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
REPLAYS = [  # (lab cell, file name, title): real swarms chosen as clear examples; see docs/RESULTS.md (P.4)
    ("W2E-loadbearing-qwen-n30-s4", "early_tip_tags", "A bad tip from the start takes over the swarm (Qwen3-235B agents)"),
    ("W2-inert-qwen-n30-s3", "late_tip_tags", "A bad tip arrives mid-run (Qwen3-235B agents)"),
    ("W1-loadbearing-qwen-n30-s1", "no_tip", "No bad tip: agents share working links (Qwen3-235B agents)"),
    ("W2-inert-qwen-n30-s1", "cleanup_tip_tags", "A late bad tip that only a few agents used (Qwen3-235B agents)"),   # the Face-Off's clean-up scene
]


def run(args: list[str], label: str) -> None:
    print(f"\n== {label}", flush=True)
    r = subprocess.run([PY, *args], cwd=ROOT)
    if r.returncode:
        raise SystemExit(f"step failed: {label}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", action="store_true")
    a = ap.parse_args()
    run(["-m", "experiments.lab.analyze_lab"], "lab analysis -> data/lab/lab_results.json")
    if (ROOT / "data" / "raw" / "ai_village" / "chat_messages.jsonl.gz").exists():      # gated raw export: only on a machine that has it
        run(["-m", "scripts.run_ai_village_full"], "AI Village whole-dataset coverage -> data/out/ai_village_full.json")
    run(["-m", "scripts.cleanup_savings"], "cleanup savings -> data/lab/cleanup_savings.json")
    run(["-m", "scripts.build_site_data"], "site data -> frontend/data/results.json")
    run(["-m", "scripts.write_results_lab"], "RESULTS.md lab sections")
    run(["-m", "scripts.export_bench"], "Agloe-Bench export")
    run(["bench_release/score.py", "--baselines", "--cond", "loadbearing,inert", "--out", "bench_release/baselines.json"], "benchmark baselines")
    for cell, name, title in REPLAYS:
        if (ROOT / "data" / "lab" / cell / "run.json").exists():
            run(["-m", "scripts.export_lab_replay", cell, "--name", name, "--title", title], f"replay: {name}")
    run(["-m", "scripts.make_card_fixtures"], "report-card parity fixtures")
    run(["-m", "scripts.make_colony_samples"], "colony sample logs (lab runs with their hidden read log)")
    run(["-m", "scripts.build_og"], "social share image")
    run(["-m", "scripts.build_paper", "--pdf"], "paper (HTML + PDF)")
    if a.tests:
        run(["-m", "pytest", "tests", "-q"], "unit tests")
        subprocess.run(["node", "frontend/card/parity.test.mjs"], cwd=ROOT, check=True)
        subprocess.run(["node", "frontend/card/colony.test.mjs"], cwd=ROOT, check=True)
    print("\nall derived artifacts rebuilt")


if __name__ == "__main__":
    main()
