"""
Pipeline orchestrator — the single E2E entry point.

``run_pipeline(...)`` executes the whole flow and returns a fully-populated
:class:`RunRecord` (persisted under ``runs/<run_id>/``). Two interchangeable
engines share the same skills, observability and feedback wiring:

* ``engine="pipeline"`` (default, robust): deterministic steps run in Python; the
  extraction ``LlmAgent`` runs via an ADK ``Runner`` (so the observability plugin
  instruments the model call). Clear error handling, easy to reason about.

* ``engine="graph"`` (ADK 2.0 graph runtime): the whole
  ``ingest -> extractor -> assemble`` graph runs as an ADK ``Workflow`` — the most
  up-to-date Google agent-orchestration protocol.

Both produce identical run records and DOCX output.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from google.genai import types as genai_types

from adk_agent.app import build_app, make_runner, resolve_model
from adk_agent.config import AdkConfig, get_adk_config
from adk_agent.observability.run_context import RunContext, set_current_run
from adk_agent.observability.run_record import RunRecord
from adk_agent.skills.extraction import (
    EXTRACTION_OUTPUT_KEY,
    build_extractor_agent,
    normalize_extraction,
)
from adk_agent.steps import do_assemble, do_pdf_text, do_scrape, load_guidelines_text

logger = logging.getLogger(__name__)

_TRIGGER = genai_types.Content(
    role="user",
    parts=[genai_types.Part(text="Extract the structured TSR data from the provided land record.")],
)


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _load_active_profile(config: AdkConfig):
    """Load the promoted prompt profile (efficiency levers), or None for production 'full'."""
    try:
        from adk_agent.optimize.profiles import load_active_profile

        return load_active_profile(config.active_profile_path)
    except Exception as e:  # pragma: no cover - optimizer optional
        logger.debug("no active profile loaded: %s", e)
        return None


async def run_pipeline(
    config: Optional[AdkConfig] = None,
    *,
    mode: str,
    output_path: str,
    pdf_path: Optional[str] = None,
    survey: Optional[Dict[str, str]] = None,
    engine: str = "pipeline",
) -> RunRecord:
    """
    Run the full TSR pipeline.

    Args:
        mode: ``"pdf"`` or ``"survey"``.
        output_path: where to write the DOCX.
        pdf_path: source PDF (pdf mode).
        survey: ``{district, taluka, village, survey_number}`` (survey mode).
        engine: ``"pipeline"`` or ``"graph"``.
    """
    config = config or get_adk_config()
    config.ensure_dirs()

    record = RunRecord(
        run_id=_new_run_id(),
        mode=mode,
        dry_run=config.dry_run or not config.has_credentials,
        model=str(config.model_name),
        inputs={"output_path": output_path, "pdf_path": pdf_path, "survey": survey, "engine": engine},
    )
    run = RunContext(
        record=record,
        output_path=output_path,
        pdf_path=pdf_path,
        runs_dir=config.runs_dir,
        options={"mode": mode, "survey": survey or {}},
        guidelines_text=load_guidelines_text(config),
        profile=_load_active_profile(config),
    )
    record.inputs["profile"] = getattr(run.profile, "name", "full")
    set_current_run(run)
    try:
        if engine == "graph":
            await _run_graph(config, run)
        else:
            await _run_pipeline_engine(config, run)
        record.status = "success"
    except Exception as e:  # surface failures but always persist the record
        logger.exception("pipeline failed")
        record.status = "error"
        record.error = str(e)
    finally:
        record.persist(config.runs_dir)
        # Persist the source document text so this run can be replayed/evaluated
        # later (e.g. promoted into the golden eval set).
        if run.pdf_text:
            try:
                (record.run_dir(config.runs_dir) / "source.txt").write_text(
                    run.pdf_text, encoding="utf-8"
                )
            except Exception:  # pragma: no cover - best effort
                pass
        set_current_run(None)
    return record


async def extract_only_record(
    config: Optional[AdkConfig] = None,
    pdf_text: str = "",
    *,
    profile=None,
    guidelines_text: Optional[str] = None,
    use_active_profile: bool = True,
) -> "tuple[Dict[str, Any], RunRecord]":
    """
    Run *only* the extraction skill on raw text and return
    ``(normalised_extraction, run_record)``.

    The run record carries the observability the optimizer reads back: token
    usage (``record.token_totals``) and per-call latency (``llm_calls``). No
    DOCX is rendered and nothing is persisted.

    *profile* overrides the prompt profile; when omitted, the promoted active
    profile is used (unless *use_active_profile* is False).
    """
    config = config or get_adk_config()
    if profile is None and use_active_profile:
        profile = _load_active_profile(config)
    record = RunRecord(run_id="eval-" + uuid.uuid4().hex[:8], mode="eval", model=str(config.model_name))
    run = RunContext(
        record=record,
        runs_dir=config.runs_dir,
        guidelines_text=(guidelines_text if guidelines_text is not None else load_guidelines_text(config)),
        profile=profile,
    )
    run.pdf_text = pdf_text
    set_current_run(run)
    try:
        extraction_raw = await _run_extractor(config, run)
        normalized = normalize_extraction(extraction_raw, pdf_text)
        record.extraction = normalized
        return normalized, record
    finally:
        set_current_run(None)


async def extract_only(
    config: Optional[AdkConfig] = None,
    pdf_text: str = "",
    *,
    profile=None,
    guidelines_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run *only* the extraction skill on raw text and return the normalised
    extraction dict. Used by the evaluator (no DOCX, no persistence).
    """
    extraction, _ = await extract_only_record(
        config, pdf_text, profile=profile, guidelines_text=guidelines_text
    )
    return extraction


