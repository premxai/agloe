# arXiv source

LaTeX source of the paper "Trap Streets for Agent Swarms: Making Copying Confess When Reads Go Unlogged" (34 pages, 11 figures, 14 tables, 4 algorithms, 6 propositions).

```
main.tex              preamble, title block, availability, bibliography, appendices
sections/             one file per section (01-intro ... 11-conclusion, A-proofs ... F-checklist)
numbers.tex           number macros   GENERATED from the result files
tables/               booktabs tables GENERATED from the result files
figures/              vector PDF figures GENERATED from the result files
refs.bib              references (every arXiv entry checked against its abstract page)
abstract.txt          plain-text abstract for the arXiv form (1,504 characters)
TODO_BEFORE_ARXIV.md  what you still have to fill in and decide
```

Rebuild the generated parts, compile, and make the upload zip (from the repository root):

```bash
python -m scripts.build_arxiv          # figures, tables, numbers.tex from the result files
python -m scripts.pack_arxiv           # compile, check the bundle builds on its own, write arxiv/dist/trap-streets-arxiv.zip
python -m scripts.arxiv_placeholders   # lists red placeholders still to fill (exit 0 when none)
```

`pack_arxiv` uses the portable Tectonic engine in `tools/tectonic/` (not committed; download it from https://github.com/tectonic-typesetting/tectonic/releases, unzip there) or any `tectonic` on PATH. To compile by hand: `cd arxiv && ../tools/tectonic/tectonic.exe --keep-intermediates main.tex` (or `latexmk -pdf main.tex`). arXiv builds from the `.bbl`, so it must be in the zip; `pack_arxiv` takes care of that.

The text refers to results only through the macros in `numbers.tex` and the generated tables, so a re-run of the lab or the analysis updates the paper everywhere. Do not edit the generated files by hand; edit `scripts/arxiv_data.py`, `scripts/arxiv_tables.py` or `scripts/arxiv_figs.py`. Backslashes in generator strings are easy to get wrong: after any change, compile and check that no `??` appears.
