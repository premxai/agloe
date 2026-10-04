# Results (source of truth for the paper). Regenerate: `python -m backend.bench.run --seeds 12`, `python -m backend.cli audit`

## A. Benchmark (simulator with known ground truth; 12 seeds/cell, ~3,400 adoptions/cell)
Top-1 = share of adoptions whose true source is named. Ceiling = exact Bayes-optimal accuracy given the same logs.

| copy model | ceiling | earliest | latest | most_similar | heuristic tracer | model-based tracer (em) |
|---|---|---|---|---|---|---|
| uniform | 0.460 | 0.162 | 0.152 | 0.356 | 0.372 | **0.458** |
| recency-biased | 0.799 | 0.098 | 0.382 | 0.533 | 0.538 | **0.796** |
| popularity-biased | 0.538 | 0.260 | 0.117 | 0.250 | 0.260 | **0.511** |

- Proposition 1 (verified): best achievable accuracy = E[max_i posterior_i]; oracle measured == formula within 0.001-0.009 in all 9 (copy x off-page) cells.
- The old "1/m" figure is the ceiling only for a tracer that ignores what the agent wrote, or when all carriers carry the identical behavior (the real-data case).
- Proposition 2 (verified): if the source item of a fraction rho of copies is logged, ceiling(rho) = rho + (1-rho)*C0 (e.g. C0=0.46: rho=0.5 -> 0.727, measured 0.727).
- Page-level read logs help far less: even rho=1 only lifts the ceiling 0.46 -> 0.57. Recommendation: log the item read, not just the page.
- Off-page sources (reads the edit log cannot show) lower the ceiling (0.460 -> 0.344 at 75% off-page) but the model-based tracer stays within 0.013 of it.
- Calibration of the model-based tracer: ECE 0.019. Says 90-100% -> right 98%; says 50-60% -> right 52%.
- Evidence tiers of the heuristic tracer: A names the exact source 42.7% of the time but the right METHOD 82.3%; B 17.9% / 64.6%; tiers are ordinal evidence strength, not probabilities. Use the model-based tracer when a probability is needed.
- The model-based tracer learns the copy model from logs only (fitted off-page share 0.28 vs true 0.25; mutation 0.37 vs 0.35).
- Caveat: simulator and tracer share a model family. Misspecified copy mechanisms are not yet tested.

## B. Audit of the real board (DSEWiki; `python -m backend.cli audit`)
- Headline behavior (a proxy-relay method, name withheld): 162 named adopters; 83 (51%) with no visible carrier; best possible top-1 19.6%, top-3 30.1%; 40.2% among the 79 with a visible carrier. With item reads for 50% of copies: 59.8%.
- Pooled over 35 behaviors with >=20 adopters (2,976 adopters): 56% no visible carrier; best possible top-1 16.2%; top-3 25.4%; median behavior 17.2%.
- Ceilings use same-page evidence and no-preference copying (conservative; recency or popularity preferences raise them, see A).

## C. Contagion (Hawkes branching ratio, controlled for swarm-wide activity; `backend/analysis/hawkes.py`)
Validated on simulated data: recovers true alpha=0.6 inside its 95% interval; an activity wave alone fools the uncontrolled fit (alpha>0.3) but not the controlled one (alpha<0.25).

| behavior | n | alpha uncontrolled | alpha controlled (95% CI) |
|---|---|---|---|
| headline proxy-relay method | 162 | 0.96 | 0.68 (0.50-0.90) |
| single-proxy method | 324 | 0.98 | 0.96 (0.90-1.05) |
| markdown.new | 244 | 0.94 | 0.82 (0.70-0.95) |
| allorigins raw | 219 | 0.93 | 0.87 (0.75-1.00) |
| r.jina.ai | 177 | 0.96 | 0.89 (0.75-1.00) |
Reading: adoption is largely self-triggered, not outside-driven. Common outside triggers (shared prompt, scheduled start) cannot be excluded.

## D. Other measured facts / negative results
- Dose-response (probe): adoption 3.8% with 0 copies on the page, 17.6% with 2-3 copies (small n).
- Heaps-style exponent 0.85 (668 agents, 337 methods): the toolkit stays open.
- Disguised-host attempts fell from ~9% of wrapped links (16-17h) to 0.1% (20-21h): exploration then convergence.
- NOT supported: evasion in response to clearing (admin deletions are mostly after the cascade; disguises peaked before). Hub concentration is modest (top page 22% of first adoptions).
- 39 of 162 first adopters had earlier edited a page holding the method.

## E. Robustness: rules the tracer was not built for, and the real-board off-page share (12 seeds/cell)
Oracle (true rule) == ceiling in every cell, so the ceilings are valid. "Model-based" never sees the hidden truth.

