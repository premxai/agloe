"""Run one arm of the Agloe mini-swarm and save everything needed to rebuild the results offline.

Arms:
  A0  Haiku 4.5, no wiki           -> what 'random' choices and routes does one model make independently?
  A1  Sonnet 5.5, no wiki          -> same, other model (same-model vs cross-model coincidences)
  B   Haiku, wiki, no tags         -> how well can the edit log alone name sources? (answer key = read log)
  C1  Haiku, wiki, inert tags      -> do random-looking tags survive copying?
  C3  Haiku, wiki, load-bearing    -> do tags that the link needs survive copying?

Usage: python -m experiments.mini_swarm.run --arm B --n 30 [--concurrency 3] [--seed 0] [--budget 25]
The budget is global across all runs (tracked in data/mini_swarm/spend.json) and checked before every request.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "mini_swarm"
ARMS = {
    "A0": ("claude-haiku-4-5", False, "none"),
    "A1": ("claude-sonnet-5-5", False, "none"),
    "B": ("claude-haiku-4-5", True, "none"),
    "C1": ("claude-haiku-4-5", True, "inert"),
    "C3": ("claude-haiku-4-5", True, "loadbearing"),
}


def _load_api_key() -> None:
    """Load ANTHROPIC_API_KEY from .env, accepting either `KEY=value` lines or a bare-key file.

    A bare-key file is what you get when a key is pasted straight into a new file; we never print the
    value, only set it in the process environment for the SDK to read.
    """
    import os

    from dotenv import load_dotenv

    env = ROOT / ".env"
    load_dotenv(env)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" not in s:
                os.environ["ANTHROPIC_API_KEY"] = s        # bare key on its own line
                return


def _spent() -> float:
    f = OUT / "spend.json"
    return json.loads(f.read_text())["spent_usd"] if f.exists() else 0.0


def _save_spent(v: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "spend.json").write_text(json.dumps({"spent_usd": round(v, 6)}))


async def run_arm(arm: str, n: int, concurrency: int, seed: int, budget_cap: float, client=None,
                  max_calls: int = 10) -> Path:
    from experiments.mini_swarm.agent import Budget, BudgetExceeded, run_agent
    from experiments.mini_swarm.world import World

    model, board, cond = ARMS[arm]
    world = World(condition=cond, board=board, seed=seed)
    budget = Budget(budget_cap, _spent())
    if client is None:
        import anthropic
        _load_api_key()
        client = anthropic.AsyncAnthropic(max_retries=4)
    sem = asyncio.Semaphore(concurrency)
    results: list = []

    async def one(i: int):
        async with sem:
            try:
                results.append(await run_agent(client, model, world, f"agent-{i + 1:02d}", budget, max_calls))
            except BudgetExceeded as e:
                results.append({"agent": f"agent-{i + 1:02d}", "status": "budget", "error": str(e)})
    t0 = time.time()
    await asyncio.gather(*(one(i) for i in range(n)))
    _save_spent(budget.spent)
    run_dir = OUT / f"{arm}-seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {k: v for k, v in asdict(world).items() if k != "pages"}
    state["pages"] = {p: [asdict(c) for c in cs] for p, cs in world.pages.items()}
    (run_dir / "world.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    with open(run_dir / "transcripts.jsonl", "w", encoding="utf-8") as f:
        for r in sorted(results, key=lambda r: r["agent"]):
            f.write(json.dumps(r, default=str) + "\n")
    summary = {"arm": arm, "model": model, "board": board, "condition": cond, "n": n, "seed": seed,
               "statuses": {s: sum(1 for r in results if r.get("status") == s) for s in {r.get("status") for r in results}},
               "arm_cost_usd": round(sum(r.get("cost_usd", 0) for r in results), 4), "total_spent_usd": round(budget.spent, 4),
               "seconds": round(time.time() - t0, 1)}
    (run_dir / "run.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return run_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS), required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=float, default=25.0)
    ap.add_argument("--max-calls", type=int, default=10, help="tool-call cap per agent (load-bearing arms need more)")
    a = ap.parse_args()
    asyncio.run(run_arm(a.arm, a.n, a.concurrency, a.seed, a.budget, max_calls=a.max_calls))


if __name__ == "__main__":
    main()
