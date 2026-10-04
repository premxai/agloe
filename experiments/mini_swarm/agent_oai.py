"""One agent against the offline World via an OpenAI-compatible API (Nebius Token Factory).

Mirror of agent.py's manual loop, but for chat.completions + OpenAI-style function calling, so we can run
non-Anthropic model families (Qwen, DeepSeek, Kimi, GLM, gpt-oss, Nemotron, ...) in the SAME offline world.
Used for the cross-family coincidence experiment: independent agents, no wiki, measure the "random" values
each model family reaches for. Still fully offline (.invalid mirrors); nothing hits the real internet.

Budget: token-based. Nebius per-model $/M prices vary and are not all known here, so we track exact token
counts and apply a CONSERVATIVE flat estimate for a running-cost display; the authoritative spend is the
Nebius console. A hard token cap bounds the run regardless.
"""
from __future__ import annotations

import json

from experiments.mini_swarm.agent import MAX_TOOL_CALLS, run_tool, task_prompt
from experiments.mini_swarm.world import World

NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1"
# Conservative cost estimate only (USD per 1M tokens, input/output). Real spend = Nebius console.
EST_PRICE = (1.0, 3.0)


def _oai_tools(board: bool) -> list:
    """OpenAI function-tool specs mirroring the World's tools."""
    core = [
        {"type": "function", "function": {
            "name": "fetch", "description": "Fetch a URL and return the response body (or an error).",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                           "required": ["url"], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "submit", "description": "Submit your final answer and the exact URL(s) that worked. Ends your task.",
            "parameters": {"type": "object", "properties": {
                "answer": {"type": "number"}, "urls": {"type": "array", "items": {"type": "string"}}},
                "required": ["answer", "urls"], "additionalProperties": False}}},
    ]
    wiki = [
        {"type": "function", "function": {
            "name": "list_pages", "description": "List the pages on your team's shared wiki.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "read_page", "description": "Read a page on the team wiki.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                           "required": ["name"], "additionalProperties": False}}},
        {"type": "function", "function": {
            "name": "write_page", "description": "Add text to a wiki page (creates it if new). Others can read it.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
                           "required": ["name", "text"], "additionalProperties": False}}},
    ]
    return core + (wiki if board else [])


class TokenBudget:
    """Token cap, plus an optional USD cap when exact per-token prices are supplied to add()."""

    def __init__(self, cap_tokens: int, used: int = 0, cap_usd: float | None = None, spent_usd: float = 0.0):
        self.cap, self.used = cap_tokens, used
        self.cap_usd, self.spent_usd = cap_usd, spent_usd

    def check(self):
        if self.used >= self.cap:
            raise RuntimeError(f"token budget {self.cap} reached (used {self.used})")
        if self.cap_usd is not None and self.spent_usd >= self.cap_usd:
            raise RuntimeError(f"USD budget ${self.cap_usd:.2f} reached (spent ${self.spent_usd:.2f})")

    def add(self, usage, price: tuple[float, float] | None = None) -> tuple[int, int]:
        pin = getattr(usage, "prompt_tokens", 0) or 0
        pout = getattr(usage, "completion_tokens", 0) or 0
        self.used += pin + pout
        if price:
            self.spent_usd += pin * price[0] + pout * price[1]
        return pin, pout


def fetch_prices(api_key: str, cache_path=None, base_url: str = NEBIUS_BASE_URL) -> dict:
    """model id -> (USD per input token, USD per output token), from the provider's verbose model list.

    Cached to `cache_path` (JSON) so runs are reproducible and do not depend on a live call."""
    import httpx

    r = httpx.get(base_url + "/models", params={"verbose": "true"},
                  headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    r.raise_for_status()
    prices = {}
    for m in r.json().get("data", []):
        p = m.get("pricing") or {}
        try:
            prices[m["id"]] = (float(p.get("prompt", 0)), float(p.get("completion", 0)))
        except (TypeError, ValueError):
            continue
    if cache_path is not None:
        from pathlib import Path
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(prices, indent=1), encoding="utf-8")
    return prices


async def run_agent_oai(client, model: str, world: World, agent: str, budget: TokenBudget,
                        max_calls: int = MAX_TOOL_CALLS, price: tuple[float, float] | None = None) -> dict:
    import openai

    tools = _oai_tools(world.board)
    messages = [{"role": "user", "content": task_prompt(world.board, max_calls, getattr(world, "notes_protocol", False))}]
    calls, tin, tout, status, nudged = 0, 0, 0, "max_calls", False
    while calls < max_calls:
        budget.check()
        try:
            resp = await client.chat.completions.create(
                model=model, messages=messages, tools=tools, tool_choice="auto", max_tokens=1500)
        except openai.AuthenticationError:
            status = "api_error:auth"; break
        except openai.BadRequestError as e:
            status = f"api_error:badrequest:{str(e)[:60]}"; break
        except openai.APIStatusError as e:
            status = f"api_error:{e.status_code}"; break
        except openai.APIConnectionError:
            status = "api_error:connection"; break
        if resp.usage:
            a, b = budget.add(resp.usage, price); tin += a; tout += b
        msg = resp.choices[0].message
        tcs = msg.tool_calls or []
        # append the assistant turn (content + any tool_calls) for the next request
        asst = {"role": "assistant", "content": msg.content or ""}
        if tcs:
            asst["tool_calls"] = [{"id": tc.id, "type": "function",
                                   "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                                  for tc in tcs]
        messages.append(asst)
        if not tcs:
            if nudged:
                status = "stopped"; break
            nudged = True
            messages.append({"role": "user", "content": "Please use the tools to try URLs, or call submit."})
            continue
        done = False
        for tc in tcs:
            calls += 1
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out = run_tool(world, agent, tc.function.name, args if isinstance(args, dict) else {})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
            done = done or tc.function.name == "submit"
        if done:
            status = "submitted"; break
    if price:
        cost, exact = tin * price[0] + tout * price[1], True
    else:
        cost, exact = tin * EST_PRICE[0] / 1e6 + tout * EST_PRICE[1] / 1e6, False
    return {"agent": agent, "model": model, "status": status, "tool_calls": calls,
            "tokens_in": tin, "tokens_out": tout, "est_cost_usd": round(cost, 6), "cost_exact": exact,
            "transcript": messages}
