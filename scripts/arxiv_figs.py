"""Figures for the arXiv paper (vector PDF, white background, colour-blind-safe palette, hatching as a second cue for print).

Every data figure reads the computed result files through scripts.arxiv_data. The two diagrams are drawn here as well so that the whole
paper rebuilds from one command:  python -m scripts.build_arxiv
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from scripts import arxiv_data as D

OUT = D.ROOT / "arxiv" / "figures"
BLUE, VERM, GREEN, GREY, LGREY, INK, ORANGE = "#0072B2", "#D55E00", "#009E73", "#7F7F7F", "#DDDDDD", "#222222", "#E69F00"
plt.rcParams.update({
    "font.family": "DejaVu Serif", "mathtext.fontset": "dejavuserif", "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#555555", "axes.linewidth": 0.8, "pdf.fonttype": 42, "ps.fonttype": 42,
    "figure.dpi": 150, "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
})
PREVIEW: Path | None = None


def save(fig, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf")
    if PREVIEW:
        PREVIEW.mkdir(parents=True, exist_ok=True)
        fig.savefig(PREVIEW / f"{name}.png", dpi=130)
    plt.close(fig)


def grid(ax, axis="y"):
    ax.grid(axis=axis, color="#E6E6E6", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def pct_axis(ax, axis="y", top=1.0):
    from matplotlib.ticker import FuncFormatter
    fmt = FuncFormatter(lambda v, _: f"{v * 100:.0f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)
    (ax.set_ylim if axis == "y" else ax.set_xlim)(0, top)


def fam_label(f):
    return D.FAMILY.get(f, f)


SHORT = {"qwen": "Qwen3\n235B", "qwen35": "Qwen3.5\n397B", "hermes": "Hermes-4\n405B", "nemotron": "Nemotron-3\n120B", "deepseek": "DeepSeek\nV4-Pro",
         "minimax": "MiniMax\nM3", "kimi": "Kimi\nK3", "glm": "GLM\n5.2", "gptoss": "gpt-oss\n120B"}


def fam_short(f):
    return SHORT.get(f, f)


# ---------------------------------------------------------------- diagrams
class _Canvas:
    """Boxes size themselves to their text, so nothing can overflow; arrows run edge to edge between boxes."""

    def __init__(self, w, h, xmax, ymax):
        self.fig, self.ax = plt.subplots(figsize=(w, h))
        self.ax.set_xlim(0, xmax); self.ax.set_ylim(0, ymax); self.ax.axis("off")

    def box(self, cx, cy, text, fc="#FFFFFF", ec=INK, fs=7.8, bold=False, ls="-", color=INK, pad=(0.17, 0.13), lw=1.0, min_w=0.0):
        t = self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", color=color, zorder=3, linespacing=1.3)
        self.fig.canvas.draw()
        bb = t.get_window_extent(self.fig.canvas.get_renderer()).transformed(self.ax.transData.inverted())
        x0, x1 = min(bb.x0 - pad[0], cx - min_w / 2), max(bb.x1 + pad[0], cx + min_w / 2)
        y0, y1 = bb.y0 - pad[1], bb.y1 + pad[1]
        self.ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.07", fc=fc, ec=ec, lw=lw, ls=ls, zorder=2))
        return {"l": (x0, cy), "r": (x1, cy), "t": (cx, y1), "b": (cx, y0), "c": (cx, cy)}

    def link(self, a, sa, b, sb, text=None, color=INK, ls="-", rad=0.0, fs=7.4, dx=0.0, dy=0.07, lw=1.1):
        p0, p1 = a[sa], b[sb]
        self.ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9, lw=lw, color=color, ls=ls, connectionstyle=f"arc3,rad={rad}", zorder=1, shrinkA=1, shrinkB=1))
        if text:
            self.ax.text((p0[0] + p1[0]) / 2 + dx, (p0[1] + p1[1]) / 2 + dy, text, ha="center", va="bottom", fontsize=fs, color=color, zorder=4)

    def note(self, x, y, text, fs=7.4, color=GREY, ha="left", style="italic"):
        self.ax.text(x, y, text, fontsize=fs, color=color, ha=ha, va="center", style=style, linespacing=1.3)


def fig_mechanism():
    """Figure 1: a trap street for a swarm. One shared page, one gateway, one registry, one copied link."""
    c = _Canvas(7.1, 3.6, 11.6, 5.2)
    page = c.box(1.75, 4.3, "shared page, v3,\nwritten by agent A:\n“working link  $L$”", fc="#F4F4F4")
    gate = c.box(5.75, 4.3, "gateway: stamps every\nserved copy of every link", fc="#E8F1F8", ec=BLUE)
    reg = c.box(9.75, 4.3, "registry (private)\n$\\tau_B\\ \\mapsto$ (reader B, page v3,\nauthor A, time $t$)", fc="#FDEFE6", ec=VERM)
    c.link(page, "r", gate, "l"); c.link(gate, "r", reg, "l", "records", dy=0.12, fs=7)
    agb = c.box(1.9, 2.4, "agent B reads the page,\nis served  $L\\,\\|\\,\\tau_B$", fc="#FFFFFF")
    agc = c.box(5.75, 2.4, "agent C copies\nB's link", fc="#FFFFFF")
    out = c.box(9.75, 2.4, "C's output (or edit)\ncontains  $L\\,\\|\\,\\tau_B$", fc="#FFFFFF")
    c.link(gate, "b", agb, "t", "serves", color=BLUE, dx=-0.7, dy=0.06); c.link(agb, "r", agc, "l"); c.link(agc, "r", out, "l")
    res = c.box(8.1, 0.62, "resolve$(\\tau_B)$: C was exposed to A's copy of $L$ through B's read,\nat time $t$. Exact, not inferred.", fc="#FDEFE6", ec=VERM)
    c.link(out, "b", res, "t", color=VERM)
    c.link(reg, "b", out, "t", color=VERM, ls="--", text="lookup", dx=0.55, dy=-0.12, fs=7)
    c.note(0.15, 0.78, "decoration is not enough: the\nmirror must need $\\tau_B$\nfor the link to work", fs=7)
    save(c.fig, "fig_mechanism")


def fig_architecture():
    """Figure 2: components and data flow."""
    c = _Canvas(7.1, 4.1, 14.6, 7.4)
    sw = c.box(1.4, 4.5, "agent swarm\n(LLM agents)", fc="#F4F4F4", bold=True)
    gw = c.box(4.7, 6.2, "gateway\nstamp · registry", fc="#E8F1F8", ec=BLUE, bold=True)
    ar = c.box(4.7, 4.5, "shared artifacts\nwiki · notes · memory", fc="#F4F4F4")
    tl = c.box(4.7, 2.8, "tools and mirrors\n(accept only tokens)", fc="#F4F4F4")
    c.link(sw, "t", gw, "l", rad=-0.25); c.link(gw, "b", ar, "t"); c.link(sw, "r", ar, "l"); c.link(sw, "b", tl, "l", rad=0.25)
    rl = c.box(8.4, 5.95, "read log (optional)\nregistry of tokens", fc="#FFFFFF", ls="--")
    el = c.box(8.4, 4.15, "edit log\n(writes, outputs)", fc="#FFFFFF")
    c.link(gw, "r", rl, "l", color=BLUE); c.link(ar, "r", el, "l")
    au = c.box(12.0, 5.05, "audit: calibrated\ncopy detection,\nread-linking, grade", fc="#FDEFE6", ec=VERM, bold=True)
    c.link(rl, "r", au, "t", rad=-0.2); c.link(el, "r", au, "b", rad=0.2)
    tg = c.box(12.0, 3.2, "trace graph:\nedges with evidence tier", fc="#FFFFFF")
    ot = c.box(12.0, 1.9, "attribution of each output;\nre-check list (downstream)", fc="#FFFFFF")
    c.link(au, "b", tg, "t"); c.link(tg, "b", ot, "t")
    vw = c.box(6.9, 1.9, "viewer: ants, trails,\nclick to trace (local)", fc="#FFFFFF", ls="--")
    c.link(ot, "l", vw, "r", ls="--")
    bh = c.box(4.6, 0.55, "benchmark harness: swarm in a sandbox\n→ hidden read log (answer key) → scorer.\nA tracer sees only the edit log (plus tokens, on the token track).",
               fc="#EFEFEF", ec=GREY, fs=6.9)
    c.link(ot, "b", bh, "r", ls="--", color=GREY, rad=0.15, text="scored against", dx=0.0, dy=-0.38)
    c.note(0.15, 2.0, "dashed = optional", fs=7)
    save(c.fig, "fig_architecture")


# ---------------------------------------------------------------- data figures
def fig_visibility():
    """Figure 3: how much of copying is traceable, by what was logged (a), and week by week in the whole AI Village chat (b)."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.1, 2.65), gridspec_kw={"width_ratios": [1.0, 1.55]})
    av = D.AV
    labels = ["real incident,\nreads not\nlogged", "AI Village,\nroom-scoped\nchat", "AI Village,\none shared\nchat"]
    vals = [0.162, av["room_scoped"]["rate"], av["pre_rooms"]["rate"]]
    a.bar(range(3), vals, color=[VERM, BLUE, BLUE], hatch=["//", "", ""], edgecolor="white", width=0.62, zorder=3)
    a.bar([0], [0.20 - 0.162], bottom=[0.162], color=VERM, alpha=0.35, hatch="//", edgecolor="white", width=0.62, zorder=3)
    for i, (v, t) in enumerate(zip(vals, ["16--20%", f"{vals[1] * 100:.0f}%", f"{vals[2] * 100:.0f}%"])):
        a.text(i, max(v, 0.2) + 0.025, t.replace("--", "–"), ha="center", fontsize=8.5)
    a.set_xticks(range(3)); a.set_xticklabels(labels, fontsize=7.3); pct_axis(a, top=1.12); grid(a)
    a.set_ylabel("copies whose source is visible\nin the log"); a.set_title("(a) by what was logged", loc="left")
    ws = [w for w in av["windows"] if w["adoptions"] >= av["min_adoptions_for_spread"]]
    for rooms, col, lab in ((False, BLUE, "one shared chat"), (True, VERM, "room-scoped chat")):
        pts = [(dt.date.fromisoformat(w["start"]), w["covered"] / w["adoptions"]) for w in ws if w["rooms"] == rooms]
        b.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color=col, ms=2.6, lw=0.9, label=lab, zorder=3)
    cut = dt.date.fromisoformat(av["rooms_cutover"]); b.axvline(cut, color=GREY, ls="--", lw=0.9)
    b.text(cut - dt.timedelta(days=9), 0.915, "rooms launched", fontsize=7.4, color=GREY, va="center", ha="center", rotation=90)
    lo = min(ws, key=lambda w: w["covered"] / w["adoptions"]); lo_v = lo["covered"] / lo["adoptions"]
    b.annotate(f"lowest week {lo_v * 100:.0f}%", (dt.date.fromisoformat(lo["start"]), lo_v), (dt.date.fromisoformat(lo["start"]) + dt.timedelta(days=55), 0.865), fontsize=7.6,
               arrowprops=dict(arrowstyle="-", color=GREY, lw=0.7))
    b.set_ylim(0.82, 1.015); b.set_yticks([0.85, 0.9, 0.95, 1.0]); b.set_yticklabels(["85%", "90%", "95%", "100%"]); grid(b)
    b.set_title(f"(b) every week of the whole chat ({av['messages']:,} agent messages)", loc="left", fontsize=8.6)
    b.legend(loc="lower left", frameon=False, fontsize=7.6, bbox_to_anchor=(0.0, 0.06))
    import matplotlib.dates as mdates
    b.xaxis.set_major_formatter(mdates.DateFormatter("%b %y")); b.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_visibility")


