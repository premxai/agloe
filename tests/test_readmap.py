"""Unit tests for the read-map verifier's token classifier (pure functions, no raw data)."""
from __future__ import annotations

from scripts.verify_readmap import classify, shannon


def test_uuid_is_high_strength():
    cls, strength = classify("9c1f4b72-6a0e-4d58-b3a1-7e25d0c4f918")
    assert cls == "uuid" and strength == "high"


def test_wayback_constructed_vs_capture():
    assert classify("20250201000000id_") == ("wayback-constructed", "low")   # round HHMMSS -> choosable
    assert classify("20130525012744id_") == ("wayback-capture", "medium")    # real capture time


def test_schema_vocabulary_is_low_strength():
    assert classify("ipeds_tuition")[1] == "low"
    assert classify("acs_ygpsar_poverty_by_gender")[0] == "snake-field"
    assert classify("numberFormat")[0] == "camel-ident"


def test_minted_slug_is_high_entropy():
    cls, strength = classify("zq7Lk2vT9xRw4mPa")
    assert strength == "high" and cls == "high-entropy"


def test_shannon_orders_random_above_repetitive():
    assert shannon("aaaaaaaaaaaa") < shannon("9c1f4b726a0e")


