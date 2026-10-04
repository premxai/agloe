"""Fill the link placeholders once you have the real URLs.

  python -m scripts.set_urls --site https://agloe.vercel.app --repo https://github.com/you/agloe [--video URL] [--hf URL]

Replaces <deployed url>, <site url>, <link> (site), <github url> (repo), <video url> and <hf dataset url> in README.md and docs/*.md, and,
when --repo / --hf are given, the paper's GITHUB-URL, HUGGING-FACE-DATASET-URL and URLs placeholders in arxiv/. It prints what it changed;
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
    ap.add_argument("--site"), ap.add_argument("--repo"), ap.add_argument("--video"), ap.add_argument("--hf")
    a = ap.parse_args()
    if not any((a.site, a.repo, a.video, a.hf)):
        ap.error("give at least one of --site --repo --video --hf")
    clean = lambda u: u.rstrip("/") if u else u
    site, repo, video, hf = clean(a.site), clean(a.repo), clean(a.video), clean(a.hf)

    doc_pairs: list[tuple[str, str]] = []
    if site:
        doc_pairs += [("<deployed url>", site), ("<site url>", site), ("<link>", site)]
    if repo:
        doc_pairs += [("<github url>", repo)]
    if video:
        doc_pairs += [("<video url>", video)]
    if hf:
        doc_pairs += [("<hf dataset url>", hf)]
    total = 0
    for p in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
        n = replace_in(p, doc_pairs)
        total += n
        if n:
            print(f"{p.relative_to(ROOT)}: {n} replaced")

    tex_pairs: list[tuple[str, str]] = []
    if repo:
        tex_pairs.append(("\\ph{GITHUB-URL}", f"\\url{{{repo}}}"))
    if hf:
        tex_pairs.append(("\\ph{HUGGING-FACE-DATASET-URL}", f"\\url{{{hf}}}"))
    if repo and hf:
        tex_pairs.append(("\\ph{URLs}", f"\\url{{{repo}}} and \\url{{{hf}}}"))
    elif repo:
        tex_pairs.append(("\\ph{URLs}", f"\\url{{{repo}}}"))
    arx = ROOT / "arxiv"
    for p in [arx / "main.tex", *sorted((arx / "sections").glob("*.tex"))]:
        n = replace_in(p, tex_pairs)
        total += n
        if n:
            print(f"{p.relative_to(ROOT)}: {n} replaced")
    if repo:
        n = replace_in(arx / "abstract.txt", [("[URLs]", repo + (f" and {hf}" if hf else ""))])
        total += n
        if n:
            print(f"arxiv/abstract.txt: {n} replaced")
    print(f"{total} placeholder(s) filled")


if __name__ == "__main__":
    main()
