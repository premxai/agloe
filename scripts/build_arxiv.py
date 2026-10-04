"""Rebuild everything the arXiv paper is made from, straight from the computed results: figures (vector PDF), tables and number macros.

  python -m scripts.build_arxiv                  # figures + tables + numbers.tex under arxiv/
  python -m scripts.build_arxiv --preview DIR    # also write PNG previews of the figures

The text (arxiv/main.tex) is hand-written and refers to numbers only through the macros in arxiv/numbers.tex.
Compile:  cd arxiv && tectonic main.tex     (or latexmk -pdf main.tex)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts import arxiv_figs, arxiv_tables


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="directory for PNG previews of the figures")
    a = ap.parse_args()
    nums = arxiv_tables.build()
    arxiv_figs.build(Path(a.preview) if a.preview else None)
    print(f"{len(nums)} number macros, tables and {len(arxiv_figs.ALL)} figures written to arxiv/")


if __name__ == "__main__":
    main()