def fig_calibration():
    """Figure 4: the coincidence trap on real logs (a), and the false-copy share under monoculture, naive vs calibrated (b)."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.1, 2.55), gridspec_kw={"width_ratios": [1.15, 1.0]})
    c, x = D.R["coincidence"], D.R["cross_team"]
    rows = [("copy calls", c["naive_calls"], c["supported_calls"]), ("cross-team\ncollusion jumps", x["naive"], x["verified"])]
    for i, (lab, n, k) in enumerate(rows):
        y = 1 - i
        a.barh(y, k / n, color=BLUE, height=0.5, zorder=3); a.barh(y, 1 - k / n, left=k / n, color=LGREY, hatch="//", edgecolor="white", height=0.5, zorder=3)
        a.text(k / n / 2, y, f"{k:,}", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        a.text(k / n + (1 - k / n) / 2, y, f"{n - k:,} declined", ha="center", va="center", fontsize=8)
        a.text(1.02, y, f"of {n:,} flagged", va="center", fontsize=8)
    a.set_yticks([1, 0]); a.set_yticklabels([r[0] for r in rows], fontsize=8); a.set_xlim(0, 1.3); a.set_ylim(-0.6, 1.6)
    a.set_xticks([0, 0.25, 0.5, 0.75, 1.0]); a.set_xticklabels(["0", "25%", "50%", "75%", "100%"]); a.set_xlabel("share of flagged matches"); grid(a, "x")
    a.set_title("(a) real incident: matches that survive calibration", loc="left", fontsize=8.6)
    z = np.array([r[0] for r in D.SIM_RESCUE]); naive = np.array([r[1] for r in D.SIM_RESCUE]); cal = np.array([r[2] for r in D.SIM_RESCUE])
    b.plot(z, naive, "s-", color=VERM, label="naive: any matching value", ms=4, zorder=3); b.plot(z, cal, "o-", color=BLUE, label=r"calibrated ($\tau=10$)", ms=4, zorder=3)
    b.axhline(0.1, color=GREY, ls="--", lw=0.9); b.text(2.0, 0.112, r"bound $1/\tau$ (Prop. 4)", fontsize=7.6, color=GREY, ha="right")
    b.set_xlabel("monoculture of ‘random’ picks\n(Zipf exponent)"); b.set_ylabel("independent agents\nfalsely called copiers"); pct_axis(b, top=0.7); grid(b)
    b.legend(frameon=False, loc="upper left", fontsize=7.6); b.set_title("(b) simulator, 2,342 repeat events", loc="left", fontsize=8.6)
    fig.tight_layout(w_pad=1.3)
    save(fig, "fig_calibration")


def fig_simulator():
    """Figure 5: the theory against a simulator with a known answer: tracers against the Bayes ceiling (a), tag survival against its ceiling (b)."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.1, 2.8), gridspec_kw={"width_ratios": [1.35, 1.0]})
    names = list(D.SIM_COPY); w = 0.17
    series = [("earliest", 1, GREY, ""), ("latest", 2, LGREY, "//"), ("heuristic", 4, ORANGE, "\\\\"), ("model-based", 5, BLUE, "")]
    for k, (lab, idx, col, hatch) in enumerate(series):
        a.bar(np.arange(3) + (k - 1.5) * w, [D.SIM_COPY[n][idx] for n in names], w, color=col, hatch=hatch, edgecolor="white", label=lab, zorder=3)
    for i, n in enumerate(names):
        a.plot([i - 2.1 * w, i + 2.1 * w], [D.SIM_COPY[n][0]] * 2, color=INK, lw=1.6, zorder=4, label="Bayes ceiling" if i == 0 else None)
    a.set_xticks(range(3)); a.set_xticklabels(names); pct_axis(a, top=0.9); grid(a); a.set_ylabel("top-1: source named correctly")
    a.legend(frameon=False, ncol=5, fontsize=6.9, loc="upper center", bbox_to_anchor=(0.5, -0.12), handlelength=1.3, columnspacing=0.8)
    a.set_title("(a) tracers against the ceiling", loc="left")
    s = np.array(D.SIM_TAGS["s"]); ss = np.linspace(0, 1, 50); c0 = D.SIM_TAGS["C0"]
    b.plot(ss, ss + (1 - ss) * c0, "--", color=INK, lw=1, label=r"$s+(1-s)C_0$ (Prop. 3)", zorder=2)
    b.plot(s, D.SIM_TAGS["ceiling"], "o", color=BLUE, ms=5, label="Bayes ceiling", zorder=3); b.plot(s, D.SIM_TAGS["tracer"], "x", color=VERM, ms=6, mew=1.5, label="model-based tracer", zorder=3)
    b.plot([0.1, 0.9], D.SIM_TAGS["static"], "-", color=GREY, lw=1.3, label="one tag per origin"); b.plot(s, D.SIM_TAGS["page"], "-", color=GREEN, lw=1.3, label="one tag per page")
    b.set_xlabel("tag survival $s$"); pct_axis(b, top=1.0); b.set_xlim(0, 1); grid(b); b.set_xticks([0, 0.25, 0.5, 0.75, 1.0]); b.set_xticklabels(["0", "25%", "50%", "75%", "100%"])
    b.legend(frameon=False, fontsize=7, loc="lower right"); b.set_title("(b) what a tag is worth", loc="left")
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_simulator")


