"""agloe command line.

  python -m backend.cli report --file swarm_logs.jsonl            (any swarm: {agent,time,channel,content} per line)
  python -m backend.cli report --dataset collusion|ai_village|lab [--lo --hi | --path world.json]
  python -m backend.cli audit  --adapter dsewiki [--method KEY] [--min-adopters 20]
  python -m backend.cli audit  --adapter jsonl --file adoptions.jsonl     (fields: agent,t,loc,order,key)
  python -m backend.cli bench  [--seeds 12]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.analysis.audit import Adoption, audit_behavior, audit_many, summarize

ROOT = Path(__file__).resolve().parents[1]


def load_rows(args) -> list[Adoption]:
    if args.adapter == "dsewiki":
        from backend.adapters.german_wiki import adoptions
        return adoptions(ROOT / "data" / "raw" / "german", ROOT / "data" / "out" / "sig_events.jsonl.gz")
    rows = []
    for line in open(args.file, encoding="utf-8"):
        d = json.loads(line)
        rows.append(Adoption(d["agent"], d["t"], d["loc"], int(d["order"]), d.get("key", "")))
    return rows


def fmt(a: dict) -> str:
    return (f"{a['name'][:70]}\n  adopters={a['adopters']}  no visible carrier={a['no_visible_carrier']} ({a['share_no_carrier']:.0%})  "
            f"1 carrier={a['one_carrier']}  2+={a['two_or_more']}\n  best possible top-1 accuracy={a['ceiling_top1']:.1%}  "
            f"top-3={a['ceiling_top3']:.1%}  (among those with a visible carrier: {a['ceiling_top1_among_visible']:.1%})\n  "
            f"if item-level reads were logged for: " + ", ".join(f"{float(k):.0%} of copies -> {v:.1%}" for k, v in a["with_reads"].items()))


def run_neutral(lr: float) -> None:
    import gzip
    from backend.adapters.german_wiki import load_jsonl_gz, load_revisions
    from backend.analysis.markers import find_pairs, read_map
    from backend.analysis.neutral import Write, summarize
    raw = ROOT / "data" / "raw" / "german"
    rows = [json.loads(l) for l in gzip.open(ROOT / "data" / "out" / "sig_events.jsonl.gz", "rt", encoding="utf-8")]
    W = [Write(r["label"], r["time"], (r["time"], r["rev_id"]), r["page_id"], r["url"]) for r in rows if r["label"] and not r["generated_page"]]
    S = summarize(W, lr_threshold=lr)
    sv, cc = S["survival"], S["copy_or_coincidence"]
    print(f"URL writes by named agents: {S['writes']:,};  reuses of another agent's URL that carries an inert value: {S['reuse_events']:,}")
    print(f"\nSurvival of the earlier inert value (the 'trap street' ingredient):")
    print(f"  all: {sv['raw']:.1%} (95% CI {sv['raw_ci'][0]:.1%}-{sv['raw_ci'][1]:.1%});  after removing chance matches: {sv['chance_corrected']:.1%}")
    for k, v in sv["by_class"].items():
        print(f"  {k:15s} n={v['n']:5d}  kept {v['rate']:.1%} (CI {v['ci'][0]:.1%}-{v['ci'][1]:.1%})")
    print(f"\nCopy or coincidence (a match counts as copying only if LR = 1/p_v >= {lr:g}):")
    print(f"  naive copy calls {cc['naive_copy_calls']:,};  supported {cc['calibrated_copy_calls']:,};  declined as weak evidence {cc['declined_as_weak_evidence']:,};"
          f"  expected pure coincidences among naive calls ~{cc['expected_coincidences_among_naive']:.0f}")
    print("\n'AI can't be random' - inert values written by the most agents:")
    for v in S["shared_values"][:12]:
        print(f"  {v['param']}={v['value'][:22]:22s} agents={v['agents']:3d}  base rate p={v['p']:.3f}  {'(LLM focal value)' if v['focal'] else ''}")
    print("  collision probability by parameter:", S["collision_by_param"])
    revs = load_revisions(raw)
    fam = {p["page_id"]: p.get("page_family", "?") for p in load_jsonl_gz(raw / "pages.jsonl.gz")}
    M = read_map(find_pairs(revs), fam)
    print(f"\nHidden read map from marker copies: {M['copies']} copies, {M['off_page_share']:.0%} read from a page other than the one edited")
    print("  top source pages:", M["source_pages"][:5])
    print("  family flows (source family -> copier family, n):", M["family_flows"][:8])
    print(f"  cross-team jumps: {len(M['cross_team'])}")
    out = ROOT / "data" / "out" / "neutral.json"
    S.pop("_events", None)
    out.write_text(json.dumps({"summary": S, "read_map": M}, indent=1, default=str), encoding="utf-8")
    print(f"\n-> {out} (local only; gitignored)")


def run_report(args) -> None:
    """Swarm Traceability Report Card for any log file, or for one of the built-in datasets."""
    from backend.analysis import report as R
    if args.file:
        ev, name = R.load_events(args.file), Path(args.file).name.split(".")[0]
    elif args.dataset == "collusion":
        ev, name = R.events_from_collusion(ROOT / "data" / "raw" / "german"), "collusion"
    elif args.dataset == "ai_village":
        ev, name = R.events_from_ai_village(ROOT / "data" / "raw" / "ai_village", args.lo, args.hi), f"ai_village_{args.lo}_{args.hi}"
    elif args.dataset == "lab":
        if not args.path:
            raise SystemExit("--dataset lab needs --path data/lab/<cell>/world.json")
        ev, name = R.events_from_lab(args.path), "lab_" + Path(args.path).parent.name
    else:
        raise SystemExit("give --file logs.jsonl or --dataset collusion|ai_village|lab")
    card = R.report_card(ev)
    pub = R.public(card)
    out = ROOT / "data" / "out" / f"report_{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pub, indent=1), encoding="utf-8")
    print(json.dumps(pub, indent=1) if args.json else R.render(card, args.title or name))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="agloe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit"); au.add_argument("--adapter", choices=["dsewiki", "jsonl"], default="dsewiki")
    au.add_argument("--file"); au.add_argument("--method"); au.add_argument("--min-adopters", type=int, default=20)
    au.add_argument("--json", action="store_true")
    be = sub.add_parser("bench"); be.add_argument("--seeds", type=int, default=12)
    sub.add_parser("markers")
    nu = sub.add_parser("neutral"); nu.add_argument("--lr", type=float, default=100.0)
    rp = sub.add_parser("report", help="Swarm Traceability Report Card (schema: backend/analysis/report.py)")
    rp.add_argument("--file", help="JSONL[.gz] of {agent,time,channel,content} events")
    rp.add_argument("--dataset", choices=["collusion", "ai_village", "lab"])
    rp.add_argument("--lo", default="2026-01-12"); rp.add_argument("--hi", default="2026-01-23")
    rp.add_argument("--path", help="world.json for --dataset lab"); rp.add_argument("--title")
    rp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "report":
        run_report(args); return
    if args.cmd == "neutral":
        run_neutral(args.lr); return
    if args.cmd == "markers":
        from backend.adapters.german_wiki import load_revisions
        from backend.analysis.markers import find_pairs, wilson
        revs = load_revisions(ROOT / "data" / "raw" / "german")
        for wo, ms in ((True, 0.0), (True, 0.6), (True, 0.8), (False, 0.6), (False, 0.8)):
            ps = find_pairs(revs, wrapper_only=wo, min_sim=ms); n = len(ps)
            a = sum(p["source_visible_on_page"] for p in ps); b = sum(p["any_writer_visible"] for p in ps)
            print(f"wrapper_only={wo!s:5} min_sim={ms:.1f}  copies={n:3d}  source visible on page {a/n:5.1%}  any writer visible {b/n:5.1%} (CI {wilson(b,n)[0]:.0%}-{wilson(b,n)[1]:.0%})")
        return
    if args.cmd == "bench":
        from backend.bench import run
        sys.argv = ["run", "--seeds", str(args.seeds)]; run.main(); return
    rows = load_rows(args)
    if args.method:
        res = audit_behavior([r for r in rows if r.key == args.method], args.method)
        print(json.dumps(res, indent=1) if args.json else fmt(res)); return
    audits = audit_many(rows, args.min_adopters); tot = summarize(audits)
    if args.json:
        print(json.dumps({"summary": tot, "behaviors": audits}, indent=1)); return
    print(f"Pooled over {tot['behaviors']} behaviors with >= {args.min_adopters} named adopters ({tot['adopters']} adopters):")
    print(f"  no visible carrier: {tot['share_no_carrier']:.0%}   best possible top-1: {tot['ceiling_top1']:.1%}   top-3: {tot['ceiling_top3']:.1%}"
          f"   median behavior: {tot['median_behavior_ceiling']:.1%}\n")
    for a in audits[:8]:
        print(fmt(a)); print()


if __name__ == "__main__":
    main()