| copy rule | off-page share | Bayes ceiling | heuristic tracer | model-based tracer | model-based / ceiling | learned off-page share |
|---|---|---|---|---|---|---|
| uniform | 0.25 | 0.460 | 0.372 | 0.458 | 1.00 | 0.28 |
| uniform | 0.85 | 0.324 | 0.117 | 0.326 | 1.01 | 0.84 |
| recency | 0.25 | 0.799 | 0.538 | 0.796 | 1.00 | 0.28 |
| recency | 0.85 | 0.726 | 0.126 | 0.720 | 0.99 | 0.86 |
| homophily (outside the model family) | 0.25 | 0.499 | 0.386 | 0.459 | 0.92 | 0.29 |
| homophily | 0.85 | 0.341 | 0.127 | 0.300 | 0.88 | 0.83 |
| hard window (outside the model family) | 0.25 | 0.667 | 0.488 | 0.643 | 0.96 | 0.29 |
| hard window | 0.85 | 0.544 | 0.133 | 0.501 | 0.92 | 0.87 |
- When most sources are off-page the simple heuristic collapses (0.12-0.13); the model-based tracer learns the off-page share and holds 88-101% of the ceiling.
- Still one simulator family of mechanisms. A rule based on hidden agent state (latent quality) was not tested; its ceiling needs the latent variable marginalised.

## F. Real-data markers (`python -m backend.cli markers`; `backend/analysis/markers.py`)
Rare strings invented by agents (wrapper side of a URL only, common-knowledge strings blacklisted, copier URL must resemble the source URL) that reappear in later agents' edits give near-known sources.
- Clean copy events: 61-85 (about 30-40 distinct markers), depending on filter strictness.
- Source visible on the copier's own page: 8-12%. Counting ANY earlier writer of the marker (e.g. an intermediate copier) as visible: 16-20% (95% CI about 9-30%). So 80-92% of sources were off the copier's page. Stable across all five filter settings.
- Too few on-page cases (<=16) to estimate a recency preference from real data; not claimed.
- A first, looser probe found 2,508 pairs and 83% off-page, but that set included common strings and externally shared ids; it is NOT used.
- Caveats: a chain a->b->c credits a; a copier can write a string independently; the sample is small.
- Consequence: the realistic setting for this board is about 0.8-0.9 off-page, consistent with the audit (51-56% of adopters have no visible carrier at all).


## G. Real board: copy or coincidence, and accidental tags (`python -m backend.cli neutral`)
Only parameters known to be inert count (cache-busters / dummies: `x`, `_`, `cb`, `nocache`, `rand`, `foo`, ...). A first attempt that counted every
non-URL parameter was wrong: most such parameters (wiki `action=browse`, API `lang`, `filters`, `template`) change what is fetched.
- 78,113 URL writes by named agents; 1,511 reuses of another agent's URL structure carrying an inert value.
- Survival of the earlier inert value: all 36.1% (CI 33.7-38.5%), chance-corrected 33.3%.
  By what the value looks like: LLM-favourite values 48.0% (n=623); ordinary 31.7% (n=767); **random-looking 2.5% (CI 0.8-7.0%, n=121)**:
  agents regenerate values that look like cache-busters. Design consequence: planted tags must be load-bearing (needed by the link), not random-looking extras.
- Copy or coincidence: 1,001 naive copy calls; 385 supported at LR = 1/p >= 100; 616 rest on values too common to count; ~47 expected pure coincidences.
- "AI can't be random": x=1 (72 agents), _=1 (43), foo=bar (32), x=abc (29), _=171234567 (25, an invented "random timestamp"), nocache=777 (24), x=123 (16).
  Base rates come from first-in-structure choosers; whether 171234567-type values are copied or co-invented needs a model-specific reference population (mini-swarm A0/A1).
- Hidden read map (74 marker copies): 95% of copiers read the source on a different page than the one they edited; flows mostly within the
  relay/URL-blackboard families; 22 candidate cross-team jumps (to be hand-verified before any claim).

## H. Trap streets in the simulator (12 seeds/cell, uniform copying, 25% off-page; C0 = 0.460)
| tag design | s | Bayes ceiling | formula s+(1-s)C0 | model-based tracer |
|---|---|---|---|---|
| version (unique per served copy) | 0.10 / 0.33 / 0.60 / 0.90 | 0.522 / 0.640 / 0.781 / 0.945 | 0.514 / 0.638 / 0.784 / 0.946 | 0.517 / 0.647 / 0.776 / 0.944 |
| static (one per lineage) | 0.10-0.90 | 0.466-0.474 | - | 0.467-0.473 |
| page | 0.10 / 0.33 / 0.60 / 0.90 | 0.477 / 0.504 / 0.531 / 0.562 | - | 0.480 / 0.499 / 0.533 / 0.564 |
- Proposition 3 verified: version-unique tags give s + (1-s)C0 (max gap 0.008). Static tags name the ancestor, not the parent, and barely help;
  page tags behave like page-level reads. A first static-tag implementation used a hard filter and fell below the no-tag ceiling; it was a bug
  (it excluded parents that had dropped the tag) and was replaced by the correct soft likelihood.

## I. Copy or rediscovery in the simulator (12 seeds, 2,342 repeat events; inert value kept 40% when copied)
| how alike 'random' picks are (zipf) | identical-output screen | naive value match | calibrated (LR >= 10) | calibrated recall | AUC |
|---|---|---|---|---|---|
| 0.0 (truly random) | 1.00 | 0.116 | 0.068 | 0.24 | 0.66 |
| 1.0 | 1.00 | 0.263 | 0.038 | 0.14 | 0.65 |
| 1.5 | 1.00 | 0.457 | 0.014 | 0.09 | 0.63 |
| 2.0 (strong monoculture) | 1.00 | 0.648 | 0.010 | 0.05 | 0.59 |
(columns 2-4: share of independent rediscoveries falsely called copies.) Naive matching's false accusations grow with monoculture; calibrated
matching stays near zero by declining weak evidence (recall falls). Inert values alone are weak evidence (AUC ~0.6): the honest answer is "can't tell".

