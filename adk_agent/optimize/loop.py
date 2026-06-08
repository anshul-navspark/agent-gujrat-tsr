"""
The optimization loop — measure -> gate -> promote.

``run_optimization`` runs the baseline (production ``full`` profile) once, then
greedily tries each efficiency lever in turn, **compounding** the ones the
regression gate accepts. Because the gate only accepts equal-or-better accuracy
with strictly fewer tokens/latency, the resulting profile is guaranteed not to
regress accuracy versus the baseline on the evaluation corpus.

It is deterministic and bounded (a fixed, finite lever list — no runaway API
spend), resumable-by-inspection (every evaluation is appended to
``leaderboard.jsonl``), and reversible (the winner is written to
``best_profile.json``; promotion to the live ``active_profile.json`` is an
explicit, undoable step).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.optimize.dataset import load_cases
from adk_agent.optimize.gate import GateDecision, RegressionGate
from adk_agent.optimize.harness import (
    ProfileResult,
    build_references,
    run_profile,
    score_runs,
)
from adk_agent.optimize.profiles import (
    FULL_PROFILE,
    PromptProfile,
    lever_candidates,
    load_active_profile,
    save_active_profile,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _leaderboard_row(result: ProfileResult, lever: Optional[str], decision: Optional[GateDecision]) -> Dict[str, Any]:
    row = {"lever": lever, "profile": result.profile.to_dict(), **result.summary()}
    if decision is not None:
        row["gate"] = decision.to_dict()
    return row


async def run_optimization(
    config: Optional[AdkConfig] = None,
    *,
    corpus_dir: Optional[str] = None,
    include_golden: bool = True,
    include_sample: bool = True,
    limit: Optional[int] = None,
    max_iters: Optional[int] = None,
    gate: Optional[RegressionGate] = None,
) -> Dict[str, Any]:
    """Run the full optimization loop; return a summary dict and write artifacts."""
    config = config or get_adk_config()
    config.ensure_dirs()
    gate = gate or RegressionGate()

    cases = load_cases(
        config, corpus_dir=corpus_dir, include_golden=include_golden,
        include_sample=include_sample, limit=limit,
    )
    out_dir = Path(config.optimize_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not cases:
        report = {
            "created_at": _now(), "cases": 0,
            "note": "No evaluation cases. Add a corpus dir of PDFs (--corpus) or "
                    "import a lawyer-corrected run into the golden set first.",
        }
        (out_dir / "last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # --- Baseline: run the production "full" profile once. ---
    baseline_runs = await run_profile(config, FULL_PROFILE, cases)
    references = build_references(cases, baseline_runs)
    baseline_result = score_runs(FULL_PROFILE, baseline_runs, references)

    rows: List[Dict[str, Any]] = [_leaderboard_row(baseline_result, lever="baseline", decision=None)]

    # --- Greedy lever search, compounding accepted levers. ---
    levers = lever_candidates()
    if max_iters is not None:
        levers = levers[:max_iters]

    best_profile = FULL_PROFILE
    best_result = baseline_result
    best_changes: Dict[str, Any] = {}
    applied: List[str] = []

    for lever_name, changes in levers:
        trial_changes = {**best_changes, **changes}
        trial_name = "+".join(["full", *applied, lever_name])
        candidate = FULL_PROFILE.with_levers(
            name=trial_name,
            description="Optimized: full prompt + " + ", ".join([*applied, lever_name]),
            **trial_changes,
        )

        cand_runs = await run_profile(config, candidate, cases)
        cand_result = score_runs(candidate, cand_runs, references)
        decision = gate.evaluate(best_result, cand_result)
        rows.append(_leaderboard_row(cand_result, lever=lever_name, decision=decision))

        if decision.accepted:
            best_profile, best_result, best_changes = candidate, cand_result, trial_changes
            applied.append(lever_name)

    # Final winner vs the original baseline.
    final_decision = gate.evaluate(baseline_result, best_result)

    # --- Persist artifacts. ---
    (out_dir / "leaderboard.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    save_active_profile(out_dir / "best_profile.json", best_profile)

    report = {
        "created_at": _now(),
        "model": str(config.model_name),
        "dry_run": config.dry_run or not config.has_api_key,
        "cases": len(cases),
        "case_modes": _mode_counts(cases),
        "gate": {
            "field_tol": gate.field_tol, "recall_tol": gate.recall_tol,
            "type_tol": gate.type_tol, "min_token_saving_pct": gate.min_token_saving_pct,
        },
        "baseline": baseline_result.summary(),
        "winner": best_result.summary(),
        "winner_profile": best_profile.to_dict(),
        "winner_model": best_result.model or str(config.model_name),
        "accepted_levers": applied,
        "cost_savings_pct": round(-final_decision.cost_delta_pct, 2),
        "token_savings_pct": round(-final_decision.token_delta_pct, 2),
        "latency_savings_pct": round(-final_decision.latency_delta_pct, 2),
        "accuracy_held": final_decision.accuracy_ok,
        "improved": best_profile.name != "full",
        "best_profile_path": str(out_dir / "best_profile.json"),
        "leaderboard_path": str(out_dir / "leaderboard.jsonl"),
    }
    (out_dir / "last_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "report.md").write_text(_render_markdown(report, rows), encoding="utf-8")
    report["report_md_path"] = str(out_dir / "report.md")
    return report


def _mode_counts(cases) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in cases:
        out[c.mode] = out.get(c.mode, 0) + 1
    return out


def _render_markdown(report: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    b, w = report["baseline"], report["winner"]
    lines = [
        "# TSR extraction optimization report",
        "",
        f"- created: {report['created_at']}",
        f"- model: `{report['model']}`  •  dry_run: {report['dry_run']}",
        f"- cases: **{report['cases']}** {report['case_modes']}",
        f"- gate: accuracy non-decreasing (tol {report['gate']['field_tol']}), "
        f"min token saving {report['gate']['min_token_saving_pct']}%",
        "",
        "## Result",
        "",
        f"- **cost savings: {report['cost_savings_pct']}%**  "
        f"(baseline ${b['avg_cost_usd']} → winner ${w['avg_cost_usd']} avg / doc; "
        f"model `{b.get('model') or report['model']}` → `{report['winner_model']}`)",
        f"- token savings: {report['token_savings_pct']}%  "
        f"(baseline {b['avg_total_tokens']} → winner {w['avg_total_tokens']} avg total tokens)",
        f"- latency savings: {report['latency_savings_pct']}%  "
        f"(baseline {b['avg_latency_ms']} → winner {w['avg_latency_ms']} ms)",
        f"- accuracy held: **{report['accuracy_held']}**  "
        f"(field {b['field_accuracy']}→{w['field_accuracy']}, "
        f"entry {b['entry_recall']}→{w['entry_recall']}, type {b['type_accuracy']}→{w['type_accuracy']})",
        f"- accepted levers: {report['accepted_levers'] or '(none — baseline already optimal on this corpus)'}",
        "",
        "## Leaderboard",
        "",
        "| lever | model | field | entry | type | total_tok | $/doc | latency_ms | gate |",
        "| ----- | ----- | ----- | ----- | ---- | --------- | ----- | ---------- | ---- |",
    ]
    for r in rows:
        g = r.get("gate") or {}
        verdict = "baseline" if r["lever"] == "baseline" else ("✅ accept" if g.get("accepted") else "—")
        lines.append(
            f"| {r['lever']} | {r.get('model', '')} | {r['field_accuracy']} | {r['entry_recall']} | "
            f"{r['type_accuracy']} | {r['avg_total_tokens']} | {r['avg_cost_usd']} | "
            f"{r['avg_latency_ms']} | {verdict} |"
        )
    lines += [
        "",
        "## Winning profile",
        "",
        "```json",
        json.dumps(report["winner_profile"], indent=2, ensure_ascii=False),
        "```",
        "",
        "Promote it with `python -m adk_agent optimize --apply` (revert with `--revert`).",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Promote / revert / show the active (live) profile.
# --------------------------------------------------------------------------- #

def promote_best(config: Optional[AdkConfig] = None) -> Optional[Path]:
    """Copy the last run's winning profile to the live ``active_profile.json``."""
    config = config or get_adk_config()
    best_path = Path(config.optimize_dir) / "best_profile.json"
    profile = load_active_profile(best_path)
    if profile is None:
        return None
    return save_active_profile(config.active_profile_path, profile)


def revert_active(config: Optional[AdkConfig] = None) -> bool:
    """Remove the live profile so runs fall back to the production ``full`` prompt."""
    config = config or get_adk_config()
    p = Path(config.active_profile_path)
    if p.exists():
        p.unlink()
        return True
    return False


def show_active(config: Optional[AdkConfig] = None) -> Optional[PromptProfile]:
    config = config or get_adk_config()
    return load_active_profile(config.active_profile_path)
