"""
Import lawyer corrections — the orchestrator of the feedback loop.

Given a completed run and a lawyer-corrected ground-truth file, it:

  1. diffs the model extraction against the truth,
  2. distils each correction into a generalised prompt guideline (deduped, with
     before/after examples) and re-renders the guidelines markdown, and
  3. promotes the corrected run into the golden eval set (so the fix becomes a
     permanent regression check).

CLI:  ``python -m adk_agent feedback import --run <run_id> --truth ground_truth.json``
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.eval.evalset import upsert_golden_case
from adk_agent.feedback.diff import _entries_by_number, diff_extractions
from adk_agent.feedback.ground_truth import load_extraction, load_ground_truth
from adk_agent.feedback.guidelines_store import (
    synthesize_guideline,
    upsert_guidelines,
    write_markdown,
)


def _resolve_run_dir(config: AdkConfig, run: Union[str, Path]) -> Path:
    p = Path(run)
    if p.exists() and p.is_dir():
        return p
    candidate = Path(config.runs_dir) / str(run)
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"run not found: {run} (looked in {config.runs_dir})")


def _load_source_text(run_dir: Path) -> str:
    src = run_dir / "source.txt"
    if src.exists():
        return src.read_text(encoding="utf-8")
    # Fall back to re-extracting from the original PDF if it is still around.
    record_file = run_dir / "record.json"
    if record_file.exists():
        try:
            rec = json.loads(record_file.read_text(encoding="utf-8"))
            pdf_path = (rec.get("inputs") or {}).get("pdf_path")
            if pdf_path and Path(pdf_path).exists():
                from tsr_generator.utils.pdf_utils import extract_text_from_pdf

                return extract_text_from_pdf(pdf_path) or ""
        except Exception:
            pass
    return ""


def _load_survey(run_dir: Path) -> Optional[Dict[str, str]]:
    record_file = run_dir / "record.json"
    if record_file.exists():
        try:
            rec = json.loads(record_file.read_text(encoding="utf-8"))
            return (rec.get("inputs") or {}).get("survey")
        except Exception:
            return None
    return None


def import_fixes(
    config: Optional[AdkConfig] = None,
    *,
    run: Union[str, Path],
    truth: Union[str, Path],
    update_eval: bool = True,
) -> Dict[str, Any]:
    """Import a lawyer-corrected ground truth for *run*; return a summary report."""
    config = config or get_adk_config()
    config.ensure_dirs()
    run_dir = _resolve_run_dir(config, run)

    model = load_extraction(run_dir)
    truth_extraction = load_ground_truth(truth)
    corrections = diff_extractions(model, truth_extraction)

    m_by = _entries_by_number(model)
    t_by = _entries_by_number(truth_extraction)
    guidelines = [
        synthesize_guideline(
            c,
            m_by.get(c.entry_number) if c.entry_number else None,
            t_by.get(c.entry_number) if c.entry_number else None,
            source_run=run_dir.name,
        )
        for c in corrections
    ]
    if guidelines:
        upsert_guidelines(config.guidelines_path, guidelines)
        write_markdown(config)

    eval_path = None
    if update_eval:
        pdf_text = _load_source_text(run_dir)
        survey = _load_survey(run_dir)
        eval_path = upsert_golden_case(
            config, run_dir.name, truth_extraction, pdf_text=pdf_text, survey=survey
        )

    report = {
        "run": run_dir.name,
        "truth": str(truth),
        "num_corrections": len(corrections),
        "corrections_by_kind": _count_by_kind(corrections),
        "guidelines_added_or_updated": len(guidelines),
        "guidelines_path": str(config.guidelines_path),
        "guidelines_md": str(config.guidelines_md_path),
        "golden_evalset": str(eval_path) if eval_path else None,
        "corrections": [c.to_dict() for c in corrections],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    out = run_dir / f"feedback-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report_path"] = str(out)
    return report


def _count_by_kind(corrections) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in corrections:
        out[c.kind] = out.get(c.kind, 0) + 1
    return out