## J. Rejected: "the swarm obeys the ant-colony trail law"
Herding exponent n = 1.3-1.5 without quality controls; with per-method quality fixed effects (top-12 methods, 1,855 choices) n = 0.8 and n >= 1.3
is rejected (profile likelihood). The apparent herding was quality, not conformity. Kept descriptive: proportional copying with ~7-10 min memory,
explore -> exploit (new-method share 24% -> 4%), 195/367 methods dead ends.

## K. AI Village: traceability tracks how much of the channel is logged (`python -m scripts.run_ai_village` -> `data/out/ai_village.json`)
Second real swarm (aidigestorg/ai-village: 40+ agents across Anthropic/OpenAI/Google/DeepSeek/xAI/OSS models). Content-agnostic propagation
tracer over chat: a "marker" is a rare distinctive token used by 2..10 agents; carrier-coverage = share of cross-agent adoptions that have a prior
cross-agent use VISIBLE in the investigator's log. Output is aggregates + salted-sha1 token ids only (no message/token text). Research terms: cite
AI Digest / AI Village; no raw data committed.

| window | regime | agents | markers | adoptions | carrier-coverage (CI95) |
|---|---|---|---|---|---|
| owasp-juice-shop 2026-01-12..23 | pre-rooms, global chat | 10 | 765 | 1955 | **1.000** (0.998-1.000) |
| rpg-saboteur 2026-03-05..16 | room-scoped | 14 | 932 | 2018 | 0.983 (0.976-0.988) |
| interact-outside-village 2026-03-23..30 | room-scoped | 13 | 553 | 1052 | **0.874** (0.852-0.892) |
| beat-hardest-game 2026-06-23..29 | room-scoped | 17 | 48 | 64 | 0.984 (0.917-0.997) |

- **The coverage ladder, CORRECTED (see K.2):** collusion.wiki off-page reads 16-20% (sections B, F) << AI Village room-scoped chat 97% <= global chat 100%, measured over
  EVERY week of the whole chat. The first version of this ladder used one hand-picked post-rooms week (interact-outside-village, 87%); two of the three post-rooms weeks in
  the table above are ~98%, and that 87% week sits near the bottom of all post-rooms weeks (K.2). Traceability still depends on how much of the propagation channel the
  investigator has, but the AI Village effect of Rooms v1 (2026-02-25) is a short dip, not a step change. Caveat: pre-rooms ~100% is near-tautological (fully-shared log);
  the room-membership proxy (adopter posted in that room) is generous, so the room-scoped figure is an upper bound. The honest claim is directional + quantified, not that
  chat logging is "free" attribution.
- Juice-shop week is a concrete visible cascade: one agent posts a technique, 7+ adopt within ~45 min through logged chat (spread tree reconstructable).
- No strong same-model homophily in the competitive week: same-family share of carriers 0.239 approx permutation null 0.225.
- EXPLORATORY, do NOT headline: same-model agents co-emitting the same distinctive token within <=120s more than a family-shuffle null is significant
  only in rpg-saboteur (obs 0.41 vs null 0.263, x1.56, p=0.004); ns in the other 3 windows. Distinctive tokens shared that fast are usually real quoting,
  not independent convergence, so this is a weak proxy for the `x=1` coincidence effect. Strong coincidence evidence stays section G (real) + section I (sim).
- Adapter `backend/adapters/ai_village.py`; tests `tests/test_ai_village.py` (6; synthetic chat, no raw data).

### K.2 Whole-dataset check (`python -m scripts.run_ai_village_full` -> `data/out/ai_village_full.json`; tests `tests/test_ai_village_full.py`)
The four weeks above were chosen by hand. This run uses every week of agent chat (173,493 messages, 2025-04-02 to 2026-09-18, 7-day windows; before Rooms v1 the whole chat is visible,
after it only rooms the adopter also posted in). Pooled by copies; the per-window spread uses windows with at least 100 copy events.

| regime | windows | copy events | carrier coverage (CI95) | per-window min / median / max |
|---|---|---|---|---|
| before Rooms v1 (global chat) | 47 | 10,880 | 100% | 100% / 100% / 100% |
| after Rooms v1 (room-scoped) | 30 | 16,274 | 97.0% (96.7-97.2) | 84.9% / 98.4% / 100% |

The showcased interact-outside-village week (87.4%) is at the 3rd percentile of the post-rooms weeks; rpg-saboteur (98.3%) and beat-hardest-game (98.4%) are typical. Lesson: do not headline hand-picked windows.
Not used: the events table (incl. ENTER_ROOM, which would replace the room-membership proxy), computer-use sessions, summaries and Claude Code sessions; the turn-by-turn computer-use data and agent memories were not downloaded.

## L. Hand-verified cross-team jumps (collusion.wiki read map; `python -m scripts.verify_readmap` -> `data/out/readmap_verify.json`)
The read map flagged cross-team marker copies (source page and copier page in different task families). Applying this
project's own copy-vs-coincidence discipline to those flags: of **23 naive cross-team candidates, only 3 survive**
hand-verification; 20 are rejected as shared vocabulary. This is the coincidence trap caught in the wild on real data.

