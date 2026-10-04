# Before you submit to arXiv

Everything below is something only you can do, or that needs a decision. Run `python -m scripts.arxiv_placeholders` at any time: it lists every red placeholder still in the paper and exits with 0 when none are left.

## 1. Fill the placeholders (they show as red `[...]` in the PDF)
| Placeholder | What to put | Where |
|---|---|---|
| Author names, affiliations, emails | real ones | `main.tex` (title block) |
| Date | month and year | `main.tex` |
| `GITHUB-URL` | public repository URL | `main.tex` (Availability), `sections/F-checklist.tex`, abstract |
| `HUGGING-FACE-DATASET-URL` | dataset URL (see section 3) | `main.tex`, `sections/C-benchmark.tex`, `sections/F-checklist.tex` |
| `ZENODO-DOI` | DOI of an archived code+data release (optional but recommended) | `main.tex` |
| `CODE-LICENSE`, `DATA-LICENSE` | e.g. MIT / Apache-2.0 for code, CC BY 4.0 for data (your call) | `main.tex` |
| `URLs` | short form of the two links | `sections/abstract.tex`; also `abstract.txt` ends with `[URLs]` |
| `INCIDENT-DATA-CITATION-AND-PERMISSION` | how the incident logs are cited, and that you may publish aggregates | `sections/06-setup.tex` |
| `CONFIRMED-WITH-ORGANISERS / DATE` | the date the organisers said the aggregates may be public | `sections/09-limits.tex` |
| `PROVIDER`, `PROVIDER-AND-DATE-RANGE`, `TEMPERATURE-ETC` | inference provider name, the dates the lab ran, the sampling settings the harness used | `tables/tab_models` (generated: edit `scripts/arxiv_tables.py`), `sections/F-checklist.tex` |
| `DECIDE` | whether agent transcripts are included in the data release (recommended: not, to keep the release small and safe) | `sections/F-checklist.tex` |
| `DATE` (x3) | access dates of the three web references | `refs.bib` |
| Acknowledgments text | funding, conflicts of interest, thanks | `main.tex` |

## 2. Check these before anything else (blockers, not polish)
1. **Organisers' OK for the incident aggregates.** The incident export was marked "draft, do not share". The paper uses aggregates only (no handles, page text, URLs or tokens), but arXiv is public and permanent. Get a written yes first, then fill `CONFIRMED-WITH-ORGANISERS`.
2. **AI Village terms.** Cite the dataset (done in `refs.bib`), do not include any of its text (the paper does not), and **tell AI Digest about the publication** (their terms ask for it).
3. **Names.** The paper uses no project or team name on purpose. If you want a name for the benchmark or the gateway, add it in one place per component and search for "the benchmark", "the gateway", "the audit".
4. **No real-data strings.** Search the compiled PDF for anything that looks like a handle, a URL from the incident, or a token. The text uses counts only; the figures are aggregate.

## 3. Release the data (Hugging Face) and the code (GitHub)
- **Hugging Face dataset** (suggested contents): the benchmark (`bench_release/`: `manifest.json`, `edit_log/`, `truth/`, `registry/`, `ceiling/`, `baselines.json`, the scorer), the lab run records without agent transcripts, and the analysis outputs the paper reads (`frontend/data/results.json`, `data/lab/lab_results.json`, `data/lab/cleanup_savings.json`, `data/out/ai_village_full.json`). Add a dataset card: what each file is, the truth definition ("copied" = exposure), the licence, the AI Village and incident disclaimers, and the exact commit of the code. **Do not upload** raw AI Village or incident data, `.env`, or `data/raw`.
- **GitHub**: push the repository (nothing is committed yet), tag a release, and (optionally) archive it on Zenodo for a DOI. The paper's figures and tables rebuild with `python -m scripts.build_arxiv`.
- Put the final URLs into the placeholders above, then re-run `python -m scripts.arxiv_placeholders`.

## 4. Compile and check the PDF
1. `python -m scripts.build_arxiv` (regenerates `figures/`, `tables/`, `numbers.tex` from the result files).
2. `python -m scripts.pack_arxiv` compiles with the portable Tectonic in `tools/tectonic/` (not committed), writes `main.bbl`, test-compiles the upload bundle from a clean folder, and writes `arxiv/dist/trap-streets-arxiv.zip`.
3. State at the last run: **34 pages, no undefined references or citations, no `??`, no BibTeX warnings**; text stays inside the margins everywhere except one 4 pt URL in the bibliography. Remaining engine warnings are cosmetic (a 0.56 pt overfull line in Appendix C, one underfull table row).
4. Read the PDF end to end yourself: every number should match its table; no red text should remain once the placeholders are filled. I read the compiled text of all 34 pages for consistency between prose, tables and figure labels, but I did not check the figures' pixels one by one (the figure generator is self-sizing and was checked as images when it was written).
5. If you change anything under `scripts/arxiv_*.py`, re-run step 1 and look for `??` in the PDF: backslashes in the generator strings are easy to get wrong.

## 5. arXiv submission
- **Category**: primary `cs.MA` (Multiagent Systems); cross-list `cs.CR` and `cs.AI` (suggestion; your call).
- **Endorsement**: first-time submitters in a category may need an endorsement; request it early.
- **Files to upload**: `arxiv/dist/trap-streets-arxiv.zip`, written by `python -m scripts.pack_arxiv` **after you have filled the placeholders** (it holds `main.tex`, `numbers.tex`, `refs.bib`, the compiled `main.bbl` that arXiv builds from, `sections/`, `tables/`, `figures/*.pdf`; not `abstract.txt`, this file, or build junk). After uploading, check arXiv's own compiled PDF before you submit.
- **Metadata**: title `Trap Streets for Agent Swarms: Making Copying Confess When Reads Go Unlogged`; abstract: paste `abstract.txt` (1,504 characters; the arXiv limit is 1,920) and replace `[URLs]`; comments field e.g. "34 pages, 11 figures, 14 tables; code and data at <url>"; licence: your choice (CC BY 4.0 is common).
- After the paper is public, update the project page and the README with the arXiv ID.

## 6. What I could not verify (so you know)
- The paper compiles with **Tectonic (an XeTeX-based engine)**, not with `pdflatex`, which is what arXiv uses. The packages are all standard TeX Live ones, but look at arXiv's own PDF after you upload, before submitting.
- The **simulator tables** (Tables sim and robust, Figures calibration b and simulator) are transcribed from `docs/RESULTS.md` (sections A, E, H, I) because the sweep is slow to re-run: `python -m backend.bench.run --seeds 12` regenerates them; compare before submitting.
- Checked against the run records and corrected: the early-tip cascade depth (deepest chain 6-9 hops in 18 of 20 tagged core-model runs, 3 and 4 in the other two; untagged runs cannot be measured) and the length of the AI Village dip after rooms launched (about three weeks, 95%, 88%, 85%). The hypotheses are described as "stated in advance", not "pre-registered", everywhere in the repository, because they were written down in our plan and not registered anywhere.
- Related work was checked at the level of arXiv abstract pages and titles (12 references verified); I did not read the full papers. Read the five failure-attribution and provenance papers before submission and adjust the positioning paragraph if needed.
