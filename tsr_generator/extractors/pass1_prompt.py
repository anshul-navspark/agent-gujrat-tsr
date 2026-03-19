"""
Pass 1 prompt builder for entry classification and land details extraction.

This module builds the first-pass LLM prompt that:
- Extracts land details (village, taluka, district, survey numbers, etc.)
- Classifies each entry by type (one of 19 canonical types)
- Extracts entry metadata (number, date, certification status)
- Does NOT extract descriptions or type-specific fields (that is Pass 2)
"""

import logging
from typing import Dict, List, Optional

from .entry_schema import normalize_entry_type
from .unified_extractor import _normalize_date_str, _parse_json_response
from ..utils.text_utils import convert_gujarati_to_english_numerals

logger = logging.getLogger(__name__)

# 19 canonical entry types with classification hints
_TYPE_HINTS = [
    ("SALE", '"sold" and "consideration"'),
    ("INHERITANCE", '"upon the demise" or "came to be mutated in his legal heirs"'),
    ("PARTITION", '"distribution took place" or "distributed his land"'),
    ("RELINQUISHMENT", '"relinquished their respective share"'),
    ("EXCHANGE", '"exchanged their respective lands"'),
    ("LIFETIME_DISTRIBUTION", '"life time distribution"'),
    ("GIFT", '"gifted" and "document no."'),
    ("LOAN", '"took a loan" or "created a charge" or "loan of Rs."'),
    ("RELEASE", '"removing the charge" or "exemption of burden"'),
    ("SEIZURE", '"seized" or "seizure order"'),
    ("ORDER", '"Taluka Circular" or government order'),
    ("ALLOTMENT", '"was allotted" or "granted the land" or "Section 43"'),
    ("TENURE_CHANGE", '"changed the condition" or "new tenure to old"'),
    ("LAND_ACQUISITION", '"Land Acquisition" or "Award No."'),
    ("LEASE", '"leased" or "lease" with period'),
    ("PROMULGATION", '"re-survey" or "promulgation"'),
    ("CORRECTION", '"corrected" or "amendment"'),
    ("NOT_RELATED", '"not related to present survey" or entry about different survey numbers'),
    ("UNAVAILABLE", '"not completely scanned" or "records destroyed" or "not available"'),
]


def build_pass1_prompt(pdf_text: str, entry_numbers_hint: List[str] = None) -> str:
    """
    Build the Pass 1 classification prompt for Gemini.

    The prompt instructs the LLM to extract land details and classify each
    entry by type, without extracting descriptions or type-specific fields.

    Args:
        pdf_text: The extracted text from the PDF.
        entry_numbers_hint: Optional list of candidate entry numbers detected
            by pre-processing (e.g. regex).

    Returns:
        The complete prompt string.
    """
    # Build type classification block
    type_lines = "\n".join(
        f"  - {name}: Look for {hint}" for name, hint in _TYPE_HINTS
    )

    hint_block = ""
    if entry_numbers_hint:
        hint_block = (
            f"\nCandidate entry numbers detected: {', '.join(entry_numbers_hint)}\n"
            "Use these as a hint but also look for any entries not in this list.\n"
        )

    prompt = f"""\
You are an expert at reading Gujarat land revenue records (AnyRoR / 7/12 extracts).
Translate ALL Gujarati text to English in your output.
For survey numbers, translate "Paiki" / "Part" / "part" to "p".

## TASK — Pass 1: Land Details & Entry Classification

From the document text below, extract:
1. **Land details** (village, taluka, district, survey numbers, etc.)
2. **Entry classification** — for EACH mutation/entry, determine its type and extract metadata.

Do NOT extract descriptions or type-specific fields (sellers, buyers, amounts, etc.). That will be done in a separate pass.

## Entry Types

Classify each entry as exactly ONE of these 19 types:
{type_lines}

## Certification Status

Translate Gujarati certification keywords:
  - રદ → "rejected"
  - ના મંજૂર / નામંજુર / નામંજૂર → "not_accepted"
  - પ્રમાણિત → "certified"

For certification_official: extract the official's POST/DESIGNATION and PLACE.
Abbreviate "Circle Officer" as "C.O." (e.g. "C.O. Sami", "Mamlatdar Dhanera").

## Date Format

All dates must be in DD/MM/YYYY format (4-digit year).

## Survey Numbers

- survey_numbers: list of current/new survey numbers mentioned in the land details header.
- old_survey_numbers: list of old survey numbers if mentioned.
- survey_number_mapping: maps OLD survey number to list of NEW survey numbers, e.g. {{"159": ["105", "141"]}}.
{hint_block}
## Output Schema

Return ONLY valid JSON (no extra text) in this exact structure:

```json
{{
  "land_details": {{
    "village_name": "",
    "taluka_name": "",
    "district_name": "",
    "survey_numbers": [],
    "old_survey_numbers": [],
    "survey_number_mapping": {{}},
    "total_area": "",
    "nature_of_land": "",
    "owners": []
  }},
  "entries": [
    {{
      "entry_number": "",
      "date": "",
      "type": "",
      "certification_status": "",
      "certification_official": "",
      "certification_date": ""
    }}
  ]
}}
```

## Document Text

{pdf_text}
"""
    return prompt