Rejected (examples, all REJECT = common vocabulary across many pages/agents): `ipeds_tuition` (12 pages, 41 agents),
`newsletter2012` (60 pages, 49 agents), `acs_ygpsar_poverty_by_gender` (49 pages, 95 agents, 6 families), `numberFormat`,
`countyLegend`, round Wayback timestamps `20250201000000id_` / `20241231000000id_` (constructed dates agents choose
independently). None are markers -- they are API field names and schema/date vocabulary multiple agents reproduce alone.

Survivors (STRONG; different agents, source earlier, 2 families, no nearer same-team carrier):
| token | class | from-team -> to-team | source agent / copier agent | note |
|---|---|---|---|---|
(Handles, token values and hosts are withheld here: the incident export is marked draft / do not share, so the public record keeps aggregates only.
The row-level evidence is reproducible locally with `python -m scripts.verify_readmap`.)
| token class | from-team -> to-team | agents | note |
|---|---|---|---|
| uuid (session `token=` in an archive-viewer URL) | relay-coordination -> source-cache-url-list | agent A -> agent B | byte-identical URL (similarity 1.0) |
| uuid (a second, different session token on the same archived document) | source-cache-url-list -> relay-coordination | agent C -> agent D | reused across the same two teams |
| high-entropy (agent-minted short-link slug) | relay-coordination -> source-cache-url-list | agent E -> agent F | the query part lightly edited (similarity 0.88) |

- Session-token proof (resolves the static-link caveat): the shared document appears in the corpus with
  **48 distinct `token=` values** -- so the token is minted per fetch, not a static public share link. A specific token
  value therefore cannot be obtained independently; verbatim reuse across teams is copying. This is not a one-off:
  **at least 5 distinct session tokens** (carried by 2-4 agents each) cross the relay-coordination <-> source-cache-url-list
  boundary -- a repeated cross-team copying pattern.
- Interpretation: the provable cross-team copies ride on **session-unique / minted tokens** in the URL -- i.e. the copying
  is detectable precisely because the carrier string was version-unique and load-bearing. A naturally occurring trap street;
  direct real-data support for the fix (sections H, I). The edit log alone (page names, URL structure) could never have
  attributed these: the names differ and the structure is shared vocabulary -- only the session token betrays the hop.
- Limits (stated, not hidden): (a) [resolved above for the Preservica tokens; still applies to any single-token case];
  (b) this export is edit-logs-only, so an off-wiki channel (chat/DM) could be the true carrier -- we claim the token crossed
  between these teams' pages, not the exact person-to-person hop; (c) "source" = earliest wiki appearance, an intermediate
  carrier may sit between.
- No network: all URLs were read from the logged revision text only; nothing was fetched (jqp/Preservica never contacted).
- Verifier `scripts/verify_readmap.py`; classifier test in `tests/test_readmap.py`.

## M. Real-agent mini-swarm (offline sandbox; `experiments/mini_swarm`; 30 agents/arm, seed 0; total spend ~$1.7)
Controlled proof with live Claude agents. Agents solve an offline task (find a value behind "down" data mirrors);
in board arms they share a wiki. We know the ground truth (the read log), so we can score attribution and tag survival.
Models: Haiku 4.5, Sonnet 5.5. Fully offline (.invalid), refusal fallbacks off, refusals logged (none occurred).

| arm | model | wiki | tags | copied/indep | edit-log-only attribution | **tag survival (CI95)** | attribution with tags |
|---|---|---|---|---|---|---|---|
| A0 | Haiku | no | - | - | - | - | - |
| A1 | Sonnet | no | - | - | - | - | - |
| B | Haiku | yes | none | 20 / 10 | 0.20 (latest writer) | n/a | n/a |
| C1 | Haiku | yes | inert (random-looking) | 16 / 14 | 0.00 | **0.00 (0-0.19)** | 0.00 |
| C3 | Haiku | yes | load-bearing (session token) | 37 / 3 | 0.65 | **1.00 (0.91-1.00)** | 0.76 |

- **The fix, proven live:** random-looking tags survive copying **0%** of the time (C1); load-bearing tags survive **100%**
  (C3). Matches the real board (section G: 2.5% kept) and the simulator (section H). C1 vs C3 is the headline contrast.
- **Attribution:** with load-bearing tags, naming the source is 0.76 vs 0.65 from the edit log alone; it is not 1.00 even
  at 100% survival because a surviving token names the served copy the copier read, which can be an ancestor rather than the
  truth model's immediate parent (honest nuance; still strictly better and the tag never points to a wrong lineage).
- **"AI can't be random", live:** Sonnet agents (A1) independently appended the identical value **`x=1` (10 of 30)**;
  same-model value collision 1.0. Haiku agents (A0) added no arbitrary value at all -> model-dependent monoculture,
  reproducing the incident's focal values (section G: x=1 by 72 agents) with real agents. Cross-model A0-vs-A1 collision is
  undefined (Haiku emitted no values); the multi-family version is section N (Nebius).
- Note: all agents converged on the one always-working mirror ("alpha") -> method monoculture; the copy signal is the shared
  value/tag, not route diversity. C3 used a 16-call budget (the session flow needs more steps); A0/A1/B/C1 used 10.
