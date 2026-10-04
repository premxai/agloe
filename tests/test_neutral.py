"""Copy-or-coincidence analysis: expected values worked out by hand on tiny synthetic logs."""
from backend.analysis.neutral import BaseRates, Write, arbitrary_params, high_entropy, structure, summarize


def w(agent, i, url, page="P"):
    return Write(agent, f"2026-06-18T10:{i:02d}:00Z", (f"2026-06-18T10:{i:02d}:00Z", f"r{i}"), page, url)


def test_only_inert_parameters_count():
    u = "https://proxy.example.invalid/api?url=https%3A%2F%2Fdata.example.invalid%2Ffiles%2Fcounty.json&jq=.&x=1&_=99"
    assert sorted(arbitrary_params(u)) == [("_", "99"), ("x", "1")]
    assert arbitrary_params("https://wiki.example/cgi?action=browse&lang=1") == []


def test_structure_blanks_only_inert_values():
    a = structure("https://m.example/?url=https://a.gov/f.json&x=1")
    b = structure("https://m.example/?url=https://a.gov/f.json&x=777")
    c = structure("https://m.example/?url=https://a.gov/g.json&x=1")
    assert a == b and a != c


def test_focal_values_get_high_base_rate():
    # ten unrelated structures whose first writers all chose x=1, one chose a random token
    writes = [w(f"a{i}", i, f"https://m.example/?url=https://a.gov/f{i}.json&x=1") for i in range(10)]
    writes.append(w("z", 20, "https://m.example/?url=https://a.gov/g.json&x=Qk7v2pLm9"))
    r = BaseRates().fit(writes)
    assert r.p("x", "1") > 0.7
    assert r.p("x", "Qk7v2pLm9") < 0.15
    assert r.collision("x") > 0.8


def test_planted_value_is_recovered_as_a_copy_and_focal_is_not():
    writes = [w(f"a{i}", i, f"https://m.example/?url=https://a.gov/f{i}.json&x=1") for i in range(10)]
    writes.append(w("src", 30, "https://m.example/?url=https://a.gov/h.json&x=Qk7v2pLm9"))
    writes.append(w("cop", 31, "https://m.example/?url=https://a.gov/h.json&x=Qk7v2pLm9", page="Q"))
    writes.append(w("src2", 32, "https://m.example/?url=https://a.gov/f1.json&x=1"))
    s = summarize(writes, lr_threshold=5)
    ev = {e["copier"].agent: e for e in s["_events"]}
    assert ev["cop"]["kept"] and 1 / ev["cop"]["p_value"] > 5      # rare value: counts as evidence
    assert ev["src2"]["kept"] and 1 / ev["src2"]["p_value"] < 5     # focal value: does not


def test_survival_counts_kept_versus_regenerated():
    writes = [w("a", 1, "https://m.example/?url=https://a.gov/f.json&_=1712345678"),
              w("b", 2, "https://m.example/?url=https://a.gov/f.json&_=1712345678"),
              w("c", 3, "https://m.example/?url=https://a.gov/f.json&_=1799999999")]
    s = summarize(writes)
    assert s["reuse_events"] == 2
    assert abs(s["survival"]["raw"] - 0.5) < 1e-9


def test_high_entropy_rule():
    assert high_entropy("JuneCitation1781188737") and high_entropy("1781188737.7044826")
    assert not high_entropy("1") and not high_entropy("777") and not high_entropy("abc")

