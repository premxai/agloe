# Canary tags for agent swarms

Plant a **version-unique, load-bearing token** in every copy of a shared artifact your swarm reads, so that when something
reappears later you can say which served copy it came from.

## Three calls

```python
from backend.canary import Canary

canary = Canary(secret="keep-this-private", gateway="https://gw.example.org")

# 1. when a page / memory / note is served to an agent: every URL gets its own token
served = canary.stamp(page_text, reader="agent-7", source="Notes@v3", author="agent-2")

# 2. your gateway (the thing in front of the destination) refuses URLs without a valid token
token, original_url = canary.unwrap(requested_url) or (None, None)     # None => refuse

# 3. when an artifact reappears (a submission, a later post, a report): which copy was it?
canary.resolve_text(later_artifact)    # -> [{"token": ..., "reader": "agent-7", "source": "Notes@v3", "author": "agent-2"}]
```

The registry (`canary.registry`, persisted with `dump()`/`load()`) is operator-side. Keep it and the secret private.

## Why load-bearing

Each served link is rewritten to `https://gw.example.org/c/<token>/<original url>`. An agent that copies the link verbatim carries the token and names the
copy it read; an agent that drops the token gets nothing from the gateway. Merely decorating a link with a random-looking suffix does not do this: whether
a harmless-looking tag survives copying depends on the copier. In our runs, inert tags survived in a very different share of copies depending on the model
family, while a token the link needs was kept whenever the agent reused the link. See `docs/RESULTS.md` (section P) for the per-family numbers.

## What it does not do

- It traces **which served copy** an artifact came from, not what an agent read and ignored. An agent can always obtain a fresh credential from the
  destination instead of reusing the one it was served; then there is nothing to trace, and the audit reports it as a tag that did not survive.
- It records the *exposure* path, not the agent's reasons. "Copied from X" means X's copy was served and its token was used.
- It adds an operator-run gateway. If you cannot put one in front of the destination, tag what you can (the report card's recommendations say what to log).
- It changes what agents see. Run it only on swarms you operate, and tell the people who review the logs that tags exist.

## Prior art

Per-recipient variants of a secret to identify a leaker (canary traps, traitor tracing); canary tokens and honeytokens in security; fictitious entries in
maps and dictionaries ("trap streets", "mountweazels"; the Agloe, NY of the project's name); copyright traps in text. What is new here is applying
the idea to agent swarms, making the tag load-bearing so removal breaks the link, and measuring survival with live agents of different model families.
