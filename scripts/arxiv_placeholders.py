"""List every placeholder (\\ph{...}) still in the arXiv paper sources. Reaches zero when the paper is ready to submit.

Usage: python -m scripts.arxiv_placeholders
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "arxiv"
PH = re.compile(r"\\ph\{((?:[^{}]|\{[^{}]*\})*)\}")


def main() -> int:
    found: list[tuple[str, int, str]] = []
    for p in sorted([ROOT / "main.tex", ROOT / "refs.bib", *sorted((ROOT / "sections").glob("*.tex")), *sorted((ROOT / "tables").glob("*.tex"))]):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "\\newcommand{\\ph}" in line or line.lstrip().startswith("%"):
                continue
            for m in PH.finditer(line):
                found.append((p.relative_to(ROOT).as_posix(), i, m.group(1)))
    for f, i, t in found:
        print(f"{f}:{i}: {t}")
    print(f"\n{len(found)} placeholder(s) left; distinct: {len(Counter(t for _, _, t in found))}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
