"""Canary kit tests (pure, no network)."""
from __future__ import annotations

from backend.canary import Canary

GW = "https://gw.example.invalid"
PAGE = "Working link: https://mirror.example.invalid/data/county.json and also https://other.example.invalid/x"


def _c():
    return Canary("test-secret", GW)


def test_each_served_copy_gets_unique_tokens_that_resolve_to_that_copy():
    c = _c()
    a = c.stamp(PAGE, reader="agent-1", source="Notes@v1", author="agent-0")
    b = c.stamp(PAGE, reader="agent-2", source="Notes@v1", author="agent-0")
    ta, tb = c.resolve_text(a), c.resolve_text(b)
    assert len(ta) == len(tb) == 2                                  # one token per URL
    assert {r["token"] for r in ta}.isdisjoint({r["token"] for r in tb})
    assert {r["reader"] for r in ta} == {"agent-1"} and {r["reader"] for r in tb} == {"agent-2"}
    assert all(r["source"] == "Notes@v1" and r["author"] == "agent-0" for r in ta + tb)


def test_a_copied_link_names_the_copy_that_was_read():
    c = _c()
    served = c.stamp(PAGE, reader="agent-9", source="Notes@v4", author="agent-3")
    copied = "see " + served.split("Working link: ")[1].split(" and")[0]       # agent pastes the first link elsewhere
    [rec] = c.resolve_text(copied)
    assert rec["reader"] == "agent-9" and rec["source"] == "Notes@v4"


def test_gateway_refuses_stripped_forged_or_foreign_tokens():
    c = _c()
    served = c.stamp("https://mirror.example.invalid/data.json", reader="r", source="s")
    token, original = c.unwrap(served)
    assert original == "https://mirror.example.invalid/data.json"
    assert c.unwrap(original) is None                                # token dropped: not served
    assert c.unwrap(f"{GW}/c/{'0' * 16}/{original}") is None          # forged
    other = Canary("another-secret", GW, registry=dict(c.registry))
    assert other.unwrap(served) is None                              # registry copied, secret unknown


def test_restamping_keeps_the_original_token_and_persistence_roundtrips(tmp_path):
    c = _c()
    once = c.stamp(PAGE, reader="agent-1", source="Notes@v1")
    twice = c.stamp(once, reader="agent-2", source="Notes@v2")
    assert once == twice
    p = tmp_path / "reg.json"
    c.dump(p)
    d = Canary.load(p, "test-secret", GW)
    assert d.resolve_text(once) == c.resolve_text(once)


def test_rejects_empty_secret_and_ignores_unregistered_text():
    try:
        Canary("")
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert _c().resolve_text("no tags here https://x.invalid/") == []
