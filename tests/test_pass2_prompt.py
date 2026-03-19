"""Tests for Pass 2 dynamic prompt builder."""

import json
import pytest

from tsr_generator.extractors.pass2_prompt import build_pass2_prompt, parse_pass2_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PDF_TEXT = "Entry No. 100 ... sold land ... Entry No. 200 ... took a loan ..."

CLASSIFIED_ENTRIES = [
    {"entry_number": "100", "type": "SALE", "date": "01/01/2020"},
    {"entry_number": "200", "type": "LOAN", "date": "15/06/2021"},
    {"entry_number": "300", "type": "SALE", "date": "10/03/2022"},
]

MIXED_ENTRIES = [
    {"entry_number": "100", "type": "SALE"},
    {"entry_number": "200", "type": "NOT_RELATED"},
    {"entry_number": "300", "type": "UNAVAILABLE"},
    {"entry_number": "400", "type": "LOAN"},
]

ALL_FIXED_ENTRIES = [
    {"entry_number": "100", "type": "NOT_RELATED"},
    {"entry_number": "200", "type": "UNAVAILABLE"},
]


# ---------------------------------------------------------------------------
# build_pass2_prompt tests
# ---------------------------------------------------------------------------


def test_build_pass2_includes_only_relevant_types():
    """SALE and LOAN present -> only those type schemas appear in prompt."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert prompt is not None
    assert "### SALE entries" in prompt
    assert "### LOAN entries" in prompt


def test_build_pass2_excludes_absent_types():
    """Types not present in the entries should NOT appear in the prompt."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert prompt is not None
    assert "### SEIZURE entries" not in prompt
    assert "### INHERITANCE entries" not in prompt
    assert "### PARTITION entries" not in prompt


def test_build_pass2_includes_few_shot_examples():
    """Prompt should contain few-shot examples for the relevant types."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert prompt is not None
    assert "Example:" in prompt
    assert "Input:" in prompt
    assert "Output:" in prompt


def test_build_pass2_lists_entry_numbers():
    """Each extractable entry should be listed with its number and type."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert prompt is not None
    assert "Entry No. 100 (SALE)" in prompt
    assert "Entry No. 200 (LOAN)" in prompt
    assert "Entry No. 300 (SALE)" in prompt


def test_build_pass2_skips_fixed_text_types():
    """NOT_RELATED and UNAVAILABLE entries should not appear in extraction list."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, MIXED_ENTRIES)
    assert prompt is not None
    # Extractable entries present
    assert "Entry No. 100 (SALE)" in prompt
    assert "Entry No. 400 (LOAN)" in prompt
    # Fixed-text entries absent from extraction list
    # (they may still appear in the raw PDF text section, so check the entries list specifically)
    entries_section = prompt.split("## Entries to extract:")[1].split("## Document text:")[0]
    assert "Entry No. 200" not in entries_section
    assert "Entry No. 300" not in entries_section
    # No NOT_RELATED/UNAVAILABLE type sections
    assert "### NOT_RELATED" not in prompt
    assert "### UNAVAILABLE" not in prompt


def test_build_pass2_returns_none_if_all_fixed():
    """If all entries are fixed-text types, return None."""
    result = build_pass2_prompt(SAMPLE_PDF_TEXT, ALL_FIXED_ENTRIES)
    assert result is None


def test_build_pass2_returns_none_for_empty_list():
    """Empty classified entries list -> None."""
    result = build_pass2_prompt(SAMPLE_PDF_TEXT, [])
    assert result is None


def test_build_pass2_includes_pdf_text():
    """The PDF text should be included in the prompt."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert SAMPLE_PDF_TEXT in prompt


def test_build_pass2_includes_field_schemas():
    """Field schemas for relevant types should be listed."""
    prompt = build_pass2_prompt(SAMPLE_PDF_TEXT, CLASSIFIED_ENTRIES)
    assert prompt is not None
    # SALE fields
    assert "sellers" in prompt
    assert "buyers" in prompt
    assert "consideration_amount" in prompt
    # LOAN fields
    assert "borrowers" in prompt
    assert "lender" in prompt


# ---------------------------------------------------------------------------
# parse_pass2_response tests
# ---------------------------------------------------------------------------


def test_parse_pass2_response_valid_json():
    """Valid JSON array should be parsed correctly."""
    data = [
        {"entry_number": "100", "sellers": ["A"], "buyers": ["B"]},
        {"entry_number": "200", "borrowers": ["C"], "lender": "Bank"},
    ]
    result = parse_pass2_response(json.dumps(data))
    assert len(result) == 2
    assert result[0]["entry_number"] == "100"
    assert result[1]["lender"] == "Bank"


def test_parse_pass2_response_handles_code_fences():
    """JSON wrapped in code fences should be parsed correctly."""
    data = [{"entry_number": "100", "sellers": ["A"]}]
    fenced = f"```json\n{json.dumps(data)}\n```"
    result = parse_pass2_response(fenced)
    assert len(result) == 1
    assert result[0]["entry_number"] == "100"


def test_parse_pass2_response_handles_code_fences_no_label():
    """Code fences without 'json' label should also work."""
    data = [{"entry_number": "42"}]
    fenced = f"```\n{json.dumps(data)}\n```"
    result = parse_pass2_response(fenced)
    assert len(result) == 1
    assert result[0]["entry_number"] == "42"


def test_parse_pass2_response_returns_empty_on_failure():
    """Unparseable input should return an empty list."""
    result = parse_pass2_response("This is not JSON at all")
    assert result == []


def test_parse_pass2_response_returns_empty_on_none():
    """None input should return an empty list."""
    result = parse_pass2_response(None)
    assert result == []


def test_parse_pass2_response_returns_empty_on_empty_string():
    """Empty string should return an empty list."""
    result = parse_pass2_response("")
    assert result == []


def test_parse_pass2_response_handles_trailing_commas():
    """JSON with trailing commas should still parse."""
    raw = '[{"entry_number": "100", "sellers": ["A",],},]'
    result = parse_pass2_response(raw)
    assert len(result) == 1
    assert result[0]["entry_number"] == "100"


def test_parse_pass2_response_extracts_array_from_surrounding_text():
    """If the LLM wraps the array in extra text, it should still be found."""
    raw = 'Here is the result:\n[{"entry_number": "55"}]\nDone.'
    result = parse_pass2_response(raw)
    assert len(result) == 1
    assert result[0]["entry_number"] == "55"