async def _run_extractor(config: AdkConfig, run: RunContext) -> Dict[str, Any]:
    """Run the extraction LlmAgent via an ADK Runner; return the raw extraction dict."""
    profile = getattr(run, "profile", None)
    model = resolve_model(config, profile)
    agent = build_extractor_agent(model, temperature=config.temperature, profile=profile)
    app = build_app(config, agent)
    runner = make_runner(app)
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id=config.user_id,
        state={"pdf_text": run.pdf_text, "guidelines_text": run.guidelines_text},
    )
    async for _ in runner.run_async(
        user_id=config.user_id, session_id=session.id, new_message=_TRIGGER
    ):
        pass
    final = await runner.session_service.get_session(
        app_name=app.name, user_id=config.user_id, session_id=session.id
    )
    extraction = (final.state or {}).get(EXTRACTION_OUTPUT_KEY) if final else None
    if extraction is None:
        raise RuntimeError("extractor produced no structured output")
    run._last_extraction = extraction  # type: ignore[attr-defined]
    return extraction


async def _run_pipeline_engine(config: AdkConfig, run: RunContext) -> None:
    if run.options.get("mode") == "survey":
        do_scrape(run, config)
    do_pdf_text(run, config)
    extraction_raw = await _run_extractor(config, run)
    do_assemble(run, config, extraction_raw)


async def _run_graph(config: AdkConfig, run: RunContext) -> None:
    from adk_agent.graph import build_graph

    model = resolve_model(config)
    app = build_app(config, build_graph(model))
    runner = make_runner(app)
    session = await runner.session_service.create_session(
        app_name=app.name,
        user_id=config.user_id,
        state={"pdf_text": "", "guidelines_text": run.guidelines_text},
    )
    async for _ in runner.run_async(
        user_id=config.user_id, session_id=session.id, new_message=_TRIGGER
    ):
        pass
    # Safety net: if the graph's assemble node didn't populate outputs, finish here.
    if not run.record.output:
        final = await runner.session_service.get_session(
            app_name=app.name, user_id=config.user_id, session_id=session.id
        )
        extraction = (final.state or {}).get(EXTRACTION_OUTPUT_KEY) if final else None
        if extraction:
            do_assemble(run, config, extraction)
        else:
            raise RuntimeError("graph run produced no extraction output")
