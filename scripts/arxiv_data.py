"""Everything the arXiv paper reports, loaded from the computed result files (never typed into the text).

Sources: frontend/data/results.json (written by scripts.build_site_data), bench_release/baselines.json, data/lab/cleanup_savings.json,
data/out/ai_village_full.json, experiments/lab/grid.py (the model roster), and the simulator tables in docs/RESULTS.md (A, E, H),
transcribed below because the simulator sweep is slow to re-run (python -m backend.bench.run --seeds 12 regenerates them).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _j(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8-sig"))


R = _j("frontend/data/results.json")
LAB = R["lab"]
BASE = _j("bench_release/baselines.json")
CLEAN = _j("data/lab/cleanup_savings.json")
AV = _j("data/out/ai_village_full.json")
DESIGN = R["design"]

# display names, in the order a reader should meet them (copy-verbatim models first)
FAMILY = {"qwen": "Qwen3-235B", "qwen35": "Qwen3.5-397B", "hermes": "Hermes-4-405B", "nemotron": "Nemotron-3-120B", "deepseek": "DeepSeek-V4-Pro",
          "minimax": "MiniMax-M3", "kimi": "Kimi-K3", "glm": "GLM-5.2", "gptoss": "gpt-oss-120B"}

# --- simulator (docs/RESULTS.md section A, E, H): 12 seeds per cell, about 3,400 adoptions per cell, 25% of reads off the page
SIM_COPY = {   # copy model -> Bayes ceiling, earliest, latest, most-similar, heuristic tracer, model-based tracer (EM)
    "uniform": (0.460, 0.162, 0.152, 0.356, 0.372, 0.458),
    "recency-biased": (0.799, 0.098, 0.382, 0.533, 0.538, 0.796),
    "popularity-biased": (0.538, 0.260, 0.117, 0.250, 0.260, 0.511),
}
SIM_TAGS = {   # tag survival s -> Bayes ceiling, formula s+(1-s)C0, model-based tracer;  C0 = 0.460
    "s": (0.10, 0.33, 0.60, 0.90), "ceiling": (0.522, 0.640, 0.781, 0.945), "formula": (0.514, 0.638, 0.784, 0.946), "tracer": (0.517, 0.647, 0.776, 0.944),
    "static": (0.466, 0.474), "page": (0.477, 0.504, 0.531, 0.562), "C0": 0.460,
}
SIM_ROBUST = [   # copy rule, off-page share, Bayes ceiling, heuristic tracer, model-based tracer
    ("uniform", 0.25, 0.460, 0.372, 0.458), ("uniform", 0.85, 0.324, 0.117, 0.326), ("recency", 0.25, 0.799, 0.538, 0.796), ("recency", 0.85, 0.726, 0.126, 0.720),
    ("homophily*", 0.25, 0.499, 0.386, 0.459), ("homophily*", 0.85, 0.341, 0.127, 0.300), ("hard window*", 0.25, 0.667, 0.488, 0.643), ("hard window*", 0.85, 0.544, 0.133, 0.501),
]
SIM_RESCUE = [(0.0, 0.116, 0.068), (1.0, 0.263, 0.038), (1.5, 0.457, 0.014), (2.0, 0.648, 0.010)]   # zipf exponent of 'random' picks -> naive vs calibrated false-copy share (RESULTS I)


def model_roster() -> dict:
    from experiments.lab.grid import ROSTER
    return dict(ROSTER)


def pc(x, d=0):
    return "n/a" if x is None else f"{x * 100:.{d}f}\\%"


def ci(d, dec=0, stack=False):
    """'71% [63--77]' from {rate, lo, hi} or {value, ci95}. An interval that rounds to a single point is left out (the value did not vary
    across runs). stack=True puts the interval under the value in small type, for fixed-width (p) columns."""
    if d is None:
        return "n/a"
    if "value" in d:
        v, lo, hi = d["value"], d["ci95"][0], d["ci95"][1]
    else:
        if d.get("rate") is None:
            return "n/a"
        v, lo, hi = d["rate"], d["lo"], d["hi"]
    sv, sl, sh = (f"{x * 100:.{dec}f}" for x in (v, lo, hi))
    if sl == sh == sv:
        return f"{sv}\\%"
    return f"{sv}\\%\\newline{{\\scriptsize[{sl}--{sh}]}}" if stack else f"{sv}\\% [{sl}--{sh}]"


def err(d):
    """(value, lower error, upper error) for matplotlib; accepts {rate, lo, hi} or {value, ci95}."""
    if d is None:
        return None
    if "value" in d:
        v, lo, hi = d["value"], d["ci95"][0], d["ci95"][1]
    else:
        if d.get("rate") is None:
            return None
        v, lo, hi = d["rate"], d["lo"], d["hi"]
    return v, max(0.0, v - lo), max(0.0, hi - v)
