"""Method signatures: turn a URL into "how it reaches its target".

A signature is deterministic and explainable (no model involved). It records the
proxy/wrapper layers (outer -> inner), how many times each inner URL is
percent-encoded, which extra parameters each wrapper carries, and any tricks
applied to the final target (trailing dot, port, obfuscated host, ...).

Three granularities, from coarse to fine:
  family_key   which services are chained          "allorigins.hexlet.app > r.jina.ai"
  method_key   + endpoint style and encoding depth "allorigins.hexlet.app/raw?url=@1 > r.jina.ai/@0"
  variant_key  + wrapper params + target tricks
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

URL_RE = re.compile(r"""https?://[^\s\]\)"'<>|]+""", re.I)
# "http" + separator that may be percent-encoded 0..3 times: ://  %3A%2F%2F  %253A%252F%252F ...
INNER_RE = re.compile(
    r"(?i)(?:(?<![a-z0-9])|(?<=%[0-9a-f]{2}))https?(?P<sep>(?:%(?:25)*3a|:)(?:%(?:25)*2f|/){1,2})"
)
FILE_EXTS = {
    "json", "txt", "pdf", "html", "htm", "xml", "csv", "js", "css", "png", "jpg", "jpeg", "gif",
    "zip", "php", "md", "xlsx", "xls", "svg", "ico", "map", "gz", "tsv", "yaml", "yml",
}
HOST_IN_PATH_RE = re.compile(
    r"(?i)^/+(?:(?:https?)/+)?(?P<h>(?:[a-z0-9-]+\.)+[a-z]{2,10}\.?)(?=[/?:#]|$)"
)
PROXY_TOKEN_RE = re.compile(r"(?i)/(?:https?)/(?P<h>(?:[a-z0-9-]+\.)+[a-z]{2,10}\.?)(?=[/?:#]|$)")
MAX_LAYERS = 8


@dataclass(frozen=True)
class Layer:
    service: str          # host of the wrapper, e.g. "r.jina.ai"
    style: str            # normalized endpoint, e.g. "/raw?url=" or "/" (path-embedded)
    depth: int            # percent-encoding depth of the inner URL
    params: tuple[str, ...] = ()  # extra parameter names carried by the wrapper

    @property
    def method(self) -> str:
        return f"{self.service}{self.style}@{self.depth}"


