# Launch drafts (for you to review and send; nothing here has been sent)

## 1. Slack: invite other teams to try the report card (post only after the organizers are fine with it)

> Hi all, Paper Towns here. We built a free report card that answers "if something bad spreads through my agents, could I trace it?"
> Drop **your own** swarm's log file on a web page (JSONL, JSON or CSV; if your column names differ it asks you to pick them) and get a graded answer in about a minute:
> which repeated strings are real copying, which are coincidence, and what to log next. It runs entirely in your browser, so **your logs never leave your machine** (check the Network tab).
> If you're happy to, share just the card: the "Copy card as JSON" button gives counts and rates only (it leaves out any text from your logs unless you tick a box).
> We'd like to show a few real examples at the demo, with names withheld unless you say otherwise. We never ask for raw logs and we don't touch anyone's live swarm. <link>/card/

### 1b. Running it with other teams (the "real results" part of the submission)

1. Get the organizers' OK first (question 2 below). Post the invite above, or walk up to teams with a laptop and open `<link>/card/`.
2. Each team drops its own log; a team that wants to share clicks "Copy card as JSON" and pastes it to you (counts and rates only).
3. Save each pasted card as its own `.json` file in a local `shared_cards/` folder (gitignored until teams agree to publish).
4. `python -m scripts.collect_cards shared_cards/` prints a table for the write-up and writes `frontend/data/team_cards.json`, which makes the "Cards from other swarms" section appear on the site
   after the next deploy. Swarms are anonymised ("Swarm A") unless you pass `--names` and the team agreed.
5. Paste the table into item 7 of `docs/SUBMISSION.md`. Report whatever the cards say, including grades that make your own claims look weaker.

If a log has no timestamps, the card's mapper offers "row order". If nobody shares a card, say so; the incident and AI Village grades are the real-data evidence.

## 2. Questions for the organizers (kickoff)

1. May aggregate figures from the collusion.wiki export (counts, rates, hashed handles) appear in public write-ups? We don't plan to show page text or handles.
2. Is it OK to invite teams to share a report card (aggregates only) at the demo?
3. What did investigators of the incident most wish they could trace? We'd like the checklist to answer that.
4. Is there a preferred way to cite the AI Village dataset in the paper?

## 3. The 2-minute demo

1. **Hook (10s).** "In the real incident, a perfect investigator could trace at most 16% of the copying. And the obvious detector made 23 accusations of cross-team collusion. 20 were agents independently typing the same dataset field names."
2. **See it (55s).** Open `replay/faceoff.html` (it plays itself; Space pauses). Narrate over it: "One bad tip, 30 AI agents. Same records, two investigators. Left: the edit log alone, a star of wrong guesses, 5 of 30 right. Right: every copied link carries a secret code, 30 of 30. Second run, a late tip: without a trace you re-check 25 outputs; follow the trace and it's 4." Say the honest line: "This is the best case, Qwen copies links exactly; some models skip the code, which is why we also closed that door." Backup: the clip from "Make a clip".
3. **Your swarm (40s).** Open the report card. Drop a participant's file, or click "Incident-like swarm" (synthetic, safe to show on screen): grade D, "165 naive matches become 16 real ones", "everyone types this", what to log next. Say that the real incident went 1,001 to 385. Then open `colony/` and drop the same file: "every agent is an ant, trails form as the log plays; click one and it traces back to what it read, and shows who is downstream, the re-check list". For a real swarm, export an AI Village window beforehand (`python -m scripts.export_log --dataset ai_village --lo 2026-03-23 --hi 2026-03-30`, local only, never uploaded or committed) and drop that file; strings stay masked unless you tick "show the strings". "Nothing is uploaded: watch the Network tab." Do not put the real incident sample on screen: its "everyone types this" table shows text from a file marked do-not-share.
4. **Why it holds (10s).** Show the site's "Make the token the only way in" chart: "some models skip the code; when the only door is the coded link, 25 to 50 percent traceable becomes 100, and every agent still finishes."
5. **Close (10s).** "Report card, canary kit and a benchmark with a hidden answer key, all open. Read the past honestly, make the future traceable."

Timing: 10 + 55 + 40 + 10 + 10 is about 2 minutes. If you only have a minute, play the face-off and skip steps 3 and 4.

Backup: a screen recording of steps 2 and 3; the card sample buttons work offline.

## 4. X thread (draft)

1. We studied the real incident where AI agents passed tricks to each other through a shared wiki. Question: when one agent's mistake spreads, can you trace it? Short answer: mostly no. 🧵
2. Even a *perfect* investigator could trace at most ~16% of the copying from the edit logs. Reads weren't logged. [chart: logs ladder]
3. The obvious detector ("same string = copied") flagged 1,001 copies; only 385 survive calibration. It flagged 23 cross-team collusion jumps; 3 were real. 20 were agents independently typing the same dataset field names.
4. Why: AI isn't random. We ran thousands of agents of 8 model families on the same tiny task. Each family has habits; several reach for the same "random" value. [fingerprint chart]
5. The fix is old: mapmakers hide a fake street (Agloe, NY) so copiers give themselves away. We serve every wiki read with its own token. A copied link names the exact copy. [replay gif]
6. But decoration isn't enough. Whether a harmless tag survives copying depends on the model, and some models just fetch their own session and skip it. When we made the token the only way in, 25-50% of outputs carried a traceable token became 100%, and every agent still finished. [tag chart]
6b. After a bad tip: re-checking everything submitted after it appeared meant 83% of outputs; following the trace meant ~9%, finding 88-92% of the outputs it reached. A tip that's there from the start reaches ~80%, so catch it early. [cleanup chart]
7. What you can use: a report card (runs in your browser, nothing uploaded), a 3-call canary kit, and Agloe-Bench, a benchmark with a hidden answer key. <link>
8. Honest limits: offline lab, one narrow task, open models, exposure not intent. All in the paper. Read the past honestly, make the future traceable. #AISwarmHackathon

## 5. Investigator's checklist (also in the paper's appendix)

1. **Log reads, not just writes.** Who was shown which page or message, and when. Without it, most sources are invisible.
2. **Give every served copy its own token** (load-bearing: the thing the agent needs to make the link work).
3. **Before you call a match copying, check the base rate.** A string used by many agents, or a field name, is vocabulary. Different models share conventions.
4. **Know your agents' habits.** Do they copy the first link, the newest, or verify? The same log supports different conclusions.
5. **Report the ceiling.** If the logs cannot tell, say so: "untraceable from these logs" is a finding.
6. **Measure who trusts a newcomer.** An early bad tip took over some models completely and was ignored by others. Check outputs, not only sources.
