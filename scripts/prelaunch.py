"""Pre-launch checks: run this right before you push, deploy and submit.

  python -m scripts.prelaunch            # fast checks (a few seconds)
  python -m scripts.prelaunch --tests    # ... plus the unit tests and the two JavaScript tests

Checks: no secrets or personal paths in files git would publish; no raw-incident or AI Village data files; the site's local links resolve and its JSON parses;
no byte-order marks; link placeholders left in the README and submission text; uncommitted changes. Exits 1 if anything is a blocker (marked FAIL);
TODO lines are things you still have to fill in.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|hf_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|(?:api[_-]?key|token|secret)['\"]?\s*[:=]\s*['\"][A-Za-z0-9_-]{20,}['\"])")
PERSONAL = re.compile(r"(C:\\Users\\|/Users/[a-z]|sri varshini)", re.I)
FORBIDDEN = re.compile(r"(^|/)(data/raw/|\.env$|chat_messages|revisions.*\.(jsonl|gz|json)$)")
LINK_PLACEHOLDERS = ["<deployed url>", "<site url>", "<github url>", "<video url>", "<hf dataset url>"]
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".md", ".json", ".jsonl", ".tex", ".bib", ".txt", ".yml", ".yaml", ".toml"}

fails: list[str] = []
todos: list[str] = []


def git_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True).stdout
    return [ROOT / l for l in out.splitlines() if l and (ROOT / l).is_file()]


def check_files(files: list[Path]) -> None:
    bad_secret, bad_personal, bad_name, bom = [], [], [], []
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if FORBIDDEN.search(rel):
            bad_name.append(rel)
        if p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size < 3_000_000:
            raw = p.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                bom.append(rel)
            text = raw.decode("utf-8", errors="ignore")
            if rel != "scripts/prelaunch.py":
                if SECRET.search(text):
                    bad_secret.append(rel)
                if PERSONAL.search(text):
                    bad_personal.append(rel)
    for label, items in (("possible secrets", bad_secret), ("personal paths or names", bad_personal), ("raw-data or env file names", bad_name), ("byte-order marks", bom)):
        if items:
            fails.append(f"{label} in: {', '.join(items[:8])}")
    print(f"files checked: {len(files)}")


def check_site() -> None:
    fe = ROOT / "frontend"
    broken, n = [], 0
    for f in list(fe.rglob("*.html")):
        if "farm" in f.parts:
            continue
        for r in re.findall(r'(?:href|src)=["\']([^"\'#?]+)', f.read_text(encoding="utf-8", errors="ignore")):
            if re.match(r"^(https?:|//|data:|mailto:|javascript:)", r) or "{" in r:
                continue
            p = fe / r.lstrip("/") if r.startswith("/") else f.parent / r
            n += 1
            if not (p.exists() or (p.is_dir() and (p / "index.html").exists()) or (p.with_suffix(".html")).exists()):
                broken.append(f"{f.relative_to(fe).as_posix()} -> {r}")
    bad_json = []
    for j in list((fe / "data").glob("*.json")) + list((fe / "replay" / "data").glob("*.json")):
        try:
            json.loads(j.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bad_json.append(f"{j.name}: {e}")
    if broken:
        fails.append("broken site links: " + "; ".join(broken[:6]))
    if bad_json:
        fails.append("site JSON does not parse: " + "; ".join(bad_json))
    print(f"site: {n} local links checked, {len(broken)} broken")
    for must in ("index.html", "card/index.html", "colony/index.html", "replay/faceoff.html", "paper/agloe.pdf"):
        if not (fe / must).exists():
            fails.append(f"site file missing: {must}")


def check_placeholders() -> None:
    for rel in ("README.md", "docs/RESULTS.md", "docs/CANARY.md", "docs/HF_RELEASE.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        left = [t for t in LINK_PLACEHOLDERS if t in text]
        if left:
            todos.append(f"{rel}: still has {', '.join(left)}  (fill it in by hand)")
    r = subprocess.run([sys.executable, "-m", "scripts.arxiv_placeholders"], cwd=ROOT, capture_output=True, text=True)
    last = [l for l in r.stdout.splitlines() if l.strip()][-1:] or [""]
    if r.returncode:
        todos.append(f"arXiv paper: {last[0]}  (draft: authors, dataset link, licence of the data, provider details)")
    git = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    if git:
        todos.append(f"{len(git)} uncommitted change(s): git add -A && git commit")


def run_tests() -> None:
    steps = [([sys.executable, "-m", "pytest", "tests", "-q"], "unit tests"), (["node", "frontend/card/parity.test.mjs"], "card parity"), (["node", "frontend/card/colony.test.mjs"], "colony tests")]
    for cmd, label in steps:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        print(f"{label}: {'ok' if r.returncode == 0 else 'FAILED'}  {tail}")
        if r.returncode:
            fails.append(f"{label} failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", action="store_true")
    a = ap.parse_args()
    check_files(git_files())
    check_site()
    check_placeholders()
    if a.tests:
        run_tests()
    for f in fails:
        print("FAIL", f)
    for t in todos:
        print("TODO", t)
    print("\nblockers:", len(fails), " to fill in:", len(todos))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