@dataclass(frozen=True)
class Signature:
    layers: tuple[Layer, ...]
    target_host: str
    target_file: str
    target_kind: str                  # "official" | "lookalike" | "other"
    flags: tuple[str, ...] = field(default=())
    target_url: str = ""              # what is ultimately fetched: host + decoded path

    @property
    def family_key(self) -> str:
        return " > ".join(l.service for l in self.layers) or "direct"

    @property
    def method_key(self) -> str:
        return " > ".join(l.method for l in self.layers) or "direct"

    @property
    def variant_key(self) -> str:
        params = ",".join(sorted({p for l in self.layers for p in l.params}))
        return f"{self.method_key} | params={params} | flags={','.join(self.flags)}"

    @property
    def sig_id(self) -> str:
        return hashlib.sha1(self.variant_key.encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        return {
            "sig_id": self.sig_id,
            "family_key": self.family_key,
            "method_key": self.method_key,
            "variant_key": self.variant_key,
            "layers": [
                {"service": l.service, "style": l.style, "depth": l.depth, "params": list(l.params)}
                for l in self.layers
            ],
            "target_host": self.target_host,
            "target_file": self.target_file,
            "target_kind": self.target_kind,
            "target_url": self.target_url,
            "flags": list(self.flags),
        }


def _encoding_depth(sep: str) -> int:
    """'://' -> 0, '%3a%2f%2f' -> 1, '%253a%252f%252f' -> 2 (first escape decides)."""
    i = sep.find("%")
    if i < 0:
        return 0
    return len(re.match(r"%((?:25)*)", sep[i:]).group(1)) // 2 + 1


def _norm_prefix(prefix: str) -> tuple[str, tuple[str, ...]]:
    """'/raw?disableCache=true&url=' -> ('/raw?url=', ('disablecache',))"""
    path, _, query = prefix.partition("?")
    path = re.sub(r"\d{4,}", "#", path)  # agent-chosen ids / timestamps, not versions like v0
    path = re.sub(r"[A-Za-z0-9+_=-]{24,}", "<blob>", path)  # opaque payloads embedded in the path
    if not query:
        return (path + "?" if "?" in prefix else path), ()
    parts = [p for p in query.split("&") if p]
    last = parts[-1].split("=")[0].lower() if parts else ""
    extra = tuple(sorted(p.split("=")[0].lower() for p in parts[:-1]))
    return f"{path}?{last}=", extra


def _decode_host(host: str) -> str:
    return unquote_n(host, 4).lower()


def _translate_goog_host(host: str) -> str:
    stem = host[: -len(".translate.goog")]
    return stem.replace("--", "\0").replace("-", ".").replace("\0", "-")


def _split_url(url: str) -> tuple[str, str, str]:
    m = re.match(r"(?i)https?://([^/?#]*)(.*)", url)
    if not m:
        return "", "", ""
    return m.group(1), m.group(2), url


def _trim_outer_params(remainder: str) -> tuple[str, tuple[str, ...]]:
    """Cut the raw remainder at the first '&': what follows belongs to the wrapper."""
    head, amp, tail = remainder.partition("&")
    if not amp:
        return head, ()
    names = tuple(sorted(p.split("=")[0].lower() for p in tail.split("&") if p))
    return head, names


def _target_kind(host: str) -> str:
    h = host.rstrip(".")
    if h.endswith("sec.gov") or h.endswith("investor.gov"):
        return "official"
    if "sec.gov" in h or "sec-gov" in h or "investor-gov" in h:
        return "lookalike"
    return "other"


def parse_signature(url: str) -> Signature | None:
    layers: list[Layer] = []
    flags: set[str] = set()
    cur = url.strip()
    # tidy trailing punctuation that wiki markup glues to URLs
    cur = re.sub(r"[.,;:!?]+$", "", cur) if not cur.endswith("sec.gov.") else cur

    for _ in range(MAX_LAYERS):
        raw_host, rest, _full = _split_url(cur)
        if not raw_host:
            return None
        host = _decode_host(raw_host)
        if host != raw_host.lower():
            flags.add("pct_host")
        host_np = host.split(":")[0]

        if host_np.endswith(".translate.goog"):
            layers.append(Layer("translate.goog", "host-rewrite", 0))
            cur = f"https://{_translate_goog_host(host_np)}{rest}"
            continue

        m = INNER_RE.search(rest)
        if m:
            sep = m.group("sep").lower()
            depth = _encoding_depth(sep)
            style, extra = _norm_prefix(rest[: m.start()])
            remainder, outer = _trim_outer_params(rest[m.end():])
            inner = "http" + ("s" if rest[m.start() + 4] in "sS" else "") + "://" + remainder
            layers.append(Layer(host_np, style, depth, tuple(sorted(set(extra) | set(outer)))))
            cur = unquote_n(inner, depth)
            continue

        m = HOST_IN_PATH_RE.match(rest) or PROXY_TOKEN_RE.search(rest)
        if m and _looks_like_host(m.group("h")) and m.group("h").lower().rstrip(".") != host_np:
            style, extra = _norm_prefix(rest[: m.start("h")].rstrip("/") + "/")
            remainder, outer = _trim_outer_params(rest[m.end("h"):])
            layers.append(Layer(host_np, style or "/", 0, tuple(sorted(set(extra) | set(outer)))))
            cur = f"https://{m.group('h')}{remainder}"
            continue

        break  # terminal URL reached

    raw_host, rest, _ = _split_url(cur)
    host = _decode_host(raw_host)
    if host.endswith("."):
        flags.add("trailing_dot")
    if re.search(r":\d+$", host):
        flags.add("port")
    if raw_host != raw_host.lower() and "%" not in raw_host:
        flags.add("host_case")
    host_clean = re.sub(r":\d+$", "", host).rstrip(".")

    path = rest.split("#")[0]
    pure_path, _, query = path.partition("?")
    if "#" in rest or re.search(r"(?i)%23", pure_path):
        flags.add("fragment")
    if re.search(r"(?i)%[0-9a-f]{2}", pure_path):
        flags.add("pct_path")
    if "//" in pure_path.replace("://", ""):
        flags.add("double_slash")
    if re.search(r"/\.{1,2}(/|$)", unquote(pure_path)):
        flags.add("dot_segment")
    if query or re.search(r"(?i)%3f", pure_path):
        flags.add("query")
    decoded_path = unquote_n(pure_path, 3).split("?")[0]
    file = decoded_path.rstrip("/").rsplit("/", 1)[-1].lower() or "/"

    base = re.sub(r"^www\.", "", host_clean)
    return Signature(
        layers=tuple(layers),
        target_host=base,
        target_file=file,
        target_kind=_target_kind(host_clean),
        flags=tuple(sorted(flags)),
        target_url=(base + (decoded_path.lower().rstrip("/") if decoded_path != "/" else "")),
    )


def _looks_like_host(candidate: str) -> bool:
    return candidate.lower().rstrip(".").rsplit(".", 1)[-1] not in FILE_EXTS


def unquote_n(s: str, n: int) -> str:
    for _ in range(n):
        s = unquote(s)
    return s


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")
