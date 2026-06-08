"""
Single-command entry point for the ADK TSR workflow.

    # Generate a TSR from a PDF (offline-capable with --dry-run)
    python -m adk_agent --pdf record.pdf --out report.docx
    python -m adk_agent --pdf record.pdf --dry-run
    python -m adk_agent --pdf record.pdf --engine graph

    # Generate from a live AnyRoR survey (scrape -> PDF -> TSR)
    python -m adk_agent --survey "Kutch/Abdasa/Keshav/150" --out report.docx

    # Feedback loop: import a lawyer-corrected ground truth
    python -m adk_agent feedback import --run <run_id> --truth ground_truth.json

    # Evaluate the extractor against the golden dataset
    python -m adk_agent eval

    # Inspect recent runs / learned guidelines
    python -m adk_agent runs
    python -m adk_agent guidelines
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from adk_agent.config import get_adk_config

_SUBCOMMANDS = {"run", "feedback", "eval", "optimize", "runs", "guidelines"}


# --------------------------------------------------------------------- helpers
def _parse_survey(s: str) -> dict:
    parts = [p.strip() for p in s.split("/")]
    if len(parts) != 4:
        raise SystemExit(
            "Error: --survey must be 'District/Taluka/Village/SurveyNo' (4 parts)."
        )
    return {"district": parts[0], "taluka": parts[1], "village": parts[2], "survey_number": parts[3]}


def _config_from_args(args) -> "object":
    overrides = {}
    if getattr(args, "dry_run", False):
        overrides["dry_run"] = True
    if getattr(args, "model", None):
        overrides["model_name"] = args.model
    if getattr(args, "runs_dir", None):
        overrides["runs_dir"] = Path(args.runs_dir)
    if getattr(args, "optimize_dir", None):
        overrides["optimize_dir"] = Path(args.optimize_dir)
    return get_adk_config(refresh=True, **overrides)


def _print_run_summary(record, config) -> None:
    tt = record.token_totals
    print()
    print(f"  run id     : {record.run_id}")
    print(f"  status     : {record.status.upper()}" + (f"  ({record.error})" if record.error else ""))
    print(f"  engine     : {record.inputs.get('engine')}   mode: {record.mode}   "
          f"dry_run: {record.dry_run}   model: {record.model}")
    print("  skills     :")
    for s in record.skills:
        print(f"      - {s.name:<22} {s.status:<8} {s.duration_ms:>6} ms")
    print(f"  tokens     : prompt={tt['prompt_tokens']} response={tt['response_tokens']} "
          f"total={tt['total_tokens']}")
    if record.output:
        print(f"  TSR DOCX   : {record.output.get('tsr_path')}")
        print(f"  entries    : {record.output.get('entries_count')}   "
              f"findings: {record.output.get('findings_count')}   "
              f"types: {record.output.get('entry_types')}")
    print(f"  run dir    : {record.run_dir(config.runs_dir)}")
    print()


# -------------------------------------------------------------------- commands
def cmd_run(args) -> int:
    from adk_agent.pipeline import run_pipeline

    config = _config_from_args(args)
    if not args.pdf and not args.survey:
        raise SystemExit("Error: provide --pdf <file> or --survey 'D/T/V/S'.")
    if args.pdf and args.survey:
        raise SystemExit("Error: use either --pdf or --survey, not both.")

    mode = "survey" if args.survey else "pdf"
    survey = _parse_survey(args.survey) if args.survey else None
    output_path = args.out or "tsr_output.docx"

    if config.dry_run or not config.has_api_key:
        print("[dry-run] No GEMINI_API_KEY / --dry-run: using offline FakeGemini model.")

    print(f"Running TSR pipeline (engine={args.engine}, mode={mode}) …")
    record = asyncio.run(
        run_pipeline(
            config,
            mode=mode,
            output_path=output_path,
            pdf_path=args.pdf,
            survey=survey,
            engine=args.engine,
        )
    )
    _print_run_summary(record, config)
    return 0 if record.status == "success" else 1


def cmd_feedback(args) -> int:
    if args.feedback_cmd != "import":
        raise SystemExit("Usage: python -m adk_agent feedback import --run <id> --truth <json>")
    from adk_agent.feedback.import_fixes import import_fixes

    config = _config_from_args(args)
    report = import_fixes(config, run=args.run, truth=args.truth, update_eval=not args.no_eval)
    print(f"Imported corrections for run {report['run']}:")
    print(f"  corrections        : {report['num_corrections']}  {report['corrections_by_kind']}")
    print(f"  guidelines updated : {report['guidelines_added_or_updated']} -> {report['guidelines_md']}")
    print(f"  golden eval set    : {report['golden_evalset']}")
    print(f"  report             : {report['report_path']}")
    return 0


def cmd_eval(args) -> int:
    from adk_agent.eval.run_eval import evaluate_golden

    config = _config_from_args(args)
    report = asyncio.run(evaluate_golden(config, live=not args.no_live, limit=args.limit))
    agg = report["aggregate"]
    print("Golden-set evaluation:")
    print(f"  model    : {report['model']}   dry_run: {report['dry_run']}   live: {report['live']}")
    if agg.get("cases"):
        print(f"  cases    : {agg['cases']}")
        print(f"  field_accuracy : {agg['field_accuracy']}")
        print(f"  entry_recall   : {agg['entry_recall']}")
        print(f"  type_accuracy  : {agg['type_accuracy']}")
        print(f"  total_corrections : {agg['total_corrections']}")
    else:
        print("  (no golden cases yet — import a lawyer-corrected run first)")
    print(f"  report   : {report['report_path']}")
    return 0


def cmd_optimize(args) -> int:
    from adk_agent.optimize.gate import RegressionGate
    from adk_agent.optimize.loop import promote_best, revert_active, run_optimization, show_active

    config = _config_from_args(args)

    if args.show:
        profile = show_active(config)
        if profile is None:
            print(f"(no active profile — runs use the production 'full' prompt)\n  {config.active_profile_path}")
        else:
            print(f"Active prompt profile ({config.active_profile_path}):\n")
            print(json.dumps(profile.to_dict(), indent=2))
        return 0

    if args.revert:
        reverted = revert_active(config)
        print("Reverted to the production 'full' prompt." if reverted
              else "(no active profile to revert)")
        return 0

    if config.dry_run or not config.has_api_key:
        print("[dry-run] No GEMINI_API_KEY / --dry-run: token savings are real but "
              "accuracy is measured against the offline FakeGemini, not real quality.")

    gate = RegressionGate(field_tol=args.field_tol, recall_tol=args.field_tol,
                          type_tol=args.field_tol, min_token_saving_pct=args.min_saving)
    print(f"Optimizing extraction (corpus={args.corpus or 'golden+sample'}, "
          f"max_iters={args.max_iters or 'all'}) …")
    report = asyncio.run(run_optimization(
        config, corpus_dir=args.corpus, include_golden=not args.no_golden,
        include_sample=not args.no_sample, limit=args.limit, max_iters=args.max_iters, gate=gate,
    ))

    if not report.get("cases"):
        print(f"\n  {report.get('note')}")
        return 1

    b, w = report["baseline"], report["winner"]
    print()
    print(f"  cases            : {report['cases']}  {report['case_modes']}")
    print(f"  baseline tokens  : {b['avg_total_tokens']}   winner: {w['avg_total_tokens']}")
    print(f"  TOKEN SAVINGS    : {report['token_savings_pct']}%   "
          f"latency: {report['latency_savings_pct']}%")
    print(f"  accuracy held    : {report['accuracy_held']}   "
          f"(field {b['field_accuracy']}→{w['field_accuracy']}, "
          f"entry {b['entry_recall']}→{w['entry_recall']}, type {b['type_accuracy']}→{w['type_accuracy']})")
    print(f"  accepted levers  : {report['accepted_levers'] or '(none — baseline already optimal)'}")
    print(f"  report           : {report.get('report_md_path')}")

    if args.apply:
        if report["improved"]:
            path = promote_best(config)
            print(f"\n  PROMOTED winner -> {path}\n  (all future runs use it; revert with "
                  f"'python -m adk_agent optimize --revert')")
        else:
            print("\n  --apply: nothing to promote (baseline was already optimal).")
    elif report["improved"]:
        print("\n  Re-run with --apply to promote the winning profile into production.")
    return 0


def cmd_runs(args) -> int:
    config = _config_from_args(args)
    runs_dir = Path(config.runs_dir)
    if not runs_dir.exists():
        print(f"(no runs yet under {runs_dir})")
        return 0
    rows = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        rec = d / "record.json"
        if not rec.exists():
            continue
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append((data.get("run_id", d.name), data.get("status", "?"), data.get("mode", "?"),
                     (data.get("output") or {}).get("entries_count", "-")))
    if not rows:
        print(f"(no runs yet under {runs_dir})")
        return 0
    print(f"Recent runs in {runs_dir}:")
    print(f"  {'run_id':<24} {'status':<8} {'mode':<8} entries")
    for run_id, status, mode, entries in rows[: args.limit]:
        print(f"  {run_id:<24} {status:<8} {mode:<8} {entries}")
    return 0


def cmd_guidelines(args) -> int:
    from adk_agent.feedback.guidelines_store import render_guidelines_for_prompt

    config = _config_from_args(args)
    text = render_guidelines_for_prompt(config)
    if not text:
        print("(no learned guidelines yet — import a lawyer-corrected run first)")
        return 0
    print("Learned guidelines injected into the extraction prompt:\n")
    print(text)
    return 0


# ----------------------------------------------------------------------- parse
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adk_agent", description="Gujarat TSR — Google ADK workflow")
    sub = p.add_subparsers(dest="command")

    # run (default)
    run = sub.add_parser("run", help="Run the E2E pipeline (PDF or survey -> TSR DOCX)")
    src = run.add_argument_group("input")
    src.add_argument("--pdf", help="Path to a land-record PDF")
    src.add_argument("--survey", help="'District/Taluka/Village/SurveyNo' (live AnyRoR scrape)")
    run.add_argument("--out", "-o", help="Output DOCX path (default: tsr_output.docx)")
    run.add_argument("--engine", choices=["pipeline", "graph"], default="pipeline",
                     help="Orchestration engine (default: pipeline; 'graph' = ADK 2.0 Workflow runtime)")
    run.add_argument("--dry-run", action="store_true", help="Run offline with the FakeGemini model")
    run.add_argument("--model", help="Override the Gemini model id")
    run.add_argument("--runs-dir", help="Override the run-records directory")
    run.set_defaults(func=cmd_run)

    # feedback import
    fb = sub.add_parser("feedback", help="Import lawyer corrections into prompts + golden set")
    fbsub = fb.add_subparsers(dest="feedback_cmd")
    imp = fbsub.add_parser("import", help="Import a corrected ground truth for a run")
    imp.add_argument("--run", required=True, help="Run id (or path to a run dir)")
    imp.add_argument("--truth", required=True, help="Path to the lawyer-corrected ground-truth JSON")
    imp.add_argument("--no-eval", action="store_true", help="Do not add the run to the golden eval set")
    imp.add_argument("--runs-dir", help="Override the run-records directory")
    fb.set_defaults(func=cmd_feedback)

    # eval
    ev = sub.add_parser("eval", help="Evaluate the extractor against the golden dataset")
    ev.add_argument("--no-live", action="store_true", help="Score stored extractions instead of re-running")
    ev.add_argument("--limit", type=int, default=None, help="Only evaluate the first N cases")
    ev.add_argument("--dry-run", action="store_true", help="Use the offline FakeGemini model")
    ev.add_argument("--model", help="Override the Gemini model id")
    ev.add_argument("--runs-dir", help="Override the run-records directory")
    ev.set_defaults(func=cmd_eval)

    # optimize
    opt = sub.add_parser(
        "optimize",
        help="Search prompt profiles for token/latency savings with no accuracy regression",
    )
    opt.add_argument("--corpus", help="Directory of land-record PDFs to evaluate against (parity mode)")
    opt.add_argument("--no-golden", action="store_true", help="Skip the lawyer-truth golden cases")
    opt.add_argument("--no-sample", action="store_true", help="Skip the bundled sample PDF")
    opt.add_argument("--limit", type=int, default=None, help="Only evaluate the first N cases")
    opt.add_argument("--max-iters", type=int, default=None, help="Only try the first M efficiency levers")
    opt.add_argument("--min-saving", type=float, default=1.0,
                     help="Min %% token saving for a lever to count as a win (default: 1.0)")
    opt.add_argument("--field-tol", type=float, default=1e-9,
                     help="Allowed accuracy drop before a lever is rejected (default: ~0, strict)")
    opt.add_argument("--apply", action="store_true", help="Promote the winning profile into production")
    opt.add_argument("--revert", action="store_true", help="Clear the active profile (back to 'full')")
    opt.add_argument("--show", action="store_true", help="Print the active (promoted) profile and exit")
    opt.add_argument("--dry-run", action="store_true", help="Use the offline FakeGemini model")
    opt.add_argument("--model", help="Override the Gemini model id")
    opt.add_argument("--optimize-dir", help="Override the optimizer artifacts directory")
    opt.set_defaults(func=cmd_optimize)

    # runs
    rn = sub.add_parser("runs", help="List recent runs")
    rn.add_argument("--limit", type=int, default=20)
    rn.add_argument("--runs-dir", help="Override the run-records directory")
    rn.set_defaults(func=cmd_runs)

    # guidelines
    gd = sub.add_parser("guidelines", help="Show learned guidelines injected into the prompt")
    gd.set_defaults(func=cmd_guidelines)

    return p


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Allow `python -m adk_agent --pdf x` (no explicit `run` subcommand).
    if argv and argv[0] not in _SUBCOMMANDS and not argv[0] in ("-h", "--help"):
        argv = ["run"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
