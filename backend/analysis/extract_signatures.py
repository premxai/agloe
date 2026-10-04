"""Build data/out/sig_events.jsonl.gz: every URL added by a revision, with its method signature.

Run: python -m backend.analysis.extract_signatures
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

from backend.adapters.german_wiki import added_urls, load_revisions
from backend.analysis.signatures import parse_signature

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "german"
OUT = ROOT / "data" / "out" / "sig_events.jsonl.gz"


def main() -> None:
    revisions = load_revisions(RAW)
    rows = list(added_urls(revisions))
    # revisions that add many URLs at once are compendia/batches: their "hops" are not separate steps
    per_rev = Counter(r["rev_id"] for r in rows)
    kept, unparsed = 0, 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        for r in rows:
            sig = parse_signature(r["url"])
            if sig is None:
                unparsed += 1
                continue
            r["batch_size"] = per_rev[r["rev_id"]]
            r["sig"] = sig.to_dict()
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            kept += 1
    print(f"revisions={len(revisions)} added_url_rows={len(rows)} written={kept} unparsed={unparsed} -> {OUT}")


if __name__ == "__main__":
    main()
