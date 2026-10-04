"""Mini-swarm harness tests with a scripted fake client: no network, no spend."""
import asyncio
from types import SimpleNamespace as NS

from experiments.mini_swarm.agent import Budget, run_agent
from experiments.mini_swarm.world import ANSWER, STALE, TARGET, World

ALPHA = "https://read.alpha-reader.invalid/" + TARGET
BETA_OK = "https://beta-proxy.invalid/get?url=https%3A%2F%2Fdata.countyfacts.invalid%2Ffiles%2Fcounty_stats.json"


def test_mirrors_are_deterministic_and_offline():
    w = World(condition="none", board=False)
    assert str(ANSWER) in w.fetch("a", ALPHA)
    assert "percent-encoded" in w.fetch("a", "https://beta-proxy.invalid/get?url=" + TARGET)
    assert str(ANSWER) in w.fetch("a", BETA_OK)
    assert "503" in w.fetch("a", "https://gamma-mirror.invalid/raw?src=" + TARGET)
    assert str(STALE) in w.fetch("a", "https://delta-cache.invalid/fetch/" + TARGET)
    assert str(ANSWER) in w.fetch("a", "https://delta-cache.invalid/fetch/" + TARGET + "?cb=42")
    assert "offline" in w.fetch("a", TARGET)
    assert "resolve" in w.fetch("a", "https://example.com/x")
    assert len(w.fetches) == 8


def test_read_log_records_what_was_served_and_by_whom():
    w = World(condition="none")
    w.write_page("agent-01", "Links", "works: " + ALPHA)
    w.read_page("agent-02", "Links")
    rec = w.reads[-1]
    assert rec["reader"] == "agent-02" and rec["version"] == 1
    assert rec["urls"][0]["author"] == "agent-01" and rec["urls"][0]["served"] == ALPHA


def test_inert_tags_are_unique_per_served_copy_and_traceable():
    w = World(condition="inert", seed=1)
    w.write_page("agent-01", "Links", "use " + ALPHA + "?_=old")
    a = w.read_page("agent-02", "Links"); b = w.read_page("agent-03", "Links")
    ta, tb = w.reads[0]["urls"][0]["tag"], w.reads[1]["urls"][0]["tag"]
    assert ta != tb and ("_=" + ta) in a and ("_=" + tb) in b and "_=old" not in a
    assert w.tags[ta]["reader"] == "agent-02" and w.tags[ta]["author"] == "agent-01"
    assert str(ANSWER) in w.fetch("agent-02", w.reads[0]["urls"][0]["served"])   # tag is inert


def test_loadbearing_tokens_are_reminted_and_required():
    w = World(condition="loadbearing", seed=2)
    msg = w.fetch("agent-01", "https://read.alpha-reader.invalid/")
    tok = msg.split("/s/")[1].split("/")[0]
    mine = f"https://read.alpha-reader.invalid/s/{tok}/{TARGET}"
    assert str(ANSWER) in w.fetch("agent-01", mine)
    assert "401" in w.fetch("agent-01", ALPHA)                                   # no session: refused
    assert "401" in w.fetch("agent-01", f"https://read.alpha-reader.invalid/s/zzzzzzzz/{TARGET}")
    w.write_page("agent-01", "Links", "works: " + mine)
    served = w.read_page("agent-02", "Links")
    new = w.reads[-1]["urls"][0]["tag"]
    assert new != tok and f"/s/{new}/" in served and w.tokens[new]["reader"] == "agent-02"
    assert str(ANSWER) in w.fetch("agent-02", w.reads[-1]["urls"][0]["served"])


class FakeClient:
    """Plays a fixed script of tool calls, one per request."""
    def __init__(self, script):
        self.script, self.i = script, 0
        self.messages = self

    async def create(self, **kw):
        name, args = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        block = NS(type="tool_use", id=f"tu{self.i}", name=name, input=args, model_dump=lambda: {"type": "tool_use", "name": name, "input": args})
        return NS(content=[block], stop_reason="tool_use", usage=NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0))


def test_agent_loop_runs_tools_stops_on_submit_and_charges_budget():
    w = World(condition="none")
    script = [("read_page", {"name": "Home"}), ("fetch", {"url": ALPHA}), ("write_page", {"name": "Links", "text": "works: " + ALPHA}),
              ("submit", {"answer": ANSWER, "urls": [ALPHA]}), ("fetch", {"url": ALPHA})]
    b = Budget(1.0)
    r = asyncio.run(run_agent(FakeClient(script), "claude-haiku-4-5", w, "agent-01", b))
    assert r["status"] == "submitted" and r["tool_calls"] == 4
    assert w.submissions[0]["answer"] == ANSWER and len(w.writes) == 1 and len(w.reads) == 1
    assert abs(b.spent - 4 * (1000 * 1.0 + 100 * 5.0) / 1e6) < 1e-9


def test_budget_cap_stops_before_spending():
    import pytest
    from experiments.mini_swarm.agent import BudgetExceeded
    with pytest.raises(BudgetExceeded):
        asyncio.run(run_agent(FakeClient([("fetch", {"url": ALPHA})]), "claude-haiku-4-5", World(), "a", Budget(0.0)))


def test_analysis_recovers_truth_and_tag_survival_on_a_scripted_world():
    from dataclasses import asdict
    from experiments.mini_swarm.analyze import investigator, route, truth_copies
    w = World(condition="inert", seed=3)
    # agent-01 discovers alpha and posts it; agent-02 reads it and keeps the served tag; agent-03 finds beta alone
    w.fetch("agent-01", ALPHA); w.write_page("agent-01", "Links", "works: " + ALPHA)
    w.read_page("agent-02", "Links"); served = w.reads[-1]["urls"][0]["served"]
    w.fetch("agent-02", served); w.submit("agent-02", ANSWER, [served])
    w.fetch("agent-03", BETA_OK); w.submit("agent-03", ANSWER, [BETA_OK])
    state = asdict(w)
    tr = truth_copies(state)
    assert tr["agent-02"]["copied"] and tr["agent-02"]["parent"] == "agent-01"
    assert not tr["agent-01"]["copied"] and not tr["agent-03"]["copied"]
    inv = investigator(state, tr)
    assert inv["copiers"] == 1 and inv["tag_survival"] == 1.0 and inv["with_tags_accuracy"] == 1.0
    assert route(served) == "alpha" and route(BETA_OK) == "beta:encoded"
