# Hugging Face dataset release

`python -m scripts.make_hf_release` builds `hf_release/` (not committed, 72 MB, 1,341 files):

| Folder | Contents |
|---|---|
| `bench/` | the benchmark: edit logs (input), hidden truth, registries, ceilings, baselines, scorer |
| `lab_runs/` | 231 lab runs (`run.json`, `world.json`), **no agent transcripts** |
| `lab_runs_discarded_designs/` | 72 runs of two of the three flawed bad-tip designs (the paper says they are kept) |
| `analysis/` | the result files the paper is generated from; `ai_village_full_aggregates.json` is weekly counts only |
| `README.md` | dataset card (draft: has TODO lines) |
| `MANIFEST.sha256` | checksums |

Never included: raw AI Village data, the real incident logs, transcripts, live-demo runs, keys.

## Before you upload
1. Open `hf_release/README.md` and fill the TODO lines: **licence** (CC BY 4.0 is a common choice), **provider and date range and sampling settings** (the same facts as in the paper's checklist), the code URL, and later the arXiv ID. Or edit `scripts/make_hf_release.py` (the `card()` function) and rebuild, so the changes survive.
2. Decide about transcripts. The default is to leave them out (smaller, nothing to review). They are in `data/lab/*/transcripts.jsonl.gz` if you want to add them.

## Upload
Create an access token at huggingface.co/settings/tokens (write access), then:

```bash
pip install -U huggingface_hub
hf auth login                                   # older versions: huggingface-cli login
hf upload <your-username>/<dataset-name> hf_release . --repo-type dataset
```

Then put the dataset URL into the paper and the README: `python -m scripts.set_urls --hf https://huggingface.co/datasets/<your-username>/<dataset-name>` (add `--repo` and `--site` too if not done yet), re-run `python -m scripts.pack_arxiv`, and commit.
