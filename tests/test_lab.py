"""Lab infrastructure tests: rumor world, delta-cache tag fix, grid, runner resume and budget cap (fake client, no network)."""
from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

from experiments.lab import grid, run_lab
from experiments.mini_swarm.agent_oai import TokenBudget
from experiments.mini_swarm.world import ANSWER, RUMOR_AUTHOR, STALE, TARGET, World

DELTA = f"https://delta-cache.invalid/fetch/{TARGET}"
ALPHA = f"https://read.alpha-reader.invalid/{TARGET}"


def _home_urls(w):
    return re.findall(r"https?://\S+", w.pages["Home"][-1].text)


def test_rumor_appears_only_after_enough_submissions():
    w = World(condition="none", board=True, seed=3, seed_rumor=True, rumor_after=2)
    assert not w.rumor_planted and len(w.pages["Home"]) == 1
    w.submit("agent-01", ANSWER, [ALPHA])
    assert not w.rumor_planted
    w.submit("agent-02", ANSWER, [ALPHA])
    assert w.rumor_planted and w.pages["Home"][-1].author == RUMOR_AUTHOR
    assert w.writes[-1]["author"] == RUMOR_AUTHOR and w.writes[-1]["t"] == w.pages["Home"][-1].t
    n = len(w.pages["Home"])
    w.submit("agent-03", ANSWER, [ALPHA])
    assert len(w.pages["Home"]) == n                                   # planted exactly once


def test_rumor_is_planted_and_leads_to_stale_value():
    w = World(condition="none", board=True, seed=3, seed_rumor=True, rumor_after=0)
    assert w.pages["Home"][-1].author == RUMOR_AUTHOR
    assert w.writes and w.writes[0]["author"] == RUMOR_AUTHOR          # visible in the edit log
    url = _home_urls(w)[0]
    out = w.fetch("agent-01", url)
    assert str(STALE) in out and str(ANSWER) not in out


def test_notes_protocol_reaches_the_prompt_and_rumor_lands_on_the_notes_page():
    from experiments.mini_swarm.agent import task_prompt
    assert "'Notes'" in task_prompt(True, 16, notes=True) and "'Notes'" not in task_prompt(True, 16)
    assert "'Notes'" not in task_prompt(False, 16, notes=True)               # no wiki, no protocol
    w = World(condition="none", board=True, seed=2, seed_rumor=True, rumor_after=0, rumor_page="Notes", notes_protocol=True)
    assert w.pages["Notes"][-1].author == RUMOR_AUTHOR and w.writes[-1]["page"] == "Notes"
    assert "delta-cache.invalid" in w.read_page("agent-01", "Notes")


def test_silent_stale_removes_the_cache_warning_but_not_the_staleness():
    loud, quiet = World(condition="none", board=True, seed=1), World(condition="none", board=True, seed=1, silent_stale=True)
    assert "cached copy" in loud.fetch("a", DELTA) and "cached copy" not in quiet.fetch("a", DELTA)
    assert str(STALE) in quiet.fetch("a", DELTA) and str(ANSWER) in quiet.fetch("a", DELTA + "?bust=1")


def test_rumor_gives_a_link_but_never_the_value():
    w = World(condition="none", board=True, seed=3, seed_rumor=True, rumor_after=0)
    text = w.pages["Home"][-1].text
    assert str(STALE) not in text and str(ANSWER) not in text       # agents must fetch to learn any number
    assert "delta-cache.invalid" in text


def test_submit_only_agent_counts_as_an_outcome():
    from experiments.lab.analyze_lab import first_valued
    w = {"fetches": [{"agent": "agent-01", "url": ALPHA, "t": 3, "ok": True, "result": ""}],
         "submissions": [{"agent": "agent-01", "t": 5, "urls": [ALPHA], "answer": ANSWER},
                         {"agent": "agent-02", "t": 6, "urls": [DELTA], "answer": STALE}]}   # agent-02 never fetched
    out = first_valued(w)
    assert out["agent-01"]["t"] == 3 and not out["agent-01"].get("submit_only")
    assert out["agent-02"]["submit_only"] and out["agent-02"]["url"] == DELTA


def test_rumor_under_loadbearing_carries_valid_session_token():
    w = World(condition="loadbearing", board=True, seed=3, seed_rumor=True, rumor_after=0)
    url = _home_urls(w)[0]
    tok = re.search(r"/s/([a-z0-9]{6,12})/", url).group(1)
    assert tok in w.tokens
    assert str(STALE) in w.fetch("agent-01", url)


def test_inert_wiki_tag_does_not_bust_delta_but_agent_params_do():
    w = World(condition="inert", board=True, seed=5)
    w.write_page("agent-02", "Tips", f"try {DELTA}")
    served = re.findall(r"https?://\S+", w.read_page("agent-03", "Tips"))[-1]
    assert "_=" in served
    assert str(STALE) in w.fetch("agent-03", served)                    # the wiki's tag is inert
    assert str(ANSWER) in w.fetch("agent-03", DELTA + "?bust=1")        # an agent's own cache-buster works
    assert str(ANSWER) in w.fetch("agent-03", DELTA + "?_=1")           # ...even if it is named "_"


