"""
Pipeline skills.

Each pipeline step is a discrete "skill". Deterministic skills wrap existing,
tested functions; the extraction skill is a native ADK ``LlmAgent``.

    pdf_text   -> tsr_generator.utils.pdf_utils.extract_text_from_pdf
    scrape     -> services.TranslationService + anyror.AnyRoRScraper  (optional)
    extraction -> native ADK LlmAgent reusing the unified-extraction prompt
    assemble   -> process_entry_details + generate_findings_table + create_tsr_document
"""

from adk_agent.skills.extraction import (
    build_extractor_agent,
    extraction_instruction,
    normalize_extraction,
)
from adk_agent.skills.pdf_text import extract_pdf_text
from adk_agent.skills.assemble import assemble_document

__all__ = [
    "build_extractor_agent",
    "extraction_instruction",
    "normalize_extraction",
    "extract_pdf_text",
    "assemble_document",
]
