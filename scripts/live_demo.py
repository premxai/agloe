"""Run a fresh swarm live (offline sandbox, Nebius) and export it to the replay page.

  python -m scripts.live_demo                     # 30 agents, a bad tip from the start, load-bearing tags (~1 min, a few cents)
  python -m scripts.live_demo --world W2 --cond inert --n 30 --family qwen

Then open the replay page and pick "LIVE ..." in the swarm picker (or add ?swarm=live.json).
Everything runs against reserved .invalid hosts; nothing leaves the sandbox. The key is read from lineage/.env.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from experiments.lab import run_lab
from experiments.lab.grid import Cell
from scripts.export_lab_replay import build

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "data" / "lab_live"


async def go(cell: Cell) -> dict:
    from openai import AsyncOpenAI

    from experiments.mini_swarm.agent_oai import NEBIUS_BASE_URL, TokenBudget

    run_lab.LAB = LIVE
    run_lab.SPEND = LIVE / "spend.json"
    prices = run_lab.load_prices()
    client = AsyncOpenAI(base_url=NEBIUS_BASE_URL, api_key=run_lab._key(), max_retries=6, timeout=180)
    budget = TokenBudget(10**9, cap_usd=3.0)                      # a live demo never needs more than a few cents
    return await run_lab.run_cell(client, cell, budget, prices)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="W2E", choices=["W1", "W2", "W2E"])
    ap.add_argument("--cond", default="loadbearing", choices=["none", "inert", "loadbearing"])
    ap.add_argument("--family", default="qwen")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=random.randrange(9000, 9999))
    a = ap.parse_args()
    cell = Cell(a.world, a.cond, a.family, a.n, a.seed)
    print(f"running {cell.n} {cell.family} agents live: world {cell.world}, tags {cell.cond}, seed {cell.seed} ...", flush=True)
    t0 = time.time()
    summary = asyncio.run(go(cell))
    print(f"done in {time.time() - t0:.0f}s, cost ${summary['cost_usd']:.3f}, statuses {summary['statuses']}", flush=True)
    d = LIVE / cell.id
    if not (d / "run.json").exists():
        raise SystemExit("run incomplete (see failed.json); try again")
    out = build(json.loads((d / "run.json").read_text(encoding="utf-8")), json.loads((d / "world.json").read_text(encoding="utf-8")))
    out["title"] = f"LIVE {time.strftime('%H:%M')} · {cell.world} · {cell.cond} tags · {cell.family}"
    dest = ROOT / "frontend" / "replay" / "data"
    (dest / "live.json").write_text(json.dumps(out), encoding="utf-8")
    index = [{"file": p.name, "title": json.loads(p.read_text(encoding="utf-8")).get("title", p.stem)}
             for p in sorted(dest.glob("*.json")) if p.name != "index.json"]
    index.sort(key=lambda r: (r["file"] != "live.json", r["file"]))              # the live swarm first
    (dest / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    s = out["stats"]
    print(f"{s['agents']} agents, {s['stale_outputs']} adopted the bad tip | edit log named {s['edit_log_correct']}/{s['copied']} sources, "
          f"tags {s['tags_correct']}/{s['copied']}\nopen: replay/?swarm=live.json")


if __name__ == "__main__":
    main()
