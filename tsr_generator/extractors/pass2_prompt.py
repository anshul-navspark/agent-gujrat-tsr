"""
Pass 2 dynamic prompt builder for type-aware field extraction.

Given the classified entries from Pass 1, this module builds a targeted
extraction prompt that includes only the schemas and few-shot examples
for entry types actually present in the document.  Fixed-text types
(NOT_RELATED, UNAVAILABLE) are skipped because they need no LLM extraction.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from .type_configs import TYPE_CONFIGS

logger = logging.getLogger(__name__)

# Types that use fixed text and do not need Pass 2 extraction
_FIXED_TEXT_TYPES = frozenset({"NOT_RELATED", "UNAVAILABLE"})


def build_pass2_prompt(
    pdf_text: str, classified_entries: List[Dict]
) -> Optional[str]:
    """
    Build the Pass 2 extraction prompt from Pass 1 classifications.

    Args:
        pdf_text: Full extracted text from the PDF.
        classified_entries: List of dicts from Pass 1, each containing
            at least ``entry_number`` and ``type``.

    Returns:
        The prompt string, or ``None`` if every entry is a fixed-text type
        (meaning no LLM extraction is needed).
    """
    # Filter out fixed-text types
    extractable = [
        e for e in classified_entries
        if e.get("type", "").upper() not in _FIXED_TEXT_TYPES
    ]

    if not extractable:
        return None

    # Collect unique types preserving first-seen order
    seen = set()
    unique_types: List[str] = []
    for entry in extractable:
        t = entry.get("type", "").upper()
        if t and t not in seen:
            seen.add(t)
            unique_types.append(t)

    # Build per-type schema + example sections
    type_sections: List[str] = []
    for entry_type in unique_types:
        config = TYPE_CONFIGS.get(entry_type)
        if config is None:
            continue

        section_lines: List[str] = [f"### {entry_type} entries"]

        # Field schema
        fields = config.get("fields", {})
        if fields:
            section_lines.append("Extract these fields:")
            for field_name, field_type in fields.items():
                section_lines.append(f"- {field_name}: {field_type}")

        # Few-shot examples (include up to 2)
        examples = config.get("examples", [])
        for ex in examples[:2]:
            ex_input = ex.get("input", "")
            ex_output = ex.get("output", {})
            section_lines.append("")
            section_lines.append("Example:")
            section_lines.append(f'Input: "{ex_input}"')
            section_lines.append(f"Output: {json.dumps(ex_output)}")

        type_sections.append("\n".join(section_lines))

    # Build entry list
    entry_lines: List[str] = []
    for entry in extractable:
        entry_num = entry.get("entry_number", "?")
        entry_type = entry.get("type", "UNKNOWN").upper()
        entry_lines.append(f"- Entry No. {entry_num} ({entry_type})")

    prompt = f"""\
You are extracting structured fields from Gujarat land record entries.
For each entry listed below, extract ONLY the fields specified for its type.
Return a JSON array with one object per entry. Each object MUST include "entry_number".

Translate all Gujarati text to English.
For survey numbers, translate "Paiki"/"Part"/"part" to "p".
Dates: DD/MM/YYYY format (4-digit years).
Amounts: numeric only (e.g., "2,50,000"), no "Rs." prefix.

## Types in this document:

{chr(10).join(type_sections)}

## Entries to extract:
{chr(10).join(entry_lines)}

## Document text:
{pdf_text}

Return ONLY the JSON array, no explanations."""

    return prompt


def parse_pass2_response(response: str) -> List[Dict]:
    """
    Parse the LLM response from Pass 2 into a list of entry dicts.

    Handles code fences and bare JSON arrays.

    Args:
        response: Raw text response from the LLM.

    Returns:
        List of dicts (one per entry), or empty list on failure.
    """
    if not response or not isinstance(response, str):
        logger.warning("Pass 2 response is empty or not a string")
        return []

    text = response.strip()

    # Strip code fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()

    # Try to find a JSON array
    # Strategy 1: the whole text is a JSON array
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: extract first [...] from text
    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        try:
            # Remove trailing commas before ] or }
            candidate = bracket_match.group(0)
            candidate = re.sub(r",\s*([\]\}])", r"\1", candidate)
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Failed to parse Pass 2 JSON array from response")
    return []
