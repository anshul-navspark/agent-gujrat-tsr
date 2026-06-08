"""
Shared pipeline steps.

These operate on a :class:`RunContext` and append :class:`SkillStep` records.
Both engines reuse them:

  * the **pipeline** engine (``pipeline.run_pipeline``) calls them directly, and
  * the **graph** engine (``graph.py`` nodes) call them from inside Workflow nodes.

Keeping them here (importing neither ``graph`` nor ``pipeline``) avoids circular
imports.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from adk_agent.config import AdkConfig
from adk_agent.observability.run_context import RunContext
from adk_agent.observability.run_record import SkillStep
from adk_agent.skills.assemble import assemble_document
from adk_agent.skills.extraction import normalize_extraction
from adk_agent.skills.pdf_text import extract_pdf_text

logger = logging.getLogger(__name__)


def load_guidelines_text(config: AdkConfig) -> str:
    """Render the learned prompt guidelines for injection (empty if none/failed)."""
    try:
        from adk_agent.feedback.guidelines_store import render_guidelines_for_prompt

        return render_guidelines_for_prompt(config)
    except Exception as e:  # pragma: no cover - feedback store optional/empty
        logger.debug("no guidelines loaded: %s", e)
        return ""


def _timed(run: RunContext, name: str):
    """Context manager that records a SkillStep with timing + status."""

    class _Ctx:
        def __enter__(self_inner):
            self_inner.t0 = time.monotonic()
            self_inner.step = SkillStep(name=name)
            return self_inner.step

        def __exit__(self_inner, exc_type, exc, tb):
            self_inner.step.duration_ms = int((time.monotonic() - self_inner.t0) * 1000)
            if exc is not None:
                self_inner.step.status = "error"
                self_inner.step.error = str(exc)
            run.record.add_skill(self_inner.step)
            return False  # never suppress

    return _Ctx()


def do_scrape(run: RunContext, config: AdkConfig) -> None:
    """Survey mode only: fetch the PDF from AnyRoR into the run dir."""
    survey = run.options.get("survey") or {}
    with _timed(run, "scrape") as step:
        from adk_agent.skills.scrape import scrape_to_pdf  # lazy: Selenium

        run_dir = run.record.run_dir(run.runs_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = str(run_dir / "source.pdf")
        result = scrape_to_pdf(
            survey["district"], survey["taluka"], survey["village"],
            survey["survey_number"], pdf_path, headless=config.headless,
        )
        run.pdf_path = result["pdf_path"]
        step.detail = {"pdf_path": run.pdf_path, "survey": survey.get("survey_number")}


def do_pdf_text(run: RunContext, config: AdkConfig) -> None:
    """Extract raw text from the source PDF into the run context."""
    with _timed(run, "pdf_text") as step:
        if not run.pdf_path:
            raise ValueError("no PDF path available for text extraction")
        text = extract_pdf_text(run.pdf_path)
        run.pdf_text = text
        step.detail = {"chars": len(text), "pdf_path": run.pdf_path}


def do_assemble(run: RunContext, config: AdkConfig, extraction_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise the extraction and render the DOCX; record outputs."""
    with _timed(run, "assemble") as step:
        normalized = normalize_extraction(extraction_raw or {}, run.pdf_text)
        run.record.extraction = normalized
        survey_override = None
        survey = run.options.get("survey") or {}
        if survey.get("survey_number"):
            survey_override = survey["survey_number"]
        summary = assemble_document(
            normalized, run.pdf_text, run.output_path, survey_override=survey_override
        )
        run.record.output = summary
        step.detail = {
            "entries_count": summary["entries_count"],
            "findings_count": summary["findings_count"],
            "tsr_path": summary["tsr_path"],
        }
        return summary