def _families(by, key_a, key_b, min_den_a=10, min_den_b=0, order=None):
    fams = [f for f in (order or D.FAMILY) if f in by and (by[f][key_a].get("den", 0) or 0) >= min_den_a and by[f][key_a].get("rate") is not None]
    return fams


def fig_survival():
    """Figure 6: does the token survive copying? By model, decoration against a token the link needs."""
    h1 = D.LAB["H1"]["by_family"]
    fams = [f for f in D.FAMILY if f in h1 and (h1[f]["loadbearing"].get("den") or 0) >= 10]
    fams.sort(key=lambda f: -(h1[f]["loadbearing"]["rate"] or 0))
    fig, ax = plt.subplots(figsize=(7.1, 2.6)); w = 0.38; xs = np.arange(len(fams))
    for k, (key, col, hatch, lab) in enumerate((("inert", BLUE, "", "decoration (inert tag)"), ("loadbearing", VERM, "//", "token the link needs"))):
        vals, lo, hi = [], [], []
        for f in fams:
            e = D.err(h1[f][key]) if (h1[f][key].get("den") or 0) >= 10 else None
            vals.append(e[0] if e else np.nan); lo.append(e[1] if e else 0); hi.append(e[2] if e else 0)
        ax.bar(xs + (k - 0.5) * w, vals, w, yerr=[lo, hi], color=col, hatch=hatch, edgecolor="white", error_kw=dict(lw=0.9, capsize=2, ecolor="#444444"), label=lab, zorder=3)
        for x, v in zip(xs, vals):
            if not np.isnan(v):
                ax.text(x + (k - 0.5) * w, min(v + 0.07, 1.05), f"{v * 100:.0f}", ha="center", fontsize=7.2)
    ax.axhline(0.9, color=GREY, ls=":", lw=0.9); ax.text(len(fams) - 0.5, 0.915, "H1 threshold for the token (90%)", ha="right", fontsize=7, color=GREY)
    ax.set_xticks(xs); ax.set_xticklabels([f"{fam_short(f)}\n(n={h1[f]['loadbearing']['den']:,})" for f in fams], fontsize=7.2); pct_axis(ax, top=1.18); ax.set_yticks([0, .25, .5, .75, 1.0])
    ax.set_ylabel("copies that kept the tag"); grid(ax); ax.legend(frameon=False, ncol=2, loc="upper right", fontsize=8, bbox_to_anchor=(1.0, 1.12))
    fig.tight_layout(); save(fig, "fig_survival")


