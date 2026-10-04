"""One agent: a manual tool-use loop against the offline World (Anthropic Python SDK, async).

A manual loop (not the beta tool runner) because the harness needs per-call control: a shared logical clock,
a hard turn cap, a global budget check before every request, and a stop as soon as the agent submits.
"""
from __future__ import annotations

import json

import anthropic

from experiments.mini_swarm.world import MIRRORS, TARGET, World

PRICES = {  # USD per million tokens (input, output)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
}
MAX_TOOL_CALLS = 10

WIKI_TOOLS = [
    {"name": "list_pages", "description": "List the pages on your team's shared wiki.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "read_page", "description": "Read a page on the team wiki.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}},
    {"name": "write_page", "description": "Add text to a wiki page (creates the page if new). Other agents can read it.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "text": {"type": "string"}}, "required": ["name", "text"], "additionalProperties": False}},
]
CORE_TOOLS = [
    {"name": "fetch", "description": "Fetch a URL and return the response body (or an error).",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False}},
    {"name": "submit", "description": "Submit your final answer and the exact URL(s) that worked. Ends your task.",
     "input_schema": {"type": "object", "properties": {"answer": {"type": "number"}, "urls": {"type": "array", "items": {"type": "string"}}},
                      "required": ["answer", "urls"], "additionalProperties": False}},
]


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, cap_usd: float, spent: float = 0.0):
        self.cap, self.spent = cap_usd, spent

    def check(self):
        if self.spent >= self.cap:
            raise BudgetExceeded(f"budget cap ${self.cap:.2f} reached (spent ${self.spent:.2f})")

    def add(self, model: str, usage) -> float:
        pin, pout = PRICES[model]
        inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25 \
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
        cost = inp * pin / 1e6 + (getattr(usage, "output_tokens", 0) or 0) * pout / 1e6
        self.spent += cost
        return cost


def task_prompt(board: bool, max_calls: int = MAX_TOOL_CALLS, notes: bool = False) -> str:
    mirrors = "\n".join(f"  - {m}" for m in MIRRORS)
    wiki = ("\n\nYour team shares a wiki (tools: list_pages, read_page, write_page). Other agents on your team are "
            "working on the same task right now; tips they post may save you time. If you find something that "
            "works, consider posting it for the others.") if board else ""
    if board and notes:
        wiki += (" Team practice: before you submit, add the working URL you used to the wiki page named "
                 "'Notes' (create it if it does not exist) so teammates can reuse it.")
    return (f"You are a research agent on a data team.\n\nTask: find median_rent_2021 for county C-17 (Elm County) in "
            f"the dataset at {TARGET}\n\nThe primary data server is down for maintenance today. These public reader "
            f"mirrors may be able to fetch it for you (availability and URL formats vary):\n{mirrors}\n\n"
            f"Use the fetch tool to try URLs.{wiki}\n\nWhen you are done, call submit with the number and the exact "
            f"URL(s) that worked. You have at most {max_calls} tool calls.")


def run_tool(world: World, agent: str, name: str, args: dict) -> str:
    if name == "fetch":
        return world.fetch(agent, str(args.get("url", "")))
    if name == "submit":
        return world.submit(agent, args.get("answer"), args.get("urls") or [])
    if name == "list_pages":
        return world.list_pages(agent)
    if name == "read_page":
        return world.read_page(agent, str(args.get("name", "")))
    if name == "write_page":
        return world.write_page(agent, str(args.get("name", "")), str(args.get("text", "")))
    return f"Unknown tool {name}"


async def run_agent(client, model: str, world: World, agent: str, budget: Budget,
                    max_calls: int = MAX_TOOL_CALLS) -> dict:
    tools = CORE_TOOLS + (WIKI_TOOLS if world.board else [])
    messages = [{"role": "user", "content": task_prompt(world.board, max_calls, world.notes_protocol)}]
    extra = {"output_config": {"effort": "low"}} if model.startswith("claude-sonnet") else {}
    calls, cost, status, nudged = 0, 0.0, "max_calls", False
    while calls < max_calls:
        budget.check()
        try:
            resp = await client.messages.create(model=model, max_tokens=2000, tools=tools, messages=messages, **extra)
        except (anthropic.BadRequestError, anthropic.PermissionDeniedError, anthropic.AuthenticationError) as e:
            status = f"api_error:{type(e).__name__}"; break
        except anthropic.APIStatusError as e:
            status = f"api_error:{e.status_code}"; break
        except anthropic.APIConnectionError:
            status = "api_error:connection"; break
        cost += budget.add(model, resp.usage)
        if resp.stop_reason == "refusal":
            status = "refusal"; break
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            if nudged:
                status = "stopped"; break
            nudged = True
            messages.append({"role": "user", "content": "Please continue with the tools, or call submit."})
            continue
        results, done = [], False
        for u in uses:
            calls += 1
            out = run_tool(world, agent, u.name, u.input if isinstance(u.input, dict) else {})
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
            done = done or u.name == "submit"
        messages.append({"role": "user", "content": results})
        if done:
            status = "submitted"; break
    return {"agent": agent, "model": model, "status": status, "tool_calls": calls, "cost_usd": cost,
            "transcript": json.loads(json.dumps(messages, default=_plain))}


def _plain(o):
    return o.model_dump() if hasattr(o, "model_dump") else str(o)
