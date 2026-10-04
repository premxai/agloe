"""LaTeX tables (booktabs) and number macros for the arXiv paper, all computed from the result files via scripts.arxiv_data.

The prose in arxiv/main.tex refers to numbers only through the macros written to arxiv/numbers.tex, so a re-run of the lab or the analysis
updates the paper everywhere at once.
"""
from __future__ import annotations

from pathlib import Path

from scripts import arxiv_data as D
from scripts.arxiv_data import ci, pc

OUT = D.ROOT / "arxiv"
FAM_ORDER = ["qwen", "qwen35", "hermes", "nemotron", "deepseek", "minimax", "kimi", "glm", "gptoss"]
NAME = D.FAMILY
TAGW = {"none": "none", "inert": "inert", "loadbearing": "load-bearing"}


def tex_escape(s: str) -> str:
    return s.replace("_", r"\_").replace("&", r"\&").replace("#", r"\#")


def texquote(s: str) -> str:
    """'word' -> ``word'' (LaTeX quotes), after escaping."""
    import re
    return re.sub(r"'([^']+)'", r"``\1''", tex_escape(s))


def signed(x: float) -> str:
    return f"{x:+.0f}".replace("-", "$-$")


NOBRACKET = "A value without an interval did not vary across runs."


def cs(d, dec=0) -> str:
    """Value with its interval stacked underneath (for fixed-width columns)."""
    return ci(d, dec, stack=True)


