"""Cross-family coincidence experiment on Nebius Token Factory (OpenAI-compatible).

Runs the no-wiki task (independent agents, no communication) across several model FAMILIES in the same
offline world, so we can measure how often agents reach for the same 'random' value within a family vs
across families. This is the controlled, ground-truth counterpart to the AI Village observation and the
collusion.wiki `x=1` finding: if same-family collision >> cross-family, monoculture is model-specific and
naive string-matching systematically over-links same-model agents.

Fully offline (.invalid mirrors). Token-budgeted; authoritative spend is the Nebius console.

Usage:
  python -m experiments.mini_swarm.run_nebius --smoke          # 1 agent x 2 families, sanity
  python -m experiments.mini_swarm.run_nebius --n 30           # full: 30 agents x all families
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
SPEND = OUT / "nebius_tokens.json"

# one representative instruct model per family; all expose OpenAI-style tool calling on Nebius
MODELS = {
    "qwen": "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "deepseek": "deepseek-ai/DeepSeek-V4-Pro",
    "kimi": "moonshotai/Kimi-K3",
    "glm": "zai-org/GLM-5.2",
    "gptoss": "openai/gpt-oss-120b",
    "nemotron": "nvidia/nemotron-3-super-120b-a12b",
    "minimax": "MiniMaxAI/MiniMax-M3",
    "hermes": "NousResearch/Hermes-4-405B",       # Llama lineage
    "gemma": "google/gemma-3-27b-it",             # Google lineage
}
TOKEN_CAP = 25_000_000      # hard bound; ~<$30 even at worst-case flat estimate


def _used() -> int:
    return json.loads(SPEND.read_text())["tokens"] if SPEND.exists() else 0


def _save_used(v: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SPEND.write_text(json.dumps({"tokens": v}))


async def run_family(client, family: str, model: str, n: int, concurrency: int, seed: int,
                     budget, max_calls: int) -> dict:
    from experiments.mini_swarm.agent_oai import run_agent_oai
    from experiments.mini_swarm.world import World

    world = World(condition="none", board=False, seed=seed)
    sem = asyncio.Semaphore(concurrency)
    results: list = []

    async def one(i: int):
        async with sem:
            try:
                results.append(await run_agent_oai(client, model, world, f"agent-{i + 1:02d}", budget, max_calls))
            except Exception as e:                                   # noqa: BLE001 - budget/transport, logged
                results.append({"agent": f"agent-{i + 1:02d}", "model": model, "status": f"error:{type(e).__name__}"})
    t0 = time.time()
    await asyncio.gather(*(one(i) for i in range(n)))
    _save_used(budget.used)
    run_dir = OUT / f"NEB-{family}-seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {k: v for k, v in asdict(world).items() if k != "pages"}
    state["pages"] = {p: [asdict(c) for c in cs] for p, cs in world.pages.items()}
    (run_dir / "world.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    with open(run_dir / "transcripts.jsonl", "w", encoding="utf-8") as f:
        for r in sorted(results, key=lambda r: r["agent"]):
            f.write(json.dumps(r, default=str) + "\n")
    statuses = {s: sum(1 for r in results if r.get("status") == s) for s in {r.get("status") for r in results}}
    summary = {"family": family, "model": model, "n": n, "seed": seed, "statuses": statuses,
               "tokens_in": sum(r.get("tokens_in", 0) for r in results),
               "tokens_out": sum(r.get("tokens_out", 0) for r in results),
               "est_cost_usd": round(sum(r.get("est_cost_usd", 0) for r in results), 4),
               "total_tokens_used": budget.used, "seconds": round(time.time() - t0, 1)}
    (run_dir / "run.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return summary


async def main_async(a) -> None:
    import os

    from dotenv import load_dotenv
    from openai import AsyncOpenAI

    from experiments.mini_swarm.agent_oai import NEBIUS_BASE_URL, TokenBudget

    load_dotenv(ROOT / ".env")
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise SystemExit("NEBIUS_API_KEY not set in lineage/.env")
    client = AsyncOpenAI(base_url=NEBIUS_BASE_URL, api_key=key, max_retries=4, timeout=120)
    budget = TokenBudget(TOKEN_CAP, _used())
    fams = list(MODELS) if a.models == "all" else a.models.split(",")
    n = 1 if a.smoke else a.n
    conc = 2 if a.smoke else a.concurrency
    fams = fams[:2] if a.smoke else fams
    for fam in fams:
        await run_family(client, fam, MODELS[fam], n, conc, a.seed, budget, a.max_calls)
    print(f"\ntotal tokens used (cumulative): {budget.used}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=8)
    ap.add_argument("--models", default="all", help="'all' or comma list of families")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
