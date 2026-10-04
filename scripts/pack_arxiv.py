"""Compile the arXiv paper, check that the upload bundle builds on its own, and write the zip to upload.

  python -m scripts.pack_arxiv

Needs a TeX engine: the portable Tectonic in tools/tectonic (see arxiv/README.md) or `tectonic` on PATH.
Steps: rebuild nothing (run scripts.build_arxiv first if results changed); compile arxiv/main.tex keeping main.bbl;
copy only what arXiv needs into a temp folder; compile it there from scratch; write arxiv/dist/trap-streets-arxiv.zip.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARX = ROOT / "arxiv"
DIST = ARX / "dist"
ZIP = DIST / "trap-streets-arxiv.zip"
TOP = ["main.tex", "numbers.tex", "main.bbl", "refs.bib"]
FOLDERS = [("sections", "*.tex"), ("tables", "*.tex"), ("figures", "*.pdf")]


def engine() -> str:
    for c in (ROOT / "tools" / "tectonic" / "tectonic.exe", ROOT / "tools" / "tectonic" / "tectonic"):
        if c.exists():
            return str(c)
    found = shutil.which("tectonic")
    if found:
        return found
    sys.exit("No TeX engine found. Put Tectonic in tools/tectonic or on PATH (see arxiv/README.md).")


def compile_in(folder: Path, keep: bool) -> tuple[int, str]:
    cmd = [engine(), "--keep-logs"] + (["--keep-intermediates"] if keep else []) + ["main.tex"]
    r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def warnings(out: str) -> list[str]:
    keep = ("Overfull", "undefined", "Undefined", "Citation", "Missing", "Emergency stop", "error")
    return sorted({l.strip() for l in out.splitlines() if l.startswith(("warning", "error")) and any(k in l for k in keep)})


def main() -> int:
    code, out = compile_in(ARX, keep=True)
    if code != 0 or not (ARX / "main.bbl").exists():
        print(out[-3000:])
        return 1
    files = [ARX / f for f in TOP]
    for folder, pat in FOLDERS:
        files += sorted((ARX / folder).glob(pat))
    missing = [f for f in files if not f.exists()]
    if missing:
        print("missing:", *[f.relative_to(ARX) for f in missing], sep="\n  ")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for f in files:
            dst = tmp / f.relative_to(ARX)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
        code2, out2 = compile_in(tmp, keep=False)
        if code2 != 0 or not (tmp / "main.pdf").exists():
            print("The bundle does not compile on its own:\n", out2[-3000:])
            return 1
        pages = next((l for l in (tmp / "main.log").read_text(errors="ignore").splitlines() if l.startswith("Output written")), "") if (tmp / "main.log").exists() else ""
    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(ARX).as_posix())
    print(f"{ZIP.relative_to(ROOT)}: {len(files)} files, {ZIP.stat().st_size / 1024:.0f} KiB; clean compile OK {pages}")
    for w in warnings(out2):
        print("  ", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
