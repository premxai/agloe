# Agloe-Bench

A benchmark for **tracing information through agent swarms**, with a hidden answer key.

In real swarms nobody knows who copied from whom: reads are rarely logged. In our offline lab the harness records every read, so for each agent we know the
teammate whose served link it actually used. A tracer sees only what an investigator would have (the edit log) and is scored against that key.

## What is in the box

| path | what it is |
|---|---|
| `edit_log/<cell>.jsonl` | **Input.** Time-ordered wiki writes and submissions (`kind`, `t`, `agent`, text/urls, `routes`). |
| `truth/<cell>.jsonl` | **Hidden key.** Per agent: `copied` (bool), `parent` (who), `answered_stale` (the planted bad tip took). Do not give this to a tracer. |
| `registry/<cell>.json` | **Tag track only.** Operator-side map from tag/token to the served copy it names. A method that does not use tags must not read it. |
| `ceiling/<cell>.json` | The best accuracy any tracer can reach from the edit log alone if copiers pick uniformly among identical posters (`uniform_ceiling`). |
| `manifest.json` | Cells: world, condition (`none`/`inert`/`loadbearing`), model family, size, seed. |
| `score.py` | Standard-library scorer with five baselines. |

Worlds: **W1** shared wiki; **W2** a bad tip appears mid-run and the stale mirror gives no warning; **W2E** the bad tip is there from the start;
**W3** the same with agents of eight model families mixed.

## Score a tracer

```
python score.py --baselines                       # latest / earliest / uniform / conservative / tags
python score.py --pred my_predictions.jsonl       # your tracer
python score.py --pred my_predictions.jsonl --world W2 --cond loadbearing
```

Predictions are JSON Lines, one per agent: `{"cell": "...", "agent": "agent-07", "source": "agent-03" | "independent", "confidence": 0.8}`.
A missing prediction counts as `independent`.

Metrics (95% confidence interval from a bootstrap over cells, because agents inside one swarm read each other):
`top1` (copied agents whose source is named correctly), `recall`, `false_accusation` (agents that worked alone but were blamed), `vs_uniform_ceiling`
(top1 divided by E[1/m]; **not** a hard upper bound, since a tracer that exploits copier habits or reads tags can exceed 1),
contamination precision/recall for the planted-bad-tip worlds, and `ece` if you give confidences.

## Read this before you cite a number

- **"Copied" means exposure:** the agent was served that link before using it. This is the standard definition in contagion studies.
- **Attribution is only well defined where the served copy is unique** (`inert` and `loadbearing` cells). In `none` cells several posts carry byte-identical
  links, so the true source is not defined by text; the key picks the earliest such post, so baselines like `earliest` look perfect there by construction.
  Compare tracers on tagged cells, or use `--cond none` only for copy-vs-independent and false accusations.
- **Single-origin bad tips are easy to root-cause without tags** (the earliest writer of that link is the origin). Tags matter for the exact chain and for
  swarms whose posts share one link.
- Cells come from open models on one provider; one narrow task; offline (`.invalid` hosts); benign.
- Agent labels are lab labels (`agent-NN`). No third-party logs are included.