def fig_attribution():
    """Figure 7: how often the immediate source is named correctly, best simple edit-log rule against codes (with that rule as the fallback)."""
    h2 = D.LAB["H2"]["by_family"]
    fams = [f for f in D.FAMILY if f in h2 and (h2[f]["with_tags"].get("den") or 0) >= 20]
    fams.sort(key=lambda f: -(h2[f]["lift_points"]["rate"] or 0))
    fig, ax = plt.subplots(figsize=(7.1, 2.7)); w = 0.38; xs = np.arange(len(fams))
    for k, (key, col, hatch, lab) in enumerate((("edit_log_only", BLUE, "", "best simple edit-log rule"), ("with_tags", VERM, "//", "codes where they survived, else that rule"))):
        e = [D.err(h2[f][key]) for f in fams]
        ax.bar(xs + (k - 0.5) * w, [v[0] for v in e], w, yerr=[[v[1] for v in e], [v[2] for v in e]], color=col, hatch=hatch, edgecolor="white", error_kw=dict(lw=0.9, capsize=2, ecolor="#444444"), label=lab, zorder=3)
    for x, f in zip(xs, fams):
        lift = h2[f]["lift_points"]["rate"] * 100
        ax.text(x, 1.10, f"{lift:+.0f} pts", ha="center", fontsize=7.8, fontweight="bold", color=VERM if lift >= 10 else GREY)
    ax.set_xticks(xs); ax.set_xticklabels([fam_short(f) for f in fams], fontsize=7.4); pct_axis(ax, top=1.2); ax.set_yticks([0, .25, .5, .75, 1.0])
    ax.set_ylabel("immediate source named correctly"); grid(ax); ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0.0, 1.02), fontsize=7.8)
    ax.text(-0.62, 1.10, "lift:", ha="right", fontsize=7.4, color=GREY, style="italic")
    fig.tight_layout(); save(fig, "fig_attribution")


