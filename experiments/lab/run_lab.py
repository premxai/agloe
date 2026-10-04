"""Resumable lab runner (Nebius Token Factory, OpenAI-compatible). All worlds are offline (.invalid).

  python -m experiments.lab.run_lab --phase smoke
  python -m experiments.lab.run_lab --phase P1 --dry-run        # projected cost from live prices, no calls
  python -m experiments.lab.run_lab --phase P3,P4,P5,P6          # chained (e.g. overnight)
  python -m experiments.lab.run_lab --status

A cell is done when data/lab/<cell>/run.json exists; finished cells are skipped, so a crashed or timed-out phase is
simply relaunched. Spend is exact (live per-token prices, cached in data/lab/nebius_prices.json) and capped: the cap
is checked before every request, and a cell interrupted by the cap is not marked done.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from experiments.lab.grid import CELL_CONCURRENCY, PHASES, ROSTER, Cell, phase

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "lab"
SPEND = LAB / "spend.json"
PRICES = LAB / "nebius_prices.json"
EST_TOKENS = {"FP": (3000, 500), "wiki": (10000, 1500)}   # per agent (in, out), from measured runs
OK_STATUSES = {"submitted", "max_calls", "stopped"}
FAMILY_OF = {m: f for f, m in ROSTER.items()}


def _spent() -> dict:
    return json.loads(SPEND.read_text()) if SPEND.exists() else {"spent_usd": 0.0, "tokens": 0}


def _save_spent(budget) -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    tmp = SPEND.with_suffix(".tmp")
    tmp.write_text(json.dumps({"spent_usd": round(budget.spent_usd, 6), "tokens": budget.used}))
    tmp.replace(SPEND)


def _key() -> str:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    k = os.environ.get("NEBIUS_API_KEY")
    if not k:
        raise SystemExit("NEBIUS_API_KEY not set in lineage/.env")
    return k


def load_prices(refresh: bool = False) -> dict:
    if PRICES.exists() and not refresh:
        return {k: tuple(v) for k, v in json.loads(PRICES.read_text()).items()}
    from experiments.mini_swarm.agent_oai import fetch_prices
    return fetch_prices(_key(), PRICES)


def estimate(cells: list[Cell], prices: dict) -> float:
    tot = 0.0
    for c in cells:
        tin, tout = EST_TOKENS["FP" if c.world == "FP" else "wiki"]
        for m in c.models():
            pin, pout = prices.get(m, (1e-6, 3e-6))
            tot += tin * pin + tout * pout
    return tot


def done(cell: Cell) -> bool:
    return (LAB / cell.id / "run.json").exists()


async def run_cell(client, cell: Cell, budget, prices: dict) -> dict:
    from experiments.mini_swarm.agent_oai import run_agent_oai
    from experiments.mini_swarm.world import World

    world = World(condition=cell.cond, board=cell.board, seed=cell.seed, seed_rumor=cell.rumor, rumor_after=cell.rumor_after,
                  notes_protocol=cell.notes, rumor_page="Notes",        # W2/W3/W4: agents post to "Notes"; the tip appears there
                  silent_stale=cell.rumor,                              # ...and the stale mirror gives no warning (a silent bad tip)
                  seed_access=cell.access_seed, gated=cell.gated)       # W4/W4G: a coordinator's entry link; W4G: no sessions on request
    models = cell.models()
    sem = asyncio.Semaphore(CELL_CONCURRENCY)
    results: list = []

    async def one(i: int):
        name = f"agent-{i + 1:02d}"
        async with sem:
            try:
                results.append(await run_agent_oai(client, models[i], world, name, budget, cell.max_calls,
                                                   price=prices.get(models[i])))
            except RuntimeError as e:                     # budget cap
                results.append({"agent": name, "model": models[i], "status": "budget", "error": str(e)})
            except Exception as e:                        # noqa: BLE001 - transport errors are recorded, not fatal
                results.append({"agent": name, "model": models[i], "status": f"error:{type(e).__name__}"})
    t0 = time.time()
    await asyncio.gather(*(one(i) for i in range(cell.n)))
    _save_spent(budget)
    statuses = Counter(r.get("status") for r in results)
    ok = sum(v for k, v in statuses.items() if k in OK_STATUSES)
    run_dir = LAB / cell.id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {k: v for k, v in asdict(world).items() if k != "pages"}
    state["pages"] = {p: [asdict(c) for c in cs] for p, cs in world.pages.items()}
    (run_dir / "world.json").write_text(json.dumps(state, default=str), encoding="utf-8")
    with gzip.open(run_dir / "transcripts.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in sorted(results, key=lambda r: r["agent"]):
            f.write(json.dumps(r, default=str) + "\n")
    summary = {"cell": cell.id, **asdict(cell), "max_calls": cell.max_calls, "cell_concurrency": CELL_CONCURRENCY,
               "agents": {r["agent"]: r.get("model") for r in results},
               "families": {r["agent"]: FAMILY_OF.get(r.get("model"), "?") for r in results},
               "statuses": dict(statuses),
               "cost_usd": round(sum(r.get("est_cost_usd", 0) for r in results), 6),
               "tokens_in": sum(r.get("tokens_in", 0) for r in results),
               "tokens_out": sum(r.get("tokens_out", 0) for r in results),
               "seconds": round(time.time() - t0, 1)}
    if statuses.get("budget"):
        summary["incomplete"] = "budget cap reached"
    elif ok < 0.8 * cell.n:
        summary["incomplete"] = f"only {ok}/{cell.n} agents finished normally"
    if "incomplete" in summary:
        (run_dir / "failed.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    else:
        (run_dir / "run.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        failed = run_dir / "failed.json"
        if failed.exists():
            failed.unlink()
    return summary


async def run_phases(names: list[str], cap: float, parallel: int) -> None:
    from openai import AsyncOpenAI

    from experiments.mini_swarm.agent_oai import NEBIUS_BASE_URL, TokenBudget

    prices = load_prices()
    s = _spent()
    budget = TokenBudget(10**12, s["tokens"], cap_usd=cap, spent_usd=s["spent_usd"])
    client = AsyncOpenAI(base_url=NEBIUS_BASE_URL, api_key=_key(), max_retries=6, timeout=180)
    for name in names:
        todo = [c for c in phase(name) if not done(c)]
        proj = estimate(todo, prices)
        print(f"\n=== {name}: {len(todo)} cells to run, projected ${proj:.2f}, spent so far ${budget.spent_usd:.2f} / cap ${cap:.2f}",
              flush=True)
        gate = asyncio.Semaphore(parallel)
        stop = False

        async def guarded(c: Cell):
            nonlocal stop
            async with gate:
                if stop:
                    return
                r = await run_cell(client, c, budget, prices)
                flag = f"  INCOMPLETE: {r['incomplete']}" if "incomplete" in r else ""
                print(f"  {c.id:34s} {json.dumps(r['statuses'])[:70]:70s} ${r['cost_usd']:.4f}  "
                      f"total ${budget.spent_usd:.2f}  {r['seconds']}s{flag}", flush=True)
                if r.get("incomplete") == "budget cap reached":
                    stop = True
        await asyncio.gather(*(guarded(c) for c in todo))
        if stop:
            print(f"STOPPED: budget cap ${cap:.2f} reached during {name}", flush=True)
            return
    print(f"\nall requested phases done; total spent ${budget.spent_usd:.2f}", flush=True)


def status() -> None:
    s = _spent()
    print(f"spent ${s['spent_usd']:.2f}  tokens {s['tokens']:,}")
    for name in PHASES:
        cells = phase(name)
        k = sum(done(c) for c in cells)
        failed = sum((LAB / c.id / "failed.json").exists() for c in cells)
        print(f"  {name:6s} {k:3d}/{len(cells):3d} cells done" + (f"  ({failed} failed, will retry)" if failed else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", help="comma list, e.g. P1 or P3,P4,P5,P6")
    ap.add_argument("--cap", type=float, default=100.0, help="hard USD cap across all lab phases")
    ap.add_argument("--parallel", type=int, default=3, help="cells run at once (each cell has its own world)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh-prices", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        status(); return
    if not a.phase:
        ap.error("--phase or --status required")
    names = [p.strip() for p in a.phase.split(",") if p.strip()]
    if a.dry_run:
        prices = load_prices(a.refresh_prices)
        tot = 0.0
        for n in names:
            cells = phase(n); todo = [c for c in cells if not done(c)]
            e = estimate(todo, prices); tot += e
            print(f"{n:6s} cells {len(cells):3d} (todo {len(todo):3d})  agent runs {sum(c.n for c in todo):5d}  projected ${e:7.2f}")
        print(f"total projected ${tot:.2f}; already spent ${_spent()['spent_usd']:.2f}")
        return
    if a.refresh_prices:
        load_prices(True)
    asyncio.run(run_phases(names, a.cap, a.parallel))


if __name__ == "__main__":
    main()