def parse_pass1_response(response: str) -> Dict:
    """
    Parse the LLM response from Pass 1.

    Handles code fences, brace matching, and other common LLM output quirks.
    Normalises entry types and dates.

    Args:
        response: Raw text response from the LLM.

    Returns:
        Parsed and normalised dictionary with land_details and entries.
    """
    parsed = _parse_json_response(response)
    if parsed is None:
        logger.warning("Failed to parse Pass 1 JSON response")
        return {"land_details": {}, "entries": []}

    # --- Normalize land details ---
    land = parsed.get("land_details", {})
    if isinstance(land, dict):
        for key in ("village_name", "taluka_name", "district_name",
                     "total_area", "nature_of_land"):
            if key in land and isinstance(land[key], str):
                land[key] = convert_gujarati_to_english_numerals(land[key])

        # Normalize survey number lists
        for key in ("survey_numbers", "old_survey_numbers"):
            if key in land and isinstance(land[key], list):
                land[key] = [
                    convert_gujarati_to_english_numerals(str(s))
                    for s in land[key]
                ]

        # Normalize survey_number_mapping values
        mapping = land.get("survey_number_mapping", {})
        if isinstance(mapping, dict):
            normalised_mapping = {}
            for old_sn, new_sns in mapping.items():
                norm_key = convert_gujarati_to_english_numerals(str(old_sn))
                if isinstance(new_sns, list):
                    normalised_mapping[norm_key] = [
                        convert_gujarati_to_english_numerals(str(s))
                        for s in new_sns
                    ]
                else:
                    normalised_mapping[norm_key] = new_sns
            land["survey_number_mapping"] = normalised_mapping

        # Normalize owners list
        owners = land.get("owners", [])
        if isinstance(owners, list):
            land["owners"] = [
                convert_gujarati_to_english_numerals(str(o))
                for o in owners
            ]

        parsed["land_details"] = land

    # --- Normalize entries ---
    entries = parsed.get("entries", [])
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Normalize type
            raw_type = entry.get("type", "")
            if raw_type:
                normalised = normalize_entry_type(str(raw_type))
                if normalised != str(raw_type).upper().replace(' ', '_'):
                    logger.debug(
                        "Pass 1: Entry %s type normalised: %s -> %s",
                        entry.get("entry_number", "?"), raw_type, normalised,
                    )
                entry["type"] = normalised

            # Normalize dates
            if "date" in entry:
                entry["date"] = _normalize_date_str(entry.get("date", ""))
            if "certification_date" in entry:
                entry["certification_date"] = _normalize_date_str(
                    entry.get("certification_date", "")
                )

        parsed["entries"] = entries

    return parsed
