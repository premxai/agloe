"""DSEWiki (collusion.wiki export) -> Lineage events.

Each wiki revision is one write by one labelled agent. What a revision *introduced*
is computed against the previous stored revision of the same page, so every added
item has a precise (page, revision, agent, time) provenance.
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from backend.analysis.signatures import extract_urls

SOURCE = "dsewiki"
# Wiki-generated index pages: they aggregate other pages' text, so they are never an original author.
GENERATED_PAGES = {"RecentChanges", "AllPages", "AllChanges"}


def load_jsonl_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def is_generated(page_id: str) -> bool:
    return page_id.rsplit("/", 1)[-1] in GENERATED_PAGES


def load_revisions(raw_dir: Path) -> list[dict]:
    revs = load_jsonl_gz(Path(raw_dir) / "revisions.jsonl.gz")
    # per-page order is the wiki's own revision sequence; global order is time then rev_id
    revs.sort(key=lambda r: (r["time"], r["rev_id"]))
    return revs


def added_urls(revisions: list[dict]) -> Iterator[dict]:
    """Yield one record per (revision, url) where the url is new relative to the page's previous revision.

    `base_missing` marks revisions whose predecessor is not in the export, so "new" may be
    an artifact. `prev_label` is the agent who wrote the previous revision of that page
    (the page's state the author was editing from), which is the direct-exposure evidence.
    """
    by_page = defaultdict(list)
    for r in revisions:
        by_page[r["page_id"]].append(r)
    for page_id, revs in by_page.items():
        revs.sort(key=lambda r: int(r["seq"]))
        prev = None
        for r in revs:
            cur = set(extract_urls(r["body"]))
            before = set(extract_urls(prev["body"])) if prev else set()
            base_missing = prev is None and r.get("diff_base_reason") != "page_created"
            for url in sorted(cur - before):
                yield {
                    "rev_id": r["rev_id"],
                    "page_id": page_id,
                    "label": r["label"] or None,
                    "time": r["time"],
                    "time_grade": r["time_grade"],
                    "url": url,
                    "prev_rev_id": prev["rev_id"] if prev else None,
                    "prev_label": (prev["label"] or None) if prev else None,
                    "base_missing": base_missing,
                    "generated_page": is_generated(page_id),
                    "batch_size": 0,  # filled in by the caller once all rows exist
                }
            prev = r


def adoptions(raw_dir: Path, sig_events: Path, official_only: bool = False):
    """Adoption rows (one per added URL) for the audit: behavior key = method_key, location = page.

    Wrapped (proxy-routed) URLs always count; bare URLs only when `official_only` target hosts are asked for,
    mirroring the lineage's node definition. Generated index pages are skipped."""
    from backend.analysis.audit import Adoption

    seq = {r["rev_id"]: int(r["seq"]) for r in load_revisions(raw_dir)}
    out = []
    with gzip.open(sig_events, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sg = r["sig"]
            if r["generated_page"] or not (sg["layers"] or (official_only and sg["target_kind"] == "official")):
                continue
            out.append(Adoption(agent=r["label"] or "", t=r["time"], loc=r["page_id"], order=seq[r["rev_id"]], key=sg["method_key"]))
    return out
