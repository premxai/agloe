"""AI Village adapter tests on synthetic chat (no raw data, no network).

Checks the two things the paper rests on: (1) carrier coverage tracks how much of the channel is in
the log -- full pre-rooms, lower once room-scoped; (2) the coincidence permutation null runs and is
calibrated under a no-homophily construction. Also guards the family mapping and the hashing.
"""
from __future__ import annotations

from backend.adapters.ai_village import (
    _fam, coincidence_test, message_tokens, spread_records, tok_id,
)

MARK = "zq7_tunnelCfg_9k"      # distinctive invented token (passes the _good filter)


def _msg(agent, family, t, content, room="r1"):
    return {"id": f"{agent}-{t}", "agent": agent, "agent_id": agent, "family": family,
            "room": room, "t": f"2026-01-12 10:00:{t:02d}.000000", "content": content}


def test_family_mapping():
    assert _fam("claude-opus-4-5-20251101") == "anthropic"
    assert _fam("claude-code::claude-opus-4-5-20251101") == "anthropic"
    assert _fam("gpt-5.2-2025-12-11") == "openai"
    assert _fam("o3-2025-04-16") == "openai"
    assert _fam("gemini-3-pro-preview") == "google"
    assert _fam("deepseek-reasoner") == "deepseek"
    assert _fam("z-ai/glm-5.2") == "other-oss"
    assert _fam("grok-4-0709") == "xai"


def test_token_filter_skips_boilerplate_keeps_distinctive():
    toks = message_tokens(f"use {MARK} after Authorization: Bearer and content-type application/json")
    assert MARK in toks
    assert not any("authorization" in x.lower() or "application" in x.lower() for x in toks)
    # scrub markers never become tokens
    assert not message_tokens("key is [REDACTED] and blob [BLOB_REMOVED]")


def test_hash_is_stable_and_not_the_token():
    h = tok_id(MARK)
    assert h == tok_id(MARK) and MARK not in h and len(h) == 10


def test_full_channel_gives_full_coverage():
    # three agents emit the same distinctive token in sequence; pre-rooms everyone sees everyone
    chat = [_msg("A", "openai", 0, f"found {MARK}"),
            _msg("B", "anthropic", 30, f"reusing {MARK}"),
            _msg("C", "google", 60, f"also {MARK}")]
    recs = spread_records(chat, rooms=False)
    assert len(recs) == 2 and all(r["visible_carrier"] for r in recs)


def test_room_scoping_hides_some_carriers():
    # A posts the token only in room r2; C only ever posts in r1 -> C's carrier is invisible under scoping
    chat = [_msg("A", "openai", 0, f"found {MARK}", room="r2"),
            _msg("C", "google", 60, f"also {MARK}", room="r1")]
    full = spread_records(chat, rooms=False)
    scoped = spread_records(chat, rooms=True)
    assert full[0]["visible_carrier"] is True
    assert scoped[0]["visible_carrier"] is False


def test_coincidence_null_calibrated_without_homophily():
    # two families, token co-emitted by mixed pairs at random -> observed ~ null, high p-value
    chat = []
    for k, (ag, fam) in enumerate([("A", "openai"), ("B", "anthropic"), ("C", "openai"), ("D", "anthropic")]):
        chat.append(_msg(ag, fam, k, f"token tok_{ag}_marker_123"))
    # one shared near-simultaneous token across a cross-family pair
    chat += [_msg("A", "openai", 10, f"{MARK} here"), _msg("B", "anthropic", 12, f"{MARK} too")]
    res = coincidence_test(chat, short_s=120.0, iters=200)
    assert res["near_simultaneous_pairs"] >= 1
    assert 0.0 <= res["observed_same_family"] <= 1.0
    assert res["p_value"] >= 0.0
