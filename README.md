# Agloe: trap streets for AI agent swarms

**When one agent's mistake spreads through a swarm, can you trace it?** Usually not, from the logs people keep.
Agloe is a toolkit and a benchmark for answering that honestly: audit how traceable your swarm is, tell real copying from coincidence, and plant canary tags so the next incident is traceable.
Built for the AI Swarm Dynamics Hackathon by **Paper Towns**. *Read the past honestly, make the future traceable.*

- **Live site / demo:** `<deployed url>` · **Paper:** [`frontend/paper/agloe.pdf`](frontend/paper/agloe.pdf) · **Results:** [`docs/RESULTS.md`](docs/RESULTS.md)
- Named after Agloe, New York: a fake town mapmakers invented so that anyone copying their map would give themselves away.

## What we found (short)

| | |
|---|---|
| **The wall** | Even a perfect investigator could trace at most **16%** of the real incident's copying from its edit logs; 56% of adopters had no visible carrier. How much is traceable depends on what is logged: about 20% of marker sources were visible in the incident, versus 97% in AI Village's room-scoped chat and 100% before rooms (measured over every week of the whole chat; the lowest week was 85%). |
| **The coincidence trap** | "Same string = copied" made **1,001** copy calls; **385** survive calibration. It flagged **23** cross-team collusion jumps; **3** survive hand verification (20 were dataset field names and timestamps that many agents type independently). |
| **Models have habits** | Independent agents of different models add throwaway "random" values at very different rates, and several choose the same one, so a shared value alone is weak evidence. |
| **Trap streets** | Serving each page view with its own load-bearing token turns a copied link into a pointer to the exact copy. Whether the token survives depends on the model: it rides along for agents that copy links verbatim and is bypassed by agents that redo the work. Tags lift attribution over the best simple edit-log rule in proportion to survival. |
| **Only way in** | Closing the door models use to skip the token (the mirror hands out sessions only through wiki-served links) raised the share of outputs carrying a traceable token from 25-50% to 100% for DeepSeek, GLM, MiniMax and Kimi, and every agent still finished. In the lab this follows from the access design, so it shows feasibility and cost, not a discovery; a gate traces access, not ideas. |
| **What to re-check** | When a bad tip has spread, tracing it cuts the re-check list from about 83% of outputs (everything submitted after the tip appeared) to about 8-9%, and finds 88-92% of the outputs the tip reached. A simple earliest-writer rule gets most of that; the codes make the list exact (no false alarms). A tip that is there from the start reaches about 80% of outputs, so nothing saves much: catch it early. |
| **A bad tip** | Whether a planted bad tip takes hold depends on the model. An early tip was adopted by every agent of the core model (Qwen3-235B) through cascades 6-9 hops deep, where the best edit-log rule named only a minority of the immediate sources, but by only part or none of the agents of most other model families; a late tip was mostly ignored. |

Details, tables with confidence intervals, and everything that did not work are in the [paper](frontend/paper/agloe.html) and `docs/RESULTS.md` (sections A-P). Honest limits are in the paper's section 6.

## Use it

**Report card** (graded answer to "can I trace this?"): drop a log file on the page `frontend/card/` (runs entirely in your browser, nothing uploaded), or

```bash
python -m backend.cli report --file my_swarm_logs.jsonl
```

Input: one JSON object per line (or one JSON array) with `agent`, `time`, `channel`, `content` (aliases such as `author`, `timestamp`, `room`, `text` are accepted). In the browser a CSV also works, and if your field names differ the page asks you to pick them (or to use row order when there are no timestamps). The card reports carrier coverage, the best possible top-1 accuracy, naive vs calibrated copy calls, "everyone types this" strings, and what to log next. "Copy card as JSON" leaves out any text taken from your logs unless you tick a box, so a team can share a card safely; `python -m scripts.collect_cards shared_cards/` turns a folder of shared cards into a table (swarms anonymised by default). The browser port is parity-tested against the Python reference.

**Canary kit** (`backend/canary.py`, [`docs/CANARY.md`](docs/CANARY.md)): stamp each served copy with a token, gate the destination on it, resolve any later artifact to the copy it came from.

**Agloe-Bench** (`bench_release/`): lab swarms with an edit-log input, a hidden answer key and a scorer.

