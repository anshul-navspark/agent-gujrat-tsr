"""
Gujarat TSR Agent — Google ADK 2.x edition.

This package re-expresses the Title Search Report (TSR) pipeline as a
skill-based Google Agent Development Kit (ADK 2.x) workflow:

    ingest (scrape? + pdf-text)  ->  extractor (LlmAgent)  ->  assemble (findings + DOCX)

It is a NEW orchestration + observability layer that *reuses* the existing,
battle-tested internals (`tsr_generator/`, `anyror/`):

  - The LLM extraction step is a native ADK ``LlmAgent`` that reuses the exact
    tuned unified-extraction prompt (`tsr_generator.extractors.unified_extractor`)
    and emits a validated structured object.
  - Deterministic steps (PDF text, findings cross-reference, DOCX rendering,
    optional AnyRoR scraping) are thin "skills" that wrap existing functions.
  - An observability ``Plugin`` records every model call (rendered prompt, raw
    response, token usage) plus per-skill timings into a durable run record.
  - A ground-truth feedback loop turns lawyer corrections into (a) learned
    prompt guidelines injected back into the extraction prompt and (b) ADK
    golden eval cases used to measure extraction quality over time.

Single command entry point::

    python -m adk_agent --pdf record.pdf --out report.docx
    python -m adk_agent --survey "Kutch/Abdasa/Keshav/150" --out report.docx
    python -m adk_agent --pdf record.pdf --dry-run          # offline, no API key
    python -m adk_agent feedback import --run <run_id> --truth corrected.json
    python -m adk_agent eval

The existing Streamlit UI, FastAPI server, CLI and Docker image are left
completely untouched.
"""

from adk_agent.config import AdkConfig, get_adk_config

__all__ = ["AdkConfig", "get_adk_config"]

__version__ = "0.1.0"
