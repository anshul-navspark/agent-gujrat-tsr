"""
Extraction skill — a native ADK ``LlmAgent`` (Gemini).

Design notes
------------
* **Reuses the exact tuned prompt.** The instruction is produced by the existing
  ``build_unified_prompt`` (the brace-heavy JSON spec, entry-type rules,
  formatting rules, certification patterns and few-shot examples). Because that
  text contains literal ``{`` / ``}``, it is supplied as a *callable* instruction
  (an ADK ``InstructionProvider``) rather than a templated string — ADK does not
  apply ``{state_key}`` substitution to callable instructions.

* **Document text comes from the run context**, not from ADK session state, so the
  same agent works identically whether it is driven directly (pipeline engine) or
  as a node inside the graph ``Workflow`` (graph engine).

* **Validated structured output.** ``output_schema=UnifiedExtraction`` upgrades the
  prompt's "return JSON like this" into ADK-enforced structured output, written to
  ``session.state['extraction']``.

* **Learned guidelines** distilled from lawyer corrections are injected into the
  prompt just before the document text, closing the improvement loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from google.adk import Agent
from google.adk.models.base_llm import BaseLlm
from google.genai import types as genai_types

from adk_agent.observability.run_context import current_run
from adk_agent.schemas import UnifiedExtraction

# Reused, tested internals from the legacy extractor.
from tsr_generator.extractors.unified_extractor import (
    build_unified_prompt,
    _identify_entry_numbers_fast,
    _extract_relevant_sections,
    _normalize_land_details,
    _normalize_mutation_entries,
    _compute_survey_aliases,
    _filter_description_to_subject_survey,
)

logger = logging.getLogger(__name__)

EXTRACTOR_AGENT_NAME = "tsr_extractor"
EXTRACTION_OUTPUT_KEY = "extraction"

_DOC_MARKER = "\nDOCUMENT TEXT:"
_GUIDELINES_HEADER = (
    "LEARNED CORRECTIONS (distilled from prior lawyer review — apply these "
    "BEFORE the generic rules above when they conflict):\n"
)


def inject_guidelines(prompt: str, guidelines_text: str) -> str:
    """Insert the learned-guidelines block just before the document text."""
    if not guidelines_text:
        return prompt
    block = "\n" + _GUIDELINES_HEADER + guidelines_text.strip() + "\n"
    idx = prompt.find(_DOC_MARKER)
    if idx == -1:
        return prompt + block
    return prompt[:idx] + block + prompt[idx:]


def build_extraction_prompt(pdf_text: str, guidelines_text: str = "") -> str:
    """Build the full extraction prompt (relevant sections + learned guidelines)."""
    document_text = _extract_relevant_sections(pdf_text or "")
    hints = _identify_entry_numbers_fast(pdf_text or "")
    prompt = build_unified_prompt(document_text, hints)
    return inject_guidelines(prompt, guidelines_text)


def extraction_instruction(ctx) -> str:  # ctx: ReadonlyContext
    """ADK InstructionProvider: render the extraction prompt for this run."""
    run = current_run()
    if run is not None:
        pdf_text = run.pdf_text
        guidelines = run.guidelines_text
        profile = getattr(run, "profile", None)
    else:  # pragma: no cover - fallback if no run context is established
        pdf_text = (ctx.state.get("pdf_text", "") if ctx else "") or ""
        guidelines = (ctx.state.get("guidelines_text", "") if ctx else "") or ""
        profile = None
    if profile is not None:
        # Lazy import avoids a cycle (optimize.profiles imports this module).
        from adk_agent.optimize.profiles import build_prompt

        return build_prompt(pdf_text, guidelines, profile)
    return build_extraction_prompt(pdf_text, guidelines)


def _generate_config(profile, temperature: float) -> "genai_types.GenerateContentConfig":
    """Build the decoding config, applying a prompt profile's levers when present."""
    temp = getattr(profile, "temperature", None)
    cfg = genai_types.GenerateContentConfig(temperature=temp if temp is not None else temperature)
    if profile is None:
        return cfg
    max_out = getattr(profile, "max_output_tokens", None)
    if max_out:
        try:
            cfg.max_output_tokens = int(max_out)
        except Exception:  # pragma: no cover - defensive
            pass
    budget = getattr(profile, "thinking_budget", None)
    if budget is not None:
        # Best-effort: older google-genai builds may lack ThinkingConfig.
        try:
            cfg.thinking_config = genai_types.ThinkingConfig(thinking_budget=int(budget))
        except Exception:  # pragma: no cover - defensive
            logger.debug("thinking_budget not applied (ThinkingConfig unavailable)")
    return cfg


def build_extractor_agent(
    model: Union[str, BaseLlm],
    *,
    temperature: float = 0.0,
    profile=None,
    agent_name: str = EXTRACTOR_AGENT_NAME,
) -> Agent:
    """Construct the extraction ``LlmAgent`` (optionally tuned by a prompt profile)."""
    return Agent(
        name=agent_name,
        model=model,
        description="Extracts structured land-record data (land details + chain-of-title entries) from a Gujarat 7/12 extract.",
        instruction=extraction_instruction,
        output_schema=UnifiedExtraction,
        output_key=EXTRACTION_OUTPUT_KEY,
        generate_content_config=_generate_config(profile, temperature),
    )


def normalize_extraction(raw: Dict[str, Any], pdf_text: str) -> Dict[str, Any]:
    """
    Apply the same post-processing the legacy ``extract_all_unified`` does:
    normalise land details, normalise entry dates, and trim multi-survey
    descriptions down to the subject survey.

    *raw* is the structured dict from ``session.state['extraction']``.
    """
    raw = dict(raw or {})
    land_details = dict(raw.get("land_details") or {})
    _normalize_land_details(land_details)
    raw["land_details"] = land_details

    mutation_entries = raw.get("mutation_entries") or []
    _normalize_mutation_entries(mutation_entries)

    # Trim multi-survey listings to the subject survey (safe by construction).
    try:
        subject = (land_details or {}).get("survey_number", "") or ""
        if subject and "," in subject:
            subject = subject.split(",")[0].strip()
        aliases = _compute_survey_aliases(subject, pdf_text or "")
        if aliases:
            for ed in mutation_entries:
                if not isinstance(ed, dict):
                    continue
                desc = ed.get("description", "")
                if desc:
                    ed["description"] = _filter_description_to_subject_survey(desc, aliases)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("survey filter skipped: %s", e)

    raw["mutation_entries"] = mutation_entries
    # entry_numbers -> list[str]
    raw["entry_numbers"] = [str(n) for n in (raw.get("entry_numbers") or [])]
    return raw
