"""Expected values are worked out by hand from real URLs seen in the DSEWiki data."""
import pytest

from backend.analysis.signatures import extract_urls, parse_signature

S = "%2F"


def methods(url):
    return [l.method for l in parse_signature(url).layers]


def test_direct():
    s = parse_signature("https://www.sec.gov/files/county.json")
    assert s.layers == ()
    assert (s.target_host, s.target_file, s.target_kind) == ("sec.gov", "county.json", "official")
    assert s.flags == ()
    assert s.method_key == "direct"


def test_query_style_wrapper_single_encoded():
    u = "https://allorigins.hexlet.app/get?url=https%3A%2F%2Fwww.sec.gov%2Ffiles%2Fcounty.json"
    assert methods(u) == ["allorigins.hexlet.app/get?url=@1"]


def test_path_embedded_wrapper():
    assert methods("https://md.succ.ai/www.sec.gov/files/county.json") == ["md.succ.ai/@0"]
    assert methods("https://r.jina.ai/http://www.sec.gov/files/county.json") == ["r.jina.ai/@0"]


def test_double_encoding_then_nested_wrapper():
    u = (
        "https://md.succ.ai/https%253A%252F%252Fallorigins.hexlet.app%252Fraw%253Furl%253D"
        "https%25253A%25252F%25252Fwww.sec.gov%25252Ffiles%25252Fcounty.json"
    )
    assert methods(u) == ["md.succ.ai/@2", "allorigins.hexlet.app/raw?url=@1"]


def test_nested_wrappers_other_file():
    u = (
        "https://markdown.new/x?url=https%3A%2F%2Fallorigins.hexlet.app%2Fraw%3Furl%3D"
        "https%253A%252F%252Fwww.sec.gov%252Ffiles%252Fregcf.json"
    )
    s = parse_signature(u)
    assert [l.method for l in s.layers] == ["markdown.new/x?url=@1", "allorigins.hexlet.app/raw?url=@1"]
    assert s.target_file == "regcf.json"


def test_translate_goog_host_rewrite():
    s = parse_signature("https://www-sec-gov.translate.goog/files/county.json?_x_tr_sl=auto&_x_tr_tl=en")
    assert [l.service for l in s.layers] == ["translate.goog"]
    assert s.target_host == "sec.gov" and s.target_file == "county.json"
    assert "query" in s.flags


def test_target_tricks():
    assert "trailing_dot" in parse_signature("https://www.sec.gov./files/county.json").flags
    assert "port" in parse_signature("https://www.sec.gov:443/files/county.json").flags
    assert "host_case" in parse_signature("https://proxy.corsfix.com/https://www.SEC.gov/files/county.json").flags


def test_obfuscated_wrapper_host():
    u = "https://%61llorigins.hexlet.app/raw?url=https%3A%2F%2Fwww.sec.gov%2Ffiles%2Fcounty.json"
    s = parse_signature(u)
    assert s.layers[0].service == "allorigins.hexlet.app"
    assert "pct_host" in s.flags


def test_encoded_filename_decodes_and_flags():
    s = parse_signature("https://proxy.corsfix.com/?https://www.sec.gov/files/count%79.json")
    assert s.layers[0].method == "proxy.corsfix.com/?@0"
    assert s.target_file == "county.json" and "pct_path" in s.flags


def test_proxy_token_path():
    s = parse_signature("https://www.proxymule.com/__PROXY__/https/www.sec.gov/files/county.json")
    assert [l.service for l in s.layers] == ["www.proxymule.com"]
    assert s.target_host == "sec.gov"


def test_wrapper_params_recorded_not_in_target():
    u = "https://jqp.vercel.app/api/v0?url=https%3A%2F%2Fwww.sec.gov%2Ffiles%2Fcounty.json&jq=%5B.x"
    s = parse_signature(u)
    assert s.layers[0].method == "jqp.vercel.app/api/v0?url=@1"
    assert s.layers[0].params == ("jq",)
    assert s.target_file == "county.json"


def test_archive_timestamp_normalized():
    u = "https://web.archive.org/web/20240101id_/https://www.sec.gov/files/county.json"
    assert methods(u) == ["web.archive.org/web/#id_/@0"]


def test_lookalike_host():
    s = parse_signature("https://sec.govwayback.com/files/county.json")
    assert s.layers == () and s.target_kind == "lookalike"


def test_variant_distinct_from_method():
    a = parse_signature("https://md.succ.ai/www.sec.gov/files/county.json")
    b = parse_signature("https://md.succ.ai/www.sec.gov./files/county.json")
    assert a.method_key == b.method_key and a.variant_key != b.variant_key


def test_extract_urls_stops_at_markup():
    t = "see [https://r.jina.ai/https://sec.gov/x.json|JINREG] and (https://a.com/b)"
    assert extract_urls(t) == ["https://r.jina.ai/https://sec.gov/x.json", "https://a.com/b"]


def test_filename_is_not_a_host():
    s = parse_signature("https://corsmirror.com/v1?url=https%3A%2F%2Fwww.sec.gov%2Frobots.txt")
    assert [l.service for l in s.layers] == ["corsmirror.com"]
    assert s.target_file == "robots.txt"


def test_single_slash_scheme():
    assert methods("https://md.succ.ai/https:/www.sec.gov/files/county.json") == ["md.succ.ai/@0"]


def test_inner_url_after_encoded_equals():
    u = "https://allorigins.hexlet.app/get?callback=x%26url%3Dhttps%253A%252F%252Fwww.sec.gov%252Ffiles%252Fcounty.json"
    s = parse_signature(u)
    assert s.layers[0].service == "allorigins.hexlet.app" and s.target_host == "sec.gov"


def test_inner_url_after_encoded_question_mark():
    u = "https://cors.hypnguyen.workers.dev/%3Fhttps%3A%2F%2Fwww.sec.gov%2Ffiles%2Fcounty.json"
    s = parse_signature(u)
    assert s.layers[0].service == "cors.hypnguyen.workers.dev" and s.target_host == "sec.gov"


def test_double_encoded_filename_with_encoded_query():
    s = parse_signature("https://www.investor.gov/files/county.json%253Fx%253D.pdf")
    assert s.target_file == "county.json"


def test_multiply_encoded_dot_in_target_host():
    u = "https://jqp.vercel.app/api/v0?url=https%3A%2F%2Fwww%25252Esec%25252Egov%2Ffiles%2Fcounty.json"
    s = parse_signature(u)
    assert s.target_host == "sec.gov" and "pct_host" in s.flags


def test_target_url_is_the_resource_whatever_the_route():
    a = parse_signature("https://md.succ.ai/https%3A%2F%2Fwww.sec.gov%2Ffiles%2Fcounty.json")
    b = parse_signature("https://allorigins.hexlet.app/raw?url=https%3A%2F%2Fsec.gov%2Ffiles%2Fcounty.json%3Fx%3D1")
    assert a.target_url == b.target_url == "sec.gov/files/county.json"


def test_embedded_payload_is_not_part_of_the_method():
    blob = "eyJzb3VyY2UiOiJodHRwczovL3d3dy5zZWMuZ292L2ZpbGVzL2NvdW50eS5qc29uIn0="
    s = parse_signature(f"https://httpbin.org/base64/{blob}?source=https://www.sec.gov/files/county.json")
    assert s.layers[0].method == "httpbin.org/base64/<blob>?source=@0"
