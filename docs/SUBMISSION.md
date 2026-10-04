# Submission text (Airtable): fill the three links, review, paste

**Team:** Paper Towns · **Project:** Agloe: trap streets for AI agent swarms
**Links:** repo `<github url>` · live demo and report card `<site url>` · paper `<site url>/paper/agloe.pdf` · video `<video url>`
**Team members / emails:** `<names and emails>`

## One-paragraph write-up

When one agent's mistake spreads through a swarm, can you trace it? In the real incident the logs recorded edits, not reads, so mostly no: even a perfect
investigator could trace at most 16% of the copying, and the obvious detector ("same string means copied") made 1,001 copy calls of which 385 survive calibration, and
23 cross-team collusion jumps of which 3 survive hand verification. Agloe is a toolkit and benchmark built from that incident: a **report card** that grades how traceable
a swarm is and separates real copying from coincidence (it runs entirely in the browser, so other teams can try it on their own logs without uploading anything); a
**canary kit** that serves each page view with its own load-bearing token so a copied link names the copy it came from; and **Agloe-Bench**, lab swarms with a hidden answer
key and a scorer. We validated them on the incident, on a second real swarm (AI Village), and in an offline lab of several thousand agent runs across eight model families.
We report what did not work as carefully as what did.

## Real results from using the tool (the optional section)

1. **The incident's edit logs cap traceability.** Report card on the incident sample: grade D (37% carrier coverage, best possible top-1 29%); 82% of naive "same string"
   matches were shared vocabulary. Across 35 behaviours (2,976 adopters), 56% had no visible carrier and the best possible top-1 attribution was 16.2%.
2. **Naive collusion detection mostly produces false findings.** 23 cross-team jumps flagged; 20 were dataset field names and timestamps typed independently by up to 49 agents;
   3 were real, and provable only because the URL carried a per-fetch session token (48 distinct values for one resource): a trap street that occurred by accident.
3. **Logging decides traceability.** Same method over every week of the whole AI Village chat (173,493 agent messages): 100% of copies had a visible source before chat was split into rooms,
   97% after (lowest week 85%), versus 16-20% in the incident, where reads were never logged. (We first showed one hand-picked post-rooms week at 87%; it was among the lowest, so we replaced it with the whole-dataset result.)
4. **Whether a bad tip takes hold depends on the model.** In the lab, an early bad tip was adopted by every agent of the core model through cascades 6 to 9 hops deep, and the
   best simple edit-log rule named only a minority of the immediate sources; other model families adopted it partly or not at all, and a late tip was ignored by most families.
5. **Tags help in proportion to how many agents copy the artifact.** Lift over the best simple edit-log rule ranged from about 0 to +68 points by model (largest for Qwen3.5, Qwen3 and Hermes); agents that redo the work
   (fetch their own session) bypass the tag. Single-origin tips can be root-caused without tags.
6. **Make the token the only way in.** We closed that door in the lab (the mirror hands out sessions only through links the wiki served). For the four models that bypassed the token, the share of outputs
   carrying a token naming their copy rose from 25-50% to 100%, and every agent still finished (refused calls per agent were unchanged). This follows from the access design, so it shows feasibility and cost, not a discovery;
   a gate traces access, not ideas an agent learns from a peer and acts on through another door.
7. **After a bad tip, trace it instead of re-running everything.** For a tip that arrives mid-run, re-checking everything after it appeared means 83% of outputs; following the trace means about 9% and finds
   88-92% of the outputs the tip reached. A simple earliest-writer rule gets most of that; the codes make the list exact. A tip that is there from the start reaches about 80% of outputs, so the saving is in catching it early.
8. **Models have habits, and share them.** Independent agents add throwaway "random" values at very different rates by model, and several choose the same value, so a shared value alone is weak evidence.
9. **Other teams' swarms.** `<fill in only if teams shared cards: paste the table from python -m scripts.collect_cards; otherwise delete this item>`

## Honest limits

Offline lab, one narrow task; open models on one provider (earlier Claude runs are single-seed); "copied" means exposure, not intent; the incident data is used as aggregates only
(it is marked draft / do not share) and the AI Village dataset under its research terms; nothing was run against anyone's live swarm. Three of our own experiment designs were wrong
and were set aside (documented in the paper, section 6, and `docs/RESULTS.md` P.6).

## Reproduce

`python -m pytest tests -q`, then `python -m scripts.finalize` (rebuilds every derived artifact from the lab data), then `python -m http.server 5188 --directory frontend`.