def fig_benchmark():
    """Figure 8: the benchmark baselines: sources named (a) and agents falsely accused (b)."""
    m = D.BASE["methods"]
    order = [("uniform", "random\nwriter"), ("latest", "latest\nwriter"), ("earliest", "earliest\nwriter"), ("conservative", "only if\nunambig."), ("tags", "tokens\n+ fallback")]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.1, 2.55)); xs = np.arange(len(order))
    cols = [GREY, GREY, GREY, GREY, VERM]; hatches = ["", "", "", "", "//"]
    for ax, key, title, ylab in ((a, "top1", "(a) source named correctly", "copying agents"), (b, "false_accusation", "(b) agents accused of copying who worked alone", "agents that worked alone")):
        e = [D.err(m[k][key]) for k, _ in order]
        ax.bar(xs, [v[0] for v in e], 0.62, yerr=[[v[1] for v in e], [v[2] for v in e]], color=cols, hatch=hatches, edgecolor="white", error_kw=dict(lw=0.9, capsize=2, ecolor="#444444"), zorder=3)
        for x, v in zip(xs, e):
            ax.text(x, min(v[0] + v[2] + 0.04, 1.08), f"{v[0] * 100:.0f}%", ha="center", fontsize=8)
        ax.set_xticks(xs); ax.set_xticklabels([n for _, n in order], fontsize=7.4); pct_axis(ax, top=1.14); ax.set_yticks([0, .25, .5, .75, 1.0]); grid(ax); ax.set_title(title, loc="left", fontsize=8.6)
    fig.tight_layout(w_pad=1.2); save(fig, "fig_benchmark")


