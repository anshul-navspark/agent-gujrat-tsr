"""
Assemble skill — turn the structured extraction into the final DOCX.

Reuses the legacy pipeline tail verbatim:
``process_entry_details`` -> ``generate_findings_table`` -> ``create_tsr_document``
(the same calls ``generate_tsr_from_pdf_optimized`` makes), so the rendered
report is byte-for-byte the same as the existing system for identical inputs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from tsr_generator.extractors.entry_details import process_entry_details
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document

logger = logging.getLogger(__name__)


def assemble_document(
    extraction: Dict[str, Any],
    pdf_text: str,
    output_path: str,
    *,
    survey_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the TSR DOCX from a (normalised) extraction dict.

    Returns a summary dict: ``{tsr_path, entries_count, findings_count,
    entry_types, land_details}``.
    """
    land_details = dict(extraction.get("land_details") or {})
    mutation_entries = extraction.get("mutation_entries") or []
    entry_numbers = extraction.get("entry_numbers") or []

    if survey_override:
        land_details["survey_number"] = survey_override

    entry_table = sorted(int(n) for n in entry_numbers if str(n).isdigit())

    entries = []
    if mutation_entries:
        entries = process_entry_details(mutation_entries)
        entries = [e for e in entries if getattr(e, "formatted_description", "").strip()]

    findings = generate_findings_table("", mutation_entries, land_details)

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    tsr_path = create_tsr_document(
        entry_table, entries, land_details, findings, output_path,
        mutation_entries=mutation_entries,
    )

    entry_types: Dict[str, int] = {}
    for e in entries:
        t = e.type.value if hasattr(e.type, "value") else str(e.type)
        entry_types[t] = entry_types.get(t, 0) + 1

    return {
        "tsr_path": tsr_path,
        "entries_count": len(entries),
        "findings_count": len(findings),
        "entry_types": entry_types,
        "land_details": land_details,
    }
