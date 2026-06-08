"""
The ADK 2.0 graph ``Workflow`` — the canonical skill graph.

    START -> ingest -> extractor(LlmAgent) -> assemble

* ``ingest``    (function node): optional AnyRoR scrape + PDF-text extraction.
* ``extractor`` (LlmAgent node):  reuses the unified-extraction prompt, emits a
  validated :class:`UnifiedExtraction` into ``session.state['extraction']``.
* ``assemble``  (function node): findings cross-reference + DOCX rendering.

Run data (``pdf_text``, the extraction) flows through the graph; run *config*
(output path, subject survey) and the live :class:`RunRecord` ride the
:class:`RunContext` ``contextvars`` carrier established by the caller.

This module also exposes ``root_agent`` so the graph is runnable with the ADK
CLI/Dev-UI (``adk run adk_agent`` / ``adk web``).
"""

from __future__ import annotations

import logging
from typing import Any, Union

from google.adk import Workflow
from google.adk.models.base_llm import BaseLlm

from adk_agent.observability.run_context import current_run
from adk_agent.skills.extraction import EXTRACTION_OUTPUT_KEY, build_extractor_agent
from adk_agent.steps import do_assemble, do_pdf_text, do_scrape

logger = logging.getLogger(__name__)


def _require_run():
    run = current_run()
    if run is None:  # pragma: no cover - only when run outside our runner
        raise RuntimeError(
            "No RunContext established. Drive the graph via adk_agent.pipeline.run_pipeline "
            "(engine='graph') or the `python -m adk_agent` CLI."
        )
    return run


def ingest_node(node_input: Any):
    """Function node: scrape (survey mode) + extract PDF text into the run context."""
    run = _require_run()
    from adk_agent.config import get_adk_config

    config = get_adk_config()
    if run.options.get("mode") == "survey":
        do_scrape(run, config)
    do_pdf_text(run, config)
    # Value threaded to the extractor as content; the extractor reads the doc from
    # the run context, so this is only a trigger.
    return {"status": "ingested", "chars": len(run.pdf_text)}


def assemble_node(node_input: Any):
    """Function node: receive the extractor's structured output and render the DOCX."""
    run = _require_run()
    from adk_agent.config import get_adk_config

    extraction_raw = _coerce_extraction(node_input, run)
    return do_assemble(run, get_adk_config(), extraction_raw)


def _coerce_extraction(node_input: Any, run) -> dict:
    """The extractor's output may arrive as the structured dict (preferred),
    a pydantic model, or we fall back to session state captured by the agent."""
    if isinstance(node_input, dict) and node_input.get("mutation_entries") is not None:
        return node_input
    if hasattr(node_input, "model_dump"):
        return node_input.model_dump()
    state_extraction = getattr(run, "_last_extraction", None)
    return state_extraction or (node_input if isinstance(node_input, dict) else {})


def build_graph(model: Union[str, BaseLlm]) -> Workflow:
    """Construct the ``ingest -> extractor -> assemble`` graph for *model*."""
    extractor = build_extractor_agent(model)
    return Workflow(
        name="tsr_pipeline",
        description="Gujarat TSR pipeline: ingest land record -> extract -> render TSR DOCX.",
        edges=[("START", ingest_node, extractor, assemble_node)],
    )


def _default_root_agent() -> Workflow:
    """Build the module-level root_agent for `adk run` / `adk web`."""
    from adk_agent.app import resolve_model
    from adk_agent.config import get_adk_config

    return build_graph(resolve_model(get_adk_config()))


# Exposed for the ADK CLI/Dev-UI (`adk run adk_agent`, `adk web`).
root_agent = _default_root_agent()
