"""Canary tags for shared agent artifacts: make copying traceable by serving every copy with its own load-bearing token.

Three calls:

    canary = Canary(secret="keep-this-private", gateway="https://gw.example.org")
    served = canary.stamp(page_text, reader="agent-7", source="Notes@v3", author="agent-2")   # when a page is served
    canary.resolve_text(later_artifact)       # when an artifact reappears: which served copy did each link come from?

How it works. `stamp` rewrites every URL in the text to `https://gw.example.org/c/<token>/<original url>` with a fresh
token per call (so per reader and per version). The gateway you run in front of the destination calls `unwrap(url)`
and refuses any URL without a valid token, so the token is load-bearing: an agent that drops it gets nothing, and an
agent that keeps it (copying the link verbatim) names the copy it read. `resolve` maps a token back to who was served
which version of what.

Why load-bearing and not a random-looking suffix: whether a decoration survives copying depends on the copier. In our
live tests inert tags survived 0% for one model and about 100% for another, and the real incident's agents kept
random-looking extras only 2.5% of the time, while tokens the link needs survived every time (docs/CANARY.md).

Prior art this builds on: canary traps / traitor tracing (per-recipient variants of a secret), canary tokens and
honeytokens (security), and copyright traps. The new part is applying it to agent swarms with a hostile-to-removal
design (load-bearing) and measuring it with live agents.

The token carries no information; the registry (kept by the operator) does. Never publish the registry or the secret.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
TOKEN_RE = re.compile(r"/c/([0-9a-f]{16})/")


class Canary:
    def __init__(self, secret: str, gateway: str = "https://gateway.invalid", registry: dict | None = None):
        if not secret:
            raise ValueError("secret must be non-empty")
        self._key = secret.encode("utf-8")
        self.gateway = gateway.rstrip("/")
        self.registry: dict[str, dict] = registry if registry is not None else {}

    # ------------------------------------------------------------------ minting
    def _mac(self, nonce: str, reader: str, source: str) -> str:
        return hmac.new(self._key, f"{nonce}|{reader}|{source}".encode("utf-8"), hashlib.sha256).hexdigest()[:8]

    def mint(self, *, reader: str, source: str, author: str | None = None, meta: dict | None = None) -> str:
        """A fresh token for one served copy; registers who it was served to and what it was a copy of."""
        nonce = os.urandom(4).hex()
        token = nonce + self._mac(nonce, reader, source)
        self.registry[token] = {"reader": reader, "source": source, "author": author, "t": time.time(), "meta": meta or {}}
        return token

    def stamp(self, text: str, *, reader: str, source: str, author: str | None = None) -> str:
        """Rewrite every URL in `text` so it carries its own token through the gateway (one token per URL)."""
        def wrap(m: re.Match) -> str:
            url = m.group(0)
            if url.startswith(self.gateway + "/c/"):                    # already stamped: leave the original token alone
                return url
            return f"{self.gateway}/c/{self.mint(reader=reader, source=source, author=author)}/{url}"
        return URL_RE.sub(wrap, text)

    # ------------------------------------------------------------------ the gateway side (load-bearing check)
    def valid(self, token: str) -> bool:
        rec = self.registry.get(token)
        return bool(rec) and hmac.compare_digest(token[8:], self._mac(token[:8], rec["reader"], rec["source"]))

    def unwrap(self, url: str) -> tuple[str, str] | None:
        """(token, original URL) if `url` carries a valid token, else None: the gateway should refuse it."""
        if not url.startswith(self.gateway + "/c/"):
            return None
        m = TOKEN_RE.match(url[len(self.gateway):])
        if not m or not self.valid(m.group(1)):
            return None
        return m.group(1), url[len(self.gateway) + len("/c/") + 16 + 1:]

    # ------------------------------------------------------------------ the investigator side
    def resolve(self, token: str) -> dict | None:
        """The served copy a (valid) token names: reader, source, author, time."""
        return self.registry.get(token) if self.valid(token) else None

    def resolve_text(self, text: str) -> list[dict]:
        """Every valid token found in an artifact, resolved. Order follows the text."""
        out = []
        for m in TOKEN_RE.finditer(text):
            rec = self.resolve(m.group(1))
            if rec:
                out.append({"token": m.group(1), **rec})
        return out

    # ------------------------------------------------------------------ persistence (operator-side only)
    def dump(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.registry), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, secret: str, gateway: str = "https://gateway.invalid") -> "Canary":
        return cls(secret, gateway, json.loads(Path(path).read_text(encoding="utf-8")))
