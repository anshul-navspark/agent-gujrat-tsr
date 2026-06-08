"""
Structured evaluator — score the extractor against ground truth.

``score_extraction(model, truth)`` computes per-case metrics (field accuracy,
entry recall, entry-type accuracy) by reusing the feedback diff engine.
``evaluate_golden(...)`` re-runs the extractor over every golden case and reports
an aggregate — a single regression number to watch as prompts/guidelines change.

In dry-run (no API key) the offline FakeGemini is used, so scores reflect the
canned payload rather than real accuracy — useful for wiring tests, not quality.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.eval.evalset import load_golden_cases
from adk_agent.feedback.diff import (
    ENTRY_FIELDS,
    LAND_FIELDS,
    _entries_by_number,
    diff_extractions,
)


def score_extraction(model: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    """Score a candidate extraction against ground truth."""
    corrections = diff_extractions(model, truth)
    t_entries = _entries_by_number(truth)
    n_truth = len(t_entries)

    missing = [c for c in corrections if c.kind == "missing_entry"]
    extra = [c for c in corrections if c.kind == "extra_entry"]
    matched = n_truth - len(missing)

    wrong_land = sum(1 for c in corrections if c.kind == "land_field")
    entry_field_corr = [
        c for c in corrections
        if c.scope == "entry" and c.kind not in ("missing_entry", "extra_entry")
    ]
    type_wrong = sum(1 for c in entry_field_corr if c.kind == "entry_type")

    total_land = len(LAND_FIELDS)
    total_entry_fields = matched * len(ENTRY_FIELDS)
    denom = total_land + total_entry_fields
    wrong = wrong_land + len(entry_field_corr)

    return {
        "field_accuracy": round(1.0 - (wrong / denom), 4) if denom else 1.0,
        "entry_recall": round(matched / n_truth, 4) if n_truth else 1.0,
        "type_accuracy": round((matched - type_wrong) / matched, 4) if matched else 1.0,
        "truth_entries": n_truth,
        "matched_entries": matched,
        "missing_entries": len(missing),
        "extra_entries": len(extra),
        "num_corrections": len(corrections),
    }


def _aggregate(per_case: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [c for c in per_case if c.get("score")]
    if not scored:
        return {"cases": 0}

    def mean(key: str) -> float:
        return round(sum(c["score"][key] for c in scored) / len(scored), 4)

    return {
        "cases": len(scored),
        "field_accuracy": mean("field_accuracy"),
        "entry_recall": mean("entry_recall"),
        "type_accuracy": mean("type_accuracy"),
        "total_corrections": sum(c["score"]["num_corrections"] for c in scored),
    }


async def evaluate_golden(
    config: Optional[AdkConfig] = None,
    *,
    live: bool = True,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Re-run the extractor over golden cases and score against ground truth."""
    config = config or get_adk_config()
    cases = load_golden_cases(config)
    if limit:
        cases = cases[:limit]

    from adk_agent.pipeline import extract_only  # lazy: avoids import cycle

    per_case: List[Dict[str, Any]] = []
    for case in cases:
        truth = case.get("expected_extraction") or {}
        pdf_text = case.get("pdf_text") or ""
        entry = {"eval_id": case.get("eval_id"), "score": None}
        if live and pdf_text:
            try:
                model = await extract_only(config, pdf_text)
                entry["score"] = score_extraction(model, truth)
            except Exception as e:  # pragma: no cover - surface but continue
                entry["error"] = str(e)
        elif not pdf_text:
            entry["error"] = "no pdf_text stored for this golden case (cannot re-run live)"
        per_case.append(entry)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": str(config.model_name),
        "dry_run": config.dry_run or not config.has_api_key,
        "live": live,
        "aggregate": _aggregate(per_case),
        "cases": per_case,
    }

    out_dir = Path(config.runs_dir) / "_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"eval-{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report["report_path"] = str(out_dir / f"eval-{stamp}.json")
    return report
