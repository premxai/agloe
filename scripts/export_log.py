"""Export one of our datasets as a log file in the swarm-log schema, ready to drop on the Colony page or the report card.

Schema (one JSON object per line): agent, time, channel, content; optional `kind` ("read" | "write" | "submit"), `source` (for a read: the
author of what was read) and `flag` (an output known to be bad). See frontend/card/index.html ("What format?").

  python -m scripts.export_log --dataset lab --cell W2-inert-qwen-n30-s1                       # our lab, WITH the hidden read log
  python -m scripts.export_log --dataset ai_village --lo 2026-03-23 --hi 2026-03-30            # one AI Village window (local only)
  python -m scripts.export_log --dataset collusion --limit 6000                                # the incident export (local only)

AI Village and the incident export are not ours to redistribute (research terms / marked "draft, do not share"): the files are written to
data/out/logs/, which is gitignored, and are meant to be dropped on the page on your own machine. Nothing is uploaded by the page.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.analysis import report as R

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "out" / "logs"


def write_jsonl(events: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, choices=["lab", "ai_village", "collusion"])
    ap.add_argument("--cell", help="lab cell id (a folder in data/lab)")
    ap.add_argument("--no-reads", action="store_true", help="lab: leave the hidden read log out (what a real investigator would have)")
    ap.add_argument("--lo"), ap.add_argument("--hi")
    ap.add_argument("--limit", type=int, default=0, help="keep only the first N events")
    ap.add_argument("--out", help="output path (default: data/out/logs/<dataset>_<what>.jsonl)")
    a = ap.parse_args()
    raw = ROOT / "data" / "raw"
    if a.dataset == "lab":
        if not a.cell:
            ap.error("--cell is required for the lab")
        ev = R.events_from_lab(ROOT / "data" / "lab" / a.cell / "world.json", with_reads=not a.no_reads)
        name = f"lab_{a.cell}{'_noreads' if a.no_reads else ''}"
    elif a.dataset == "ai_village":
        if not (a.lo and a.hi):
            ap.error("--lo and --hi (YYYY-MM-DD) are required for ai_village")
        ev = R.events_from_ai_village(raw / "ai_village", a.lo, a.hi)
        name = f"ai_village_{a.lo}_{a.hi}"
    else:
        ev = R.events_from_collusion(raw / "german")
        name = "collusion_incident"
    if a.limit:
        ev = ev[: a.limit]
    path = write_jsonl(ev, Path(a.out) if a.out else OUT / f"{name}.jsonl")
    print(f"{len(ev):,} events -> {path}")
    if a.dataset != "lab":
        print("LOCAL ONLY: this dataset is not ours to redistribute. Do not commit or upload the file; drop it on the page on your own machine.")


if __name__ == "__main__":
    main()