def fig_gated():
    """Figure 9: closing the way around the token: the share of outputs that carry a token naming the copy they came from."""
    g = {f: v for f, v in D.LAB["gated"].items() if v.get("W4") and v.get("W4G")}
    fams = sorted(g, key=lambda f: g[f]["W4"]["traceable"]["rate"])
    fig, ax = plt.subplots(figsize=(7.1, 2.4)); w = 0.38; xs = np.arange(len(fams))
    for k, (key, col, hatch, lab) in enumerate((("W4", BLUE, "", "mirror hands a session to anyone"), ("W4G", VERM, "//", "sessions only through wiki links (gated)"))):
        e = [D.err(g[f][key]["traceable"]) for f in fams]
        ax.bar(xs + (k - 0.5) * w, [v[0] for v in e], w, yerr=[[v[1] for v in e], [v[2] for v in e]], color=col, hatch=hatch, edgecolor="white", error_kw=dict(lw=0.9, capsize=2, ecolor="#444444"), label=lab, zorder=3)
        for x, v in zip(xs, e):
            ax.text(x + (k - 0.5) * w, min(v[0] + v[2] + 0.04, 1.08), f"{v[0] * 100:.0f}", ha="center", fontsize=7.4)
    for x, f in zip(xs, fams):
        ax.text(x, -0.30, f"done {g[f]['W4']['completed']['rate'] * 100:.0f}→{g[f]['W4G']['completed']['rate'] * 100:.0f}%", ha="center", fontsize=6.9, color=GREY, transform=ax.get_xaxis_transform())
    ax.set_xticks(xs); ax.set_xticklabels([fam_short(f).replace("\n", " ") for f in fams], fontsize=7.6); pct_axis(ax, top=1.2); ax.set_yticks([0, .25, .5, .75, 1.0]); grid(ax)
    ax.set_ylabel("outputs with a\ntraceable token"); ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0.0, 1.0), fontsize=7.8)
    fig.tight_layout(); save(fig, "fig_gated")


