"""Tests for Pass 1 prompt builder."""

import json
import pytest

from tsr_generator.extractors.pass1_prompt import build_pass1_prompt, parse_pass1_response


class TestBuildPass1Prompt:
    """Tests for build_pass1_prompt."""

    def test_build_pass1_prompt_contains_key_sections(self):
        """Prompt must mention land_details, entries, type, and certification fields."""
        prompt = build_pass1_prompt("sample pdf text")
        assert "land_details" in prompt
        assert "entries" in prompt
        assert '"type"' in prompt
        assert "certification_status" in prompt
        assert "certification_official" in prompt
        assert "certification_date" in prompt
        assert "village_name" in prompt
        assert "survey_numbers" in prompt

    def test_build_pass1_prompt_includes_all_types(self):
        """All 19 canonical type names must appear in the prompt."""
        prompt = build_pass1_prompt("sample pdf text")
        expected_types = [
            "SALE", "INHERITANCE", "PARTITION", "RELINQUISHMENT",
            "EXCHANGE", "LIFETIME_DISTRIBUTION", "GIFT", "LOAN",
            "RELEASE", "SEIZURE", "ORDER", "ALLOTMENT",
            "TENURE_CHANGE", "LAND_ACQUISITION", "LEASE",
            "PROMULGATION", "CORRECTION", "NOT_RELATED", "UNAVAILABLE",
        ]
        for type_name in expected_types:
            assert type_name in prompt, f"{type_name} not found in prompt"

    def test_build_pass1_prompt_does_not_ask_for_descriptions(self):
        """Prompt must explicitly say NOT to extract descriptions."""
        prompt = build_pass1_prompt("sample pdf text")
        assert "Do NOT extract descriptions" in prompt

    def test_build_pass1_prompt_includes_entry_hint(self):
        """When entry_numbers_hint is provided, prompt must include them."""
        prompt = build_pass1_prompt("sample pdf text", entry_numbers_hint=["101", "205", "310"])
        assert "Candidate entry numbers detected" in prompt
        assert "101" in prompt
        assert "205" in prompt
        assert "310" in prompt

    def test_build_pass1_prompt_no_hint_when_none(self):
        """When entry_numbers_hint is None, no candidate line appears."""
        prompt = build_pass1_prompt("sample pdf text")
        assert "Candidate entry numbers detected" not in prompt

    def test_build_pass1_prompt_includes_pdf_text(self):
        """The PDF text must appear in the prompt."""
        prompt = build_pass1_prompt("THIS_IS_UNIQUE_PDF_CONTENT")
        assert "THIS_IS_UNIQUE_PDF_CONTENT" in prompt


class TestParsePass1Response:
    """Tests for parse_pass1_response."""

    def _make_response(self, data: dict, wrap_fences: bool = False) -> str:
        """Helper to build a JSON response string."""
        raw = json.dumps(data, indent=2)
        if wrap_fences:
            return f"```json\n{raw}\n```"
        return raw

    def _sample_data(self) -> dict:
        return {
            "land_details": {
                "village_name": "Datha",
                "taluka_name": "Talaja",
                "district_name": "Bhavnagar",
                "survey_numbers": ["105"],
                "old_survey_numbers": ["159"],
                "survey_number_mapping": {"159": ["105"]},
                "total_area": "1-20",
                "nature_of_land": "Agricultural",
                "owners": ["Ramesh Patel"],
            },
            "entries": [
                {
                    "entry_number": "101",
                    "date": "15/06/2005",
                    "type": "SALE",
                    "certification_status": "certified",
                    "certification_official": "C.O. Talaja",
                    "certification_date": "21/06/2005",
                }
            ],
        }

    def test_parse_pass1_response_valid_json(self):
        """Valid JSON should parse correctly."""
        data = self._sample_data()
        result = parse_pass1_response(self._make_response(data))
        assert result["land_details"]["village_name"] == "Datha"
        assert len(result["entries"]) == 1
        assert result["entries"][0]["entry_number"] == "101"
        assert result["entries"][0]["type"] == "SALE"

    def test_parse_pass1_normalizes_types(self):
        """MORTGAGE should normalize to LOAN, DEATH to INHERITANCE."""
        data = self._sample_data()
        data["entries"] = [
            {"entry_number": "1", "date": "01/01/2020", "type": "MORTGAGE",
             "certification_status": "", "certification_official": "", "certification_date": ""},
            {"entry_number": "2", "date": "02/01/2020", "type": "DEATH",
             "certification_status": "", "certification_official": "", "certification_date": ""},
        ]
        result = parse_pass1_response(self._make_response(data))
        assert result["entries"][0]["type"] == "LOAN"
        assert result["entries"][1]["type"] == "INHERITANCE"

    def test_parse_pass1_normalizes_dates(self):
        """2-digit years should be expanded to 4-digit."""
        data = self._sample_data()
        data["entries"][0]["date"] = "15/06/05"
        data["entries"][0]["certification_date"] = "21/06/99"
        result = parse_pass1_response(self._make_response(data))
        assert result["entries"][0]["date"] == "15/06/2005"
        assert result["entries"][0]["certification_date"] == "21/06/1999"

    def test_parse_pass1_handles_code_fences(self):
        """JSON wrapped in ```json ... ``` should parse correctly."""
        data = self._sample_data()
        result = parse_pass1_response(self._make_response(data, wrap_fences=True))
        assert result["land_details"]["village_name"] == "Datha"
        assert len(result["entries"]) == 1

    def test_parse_pass1_handles_empty_response(self):
        """Empty or unparseable response should return empty structure."""
        result = parse_pass1_response("This is not JSON at all")
        assert result == {"land_details": {}, "entries": []}

    def test_parse_pass1_gujarati_numerals_in_land_details(self):
        """Gujarati numerals in land details should be converted."""
        data = self._sample_data()
        data["land_details"]["total_area"] = "\u0ae7-\u0ae8\u0ae6"  # ૧-૨૦
        result = parse_pass1_response(self._make_response(data))
        assert result["land_details"]["total_area"] == "1-20"
