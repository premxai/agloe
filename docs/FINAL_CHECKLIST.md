# Final checklist (Sun 4 Oct 2026, submission 5pm PT, demos 6-7pm)

Everything that could be done without your accounts is done and committed locally (nothing is pushed or deployed). What is left needs you. In order:

## 1. Push the code (about 5 minutes)
1. On github.com create an empty public repository (no README, no licence: the repo has both). Copy its URL.
2. In `lineage/`:
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. Check on GitHub that there is no `.env`, no `data/` folder and no `tools/` folder. (`python -m scripts.prelaunch` already checks this locally.)

## 2. Deploy the site (about 5 minutes)
```bash
cd frontend
npx vercel --prod          # first time: log in, accept the defaults; the config is in frontend/vercel.json
```
Open the URL it prints and check, on desktop and on your phone: the landing page, `/card/` (click "Incident-like swarm"), `/colony/`, `/replay/faceoff.html` (press Space), `/paper/agloe.html`. A page that is blank means the site's security policy blocked something: tell me the page and I will fix it.

## 3. Fill in the links (1 minute)
```bash
python -m scripts.set_urls --site https://<your-site> --repo https://github.com/<you>/<repo> --video <video url> [--hf <dataset url>]
git add -A && git commit -m "Fill in links" && git push
python -m scripts.prelaunch          # should show 0 blockers
```

## 4. Video (5 minutes, optional but recommended)
`media/agloe-face-off.mp4` is a silent recording of the Face-Off story (58 s). Upload it (YouTube unlisted or Drive "anyone with the link") and use that link for `--video`. To re-record: open `/replay/faceoff.html` and press "Make a clip".

## 5. Submit on Airtable (5 minutes)
Paste from `docs/SUBMISSION.md`: the write-up, the "real results" section, the three links, team Paper Towns, names and emails. Delete item 9 of the results unless other teams shared cards. **Before 5:00pm PT.**

## 6. Ask the organisers (needed for anything public beyond the demo)
- May aggregate figures from the collusion.wiki export (counts, rates, hashed handles) appear in public write-ups? The repo and site publish aggregates only.
- Is it OK to invite teams to try the report card (`docs/LAUNCH.md` section 1)? Post the Slack message only after they say yes.
- Tell AI Digest about the publication (their dataset terms ask for it).

## 7. Demo (6-7pm)
Script and timings: `docs/LAUNCH.md` section 3. Open the site on the projector, start with `/replay/faceoff.html`. Backup: the mp4. Have the "Incident-like swarm" sample ready in `/card/` and `/colony/`; never show the real incident's text on screen.

## Later (not needed for the hackathon)
- arXiv: `arxiv/TODO_BEFORE_ARXIV.md` (25 placeholders, organisers' OK, endorsement). Hugging Face dataset: `docs/HF_RELEASE.md`.
- Licence: `LICENSE` is MIT with "Paper Towns" as the holder; change the name if you prefer.

## What was checked today
Full rebuild from the lab data (`python -m scripts.finalize --tests`), 116 unit tests plus the two JavaScript tests, a fresh clone of the committed repo passing the tests, every site page loading with no failed requests or console errors, no secrets or personal paths in published files, the arXiv paper compiling to 34 pages from a clean folder.