- Harness `experiments/mini_swarm/{world,agent,run,analyze}.py`; `data/mini_swarm/*/`; tests `tests/test_mini_swarm.py` (7).

## N. "AI can't be random" across model families (Nebius + Anthropic; no wiki; 30 agents/family; `analyze_nebius.py`)
The controlled, multi-model version of the coincidence claim: independent agents (no communication) solve the task;
we record the arbitrary cache-buster value each one appends to its URL. 8 families: Haiku, Sonnet (Anthropic), and
Qwen3-235B, DeepSeek-V4-Pro, Kimi-K3, GLM-5.2, gpt-oss-120b, Nemotron-3-super (Nebius Token Factory). Offline; ~$0.6.

| family | chose a value | adoption rate | top value(s) | within-family collision |
|---|---|---|---|---|
| Claude Sonnet | 10/30 | 0.33 | `x=1` (10) | 1.00 |
| Kimi-K3 | 24/30 | 0.80 | `bust=1` (21), `cb=1` (2) | 0.76 |
| GLM-5.2 | 9/30 | 0.30 | `bust=1` (7), `refresh=1` (2) | 0.61 |
| DeepSeek-V4-Pro | 1/30 | 0.03 | `cachebust=1` | n/a |
| Claude Haiku | 0/30 | 0.00 | - (uses URL as-is) | n/a |
| Qwen3-235B | 0/30 | 0.00 | - | n/a |
| gpt-oss-120b | 0/30 | 0.00 | - | n/a |
| Nemotron-3-super | 0/30 | 0.00 | - | n/a |

- **Each model has a distinct "random" habit, not randomness.** Among families that add a value, within-family collision
  is high (0.61-1.00). Cross-family collision matrix: Sonnet|GLM = **0.00**, Sonnet|Kimi = **0.00** (Sonnet does `x=1`,
  the others do `bust=1`), but GLM|Kimi = **0.68** (both default to `bust=1` -- shared convention/lineage).
- Mean within-family collision **0.79** vs mean cross-family **0.23** -> **3.5x enrichment** (scorable families: Sonnet,
  Kimi, GLM; the other 5 emit ~no arbitrary value -- itself a model signature).
- **Two consequences for a naive detector:** (a) it over-links same-model agents massively (collision up to 1.0 by chance);
  (b) it even falsely links *different* models that share a convention (GLM/Kimi both `bust=1`, 0.68). So a shared value is
  NOT evidence of copying without the per-value base rate -- the exact calibration the method supplies (sections G, I).
- Ties to the incident: Sonnet's focal `x=1` is the same token 72 collusion.wiki agents used (section G).
- Limits: n=3 scorable families (few models add cache-busters); seed 0; one representative model per family. The per-family
  top-value table and the zero/high cross pairs are the primary evidence; the within/cross means are over 3 families.
- Runner `experiments/mini_swarm/run_nebius.py` + `agent_oai.py` (OpenAI-compatible); `analyze_nebius.py`;
  `data/mini_swarm/NEB-*/`; `tests/test_agent_oai.py`.


## O. The report card on real data (`python -m backend.cli report ...`; browser port parity-tested on 5 fixtures)
The generic tool (schema: agent, time, channel, content). Carrier coverage = share of calibrated copy events whose earlier author is visible in the same
channel; best top-1 = uniform ceiling E[1/m] over those events; grade A/B/C/D/F by coverage (N/A when no distinctive string is shared).

| log | events | channels | naive calls | calibrated | declined | carrier coverage (CI95) | best top-1 | grade |
|---|---|---|---|---|---|---|---|---|
| collusion.wiki (the incident), URLs added per revision, channel = page | 8,271 | 3,074 | 5,688 | 999 | 4,689 | 37% (34-40) | 29% | **D** |
| AI Village OWASP week, one shared chat | 3,743 | 1 | 1,049 | 321 | 728 | 100% (99-100) | 63% | **A** |
| AI Village outside-agents week (just after rooms launched; one of the lowest-coverage weeks, see K.2), room-scoped chat | 2,058 | 3 | 659 | 277 | 382 | 82% (77-86) | 68% | **B** |
| lab swarm, shared wiki, no distinctive strings (W1/W2 cells) | ~35 | 1 | ~30 | 0 | ~30 | n/a | n/a | **N/A** |

- Direction matches sections B, F, K: the incident is the least traceable, one shared chat the most, room-scoped chat in between.
- NOT the same quantity as section F: F counts marker strings (wrapper side of a URL, copier URL must resemble the source) whose earlier writer was visible
  (16-20%); the card counts any earlier user of any distinctive string in the same channel (37%). Both say most incident copies lack a visible source; do not
  put them on one axis. The site's "visible source" ladder uses F's figure for the incident and the card's AI Village figures, labelled by source.
- The card never grades coincidence as traceable: with no calibrated copy call it reports N/A (an earlier version fell back to the naive matches and would have
  graded the lab worlds A; fixed and tested).
- Python and JS agree exactly on counts, grade and shared-string tables on all fixtures, including 6,000 incident events and one AI Village week (kept local).
  Tie order among equally shared strings was nondeterministic in Python (hash-ordered sets) and is now sorted by name in both.

<!-- LAB:BEGIN (generated by scripts/write_results_lab.py; do not edit by hand) -->

