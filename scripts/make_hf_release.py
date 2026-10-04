"""Assemble the Hugging Face dataset folder (hf_release/, not committed) from what this repository already holds.

  python -m scripts.make_hf_release

Contents: the benchmark (bench/), the lab run records without agent transcripts (lab_runs/, plus lab_runs_discarded_designs/ for the flawed designs
described in the paper), the analysis outputs the paper reads (analysis/), a dataset card (README.md) and MANIFEST.sha256.
NEVER included: raw AI Village or incident data, transcripts, live-demo runs, keys. See docs/HF_RELEASE.md for the upload commands.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from experiments.lab.analyze_lab import SMOKE_SEED_MIN

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hf_release"
LAB = ROOT / "data" / "lab"
ANALYSIS = [
    (LAB / "lab_results.json", "lab_results.json"),
    (LAB / "cleanup_savings.json", "cleanup_savings.json"),
    (LAB / "spend.json", "lab_spend.json"),
    (ROOT / "frontend" / "data" / "results.json", "results.json"),
    (ROOT / "bench_release" / "baselines.json", "baselines.json"),
    (ROOT / "data" / "out" / "ai_village_full.json", "ai_village_full_aggregates.json"),
]
KEEP = {"run.json", "world.json"}          # transcripts are deliberately left out


def commit() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def wipe(path: Path) -> None:
    """Empty a folder. Files go first (retrying), folders are removed best-effort: a synced folder (OneDrive) can briefly refuse a delete."""
    if not path.exists():
        return
    for f in [p for p in path.rglob("*") if p.is_file()]:
        for _ in range(5):
            try:
                f.unlink()
                break
            except PermissionError:
                time.sleep(0.5)
    for d in sorted((p for p in path.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            d.rmdir()
        except OSError:
            pass


def is_connectivity_check(run_dir: Path) -> bool:
    try:
        return json.loads((run_dir / "run.json").read_text(encoding="utf-8")).get("seed", 0) >= SMOKE_SEED_MIN
    except (OSError, ValueError):
        return False


def copy_runs() -> tuple[int, int]:
    kept = discarded = 0
    for f in sorted(LAB.rglob("*")):
        if not f.is_file() or f.name not in KEEP:
            continue
        rel = f.relative_to(LAB)
        top = rel.parts[0]
        if top == "lab_live" or (not top.startswith("_invalid") and is_connectivity_check(f.parent)):
            continue
        folder = "lab_runs_discarded_designs" if top.startswith("_invalid") else "lab_runs"
        dst = OUT / folder / (Path(*rel.parts[1:]) if folder.endswith("designs") and len(rel.parts) > 2 else rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        if f.name == "run.json":
            discarded += folder.endswith("designs")
            kept += not folder.endswith("designs")
    return kept, discarded


def card(res: dict, runs: int, discarded: int) -> str:
    sp = res.get("spend", {})
    return f"""# Trap-street benchmark and lab records for agent swarms (dataset card)

**Status: draft. Fill the TODO lines before publishing.**

Data for the paper "Trap Streets for Agent Swarms: Making Copying Confess When Reads Go Unlogged": a benchmark for tracing how an item spread between LLM agents from their
edit logs, with a hidden read log as the answer key, and the run records of the offline lab behind the paper's results.

## Contents
| Folder | What it is |
|---|---|
| `bench/` | The benchmark: `manifest.json`, `edit_log/` (the input a tracer sees), `truth/` (hidden answer key), `registry/` (token to served copy, for the token track), `ceiling/`, `baselines.json`, `score.py` (standard library only), `README.md` (format). {sp.get('bench_cells', 187)} cells; the {150} with inert or load-bearing tags form the baseline set. |
| `lab_runs/` | One folder per lab run (a swarm): `run.json` (world, tag condition, model family, size, seed, cost) and `world.json` (writes, served reads, fetches, submissions, tokens). {runs} runs, {sp.get('lab_agent_runs', 'about 7,300')} agent runs in total. **No agent transcripts.** |
| `lab_runs_discarded_designs/` | Run records ({discarded} runs) of two of the three bad-tip designs we set aside as flawed, kept so the claim can be checked. Connectivity checks (seed 900 and up) are not included. |
| `analysis/` | The analysis outputs the paper's figures, tables and numbers are generated from. `ai_village_full_aggregates.json` holds weekly counts only. |
| `MANIFEST.sha256` | Checksums of every file. |

## How the data was made
All runs are offline: every host is on the reserved `.invalid` domain, the tasks are benign and fictional, and nothing touched anyone's live system. Agents are open-weight models
(eight families) reached through one inference provider; **TODO: provider, date range, sampling settings.** "Copied" means exposure before use (the agent was served the item
first); it says nothing about intent. In untagged conditions byte-identical links make the source undefined, so attribution is scored only on tagged conditions.

## Not included
Raw AI Village data (gated, research-use; cite AI Digest, "AI Village dataset", 2026) and the real incident logs (not for redistribution). Nothing here contains their text,
handles or URLs; `ai_village_full_aggregates.json` is counts per week.

## Licence and citation
**TODO: licence (CC BY 4.0 is a common choice for data).** Code: https://github.com/premxai/agloe (commit `{commit()}` when this folder was built). **TODO: citation (arXiv ID) once posted.**
"""


def main() -> None:
    wipe(OUT)
    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "bench_release", OUT / "bench", dirs_exist_ok=True)
    kept, discarded = copy_runs()
    (OUT / "analysis").mkdir()
    for src, name in ANALYSIS:
        if src.exists():
            shutil.copy2(src, OUT / "analysis" / name)
        else:
            print("missing (skipped):", src.relative_to(ROOT))
    res = json.loads((ROOT / "frontend" / "data" / "results.json").read_text(encoding="utf-8"))
    (OUT / "README.md").write_text(card(res, kept, discarded), encoding="utf-8")
    lines = []
    for f in sorted(OUT.rglob("*")):
        if f.is_file() and f.name != "MANIFEST.sha256":
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(OUT).as_posix()}")
    (OUT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"hf_release/: {len(lines)} files, {size / 1e6:.0f} MB; {kept} lab runs + {discarded} discarded-design runs; no transcripts")


if __name__ == "__main__":
    main()