def table(name: str, head: list[str], rows: list[list[str]], align: str, caption: str, label: str, note: str = "", small: bool = True, star: bool = False,
          size: str = "", sep: int = 0) -> None:
    """Row markers: ["---"] is a rule, ["~"] a small gap. size overrides the font size (e.g. \\footnotesize); sep sets the column padding in pt."""
    env = "table*" if star else "table"
    lines = [f"\\begin{{{env}}}[t]", "\\centering", size or ("\\small" if small else ""), f"\\setlength{{\\tabcolsep}}{{{sep}pt}}" if sep else "",
             f"\\caption{{{caption}}}\\label{{{label}}}", f"\\begin{{tabular}}{{{align}}}", "\\toprule", " & ".join(head) + " \\\\", "\\midrule"]
    for r in rows:
        lines.append("\\midrule" if r == ["---"] else "\\addlinespace[3pt]" if r == ["~"] else " & ".join(r) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    if note:
        lines += [f"\\par\\smallskip\\parbox{{0.96\\linewidth}}{{\\footnotesize {note}}}"]
    lines += [f"\\end{{{env}}}", ""]
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    (OUT / "tables" / f"{name}.tex").write_text("\n".join(l for l in lines if l != ""), encoding="utf-8")


def n(x) -> str:
    return f"{x:,}".replace(",", "{,}")


# ---------------------------------------------------------------- tables
def t_real():
    av, inc, co, ct = D.AV, D.R["incident"], D.R["coincidence"], D.R["cross_team"]
    rows = [
        ["Incident", f"adopters analysed ({inc['behaviors']} behaviours, $\\geq$20 adopters each)", n(inc["adopters"])],
        ["Incident", "adopters with no visible carrier", pc(inc["no_carrier"])],
        ["Incident", "best possible top-1 source accuracy from the edit log", pc(inc["best_top1"], 1)],
        ["Incident", "naive ``same string'' copy calls $\\to$ calls that survive calibration", f"{n(co['naive_calls'])} $\\to$ {n(co['supported_calls'])}"],
        ["Incident", "cross-team collusion jumps flagged $\\to$ verified by hand", f"{ct['naive']} $\\to$ {ct['verified']}"],
        ["AI Village, one chat", f"copies with a visible source ({av['pre_rooms']['windows']} weekly windows, {n(av['pre_rooms']['adoptions'])} copies)", pc(av["pre_rooms"]["rate"], 1)],
        ["AI Village, rooms", f"copies with a visible source ({av['room_scoped']['windows']} weekly windows, {n(av['room_scoped']['adoptions'])} copies)",
         f"{pc(av['room_scoped']['rate'], 1)} [{av['room_scoped']['ci95'][0] * 100:.1f}--{av['room_scoped']['ci95'][1] * 100:.1f}]"],
        ["AI Village, rooms", "weekly coverage: lowest / median / highest", f"{pc(av['room_scoped']['window_min'], 1)} / {pc(av['room_scoped']['window_median'], 1)} / {pc(av['room_scoped']['window_max'], 0)}"],
    ]
    table("tab_real", ["Log", "Measurement", "Result"], rows, "@{}lp{8.2cm}r@{}", "Results on two real logs. The incident is a shared wiki edited by AI agents; AI Village is a long-running multi-agent environment with a shared chat.",
          "tab:real", "Intervals are 95\\% Wilson intervals. Coverage in AI Village is the share of copy events whose earlier author is visible in the log where the copy happened (Section~\\ref{sec:setup}).")


def t_design():
    rows = []
    for w in D.DESIGN["worlds"]:
        fam = f"{len(w['families'])} models" if len(w["families"]) > 3 else ", ".join(w["families"])
        rows.append([w["world"], texquote(w["what"]), fam, "/\\allowbreak ".join(TAGW[c] for c in w["conds"]), ", ".join(map(str, w["sizes"])), n(w["cells"]), n(w["agent_runs"])])
    rows.append(["---"]); t = D.DESIGN["totals"]
    rows.append(["All", "", "", "", "", n(t["cells"]), n(t["agent_runs"])])
    table("tab_design", ["World", "What it is", "Models", "Tags", "Size", "Runs", "Agent runs"], rows, "@{}lL{4.6cm}lL{2.0cm}lrr@{}",
          "The offline lab as it was run (read from the run records). A run is one swarm; ``size'' is agents per swarm.", "tab:design",
          f"{D.DESIGN['smoke_runs_excluded']} connectivity checks are not counted. Three flawed bad-tip designs were set aside (Section~\\ref{{sec:problems}}); the run records of {D.DESIGN['flawed_designs_set_aside']} of them are kept with the data.",
          star=True, size="\\footnotesize", sep=4)


def t_hyp():
    L = D.LAB
    h1, h2 = L["H1"], L["H2"]["by_family"]
    fams = [f for f, v in h2.items() if (v["with_tags"].get("den") or 0) >= 20 and v["lift_points"]["rate"] is not None]
    h2n = sum(1 for f in fams if h2[f]["lift_points"]["rate"] >= 0.10)
    tested = [v for v in h1["by_family"].values() if (v["loadbearing"].get("den") or 0) >= 10 and (v["inert"].get("den") or 0) >= 10]
    lb = sum(1 for v in tested if v["loadbearing"]["rate"] >= 0.9); ine = sum(1 for v in tested if v["inert"]["rate"] > 0.1)
    w2, w2e = L["H4"]["W2|loadbearing"]["contaminated_attribution_with_tags"]["rate"], L["H4"]["W2E|loadbearing"]["contaminated_attribution_with_tags"]["rate"]
    rows = [
        ["H1", "Load-bearing tokens survive copying in $\\geq$90\\% of copies, inert tags in $\\leq$10\\%.", f"Not met. {h1['families_passing']} of {h1['families_tested']} families met both halves: {lb} kept the token in $\\geq$90\\%, but inert tags survived more than 10\\% in {ine}."],
        ["H2", "Tokens beat the best simple edit-log rule by $\\geq$10 points.", f"{h2n} of {len(fams)} families (lift from {signed(min(h2[f]['lift_points']['rate'] for f in fams) * 100)} to {signed(max(h2[f]['lift_points']['rate'] for f in fams) * 100)} points), in proportion to token survival."],
        ["H3", "Agents of one family pick the same ``random'' value more often than agents of different families.", f"Not supported: {D.LAB['H3']['mean_within']:.2f} within vs {D.LAB['H3']['mean_cross']:.2f} across families."],
        ["H4", "Tokens name the source of $\\geq$80\\% of the bad outputs.", f"Supported where tokens survive: {pc(w2)} (late tip), {pc(w2e)} (early tip)."],
        ["H5", "The audit's predicted ceiling is within 0.10 of the measured accuracy.", "Dropped, as stated in advance: lab swarms share no distinctive strings, so the audit reports N/A on them."],
    ]
    table("tab_hyp", ["", "Stated before the runs", "What happened"], rows, "@{}lp{5.4cm}p{7.6cm}@{}", "Hypotheses fixed before the lab runs, and their outcomes.", "tab:hyp", star=True)


def t_bench():
    m = D.BASE["methods"]
    order = [("uniform", "random earlier writer"), ("latest", "latest writer"), ("earliest", "earliest writer"), ("conservative", "name a source only if unambiguous"), ("tags", "token, else the unambiguous rule")]
    rows = []
    for k, lab in order:
        v = m[k]
        rows.append([lab, cs(v["top1"], 1), cs(v["recall"], 0), cs(v["false_accusation"], 1), cs(v.get("contamination_precision")) if v.get("contamination_precision") else "n/a",
                     cs(v.get("contamination_recall")) if v.get("contamination_recall") else "n/a"])
    table("tab_bench", ["Method", "Top-1 (copying agents)", "Recall", "False accusation", "Bad-tip precision", "Bad-tip recall"], rows, "@{}L{4.4cm}C{1.9cm}C{1.9cm}C{1.9cm}C{1.9cm}C{1.9cm}@{}",
          f"Benchmark baselines on {D.BASE['cells']} tagged lab runs (95\\% bootstrap intervals over runs).", "tab:bench",
          "Top-1: copying agents whose immediate source is named correctly. False accusation: agents that worked alone but were blamed on someone; the first three rules name a source whenever any earlier writer posted the same link, so their rate is high by construction. Bad-tip columns: the outputs the planted tip reached, found by following the predicted sources back to it. " + NOBRACKET, star=True, size="\\footnotesize", sep=4)


def t_family():
    h1, h2 = D.LAB["H1"]["by_family"], D.LAB["H2"]["by_family"]
    rows = []
    for f in FAM_ORDER:
        if f not in h2 or (h2[f]["with_tags"].get("den") or 0) < 20:
            continue
        lift = h2[f]["lift_points"]["rate"] * 100
        rows.append([NAME[f], n(h1[f]["loadbearing"]["den"]), cs(h1[f]["inert"]) if (h1[f]["inert"].get("den") or 0) >= 10 else "n/a", cs(h1[f]["loadbearing"]),
                     cs(h2[f]["edit_log_only"]), cs(h2[f]["with_tags"]), signed(lift)])
    table("tab_family", ["Model", "Copies", "Inert tag kept", "Token kept", "Best edit-log rule", "Token, else that rule", "Lift (pts)"], rows, "@{}lrC{1.9cm}C{1.9cm}C{1.9cm}C{1.9cm}r@{}",
          "Tag survival and attribution by model (load-bearing runs; models with at least 20 copying agents).", "tab:family",
          "Copies: copying agents in the load-bearing runs. Bracketed values are 95\\% bootstrap intervals over runs. The best edit-log rule is the best of latest, earliest and random writer for each run, chosen with the answer key in hand. Models with too few copying agents are in Appendix~\\ref{app:tables}. " + NOBRACKET, star=True, size="\\footnotesize", sep=4)


def t_gated():
    g = {f: v for f, v in D.LAB["gated"].items() if v.get("W4") and v.get("W4G")}
    rows = []
    order = sorted(g, key=lambda f: g[f]["W4"]["traceable"]["rate"])
    for i, f in enumerate(order):
        a, b = g[f]["W4"], g[f]["W4G"]
        assert a["agents"] == b["agents"] == 60, (f, a["agents"], b["agents"])
        for first, (world, v) in enumerate((("open", a), ("gated", b))):
            rows.append([NAME[f] if not first else "", world, cs(v["completed"]), cs(v["traceable"]), cs(v["with_tags"]), f"{v['failed_calls_per_agent']:.1f}"])
        if i < len(order) - 1:
            rows.append(["~"])
    table("tab_gated", ["Model", "World", "Right answer", "Output carries its token", "Source named, with token", "Refused calls per agent"], rows, "@{}llC{2.3cm}C{2.3cm}C{2.3cm}C{2.0cm}@{}",
          "Closing the other way in. Open: the mirror hands a session to anyone. Gated: access only through links the wiki served.", "tab:gated",
          "Each world has two runs of 30 agents per model. In the gated world every output that exists holds a token the wiki served to that agent; the source is named correctly less than 100\\% of the time because an agent sometimes reports a different link from the one it first fetched. " + NOBRACKET,
          star=True, size="\\footnotesize", sep=4)


def t_cleanup():
    rows = []
    names = [("everyone", "re-run everything"), ("after_tip", "everything submitted after the tip"), ("earliest", "follow the earliest visible writer"),
             ("tags+backup", "follow the tokens (earliest writer where lost)"), ("tags", "follow the tokens only")]
    for key, lab in (("W2 tags", "Tip arrives mid-run"), ("W2E tags", "Tip is there from the start")):
        a = D.CLEAN[key]
        rows.append([f"\\multicolumn{{5}}{{@{{}}l}}{{\\textit{{{lab}}}: {a['runs']} runs, {n(a['outputs'])} outputs; the tip reached {n(a['reached'])} of them and {n(a['stale'])} are wrong}}\\\\"])
        for m, mlab in names:
            v = a["methods"][m]
            rows.append([mlab, cs(v["flagged_share"]), cs(v["reached_found"]), cs(v["precision"]), cs(v["bad_found"])])
        rows.append(["---"])
    rows.pop()
    lines = ["\\begin{table*}[t]", "\\centering", "\\footnotesize", "\\setlength{\\tabcolsep}{4pt}",
             "\\caption{What an operator would re-check after a bad tip, by how the list is made (tagged runs, all models).}\\label{tab:cleanup}",
             "\\begin{tabular}{@{}L{5.0cm}C{2.2cm}C{2.2cm}C{2.2cm}C{2.2cm}@{}}", "\\toprule", "List & Share of outputs to re-check & Affected outputs found & Share of list truly affected & Wrong outputs on the list \\\\", "\\midrule"]
    for r in rows:
        lines.append("\\midrule" if r == ["---"] else (r[0].replace("\\\\", "") + " \\\\" if len(r) == 1 else " & ".join(r) + " \\\\"))
    lines += ["\\bottomrule", "\\end{tabular}",
              "\\par\\smallskip\\parbox{0.96\\linewidth}{\\footnotesize ``Affected'' means the output's chain of copying leads back to the planted post (hidden read log). ``Wrong'' means the output carries the stale value; some arrive another way (agents that try the stale mirror on their own), which no trace from the tip can find. Intervals: 95\\% bootstrap over runs; " + NOBRACKET[0].lower() + NOBRACKET[1:] + "}",
              "\\end{table*}"]
    (OUT / "tables" / "tab_cleanup.tex").write_text("\n".join(lines), encoding="utf-8")


def t_simulator():
    rows = []
    for k, (ceil, e, l, ms, h, em) in D.SIM_COPY.items():
        rows.append([k, f"{ceil:.3f}", f"{e:.3f}", f"{l:.3f}", f"{ms:.3f}", f"{h:.3f}", f"\\textbf{{{em:.3f}}}"])
    table("tab_sim", ["Copy model", "Bayes ceiling", "Earliest", "Latest", "Most similar", "Heuristic", "Model-based"], rows, "@{}lcccccc@{}",
          "Top-1 accuracy of tracers against the exact Bayes ceiling in a simulator with a known answer (12 seeds, about 3,400 adoptions per cell).", "tab:sim",
          "The model-based tracer learns the copy process from the log alone. Under three further copy rules, two of them outside the model family it assumes (marked $^{*}$), it keeps 88--101\\% of the ceiling (Appendix~\\ref{app:tables}).", star=True)
    rows = [[r[0], f"{r[1]:.2f}", f"{r[2]:.3f}", f"{r[3]:.3f}", f"{r[4]:.3f}", f"{r[4] / r[2]:.2f}"] for r in D.SIM_ROBUST]
    table("tab_robust", ["Copy rule", "Off-page share", "Ceiling", "Heuristic", "Model-based", "Model-based / ceiling"], rows, "@{}lccccc@{}",
          "Robustness of the model-based tracer to copy rules it was not built for ($^{*}$) and to hidden reads (off-page share).", "tab:robust")


def t_tip():
    late, early = D.LAB["rumor_by_family"], D.LAB["early_rumor_by_family"]
    rows = []
    for f in FAM_ORDER:
        if f in late or f in early:
            rows.append([NAME[f], ci(late.get(f)) if late.get(f) and late[f].get("rate") is not None else "n/a", ci(early.get(f)) if early.get(f) and early[f].get("rate") is not None else "n/a"])
    table("tab_tip", ["Model", "Tip arrives mid-run", "Tip is there from the start"], rows, "@{}lcc@{}",
          "Outputs that carry the planted bad value, by model (tagged runs; 95\\% bootstrap intervals over runs).", "tab:tip",
          "Wide intervals reflect two to four runs per model; adoption varies sharply from run to run.")


def t_models():
    ros = D.model_roster()
    rows = [[NAME.get(f, f), f"\\texttt{{{tex_escape(ros[f])}}}", {"qwen": "core model (most runs)", "qwen35": "strong-model check"}.get(f, "tag and bad-tip runs")] for f in FAM_ORDER if f in ros]
    table("tab_models", ["Family", "Model identifier (provider: \\ph{PROVIDER})", "Role"], rows, "@{}llp{3.6cm}@{}", "The model roster. Identifiers are the strings sent to the inference provider.", "tab:models")


def t_habits():
    adopt, top = D.LAB["H3"]["adoption_rate"], D.LAB["H3"]["top_values"]
    rows = []
    for f in sorted(adopt, key=lambda f: -adopt[f]):
        v = top.get(f)
        rows.append([NAME.get(f, f), pc(adopt[f]), f"\\texttt{{{tex_escape(v[0][0])}}} ($\\times${v[0][1]})" if v else "--"])
    table("tab_habits", ["Model", "Agents adding a cache-buster value", "Most common value"], rows, "@{}lcl@{}",
          "Independent agents (no wiki) differ in whether they add a throwaway ``random'' value to a URL, and several pick the same one.", "tab:habits",
          "30 agents per model per run, three runs.")


def t_scale():
    sw, mx, st = D.LAB["size_sweep"], D.LAB["mixed_swarm"], D.LAB["strong_model"]
    rows = []
    for k, v in sw.items():
        if v["tag_survival"].get("rate") is not None:
            rows.append([f"core model, {k} agents", n(v["tag_survival"]["den"]), cs(v["tag_survival"]), cs(v["with_tags"]), cs(v["edit_log_latest"]), cs(v["copy_share"])])
    rows.append(["---"])
    for c, v in mx.items():
        if v.get("seeds"):
            rows.append([f"mixed swarm, {TAGW[c]} tags", n(v["tag_survival"]["den"]), cs(v["tag_survival"]), "--", "--", cs(v["cross_family_copy_share"])])
    table("tab_scale", ["Setting", "Copies", "Token kept", "Source named, with token", "Source named, latest writer", "Copy share$^{\\dagger}$"], rows, "@{}L{3.8cm}rC{1.9cm}C{1.9cm}C{1.9cm}C{1.9cm}@{}",
          "Swarm size and mixed swarms (core model; and all eight families in one wiki).", "tab:scale",
          "Core-model rows are the load-bearing runs of W1 with 10, 30 and 100 agents (5, 10 and 3 runs). $^{\\dagger}$In the mixed-swarm rows this column is the share of copies whose source belongs to another family; attribution columns are omitted there (see the data release). " + NOBRACKET,
          star=True, size="\\footnotesize", sep=4)


# ---------------------------------------------------------------- number macros
def numbers():
    L, B, inc, co, ct, av, sp, m = D.LAB, D.BASE["methods"], D.R["incident"], D.R["coincidence"], D.R["cross_team"], D.AV, D.R["spend"], D.BASE["methods"]
    h2 = L["H2"]["by_family"]
    fams = [f for f, v in h2.items() if (v["with_tags"].get("den") or 0) >= 20 and v["lift_points"]["rate"] is not None]
    lifts = [h2[f]["lift_points"]["rate"] * 100 for f in fams]
    g = {f: v for f, v in L["gated"].items() if v.get("W4") and v.get("W4G")}
    byp = [f for f in g if g[f]["W4"]["traceable"]["rate"] < 0.9]
    cl, ce = D.CLEAN["W2 tags"]["methods"], D.CLEAN["W2E tags"]["methods"]
    h1 = L["H1"]["by_family"]
    early = L["early_rumor_by_family"]
    M = {
        "nCells": n(sp["lab_cells"]), "nRuns": n(sp["lab_agent_runs"]), "nFamilies": "8", "labUSD": f"{sp['lab_usd']:.0f}",
        "nAdopters": n(inc["adopters"]), "nBehaviours": str(inc["behaviors"]), "noCarrier": pc(inc["no_carrier"]), "bestTop": pc(inc["best_top1"], 1),
        "naiveCalls": n(co["naive_calls"]), "trustedCalls": n(co["supported_calls"]), "crossNaive": str(ct["naive"]), "crossVerified": str(ct["verified"]), "crossRejected": str(ct["rejected"]),
        "avMessages": n(av["messages"]), "avPre": pc(av["pre_rooms"]["rate"]), "avPost": pc(av["room_scoped"]["rate"]), "avPostMin": pc(av["room_scoped"]["window_min"]),
        "avPostMedian": pc(av["room_scoped"]["window_median"]), "avPreWeeks": str(av["pre_rooms"]["windows"]), "avPostWeeks": str(av["room_scoped"]["windows"]),
        "avPostCopies": n(av["room_scoped"]["adoptions"]), "avPreCopies": n(av["pre_rooms"]["adoptions"]), "avFirst": av["first_day"], "avLast": av["last_day"],
        "benchCells": str(D.BASE["cells"]), "benchAll": n(sp["bench_cells"]), "benchTagsTop": pc(m["tags"]["top1"]["value"], 1), "benchEarliestTop": pc(m["earliest"]["top1"]["value"], 1), "benchLatestTop": pc(m["latest"]["top1"]["value"], 1),
        "benchUniformTop": pc(m["uniform"]["top1"]["value"], 1), "benchConsTop": pc(m["conservative"]["top1"]["value"], 1),
        "benchTagsFA": pc(m["tags"]["false_accusation"]["value"], 1), "benchRuleFA": pc(m["earliest"]["false_accusation"]["value"], 1), "benchConsFA": pc(m["conservative"]["false_accusation"]["value"], 1),
        "benchTagsRecall": pc(m["tags"]["recall"]["value"], 0), "benchTagsECE": f"{m['tags'].get('ece_accusations', 0):.3f}",
        "liftMin": f"{min(lifts):+.0f}".replace("-", "$-$"), "liftMax": f"{max(lifts):+.0f}", "nLiftFamilies": str(len(fams)), "nLiftTen": str(sum(1 for x in lifts if x >= 10)),
        "gatedOpenLo": pc(min(g[f]["W4"]["traceable"]["rate"] for f in byp)), "gatedOpenHi": pc(max(g[f]["W4"]["traceable"]["rate"] for f in byp)), "nBypass": str(len(byp)), "nBypassWord": ["no", "one", "two", "three", "four", "five", "six", "seven", "eight"][len(byp)],
        "recheckAfter": pc(cl["after_tip"]["flagged_share"]["rate"]), "recheckTrace": pc(cl["tags+backup"]["flagged_share"]["rate"]), "recheckEarliest": pc(cl["earliest"]["flagged_share"]["rate"]),
        "recheckFoundLo": pc(cl["tags+backup"]["reached_found"]["rate"]), "recheckFoundHi": pc(cl["earliest"]["reached_found"]["rate"]),
        "earlyReach": pc(D.CLEAN["W2E tags"]["reached"] / D.CLEAN["W2E tags"]["outputs"]), "earlyEarliest": pc(ce["earliest"]["flagged_share"]["rate"]),
        "qwenEarly": pc(early["qwen"]["rate"]), "gptossEarly": pc(early["gptoss"]["rate"]),
        "qwenInert": pc(h1["qwen"]["inert"]["rate"]), "qwenToken": pc(h1["qwen"]["loadbearing"]["rate"]), "glmToken": pc(h1["glm"]["loadbearing"]["rate"]),
        "stalePerRunLate": "4", "tauDefault": "100", "maxAgents": "10", "gradeA": "90", "gradeB": "70", "gradeC": "50", "gradeD": "25",
        "simRescueNaive": pc(D.SIM_RESCUE[-1][1]), "simRescueCal": pc(D.SIM_RESCUE[-1][2]),
    }
    lines = ["% generated by scripts/arxiv_tables.py from the result files: do not edit by hand"]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in M.items()]
    (OUT / "numbers.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return M


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (t_real, t_design, t_hyp, t_bench, t_family, t_gated, t_cleanup, t_simulator, t_tip, t_models, t_habits, t_scale):
        f()
    return numbers()