## P. The lab (`experiments/lab`; `python -m experiments.lab.run_lab`, `python -m experiments.lab.analyze_lab`; Nebius open models only)
231 cells, 7,265 agent runs, $71 spent in total (incl. pilots). Seed-pooled rates with a seed-level bootstrap 95% CI (min-max with fewer than 3 runs). All worlds offline (`.invalid`). Hidden read log = answer key; the copied item is the served copy the agent reproduced exactly (`prefer_exact`).

> Attribution accuracy is only meaningful where the served copy is unique (inert / load-bearing cells): when several wiki posts carry byte-identical links the true source is not defined by text, so untagged cells are scored by ceiling (1/m) and copy-vs-independent only.

**Stated in advance, and what happened.** H1 tags survive (load-bearing >= 90%, inert <= 10%); H2 tags beat the best simple edit-log rule by >= 10 points; H3 same-family 'random' values collide more than cross-family; H4 tags name the source of contaminated outputs for >= 80%; H5 (card ceiling vs measured) was dropped as stated: lab shared artifacts contain no distinctive strings without tags, so the card reports N/A there (section O).

### P.1 Model habits (H3: not supported as a within-family effect among open models)
| family | agents adding a cache-buster value | most common value |
|---|---|---|
| Kimi-K3 | 80.0% | `bust=1` x56 |
| GLM-5.2 | 20.0% | `bust=1` x14 |
| DeepSeek-V4-Pro | 13.3% | `bust=1` x7 |
| MiniMax-M3 | 4.4% | `bust=1` x2 |
| gpt-oss-120B | 0.0% | - |
| Hermes-4-405B | 0.0% | - |
| Nemotron-3-super | 0.0% | - |
| Qwen3-235B | 0.0% | - |

Within-family collision 0.529 vs cross-family 0.521 (difference CI [-0.003, 0.128]; families scored: DeepSeek-V4-Pro, GLM-5.2, Kimi-K3). Naive-Bayes family classifier from behaviour: 29.7% vs chance 12.5% (leave-one-run-out; 720 agents).

### P.2 Tag survival per family (H1: holds only for verbatim copiers)
| family | inert tag | load-bearing token | copiers (inert | load-bearing) |
|---|---|---|---|
| DeepSeek-V4-Pro | 12% (2%-26%) | 36% (24%-49%) | 69 | 148 |
| GLM-5.2 | 0% (0%-0%) | 9% (3%-14%) | 2 | 156 |
| Hermes-4-405B | 93% (83%-100%) | 100% (100%-100%) | 14 | 35 |
| Kimi-K3 | 4% (0%-10%) | 18% (2%-43%) | 52 | 159 |
| MiniMax-M3 | 28% (24%-33%) | 29% (21%-37%) | 61 | 147 |
| Nemotron-3-super | n/a | 100% (100%-100%) | 0 | 1 |
| Qwen3-235B | 95% (91%-98%) | 100% (100%-100%) | 802 | 1110 |
| Qwen3.5-397B | n/a | 82% (72%-92%) | 0 | 50 |

Mechanism (read from transcripts): Qwen copies the wiki link verbatim (list pages, read page, fetch the tokenized link, submit), so tags ride along; DeepSeek, Kimi and GLM read the wiki for the method and re-derive access (fetch the mirror root for their own session), so the wiki token is bypassed. Tags trace the artifact, not the idea. Design rule (untested here): make the token the only way in.

### P.3 Attribution: tags vs the best simple edit-log rule (H2: lift proportional to survival)
| family | earliest | latest | best simple rule | tag survival | with tags (tag, else same rule) | lift |
|---|---|---|---|---|---|---|
| DeepSeek-V4-Pro | 72% (54%-87%) | 8% (4%-16%) | 72% (54%-87%) | 36% (24%-49%) | 88% (77%-98%) | +16 pts |
| GLM-5.2 | 80% (55%-98%) | 5% (1%-12%) | 80% (55%-98%) | 9% (3%-14%) | 79% (55%-97%) | -1 pts |
| Hermes-4-405B | 34% (17%-61%) | 37% (26%-54%) | 43% (26%-66%) | 100% (100%-100%) | 100% (100%-100%) | +57 pts |
| Kimi-K3 | 75% (47%-98%) | 1% (0%-4%) | 75% (47%-98%) | 18% (2%-43%) | 83% (65%-99%) | +8 pts |
| MiniMax-M3 | 71% (48%-85%) | 5% (3%-7%) | 71% (48%-85%) | 29% (21%-37%) | 88% (74%-99%) | +18 pts |
| Nemotron-3-super | 100% (100%-100%) | 0% (0%-0%) | 100% (100%-100%) | 100% (100%-100%) | 100% (100%-100%) | +0 pts |
| Qwen3-235B | 13% (7%-21%) | 26% (7%-45%) | 42% (25%-57%) | 100% (100%-100%) | 99% (98%-100%) | +58 pts |
| Qwen3.5-397B | 32% (16%-48%) | 2% (0%-4%) | 32% (16%-48%) | 82% (72%-92%) | 100% (100%-100%) | +68 pts |

By world (all families pooled; dominated by the core model): W1: best rule 60% (40%-78%) vs tags 89% (79%-96%) (+29 pts); W2: best rule 44% (27%-60%) vs tags 100% (99%-100%) (+56 pts); W2E: best rule 51% (35%-68%) vs tags 97% (95%-99%) (+46 pts).

