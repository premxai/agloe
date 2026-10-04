"""Fill the paper's link placeholders once you have the URLs.

  python -m scripts.set_urls [--repo https://github.com/you/agloe] [--hf https://huggingface.co/datasets/you/name]

Replaces the GITHUB-URL, HUGGING-FACE-DATASET-URL and URLs placeholders in arxiv/ (main.tex, sections/, abstract.txt). Prints what it changed;
re-run `python -m scripts.pack_arxiv` afterwards to rebuild the arXiv zip.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_in(path: Path, pairs: list[tuple[str, str]]) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    n = 0
    for old, new in pairs:
        n += text.count(old)
        text = text.replace(old, new)
    if n:
        path.write_text(text, encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo"), ap.add_argument("--hf")
    a = ap.parse_args()
    if not (a.repo or a.hf):
        ap.error("give --repo and/or --hf")
    repo, hf = (u.rstrip("/") if u else u for u in (a.repo, a.hf))

    pairs: list[tuple[str, str]] = []
    if repo:
        pairs.append(("\\ph{GITHUB-URL}", f"\\url{{{repo}}}"))
    if hf:
        pairs.append(("\\ph{HUGGING-FACE-DATASET-URL}", f"\\url{{{hf}}}"))
    if repo and hf:                      # the abstract names code and data, so it waits for both
        pairs.append(("\\ph{URLs}", f"\\url{{{repo}}} and \\url{{{hf}}}"))
    arx, total = ROOT / "arxiv", 0
    for p in [arx / "main.tex", *sorted((arx / "sections").glob("*.tex"))]:
        n = replace_in(p, pairs)
        total += n
        if n:
            print(f"{p.relative_to(ROOT)}: {n} replaced")
    if repo and hf:
        n = replace_in(arx / "abstract.txt", [("[URLs]", f"{repo} and {hf}")])
        total += n
        if n:
            print(f"arxiv/abstract.txt: {n} replaced")
    print(f"{total} placeholder(s) filled")


if __name__ == "__main__":
    main()