```bash
python bench_release/score.py --baselines
python bench_release/score.py --pred my_predictions.jsonl
```

**Colony** (`frontend/colony/`, live, nothing uploaded): drop any swarm's log (JSONL, JSON, CSV, `.gz`) and watch it as an ant colony. Every agent is an ant, chambers are the rooms or pages it works in, trails form as agents pick things up from each other, and a click traces an ant back to what it read and forward to everyone downstream (the re-check list). With a read log (`kind: "read"`) the trails are exact; without one they are inferred from shared strings, as a real investigator would have to. Samples are our lab runs with their hidden read logs; AI Village and the real incident are not redistributed, so export them locally and drop the file:

```bash
python -m scripts.export_log --dataset ai_village --lo 2026-03-23 --hi 2026-03-30
```

The page states the criteria each run was set up under, and the project page has a "How we tested" section (worlds, tag conditions, models, seeds, scores, exclusions, the hypotheses we stated in advance and what happened to each).

**Face-Off** (`frontend/replay/faceoff.html`): a one-minute, self-playing story built for a screen or projector. A bad tip spreads through 30 agents while two investigators try to trace it from the same records (the edit log alone against trap-street codes), then a second run shows what each would have to re-check after a late tip (25 outputs against 4). Every number is computed in the page from the recorded lab runs; "Make a clip" records the whole story as a video.

**Swarm replay** (`frontend/replay/`): one real lab swarm, three views: hidden truth, what the edit log would conclude, what tags reveal. Run a fresh swarm live (offline sandbox, a few cents): `python -m scripts.live_demo`.

**Local site:** `python -m http.server 5188 --directory frontend`, then open `http://localhost:5188/`.
**Deploy** (static, no build): `cd frontend && npx vercel --prod` (the config and ignore file are in `frontend/`).

## Reproduce

```bash
pip install -r requirements.txt
python -m pytest tests -q                      # unit tests (no network, no data needed)
node frontend/card/parity.test.mjs             # JS report card matches the Python reference
python -m experiments.lab.run_lab --phase smoke --dry-run      # lab grid and projected cost
python -m experiments.lab.run_lab --phase P1                   # needs NEBIUS_API_KEY in .env
python -m experiments.lab.analyze_lab          # H1-H4, forward trace, fingerprints -> data/lab/lab_results.json
python -m scripts.write_results_lab            # regenerates the lab sections of docs/RESULTS.md
python -m scripts.build_site_data && python -m scripts.build_paper --pdf
```

Keys live in `.env` only (never committed; see `.env.example`). The real-data analyses (`backend.cli audit|neutral|markers`, `scripts/run_ai_village.py`, `scripts/verify_readmap.py`) need datasets you obtain yourself (see below) and are not run by the tests.

## Data and ethics

- **Lab:** every run is offline (reserved `.invalid` domains), benign, and against our own simulated world. Nothing was tested against, probed or injected into anyone's live system, and the report card runs locally and never sees anyone's logs.
- **collusion.wiki incident export:** marked "draft, do not share". It is **not** included, and this repo publishes aggregates only (no handles, no page text, no URLs). The row-level evidence is reproducible locally by someone with access.
- **AI Village dataset** ([aidigestorg/ai-village](https://huggingface.co/datasets/aidigestorg/ai-village), gated, research use only): not included; we used it for propagation statistics only, with hashed token ids. Cite as AI Digest, "AI Village dataset", 2026.
- Open-model runs use the Nebius Token Factory; Claude Haiku 4.5 and Sonnet 5.5 were used for earlier single-seed arms (`docs/RESULTS.md` M, N).

## Layout

```
backend/analysis/report.py   the report card (CLI + parity reference)      backend/canary.py   canary-tag kit
backend/sim, backend/bench   simulator with ground truth, ceilings, tracers  backend/adapters   collusion.wiki / AI Village adapters
experiments/lab              lab grid, resumable runner, analysis              experiments/mini_swarm   offline worlds and agents
frontend/{card,replay,paper} browser report card, swarm replay, paper         bench_release        Agloe-Bench scorer and format
scripts/                     exports, site and paper builders, live demo       docs/                RESULTS, CANARY, LAUNCH drafts
```

## License

Code: MIT. Data and third-party content keep their owners' terms (see above).