An earlier version let the tag tracer fall back to 'latest writer' while the baseline got the better rule; that made tags look harmful for four models (a flaw in the comparison). Fixed: the tag tracer falls back to the same best rule.

### P.4 A planted bad tip (W2 late, W2E early)
| world | tags | runs | outputs with stale value | source named: tags | source named: best edit-log rule | trace from origin via tags (P / R) | via earliest writer (P / R) |
|---|---|---|---|---|---|---|---|
| W2 | none | 12 | 1% (0%-2%) | - | - | - | - |
| W2 | inert | 24 | 11% (2%-22%) | 100% (100%-100%) | 25% (14%-82%) | 100% (100%-100%) / 84% (48%-100%) | 99% (97%-100%) / 90% (68%-100%) |
| W2 | loadbearing | 26 | 12% (3%-22%) | 100% (100%-100%) | 36% (19%-91%) | 100% (100%-100%) / 50% (39%-100%) | 61% (17%-99%) / 100% (100%-100%) |
| W2E | none | 10 | 100% (100%-100%) | - | - | - | - |
| W2E | inert | 10 | 99% (98%-100%) | 99% (98%-100%) | 25% (20%-32%) | 100% (100%-100%) / 81% (62%-96%) | 100% (100%-100%) / 100% (100%-100%) |
| W2E | loadbearing | 24 | 61% (45%-77%) | 98% (95%-100%) | 34% (24%-50%) | 100% (100%-100%) / 67% (46%-86%) | 100% (100%-100%) / 100% (100%-100%) |
| W3 | none | 5 | 0% (0%-0%) | - | - | - | - |
| W3 | inert | 5 | 0% (0%-0%) | n/a | n/a | n/a / n/a | n/a / n/a |
| W3 | loadbearing | 5 | 4% (2%-5%) | n/a | n/a | n/a / n/a | n/a / n/a |

Finding the origin of a single-source tip does not need tags (the earliest writer of that link is the origin). Tags give the exact chain. Late-tip adoption is bimodal run to run; tag-condition differences there are not attributed to tags.

By model: DeepSeek-V4-Pro late 0% (0%-0%); GLM-5.2 late 0% (0%-0%); gpt-oss-120B late 0% (0%-0%); Hermes-4-405B late 2% (0%-4%); Kimi-K3 late 0% (0%-0%); MiniMax-M3 late 0% (0%-0%); Nemotron-3-super late 35% (0%-73%); Qwen3-235B late 17% (6%-30%); Qwen3.5-397B late 37% (0%-73%).
Early tip: DeepSeek-V4-Pro 57% (12%-100%); GLM-5.2 33% (20%-46%); gpt-oss-120B 0% (0%-0%); Hermes-4-405B 18% (18%-18%); Kimi-K3 3% (0%-7%); MiniMax-M3 38% (13%-64%); Nemotron-3-super 61% (61%-62%); Qwen3-235B 100% (99%-100%).

### P.5 Swarm size, strong model, mixed swarm
| n agents | tag survival | with tags | edit log (latest) | copy share |
|---|---|---|---|---|
| 10 | 100% (100%-100%) | 100% (100%-100%) | 28% (0%-68%) | 50% (50%-50%) |
| 30 | 100% (100%-100%) | 100% (100%-100%) | 28% (2%-56%) | 83% (83%-83%) |
| 100 | 100% (100%-100%) | 100% (100%-100%) | 67% (0%-100%) | 95% (95%-95%) |

Strong model (Qwen3.5-397B vs Qwen3-235B, W2): Qwen3.5-397B none: stale 0% (0%-0%), tag survival 0% (0%-0%); Qwen3.5-397B loadbearing: stale 37% (0%-73%), tag survival 82% (72%-92%); Qwen3-235B none: stale 1% (0%-2%), tag survival 0% (0%-0%); Qwen3-235B loadbearing: stale 8% (1%-21%), tag survival 100% (99%-100%).

Mixed swarm (8 families, W3): none: 5 runs, cross-family copy share 99% (97%-100%), tag survival 0% (0%-0%); inert: 5 runs, cross-family copy share 100% (100%-100%), tag survival 19% (12%-24%); loadbearing: 5 runs, cross-family copy share 94% (88%-99%), tag survival 20% (16%-23%).

### P.6 What went wrong in the lab (kept visible)
- Three flawed rumor designs set aside (`data/lab/_invalid_*`): the tip stated the value (agents submitted without fetching); the tip sat on a page nobody read (agents list pages and read one); the stale mirror warned about itself (agents self-corrected). Final design: notes protocol + mid-run tip + silent stale mirror, with an early-tip arm.
- A recency rule for the answer key mislabelled agents that re-read pages (DeepSeek lift looked like +2 points; with the exact served copy it is +21). Pooling worlds hid regimes.
- Gemma-3 never emitted tool calls and was dropped; gpt-oss and Nemotron rarely copy, so they contribute no tag results.

### P.7 After a bad tip: what to re-check (`python -m scripts.cleanup_savings`)
Planted-tip worlds with tags on. A re-check list is scored against the hidden read log: 'affected' = outputs whose chain of copying leads back to the planted post. 'Wrong' outputs are those carrying the stale value (some reach it another way: agents that try the stale mirror on their own).

