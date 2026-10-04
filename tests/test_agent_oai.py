"""agent_oai (OpenAI-compatible runner) tests with a fake client -- no network, no key."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from experiments.mini_swarm.agent_oai import TokenBudget, _oai_tools, run_agent_oai
from experiments.mini_swarm.world import TARGET, World

ALPHA = f"https://read.alpha-reader.invalid/{TARGET}"


def _usage(a=100, b=20):
    return SimpleNamespace(prompt_tokens=a, completion_tokens=b)


def _toolcall(cid, name, args):
    return SimpleNamespace(id=cid, type="function", function=SimpleNamespace(name=name, arguments=args))


def _resp(content, tool_calls):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
                           usage=_usage())


class FakeCompletions:
    def __init__(self, scripted):
        self._scripted = scripted
        self.calls = 0

    async def create(self, **kw):
        r = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        return r


class FakeClient:
    def __init__(self, scripted):
        self.chat = SimpleNamespace(completions=FakeCompletions(scripted))


def test_oai_tools_shape():
    core = _oai_tools(board=False)
    names = {t["function"]["name"] for t in core}
    assert names == {"fetch", "submit"}
    assert _oai_tools(board=True)[-1]["function"]["name"] == "write_page"


def test_run_agent_oai_fetch_then_submit():
    scripted = [
        _resp("trying the mirror", [_toolcall("c1", "fetch", f'{{"url": "{ALPHA}"}}')]),
        _resp("done", [_toolcall("c2", "submit", '{"answer": 1342, "urls": ["' + ALPHA + '"]}')]),
    ]
    world = World(condition="none", board=False, seed=1)
    budget = TokenBudget(1_000_000)
    out = asyncio.run(run_agent_oai(FakeClient(scripted), "fake/model", world, "agent-01", budget, max_calls=8))
    assert out["status"] == "submitted"
    assert out["tool_calls"] == 2
    assert out["tokens_in"] > 0 and out["tokens_out"] > 0
    assert world.submissions and world.submissions[0]["answer"] == 1342


def test_run_agent_oai_nudge_then_stop_when_no_tool_calls():
    scripted = [_resp("I am thinking out loud with no tool call", None)]
    world = World(condition="none", board=False, seed=1)
    out = asyncio.run(run_agent_oai(FakeClient(scripted), "fake/model", world, "agent-02", TokenBudget(10_000), max_calls=8))
    assert out["status"] == "stopped"          # one nudge, then stop
    assert out["tool_calls"] == 0


def test_token_budget_raises_when_capped():
    b = TokenBudget(cap_tokens=5, used=5)
    try:
        b.check()
        raised = False
    except RuntimeError:
        raised = True
    assert raised
