"""Build paper/agloe.html from the computed result files (prose is written here; every number and table is read from data).

Inputs: frontend/data/results.json (python -m scripts.build_site_data), data/lab/lab_results.json, data/out/*.json.
Output: paper/agloe.html (print stylesheet). PDF: see build_pdf() / `python -m scripts.build_paper --pdf` (Edge headless).
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "frontend" / "paper"          # served by the site at /paper/ (the landing page links to it)
NAMES = {"qwen": "Qwen3-235B", "deepseek": "DeepSeek-V4-Pro", "kimi": "Kimi-K3", "glm": "GLM-5.2", "gptoss": "gpt-oss-120B",
         "nemotron": "Nemotron-3-super", "minimax": "MiniMax-M3", "hermes": "Hermes-4-405B", "gemma": "Gemma-3-27B", "qwen35": "Qwen3.5-397B",
         "mix": "8 families mixed"}
S1, S2 = "#2a78d6", "#eb6834"                      # categorical slots 1-2 (validated light palette, dataviz reference)
e = html.escape


def jl(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def pc(x, d=0):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def rate(d):
    return "n/a" if not d or d.get("rate") is None else pc(d["rate"])


def ci(d):
    if not d or d.get("rate") is None:
        return "n/a"
    return f"{pc(d['rate'])} ({pc(d['lo'])}&ndash;{pc(d['hi'])})"


def table(head, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def svg_bars(rows, series, title, w=640):
    """Horizontal bars (static): rows [(label, [values 0..1 or None])], series [(name, color)]. 100% = full plot width."""
    lh, pad_l, pad_r, top = 18 * len(series) + 10, 150, 56, 28
    h = top + lh * len(rows) + 30
    pw = w - pad_l - pad_r
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(title)}" class="fig">']
    for k in range(5):
        x = pad_l + pw * k / 4
        out.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{h - 24}" stroke="#e1e0d9" stroke-width="1"/>'
                   f'<text x="{x:.1f}" y="{h - 8}" font-size="10" text-anchor="middle" fill="#898781">{k * 25}%</text>')
    if len(series) > 1:
        lx = pad_l
        for name, col in series:
            out.append(f'<rect x="{lx}" y="4" width="10" height="10" rx="2" fill="{col}"/><text x="{lx + 15}" y="13" font-size="11" fill="#52514e">{e(name)}</text>')
            lx += 15 + 7 * len(name) + 18
    for i, (lab, vals) in enumerate(rows):
        y0 = top + i * lh
        out.append(f'<text x="{pad_l - 10}" y="{y0 + lh / 2 - 1:.1f}" font-size="11.5" text-anchor="end" fill="#52514e">{e(lab)}</text>')
        for j, v in enumerate(vals):
            by = y0 + j * 18 + 2
            if v is None:
                out.append(f'<text x="{pad_l + 6}" y="{by + 11}" font-size="10" fill="#898781">no data</text>')
                continue
            bw = max(1.5, pw * min(1, max(0, v)))
            out.append(f'<rect x="{pad_l}" y="{by}" width="{bw:.1f}" height="13" rx="3" fill="{series[j][1]}"/>'
                       f'<text x="{pad_l + bw + 6:.1f}" y="{by + 11}" font-size="11" fill="#0b0b0b">{pc(v)}</text>')
    out.append(f'<line x1="{pad_l}" y1="{top - 6}" x2="{pad_l}" y2="{h - 24}" stroke="#c3c2b7"/></svg>')
    return "\n".join(out)


def build() -> str:
    R = jl(ROOT / "frontend" / "data" / "results.json") or {}
    lab = (R.get("lab")) or jl(ROOT / "data" / "lab" / "lab_results.json") or {}
    inc, co, ct = R.get("incident", {}), R.get("coincidence", {}), R.get("cross_team", {})
    sp = R.get("spend", {})
    avf = R.get("ai_village_full") or {}
    if avf:
        pre, post = avf["pre_rooms"], avf["room_scoped"]
        low = min((s for s in avf.get("showcased", []) if s["rooms"] and s.get("rate") is not None), key=lambda s: s["rate"], default=None)
        av_txt = (f"<p>In AI Village (40+ agents of several vendors, public dataset) the chat is logged for everyone. We ran the same measurement over every week of the whole chat "
                  f"({avf['messages']:,} agent messages, {avf['first_day']} to {avf['last_day']}): {pc(pre['rate'])} of copies had a visible source in the {pre['windows']} weeks before chat was split into rooms, "
                  f"and {pc(post['rate'])} in the {post['windows']} weeks after (lowest week {pc(post['window_min'])}, median {pc(post['window_median'])}). "
                  f"A channel everyone can read is almost always traceable, so the contrast with the incident is what matters: its reads were never logged. "
                  + (f"We first reported four hand-picked weeks, including a post-rooms week at {pc(low['rate'])} that turned out to sit near the bottom of the post-rooms weeks "
                     f"(percentile {low['percentile_in_regime']:.2f}); the whole-dataset result replaces it. " if low else "")
                  + "A test that same-model agents co-emit the same distinctive token more than chance was significant in one of four weeks and is not claimed.</p>")
    else:
        av_txt = ("<p>In AI Village (40+ agents of several vendors, public dataset) the chat is logged for everyone, so copying is traceable almost every time; the whole-dataset run "
                  "was not available in this build.</p>")
    H1, H2, H3, H4 = (lab.get(k, {}) for k in ("H1", "H2", "H3", "H4"))
    fa = lab.get("fingerprint_attribution", {})
    fams = [f for f, v in H1.get("by_family", {}).items() if v["loadbearing"].get("rate") is not None or v["inert"].get("rate") is not None]
    lbs = [H1["by_family"][f]["loadbearing"]["rate"] for f in fams if H1["by_family"][f]["loadbearing"].get("rate") is not None]
    ins = [H1["by_family"][f]["inert"]["rate"] for f in fams if H1["by_family"][f]["inert"].get("rate") is not None]

    # ---------------------------------------------------------------- figures and tables from data
    ladder = R.get("ladder", [])
    fig_ladder = svg_bars([(r["label"], [r["value"]]) for r in ladder], [("Visible source", S1)], "Share of copy events whose source is visible, by logging regime") if ladder else ""
    adopt = H3.get("adoption_rate", {})
    fig_fp = svg_bars(sorted([(NAMES.get(f, f), [v]) for f, v in adopt.items() if f != "gemma"], key=lambda r: -r[1][0]),
                      [("Agents that add a cache-buster value", S1)], "Cache-buster adoption by model family") if adopt else ""
    tag_rows = sorted([(NAMES.get(f, f), [H1["by_family"][f]["inert"].get("rate"), H1["by_family"][f]["loadbearing"].get("rate")]) for f in fams],
                      key=lambda r: -(r[1][1] if r[1][1] is not None else -1))
    fig_tags = svg_bars(tag_rows, [("Inert tag", S1), ("Load-bearing token", S2)], "Tag survival by family") if tag_rows else ""
    wl = {"W1": "Shared wiki", "W2": "Bad tip appears late", "W2E": "Bad tip from the start"}
    h2w = H2.get("by_world", {})
    h2f = H2.get("by_family", {})
    attr_fams = sorted([f for f, v in h2f.items() if v["with_tags"].get("den", 0) >= 20], key=lambda f: -(h2f[f]["lift_points"].get("rate") or 0))
    attr_rows = [(NAMES.get(f, f), [h2f[f]["edit_log_only"].get("rate"), h2f[f]["with_tags"].get("rate")]) for f in attr_fams]
    fig_attr = svg_bars(attr_rows, [("Edit log, best simple rule", S1), ("Tag where it survived, else the same rule", S2)], "Source named correctly") if attr_rows else ""
    lifts = [h2f[f]["lift_points"]["rate"] for f in attr_fams if h2f[f]["lift_points"].get("rate") is not None]
    lift_txt = (f"from {min(lifts) * 100:+.0f} to {max(lifts) * 100:+.0f} points depending on the model" if lifts else "by a model-dependent amount")

    t_h1 = table(["Model family", "Inert tag survives", "Load-bearing token survives", "copiers (inert / load-bearing)"],
                 [[NAMES.get(f, f), ci(H1["by_family"][f]["inert"]), ci(H1["by_family"][f]["loadbearing"]),
                   f"{H1['by_family'][f]['inert'].get('den', 0)} / {H1['by_family'][f]['loadbearing'].get('den', 0)}"] for f in fams], "num")
    t_h2 = table(["Model family", "Earliest", "Latest", "Best simple rule", "Tag survival", "With tags", "Lift (points)"],
                 [[NAMES.get(f, f), rate(h2f[f]["edit_log_earliest"]), rate(h2f[f]["edit_log_latest"]), ci(h2f[f]["edit_log_only"]),
                   rate(H1["by_family"][f]["loadbearing"]), ci(h2f[f]["with_tags"]),
                   ("n/a" if h2f[f]["lift_points"].get("rate") is None else f"{h2f[f]['lift_points']['rate'] * 100:+.0f}")] for f in attr_fams], "num") if attr_fams else ""
    h4rows = []
    for key, v in H4.items():
        if not v.get("seeds"):
            continue
        w, c = key.split("|")
        ft = v["forward_trace"]
        tagged = c != "none"
        h4rows.append([wl.get(w, w), {"none": "none", "inert": "inert tag", "loadbearing": "load-bearing"}[c], str(v["seeds"]), ci(v["spread_rate"]),
                       ci(v["contaminated_attribution_with_tags"]) if tagged else "&ndash;", ci(v["contaminated_attribution_edit_log"]) if tagged else "&ndash;",
                       (f"{rate(ft['tags']['precision'])} / {rate(ft['tags']['recall'])}") if tagged else "&ndash;",
                       (f"{rate(ft['edit_log_earliest']['precision'])} / {rate(ft['edit_log_earliest']['recall'])}") if tagged else "&ndash;"])
    t_h4 = table(["World", "Tags", "runs", "Outputs with the stale value", "Source named, tags", "Source named, edit log (best rule)",
                  "Trace from origin via tags (P / R)", "Trace via earliest writer (P / R)"], h4rows, "num small") if h4rows else ""
    fp_top = {f: (v[0] if v else None) for f, v in H3.get("top_values", {}).items()}
    t_fp = table(["Model family", "Agents adding a value", "Most common value"],
                 [[NAMES.get(f, f), pc(adopt[f]), (f"<code>{e(fp_top[f][0])}</code> &times; {fp_top[f][1]}" if fp_top.get(f) else "&ndash;")]
                  for f in sorted(adopt, key=lambda x: -adopt[x]) if f != "gemma"], "num") if adopt else ""
    size = lab.get("size_sweep", {})
    t_size = table(["Swarm size", "Tag survival", "With tags", "Edit log (latest)", "copy share"],
                   [[n, ci(v["tag_survival"]), ci(v["with_tags"]), ci(v["edit_log_latest"]), ci(v["copy_share"])] for n, v in size.items() if v["tag_survival"].get("rate") is not None], "num") if size else ""
    cl = jl(ROOT / "data" / "lab" / "cleanup_savings.json") or {}
    cl_names = {"everyone": "Re-run everything", "after_tip": "Re-check everything after the tip appeared", "earliest": "Follow the earliest visible writer",
                "tags+backup": "Follow the codes (earliest writer where a code was lost)", "tags": "Follow the codes only"}
    cl_rows = [[lbl, name, ci(cl[sc]["methods"][k]["flagged_share"]), ci(cl[sc]["methods"][k]["reached_found"]), ci(cl[sc]["methods"][k]["precision"])]
               for sc, lbl in (("W2 tags", "Tip arrives mid-run"), ("W2E tags", "Tip there from the start")) if sc in cl for k, name in cl_names.items()]
    t_clean = table(["Bad tip", "Re-check list", "Share of outputs to re-check", "Affected outputs found", "Share of list truly affected"], cl_rows, "num small") if cl_rows else ""
    clean_txt = ""
    if "W2 tags" in cl and "W2E tags" in cl:
        a, b = cl["W2 tags"], cl["W2E tags"]
        clean_txt = (f"<p><b>What to re-check.</b> When a tip has spread, an operator needs a list of outputs to re-examine. We scored each candidate list against the hidden read log "
                     f"(&lsquo;affected&rsquo; means the output&rsquo;s chain of copying leads back to the planted post). For a tip that arrives mid-run ({a['runs']} tagged runs, {a['outputs']:,} outputs, "
                     f"{a['reached']} reached), re-checking everything submitted after the tip appeared means {pc(a['methods']['after_tip']['flagged_share']['rate'])} of outputs, while tracing the tip "
                     f"gives {pc(a['methods']['tags+backup']['flagged_share']['rate'])}&ndash;{pc(a['methods']['earliest']['flagged_share']['rate'])} and finds {pc(a['methods']['tags+backup']['reached_found']['rate'])}&ndash;"
                     f"{pc(a['methods']['earliest']['reached_found']['rate'])} of the affected outputs. The saving comes from tracing at all: the earliest-writer rule is nearly as good as the codes for a single-source tip, "
                     f"and the codes make the list exact (every flagged output truly affected) rather than shorter. When the tip is there from the start and the swarm adopts it, it reaches "
                     f"{pc(b['reached'] / b['outputs'])} of outputs and no list saves much: the work saved is by catching a tip early. And {a['stale_not_reached']} of the {a['stale']} wrong outputs "
                     f"in the mid-run worlds had no chain to the tip (agents that tried the stale mirror on their own); a trace from the tip cannot find them, only fixing the mirror can.</p>")
    gt = {f: v for f, v in lab.get("gated", {}).items() if v.get("W4") and v.get("W4G")}
    t_gated, gated_txt = "", ""
    if gt:
        order = sorted(gt, key=lambda f: gt[f]["W4"]["traceable"].get("rate") or 0)
        t_gated = table(["Model family", "Agents (open / gated)", "Submitted the right answer", "Output carries a token naming its copy", "Tag survival among copiers",
                         "Source named correctly, with tags", "Refused calls per agent"],
                        [[NAMES.get(f, f), f"{gt[f]['W4']['agents']} / {gt[f]['W4G']['agents']}", f"{ci(gt[f]['W4']['completed'])} &rarr; {ci(gt[f]['W4G']['completed'])}",
                          f"{ci(gt[f]['W4']['traceable'])} &rarr; {ci(gt[f]['W4G']['traceable'])}", f"{ci(gt[f]['W4']['tag_survival'])} &rarr; {ci(gt[f]['W4G']['tag_survival'])}",
                          f"{ci(gt[f]['W4']['with_tags'])} &rarr; {ci(gt[f]['W4G']['with_tags'])}",
                          f"{gt[f]['W4']['failed_calls_per_agent']} &rarr; {gt[f]['W4G']['failed_calls_per_agent']}"] for f in order], "num small")
        gain = {f: (gt[f]["W4G"]["traceable"].get("rate") or 0) - (gt[f]["W4"]["traceable"].get("rate") or 0) for f in order}
        lead = [f for f in order if gain[f] >= 0.1]
        done_o = [gt[f]["W4"]["completed"]["rate"] for f in order if gt[f]["W4"]["completed"].get("rate") is not None]
        done_g = [gt[f]["W4G"]["completed"]["rate"] for f in order if gt[f]["W4G"]["completed"].get("rate") is not None]
        span = lambda xs: pc(min(xs)) if min(xs) == max(xs) else f"{pc(min(xs))}&ndash;{pc(max(xs))}"
        wt = [gt[f]["W4G"]["with_tags"]["rate"] for f in order if gt[f]["W4G"]["with_tags"].get("rate") is not None]
        gated_txt = (f"<p>The design rule that follows from section 4.3 is that the token must be the only way in. We tested it in the lab. In W4 a coordinator posts the team&rsquo;s working link, agents share their URLs on a "
                     f"notes page, and the mirror root still hands a session to anyone; W4G is the same world with the root closed, so a working request must carry a link the wiki served. "
                     f"({sum(gt[f]['W4']['agents'] + gt[f]['W4G']['agents'] for f in gt)} agent runs, {len(gt)} model families, load-bearing tokens in both.) "
                     + (f"For the models that bypass tags when they can, the share of outputs that carry a token naming the copy they came from rises: "
                        + "; ".join(f"{NAMES.get(f, f)} {pc(gt[f]['W4']['traceable']['rate'])} to {pc(gt[f]['W4G']['traceable']['rate'])}" for f in lead) + ". " if lead else "")
                     + f"Agents still finished: {span(done_o)} submitted the right answer in the open world and {span(done_g)} in the gated one. "
                     f"The price is calls spent on refused requests before an agent reads the wiki (last column).</p>"
                     "<p>Two limits matter more than the numbers. First, with the door closed, tracing follows from the access design rather than from the agents&rsquo; habits, so this is a cost-and-feasibility "
                     "result, not a discovery about attribution; the token in a submission names the copy the agent was served, which can differ from the copy it fetched first when an agent reports a different link "
                     f"than the one it used (which is why the source is named correctly {span(wt)} of the time in the gated world, not always 100%). Second, a gate traces access, not ideas: an agent that learns which mirror works "
                     "from a peer and then obtains access through another legitimate route leaves no trail. Whether a real system can close every door as this lab does is a deployment question we do not answer.</p>")
    mix = lab.get("mixed_swarm", {})
    t_mix = table(["Tags", "runs", "Copies from another family", "Tag survival"],
                  [[c, str(v["seeds"]), ci(v["cross_family_copy_share"]), ci(v["tag_survival"])] for c, v in mix.items() if v.get("seeds")], "num") if mix else ""

    ok_fams = [NAMES.get(f, f) for f in fams
               if H1["by_family"][f]["loadbearing"].get("den", 0) >= 10 and H1["by_family"][f]["inert"].get("den", 0) >= 10
               and H1["by_family"][f]["loadbearing"]["rate"] >= 0.9 and H1["by_family"][f]["inert"]["rate"] <= 0.1]
    tested = [f for f in fams if H1["by_family"][f]["loadbearing"].get("den", 0) >= 10 and H1["by_family"][f]["inert"].get("den", 0) >= 10]
    h1_verdict = (f"Both held for {len(ok_fams)} of {len(tested)} families with enough copiers" + (f" ({', '.join(ok_fams)})." if ok_fams else ".")
                  if tested else "")
    rb, eb = lab.get("rumor_by_family", {}), lab.get("early_rumor_by_family", {})
    late = {f: v for f, v in rb.items() if v.get("rate") is not None and f != "gemma" and v.get("den", 0) >= 50}
    early = {f: v for f, v in eb.items() if v.get("rate") is not None and f != "gemma" and v.get("den", 0) >= 20}
    late_took = ", ".join(f"{NAMES.get(f, f)} {pc(v['rate'])}" for f, v in late.items() if v["rate"] > 0.02)
    late_ign = [NAMES.get(f, f) for f, v in late.items() if v["rate"] <= 0.02]
    early_list = ", ".join(f"{NAMES.get(f, f)} {pc(v['rate'])}" for f, v in sorted(early.items(), key=lambda kv: -kv[1]["rate"]))
    n_hi = sum(1 for v in early.values() if v["rate"] >= 0.9)
    early_lo = [NAMES.get(f, f) for f, v in early.items() if v["rate"] <= 0.1]
    early_interp = ("took over every family we ran it on" if early and n_hi == len(early)
                    else f"took over {n_hi} of {len(early)} families completely and was ignored (at most 10%) by {len(early_lo)} ({', '.join(early_lo)})" if early else "")
    bad_tip_families = (f"<p>By model: a <b>late</b> tip was adopted by {late_took or 'no family'} of agents (run-level intervals are wide) and ignored, at most 2% adoption, by "
                        f"{len(late_ign)} of {len(late)} families ({', '.join(late_ign)}). An <b>early</b> tip {early_interp} (share of agents with the stale value: {early_list}). "
                        "So whether a bad tip spreads depends on when it appears <i>and</i> on how much the model trusts a newcomer; the lesson is to measure your own agents, not to assume.</p>") if late and early else ""
    bl = jl(ROOT / "bench_release" / "baselines.json")
    def _m(s, k):
        d = s.get(k)
        return "n/a" if not d else f"{pc(d['value'])} ({pc(d['ci95'][0])}&ndash;{pc(d['ci95'][1])})"
    t_bench = table(["Tracer (reads the edit log only, except tags)", "Sources named correctly", "Copies it attributes", "Independent agents it falsely blames", "Contamination trace P / R"],
                    [[{"latest": "blame the latest teammate with the same link", "earliest": "blame the earliest", "uniform": "pick one at random",
                       "conservative": "blame only when exactly one candidate", "tags": "read the tag, else the conservative rule"}[m],
                      _m(s, "top1"), _m(s, "recall"), _m(s, "false_accusation"),
                      f"{pc(s['contamination_precision']['value']) if s.get('contamination_precision') else 'n/a'} / {pc(s['contamination_recall']['value']) if s.get('contamination_recall') else 'n/a'}"]
                     for m, s in (bl or {}).get("methods", {}).items()], "num small") if bl else ""
    bench_txt = (f"<p>Baselines on the {bl['cells']} tagged cells of Agloe-Bench (inert and load-bearing; untagged cells have no well-defined source and are not scored for attribution). "
                 "All three simple rules accuse most agents that worked alone, because a same-link post by someone else is almost always available; the confidence intervals are over cells.</p>" + t_bench) if bl else ""
    sm = lab.get("strong_model", {})
    sm_rows = [[NAMES.get(f, f), {"none": "none", "loadbearing": "load-bearing"}[c], ci(v[c]["stale"]), ci(v[c]["tag_survival"])]
               for f, v in sm.items() for c in ("none", "loadbearing") if v[c]["stale"].get("rate") is not None]
    t_strong = table(["Model", "Tags", "Outputs with the stale value (late tip)", "Tag survival"], sm_rows, "num") if len(sm_rows) > 2 else ""
    mixed_ok = [v for v in mix.values() if v.get("seeds") and v["cross_family_copy_share"].get("rate") is not None]
    mix_txt = (f"In swarms of eight model families sharing one wiki, {pc(min(v['cross_family_copy_share']['rate'] for v in mixed_ok))}&ndash;{pc(max(v['cross_family_copy_share']['rate'] for v in mixed_ok))} "
               "of copies crossed family lines (random mixing alone would give 87.5%), so information flowed freely between models and a detector that expects same-model clustering would miss real transmission; "
               f"tag survival fell to {pc(min(v['tag_survival']['rate'] for v in mixed_ok if v['tag_survival'].get('rate') is not None))}&ndash;{pc(max(v['tag_survival']['rate'] for v in mixed_ok))} because copying styles differ.") if mixed_ok else ""
    lb_rng = (f"{pc(min(lbs))}&ndash;{pc(max(lbs))}" if lbs else "n/a")
    in_rng = (f"{pc(min(ins))}&ndash;{pc(max(ins))}" if ins else "n/a")
    lift_all = H2.get("all", {}).get("lift_points", {})
    nb_acc, nb_chance = fa.get("accuracy"), fa.get("chance")

    css = """
    @page { size: Letter; margin: 0.85in 0.9in; }
    body { font: 11pt/1.5 Georgia, 'Times New Roman', serif; color: #111; max-width: 7in; margin: 0 auto; padding: 0 12px; }
    h1 { font: 700 21pt/1.2 system-ui, 'Segoe UI', sans-serif; margin: .2em 0 .1em; } h2 { font: 700 13.5pt system-ui, 'Segoe UI', sans-serif; margin: 1.5em 0 .3em; }
    h3 { font: 700 11pt system-ui, 'Segoe UI', sans-serif; margin: 1.1em 0 .2em; }
    .by { color: #444; font: 10pt system-ui, sans-serif; margin: 0 0 1em; } .abs { border-left: 3px solid #ccc; padding: .1em 0 .1em 12px; margin: 1em 0; }
    table { border-collapse: collapse; width: 100%; font: 9.5pt system-ui, 'Segoe UI', sans-serif; margin: .6em 0 1em; } table.small { font-size: 8.5pt; }
    th, td { text-align: left; padding: 3px 6px; border-bottom: 1px solid #ddd; vertical-align: top; } th { border-bottom: 1.5px solid #111; font-weight: 600; }
    code { font: 9.5pt ui-monospace, Menlo, Consolas, monospace; background: #f3f2ee; padding: 0 3px; }
    figure { margin: 1em 0; break-inside: avoid; } figcaption { font: 9.5pt system-ui, sans-serif; color: #333; margin-top: 2px; } .fig { width: 100%; height: auto; }
    .box { border: 1px solid #bbb; padding: 8px 14px; margin: 1em 0; break-inside: avoid; font-size: 10.5pt; } .small { font-size: 9.5pt; color: #333; }
    ol li, ul li { margin: .25em 0; } a { color: #1c4fa0; }
    """
    body = f"""
<h1>Agloe: What Swarm Logs Can&rsquo;t Tell You, and Trap Streets That Make Copying Confess</h1>
<p class="by">Paper Towns &middot; AI Swarm Dynamics Hackathon, October 2026 &middot; code, benchmark and live demo: see the project page</p>

<div class="abs"><b>Abstract.</b> When AI agents share notes, one agent&rsquo;s mistake can spread to many, and the logs people keep rarely say who learned what from whom.
We study this on a real incident (a shared wiki edited by AI agents) and on a second real swarm (AI Village), then in an offline lab of {sp.get('lab_agent_runs', 0):,} agent runs across eight model families.
Three results. (1) <b>The wall.</b> Even a perfect investigator could trace at most {pc(inc.get('best_top1'))} of the incident&rsquo;s copying from its edit logs; {pc(inc.get('no_carrier'))} of adopters had no visible carrier. How much is traceable depends on what is logged.
(2) <b>The coincidence trap.</b> &ldquo;Same string means copied&rdquo; made {co.get('naive_calls', '1,001'):,} copy calls of which {co.get('supported_calls', 385)} survive calibration, and {ct.get('naive', 23)} cross-team jumps of which {ct.get('verified', 3)} survive hand verification. Agents of different models make characteristic &ldquo;random&rdquo; choices, and several share them.
(3) <b>Trap streets.</b> Serving each page view with its own load-bearing token turns a copied link into a pointer to the exact copy it came from; against the best simple edit-log rule it lifts the share of sources named correctly {lift_txt}, in proportion to how many agents copy the link rather than redo the work. Whether a token survives copying depends on the model: load-bearing tokens survived in {lb_rng} of copies across families, decorative tags in {in_rng}.
We release a report card (CLI and in-browser), a canary-tag kit, and Agloe-Bench, a benchmark with a hidden answer key.</div>

<h2>1. The problem</h2>
<p>In the incident that motivates this work, AI agents passed workarounds to each other through a shared wiki. Investigators had the wiki&rsquo;s edit history, which records what was written, not what was read. So when an agent used a workaround, there was usually no way to say where it came from. The same question arises for any swarm that shares notes, memory or code: if something bad enters, can you find where, and which agents it reached?</p>
<p>We make four contributions: a measurement of how much of a real swarm&rsquo;s copying is traceable (and why the obvious detectors mislead); a controlled lab with ground truth in which we test a fix; a set of open tools; and a list of things that did not work, which we report in section 6.</p>

<h2>2. Definitions and what the logs can support</h2>
<p><b>Edit log vs read log.</b> The edit log shows writes. The read log shows which page version each agent was served. Only the lab has the read log. <b>Copy</b> means exposure: the agent was served the item before using it, the standard definition in contagion studies; it says nothing about intent.</p>
<p><b>Ceilings.</b> In a simulator with known ground truth we proved and checked three facts (RESULTS A, H): the best top-1 accuracy any tracer can reach from a log equals the expected maximum posterior of the true source (the oracle matched the formula within 0.009); logging item-level reads for a fraction &rho; of copies lifts the ceiling to &rho; + (1&minus;&rho;)C<sub>0</sub>; and version-unique tags that survive copying with probability s lift it to s + (1&minus;s)C<sub>0</sub> (checked within 0.008). A model-based tracer reached the ceiling (0.458 vs 0.460 under uniform copying; 0.796 vs 0.799 under recency) and was calibrated (ECE 0.019). The ceiling depends on how copiers choose: a tracer that knows copiers prefer the first link can do far better than one that does not, and tags do not need that knowledge.</p>

<h2>3. The real incident, and a second real swarm</h2>
<h3>3.1 The wall</h3>
<p>Across {inc.get('behaviors', 35)} behaviours with at least 20 named adopters ({inc.get('adopters', 2976):,} adopters), {pc(inc.get('no_carrier'))} had no visible carrier and the best possible top-1 attribution was {pc(inc.get('best_top1'), 1)}. For marker strings (rare strings that reappear in other agents&rsquo; edits), the earlier writer was visible in 16&ndash;20% of cases; 80&ndash;92% of sources were off the copier&rsquo;s page. These agents read from places the log does not record.</p>
<figure>{fig_ladder}<figcaption>Figure 1. Share of copy events whose source is visible in the log. The incident figure is for marker strings (RESULTS F); the AI Village figures are carrier coverage of rare strings in chat, pooled over every week of the whole dataset (<code>scripts/run_ai_village_full.py</code>). They are different measurements; the direction is the point.</figcaption></figure>
<h3>3.2 The coincidence trap</h3>
<p>Matching on shared strings flagged {co.get('naive_calls', 1001):,} copies on the incident board; {co.get('supported_calls', 385)} survive a likelihood-ratio test against the per-value base rate. Among the {ct.get('naive', 23)} cross-team collusion jumps the same matching flagged, {ct.get('rejected', 20)} were dataset field names, timestamps and other vocabulary that many agents type independently (for example a field name used by 41 agents on 12 pages); {ct.get('verified', 3)} survived: two session-token URLs and one minted short-link slug. We confirmed the session tokens were minted per fetch (48 distinct values for one resource), so reuse of a specific value cannot be independent. Notably these three hops are provable only because the URL carried a per-fetch token, a trap street that occurred by accident.</p>
<h3>3.3 A second swarm</h3>
{av_txt}

<h2>4. The lab</h2>
<h3>4.1 Design</h3>
<p>Agents (language models with tools) must find a number behind &ldquo;down&rdquo; data servers, using mirror URLs on reserved <code>.invalid</code> domains, so nothing leaves the sandbox. In <b>W1</b> agents share a wiki. In <b>W2</b> they are asked to post their working URL to a &ldquo;Notes&rdquo; page, and a tip recommending a stale mirror (it returns old data with no warning) appears after five agents have finished; in <b>W2E</b> it is there from the start; in <b>W3</b> agents of eight model families share one wiki. Conditions: <i>none</i>; <i>inert</i> (each served link gets a random-looking query value that mirrors ignore); <i>load-bearing</i> (each served link carries a session token the mirror requires, re-minted per served copy). Each cell is 30 agents (10 to 100 in the size sweep); results pool seeds with a seed-level bootstrap because agents in one swarm read each other. The answer key is the read log. When several posts carry byte-identical links the source is not defined by text, so attribution is scored only in tagged cells, where the served copy is unique.</p>
<p>We changed this design three times after pilots, and report why (section 6). The final design, models (Qwen3-235B, DeepSeek-V4-Pro, Kimi-K3, GLM-5.2, gpt-oss-120B, Nemotron-3-super, MiniMax-M3, Hermes-4-405B; Gemma-3 never emitted tool calls and was dropped) and all cells are in the repository.</p>

<h3>4.2 Models have habits, and share them</h3>
<p>With no wiki, independent agents of different families add a throwaway cache-buster value to the URL at very different rates, and several choose the same value.</p>
<figure>{fig_fp}<figcaption>Figure 2. Share of independent agents that add a cache-buster value, by model family (three runs of 30 agents each).</figcaption></figure>
{t_fp}
<p>A value shared across vendors (here <code>bust=1</code>) is weak evidence of copying even between different models, so a matcher needs the base rate per value. Same-family and cross-family collision rates for these open models were similar ({H3.get('mean_within', 'n/a')} vs {H3.get('mean_cross', 'n/a')}; a difference interval of {H3.get('diff_ci95')}), so our earlier single-seed result for Claude Sonnet (<code>x=1</code>, never matched by the open models) did not generalise as a within-family effect; what does generalise is that models differ in <i>whether</i> they add a value at all. A naive-Bayes classifier using the first value, the first mirror tried and the number of fetches names a model&rsquo;s family {pc(nb_acc)} of the time against {pc(nb_chance, 1)} by chance (leave-one-run-out).</p>

<h3>4.3 Whether a tag survives depends on the model</h3>
<figure>{fig_tags}<figcaption>Figure 3. Share of copiers whose submission still carries the tag, by model family, pooled over wiki worlds.</figcaption></figure>
{t_h1}
<p>We stated in advance that load-bearing tokens would survive at least 90% of copies and inert tags at most 10%. {h1_verdict} Inert survival ranged from {in_rng} and load-bearing from {lb_rng}, so neither number is a property of the tag; both are a property of how the copier copies.</p>
<p><b>Tags trace the artifact, not the idea.</b> A typical Qwen3-235B run is <i>list pages, read the page, fetch the wiki&rsquo;s link, submit</i>: it copies the link verbatim, so both kinds of tag ride along. DeepSeek, Kimi and GLM instead read the wiki to learn the <i>method</i> and then redo it: they fetch the mirror&rsquo;s root to obtain their own session and use that, so the wiki&rsquo;s token is bypassed even though the link needs <i>a</i> token, because our mirror hands sessions to anyone. We count those agents as copiers of the behaviour (they were served the route first) and the tag, correctly, does not follow them. The design rule that follows is that the token must be the only way in: a gateway that grants access only through served copies makes surviving the copy a condition of success (tested in section 4.7). Where access can be re-derived, a careful agent leaves no tag trail, and that is a limit of the approach, not of this implementation.</p>

<h3>4.4 What tags buy</h3>
<p>We compare tags with the best simple edit-log rule for each cell (blame the earliest teammate who wrote the same link, the latest, or a uniform pick, whichever scores highest), because comparing with a single heuristic overstates the benefit: in these swarms agents mostly copy the first link on a page, which makes &ldquo;blame the latest&rdquo; nearly worthless and &ldquo;blame the earliest&rdquo; surprisingly good. The tag tracer is the fair combination: read the token where it survived, and use the same best rule where it did not. (An earlier version of our analysis let the tag tracer fall back to &ldquo;latest&rdquo; while the baseline got the better rule; it made tags look harmful for four of the models, and was a flaw in the comparison, not in the tags.)</p>
<figure>{fig_attr}<figcaption>Figure 4. Share of copies whose immediate source is named correctly, by model family (load-bearing cells; families with at least 20 copiers). Orange: read the token where it survived, else apply the same best simple rule.</figcaption></figure>
{t_h2}
<p>Against the best simple rule, the lift is {lift_txt}, and it tracks tag survival: gain &asymp; s(1&minus;C<sub>0</sub>), as the theory predicts. Tags transform attribution for models that copy links verbatim and add little for models that redo the work, whose copying the edit log already traces fairly well with the right rule (about 0.6 here). A tracer that learns the copiers&rsquo; habit from data can approach the edit-log ceiling; tags give exactness without learning it, but only where the artifact itself is copied.</p>

<h3>4.5 A bad tip</h3>
{t_h4}
{bad_tip_families}
<p>For the core model (the only family with enough early-tip runs for a source-attribution comparison), when the tip is there from the start every agent adopts it and the cascade is deep (six to nine hops in our runs), while the best edit-log rule names only a small share of immediate sources. When it arrives late, adoption varies sharply from run to run, from nearly none to nearly all, so we report it with run-level intervals and do not attribute the differences between tag conditions to the tags. <b>Finding the origin of a single-source tip did not need tags</b>: the earliest writer of that link is the origin (trace precision and recall close to 1). Tags are needed for the exact chain, which determines who infected whom, and they do not depend on how the copiers choose.</p>
{clean_txt}
{t_clean}

<h3>4.6 Swarm size, a stronger model, and mixed swarms</h3>
{('<p>Swarm size:</p>' + t_size) if t_size else '<p class="small">Size sweep: not available in this build.</p>'}
{('<p>Mixed-family swarms:</p>' + t_mix) if t_mix else ''}
{('<p>' + mix_txt + '</p>') if mix_txt else ''}
{('<p>A stronger model from the core family (Qwen3.5-397B) against the core model:</p>' + t_strong) if t_strong else ''}

{('<h3>4.7 Making the token the only way in</h3>' + gated_txt + t_gated) if gated_txt else ''}

<h2>5. Tools</h2>
<ul>
<li><b>Report card</b> (<code>python -m backend.cli report --file logs.jsonl</code>, and a browser page that runs entirely locally). Input: one JSON object per line with agent, time, channel, content. Output: a grade, carrier coverage, the best possible top-1, naive vs calibrated copy calls, the most-shared strings, and what to log next. On the incident sample it gives D (37% coverage; 5,688 naive calls, 999 calibrated); on two AI Village weeks, A (one shared chat) and B (a week just after rooms launched, one of the lowest-coverage weeks); for lab swarms with no distinctive strings, N/A, never a grade. The browser port matches the Python reference on all test fixtures.</li>
<li><b>Colony</b> (a browser page, local only): load any swarm log, including a lab run with its hidden read log, and watch it as an ant colony. Every agent is an ant, trails form as agents pick things up from each other, and a click traces an ant back to what it read and forward to everyone downstream of it (the re-check list). Its tracing core is the report card&rsquo;s, and a test requires the two to count copies identically.</li>
<li><b>Canary kit</b> (<code>backend/canary.py</code>): stamp each served copy with a token, gate the destination on it, resolve any later artifact to the copy it came from.</li>
<li><b>Agloe-Bench</b>: {sp.get('bench_cells', 'many')} lab cells with the edit log as input, the hidden key, the tag registry for the tag track, and a standard-library scorer with five baselines and cell-level bootstrap intervals.</li>
</ul>
{bench_txt}
<div class="box"><b>Investigator&rsquo;s checklist.</b> (1) Log reads, not just writes. (2) Give every served copy its own token, one the destination needs. (3) Before calling a match copying, check the value&rsquo;s base rate; different models share conventions. (4) Learn your agents&rsquo; habits (first link, newest, verify). (5) Report the ceiling: &ldquo;untraceable from these logs&rdquo; is a finding. (6) A bad tip can take over a swarm: check outputs as well as sources.</div>

<h2>6. What did not work, and limits</h2>
<ul>
<li>A claim that the swarm follows an ant-colony trail law fell apart once per-method quality was controlled (exponent 0.8, not 1.5); it was quality, not herding.</li>
<li>Our first planted-bad-tip worlds were wrong, three times: the tip stated the value, so agents submitted it without fetching; the tip sat on a page nobody read (agents list pages and read one); and the stale mirror warned about itself, so agents corrected. We set those runs aside and say so. A late tip is mostly ignored by the model we used for the core runs, which prefer the first link; a late-tip result therefore describes that habit.</li>
<li>Pooling worlds hid regimes, and a recency rule for the answer key mislabelled agents that re-read pages; both are fixed and the key now prefers the exact served copy.</li>
<li>Scope: one narrow offline task; open models on one provider (earlier Claude runs are single-seed); exposure rather than intent; the incident data is used as aggregates only.</li>
</ul>

<h2>7. Related work</h2>
<p>Inferring who infected whom from cascades (NetInf and NetRate, trace complexity); phylogenies of chain letters and memes; stemmatology (shared errors identify descent); forensic match probabilities (the base rate of a trait matters); canary traps and traitor tracing, canary tokens and honeytokens, copyright traps; and recent work on agent provenance and failure attribution in multi-agent systems. What is new here is the traceability ceiling for edit-log-only swarms, the coincidence calibration against model habits, and a live-agent measurement of tag survival.</p>

<h2>8. Ethics and reproducibility</h2>
<p>All runs are offline against reserved domains; nothing was tested on anyone&rsquo;s live system, and the report card runs locally and never sees anyone&rsquo;s logs. Incident and AI Village data are used under their owners&rsquo; terms, as aggregates; AI Village is cited as AI Digest, &ldquo;AI Village dataset&rdquo;, 2026. The lab spent ${sp.get('lab_usd', 0):.0f} on open-model API calls; every number here is read from <code>docs/RESULTS.md</code> and the files it names, and the tests pass.</p>
"""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Agloe: What Swarm Logs Can&rsquo;t Tell You</title><style>{css}</style></head><body>{body}</body></html>'


def build_pdf(html_path: Path, pdf_path: Path) -> bool:
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.exists():
        print("Edge not found; open paper/agloe.html and print to PDF")
        return False
    subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, timeout=120, capture_output=True)
    return pdf_path.exists()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    PAPER.mkdir(exist_ok=True)
    (PAPER / "agloe.html").write_text(build(), encoding="utf-8")
    print("-> paper/agloe.html")
    if a.pdf:
        print("-> paper/agloe.pdf" if build_pdf(PAPER / "agloe.html", PAPER / "agloe.pdf") else "pdf failed")


if __name__ == "__main__":
    main()