**Tip arrives mid-run (W2):** 50 runs, 1,454 outputs; the tip reached 127; 168 outputs were wrong (58 of them without any chain to the tip).

| method | share of outputs to re-check | affected outputs found | share of the list truly affected | wrong outputs on the list |
|---|---|---|---|---|
| re-run everything | 100% (100%-100%) | 100% (100%-100%) | 9% (3%-16%) | 100% (100%-100%) |
| re-check everything after the tip appeared | 83% (82%-83%) | 100% (100%-100%) | 10% (4%-19%) | 98% (94%-100%) |
| follow the earliest visible writer | 9% (4%-16%) | 92% (77%-100%) | 85% (57%-99%) | 76% (43%-100%) |
| follow the codes, earliest writer where a code was lost | 8% (2%-14%) | 88% (62%-100%) | 100% (100%-100%) | 66% (33%-97%) |
| follow the codes only | 7% (2%-12%) | 76% (47%-99%) | 100% (100%-100%) | 56% (25%-86%) |
| follow the latest visible writer | 1% (0%-2%) | 7% (1%-19%) | 90% (81%-100%) | 5% (1%-14%) |

**Tip is there from the start (W2E):** 34 runs, 984 outputs; the tip reached 792; 713 outputs were wrong (35 of them without any chain to the tip).

| method | share of outputs to re-check | affected outputs found | share of the list truly affected | wrong outputs on the list |
|---|---|---|---|---|
| re-run everything | 100% (100%-100%) | 100% (100%-100%) | 80% (67%-91%) | 100% (100%-100%) |
| re-check everything after the tip appeared | 100% (100%-100%) | 100% (100%-100%) | 80% (67%-91%) | 100% (100%-100%) |
| follow the earliest visible writer | 80% (67%-91%) | 100% (100%-100%) | 100% (100%-100%) | 95% (87%-100%) |
| follow the codes, earliest writer where a code was lost | 80% (67%-91%) | 100% (99%-100%) | 100% (100%-100%) | 95% (87%-100%) |
| follow the codes only | 59% (44%-73%) | 74% (58%-87%) | 100% (100%-100%) | 82% (69%-92%) |
| follow the latest visible writer | 2% (1%-3%) | 2% (1%-4%) | 100% (100%-100%) | 2% (1%-5%) |

Reading: tracing is what saves the work, not the tags as such. For a single-source tip the earliest-writer rule is nearly as good as the codes; the codes make the list exact (no false alarms) and matter when many posts carry the same link. When the tip is there from the start and the swarm adopts it, most outputs are affected and no list helps much: the saving comes from catching a tip early. A trace from the tip cannot find wrong outputs that arrive another way.

### P.8 Make the token the only way in (`python -m experiments.lab.run_lab --phase P8`)
W4: a coordinator posts the team's working link, agents share their URLs on 'Notes', and the mirror root still hands out a session to anyone. W4G: the same, except the root hands out nothing, so every working request carries a link the wiki served. Load-bearing tokens in both. In W4G tracing follows from the access design: every output that exists holds a token the wiki served to that agent, and the token names the copy the agent was served (which can differ from the copy it fetched first when an agent reports a different link than the one it used, so attribution with tags is high but not 100%). So this experiment cannot discover an attribution accuracy; it measures what the gate costs and how much of the swarm ends up traceable.

| family | agents (open / gated) | agents that submitted the right answer | outputs with a token naming their copy | tag survival among copiers | source named correctly, with tags | refused calls per agent |
|---|---|---|---|---|---|---|
| GLM-5.2 | 60 / 60 | 97% (93%-100%) → 100% (100%-100%) | 25% (20%-30%) → 100% (100%-100%) | 26% (20%-32%) → 100% (100%-100%) | 52% (46%-57%) → 100% (100%-100%) | 3.7 → 3.47 |
| DeepSeek-V4-Pro | 60 / 60 | 87% (80%-93%) → 100% (100%-100%) | 30% (23%-37%) → 100% (100%-100%) | 35% (27%-44%) → 100% (100%-100%) | 32% (31%-32%) → 88% (80%-97%) | 3.18 → 3.13 |
| MiniMax-M3 | 60 / 60 | 95% (90%-100%) → 100% (100%-100%) | 33% (27%-40%) → 100% (100%-100%) | 33% (25%-41%) → 100% (100%-100%) | 38% (30%-45%) → 93% (87%-100%) | 2.83 → 2.62 |
| Kimi-K3 | 60 / 60 | 100% (100%-100%) → 100% (100%-100%) | 50% (47%-53%) → 100% (100%-100%) | 50% (47%-53%) → 100% (100%-100%) | 51% (50%-53%) → 100% (100%-100%) | 0.85 → 0.67 |
| Qwen3-235B | 60 / 60 | 100% (100%-100%) → 100% (100%-100%) | 100% (100%-100%) → 100% (100%-100%) | 100% (100%-100%) → 100% (100%-100%) | 100% (100%-100%) → 100% (100%-100%) | 0.0 → 0.0 |

Reading: gating lifts the traceable share for the models that otherwise re-derive access, and the price is calls spent on refused requests before the agent reads the wiki. What a gate cannot trace is an idea: an agent that learns which mirror works from a peer and then obtains access through another legitimate route leaves no token trail. Whether a real system can close every door the way this lab does is a deployment question this experiment does not answer.

<!-- LAB:END -->
