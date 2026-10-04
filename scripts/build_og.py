"""Render frontend/og.html to frontend/og.png (1200x630 link-preview image) with headless Edge.

The headline number is read from frontend/data/results.json so the card never disagrees with the site.
Usage: python -m scripts.build_og
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def main() -> None:
    page = ROOT / "frontend" / "og.html"
    res = json.loads((ROOT / "frontend" / "data" / "results.json").read_text(encoding="utf-8"))
    pct = f"{round(res['incident']['best_top1'] * 100)}%"
    page.write_text(re.sub(r'(<div class="big">)[^<]*(</div>)', rf"\g<1>{pct}\g<2>", page.read_text(encoding="utf-8")), encoding="utf-8")
    out = ROOT / "frontend" / "og.png"
    if not EDGE.exists():
        raise SystemExit("Edge not found; screenshot frontend/og.html at 1200x630 manually")
    subprocess.run([str(EDGE), "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={out}", "--window-size=1200,630", page.as_uri()],
                   check=True, timeout=120, capture_output=True)
    print(f"-> {out} ({out.stat().st_size // 1024} KB), headline {pct}")


if __name__ == "__main__":
    main()