def fig_cleanup():
    """Figure 10: what an operator has to re-check after a bad tip, by how the list was made."""
    fig, ax = plt.subplots(figsize=(7.1, 2.65))
    rows = [("everyone", "re-run everything"), ("after_tip", "everything submitted after\nthe tip appeared"), ("earliest", "follow the earliest\nvisible writer"), ("tags+backup", "follow the tokens\n(earliest writer where lost)"), ("tags", "follow the tokens only")]
    scen = [("W2 tags", "tip arrives mid-run", BLUE, ""), ("W2E tags", "tip is there from the start", VERM, "//")]
    h = 0.36; ys = np.arange(len(rows))[::-1]
    for k, (key, lab, col, hatch) in enumerate(scen):
        for y, (m, _) in zip(ys, rows):
            e = D.err(D.CLEAN[key]["methods"][m]["flagged_share"])
            ax.barh(y + (0.5 - k) * h, e[0], h, xerr=[[e[1]], [e[2]]], color=col, hatch=hatch, edgecolor="white", error_kw=dict(lw=0.8, capsize=2, ecolor="#444444"), label=lab if y == ys[0] else None, zorder=3)
            ax.text(min(e[0] + e[2] + 0.025, 1.08), y + (0.5 - k) * h, f"{e[0] * 100:.0f}%", va="center", fontsize=7.6)
    ax.set_yticks(ys); ax.set_yticklabels([r[1] for r in rows], fontsize=7.6); pct_axis(ax, "x", top=1.2); ax.set_xticks([0, .25, .5, .75, 1.0]); ax.set_xlabel("share of outputs to re-check (lower is less work)")
    grid(ax, "x"); ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0.0, 1.0), fontsize=7.8)
    fig.tight_layout(); save(fig, "fig_cleanup")


def fig_tip():
    """Figure 11: does a planted bad tip take hold? Late tip against a tip that is there from the start, by model."""
    late, early = D.LAB["rumor_by_family"], D.LAB["early_rumor_by_family"]
    fams = [f for f in D.FAMILY if f in early and early[f].get("rate") is not None]
    fams.sort(key=lambda f: -early[f]["rate"])
    fig, ax = plt.subplots(figsize=(7.1, 2.5)); w = 0.38; xs = np.arange(len(fams))
    for k, (src, col, hatch, lab) in enumerate(((late, BLUE, "", "tip arrives mid-run"), (early, VERM, "//", "tip is there from the start"))):
        e = [D.err(src.get(f)) or (0, 0, 0) for f in fams]
        ax.bar(xs + (k - 0.5) * w, [v[0] for v in e], w, yerr=[[v[1] for v in e], [v[2] for v in e]], color=col, hatch=hatch, edgecolor="white", error_kw=dict(lw=0.9, capsize=2, ecolor="#444444"), label=lab, zorder=3)
        for x, v in zip(xs, e):
            ax.text(x + (k - 0.5) * w, min(v[0] + v[2] + 0.04, 1.06), f"{v[0] * 100:.0f}", ha="center", fontsize=7.2)
    ax.set_xticks(xs); ax.set_xticklabels([fam_short(f) for f in fams], fontsize=7.4); pct_axis(ax, top=1.18); ax.set_yticks([0, .25, .5, .75, 1.0]); grid(ax)
    ax.set_ylabel("outputs carrying the bad value"); ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0.0, 1.0), fontsize=7.8)
    fig.tight_layout(); save(fig, "fig_tip")


ALL = [fig_mechanism, fig_architecture, fig_visibility, fig_calibration, fig_simulator, fig_survival, fig_attribution, fig_benchmark, fig_gated, fig_cleanup, fig_tip]


def build(preview: Path | None = None) -> list[str]:
    global PREVIEW
    PREVIEW = preview
    for f in ALL:
        f()
    return [f.__name__.replace("fig_", "fig_") for f in ALL]