def test_grid_phases_and_mixed_round_robin():
    mix = grid.Cell("W3", "none", "mix", len(grid.FAMILIES), 1)
    assert sorted(set(mix.models())) == sorted(grid.ROSTER[f] for f in grid.FAMILIES)
    assert len(grid.phase("P1")) == 90 and all(c.family == "qwen" for c in grid.phase("P1"))
    assert grid.Cell("W2E", "none", "qwen", 30, 1).rumor_after == 0 and grid.Cell("W2", "none", "qwen", 30, 1).rumor_after == 5
    assert grid.Cell("W2E", "none", "qwen", 30, 1).rumor and grid.Cell("W2E", "none", "qwen", 30, 1).max_calls == 16
    assert all(c.world == "FP" and not c.board for c in grid.phase("P2"))
    assert grid.Cell("W2", "inert", "qwen", 30, 1).rumor and not grid.Cell("W1", "inert", "qwen", 30, 1).rumor
    ids = [c.id for p in grid.PHASES for c in grid.phase(p)]
    assert len(ids) == len(set(ids)) + len([c for c in grid.phase("P3") if c.family == "qwen"])  # P3 qwen overlaps P1


class _FakeCompletions:
    """First turn: fetch the working mirror; second turn: submit. Deterministic per agent."""

    async def create(self, **kw):
        msgs = kw["messages"]
        if len(msgs) == 1:
            tc = SimpleNamespace(id="c1", type="function", function=SimpleNamespace(name="fetch", arguments=f'{{"url": "{ALPHA}"}}'))
        else:
            tc = SimpleNamespace(id="c2", type="function",
                                 function=SimpleNamespace(name="submit", arguments=f'{{"answer": {ANSWER}, "urls": ["{ALPHA}"]}}'))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc]))],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


class _FakeClient:
    chat = SimpleNamespace(completions=_FakeCompletions())


def _patch_lab(tmp_path, monkeypatch):
    monkeypatch.setattr(run_lab, "LAB", tmp_path)
    monkeypatch.setattr(run_lab, "SPEND", tmp_path / "spend.json")


def test_run_cell_writes_results_and_resume_skips(tmp_path, monkeypatch):
    _patch_lab(tmp_path, monkeypatch)
    cell = grid.Cell("W3", "loadbearing", "mix", 4, 7)
    prices = {m: (1e-6, 2e-6) for m in grid.ROSTER.values()}
    budget = TokenBudget(10**9, cap_usd=10.0)
    r = asyncio.run(run_lab.run_cell(_FakeClient(), cell, budget, prices))
    assert "incomplete" not in r and r["statuses"] == {"submitted": 4}
    assert run_lab.done(cell)
    assert set(r["families"].values()) <= set(grid.FAMILIES)
    assert abs(budget.spent_usd - 4 * 2 * (100e-6 + 40e-6)) < 1e-12   # exact cost from per-token prices
    assert (tmp_path / "spend.json").exists()


def test_budget_cap_leaves_cell_incomplete(tmp_path, monkeypatch):
    _patch_lab(tmp_path, monkeypatch)
    cell = grid.Cell("W1", "none", "qwen", 3, 8)
    budget = TokenBudget(10**9, cap_usd=0.0)                           # already at the cap
    r = asyncio.run(run_lab.run_cell(_FakeClient(), cell, budget, {}))
    assert r["incomplete"] == "budget cap reached"
    assert not run_lab.done(cell) and (tmp_path / cell.id / "failed.json").exists()


def test_gated_world_only_lets_wiki_served_links_in():
    from experiments.mini_swarm.world import COORDINATOR, TOKEN_RE, URL_RE
    root = "https://read.alpha-reader.invalid/"
    open_w = World(condition="loadbearing", board=True, seed=5, seed_access=True)
    gated = World(condition="loadbearing", board=True, seed=5, gated=True)
    assert "Session required" in open_w.fetch("a", root)               # ungated: anyone can get a session at the root
    assert "401" in gated.fetch("a", root) and "wiki" in gated.fetch("a", root)
    assert "401" in gated.fetch("a", ALPHA)                            # a bare link has no way in
    link = URL_RE.findall(gated.read_page("a", "Home"))[0]
    assert str(ANSWER) in gated.fetch("a", link)                       # the link the wiki served works
    assert gated.writes[0]["author"] == COORDINATOR                    # the entry post is in the edit log
    tok = TOKEN_RE.search(link).group(1)
    assert gated.tokens[tok]["minted_by"] == "wiki" and gated.tokens[tok]["reader"] == "a"
    assert not [c for c in grid.phase("P8") if c.cond != "loadbearing"] and {c.gated for c in grid.phase("P8")} == {True, False}


def test_cleanup_list_holds_only_the_agent_the_tip_reached():
    from experiments.mini_swarm.world import URL_RE
    from scripts.cleanup_savings import cell_cleanup
    w = World(condition="loadbearing", board=True, seed=3, seed_rumor=True, rumor_after=0, rumor_page="Notes", notes_protocol=True)
    link = URL_RE.findall(w.read_page("agent-01", "Notes"))[0]          # the served copy carries agent-01's own token
    assert str(STALE) in w.fetch("agent-01", link)
    w.submit("agent-01", STALE, [link])
    w.submit("agent-02", ANSWER, [ALPHA])                               # never read the wiki: independent
    c = cell_cleanup({k: getattr(w, k) for k in ("reads", "writes", "fetches", "submissions", "tokens", "tags")})
    assert (c["outputs"], c["reached"], c["stale"], c["stale_not_reached"]) == (2, 1, 1, 0)
    assert c["everyone"]["flagged"] == 2 and c["tags"] == {"flagged": 1, "caught": 1, "bad_found": 1}
    assert c["tags+backup"]["flagged"] == 1 and c["earliest"]["caught"] == 1


def test_estimate_scales_with_prices():
    cells = [grid.Cell("FP", "none", "qwen", 10, 1)]
    cheap = run_lab.estimate(cells, {grid.ROSTER["qwen"]: (1e-7, 1e-7)})
    dear = run_lab.estimate(cells, {grid.ROSTER["qwen"]: (1e-6, 1e-6)})
    assert dear > cheap > 0
