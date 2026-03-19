"""Tests for the two-pass structured extraction pipeline."""

import json
import pytest

from tsr_generator.extractors.unified_extractor import (
    _format_amount,
    _merge_pass2_into_entries,
    _convert_land_details_for_compat,
    StructuredExtractionResult,
)


# ---------------------------------------------------------------------------
# _format_amount tests
# ---------------------------------------------------------------------------


class TestFormatAmount:
    def test_basic_formatting(self):
        assert _format_amount("250000") == "2,50,000"

    def test_small_number(self):
        assert _format_amount("500") == "500"

    def test_already_formatted(self):
        assert _format_amount("2,50,000") == "2,50,000"

    def test_empty(self):
        assert _format_amount("") == ""

    def test_non_numeric(self):
        assert _format_amount("not a number") == "not a number"

    def test_large_number(self):
        assert _format_amount("10000000") == "1,00,00,000"

    def test_four_digits(self):
        assert _format_amount("5000") == "5,000"

    def test_five_digits(self):
        assert _format_amount("50000") == "50,000"

    def test_six_digits(self):
        assert _format_amount("100000") == "1,00,000"


# ---------------------------------------------------------------------------
# _merge_pass2_into_entries tests
# ---------------------------------------------------------------------------


class TestMergePass2:
    def test_basic_merge(self):
        pass1 = [
            {
                "entry_number": "100",
                "date": "01/01/2020",
                "type": "SALE",
                "certification_status": "certified",
                "certification_official": "C.O. Sami",
                "certification_date": "10/10/2020",
            }
        ]
        pass2 = [
            {
                "entry_number": "100",
                "sellers": ["A"],
                "buyers": ["B"],
                "consideration_amount": "500000",
            }
        ]
        merged = _merge_pass2_into_entries(pass1, pass2)
        assert len(merged) == 1
        entry = merged[0]
        assert entry["entry_number"] == "100"
        assert entry["type"] == "SALE"
        assert entry["sellers"] == ["A"]
        assert entry["buyers"] == ["B"]
        # Amount should be formatted
        assert entry["consideration_amount"] == "5,00,000"
        # Description should be rendered by template
        assert "sold" in entry["description"].lower() or entry["description"] == ""
        # Certification should be built
        assert "certified" in entry["certification"]

    def test_merge_with_missing_pass2(self):
        """Entries without Pass 2 data still get metadata from Pass 1."""
        pass1 = [
            {
                "entry_number": "200",
                "date": "15/06/21",
                "type": "NOT_RELATED",
                "certification_status": "",
                "certification_official": "",
                "certification_date": "",
            }
        ]
        merged = _merge_pass2_into_entries(pass1, [])
        assert len(merged) == 1
        entry = merged[0]
        assert entry["entry_number"] == "200"
        # Date should be normalized
        assert entry["date"] == "15/06/2021"
        # Fixed-text type should render
        assert "not related" in entry["description"].lower()

    def test_merge_preserves_all_pass1_entries(self):
        pass1 = [
            {"entry_number": "100", "date": "", "type": "LOAN",
             "certification_status": "", "certification_official": "",
             "certification_date": ""},
            {"entry_number": "200", "date": "", "type": "RELEASE",
             "certification_status": "", "certification_official": "",
             "certification_date": ""},
        ]
        pass2 = [
            {"entry_number": "100", "borrowers": ["X"], "lender": "SBI", "amount": "20000"},
        ]
        merged = _merge_pass2_into_entries(pass1, pass2)
        assert len(merged) == 2
        # Entry 100 has Pass 2 fields
        assert merged[0]["lender"] == "SBI"
        # Entry 200 has no Pass 2 fields
        assert "lender" not in merged[1] or merged[1].get("lender", "") == ""


# ---------------------------------------------------------------------------
# _convert_land_details_for_compat tests
# ---------------------------------------------------------------------------


class TestConvertLandDetails:
    def test_basic_conversion(self):
        pass1_land = {
            "village_name": "Keshav",
            "taluka_name": "Dhanera",
            "district_name": "Banaskantha",
            "survey_numbers": ["105", "141"],
            "old_survey_numbers": ["159"],
            "total_area": "2-55-98",
            "nature_of_land": "Old Tenure Agricultural",
            "owners": ["Ram", "Shyam"],
        }
        compat = _convert_land_details_for_compat(pass1_land)
        assert compat["village_name"] == "Keshav"
        assert "105" in compat["survey_number"]
        assert "141" in compat["survey_number"]
        assert compat["old_survey_number"] == "159"
        assert "Ram" in compat["owner"]
        assert "Shyam" in compat["owner"]

    def test_empty_fields_default(self):
        compat = _convert_land_details_for_compat({})
        assert compat["village_name"] == "Not Available"
        assert compat["survey_number"] == "Not Available"
        assert compat["old_survey_number"] == "Not Available"
        assert compat["owner"] == "Not Available"


# ---------------------------------------------------------------------------
# Findings with structured entries
# ---------------------------------------------------------------------------


class TestFindingsWithStructuredEntries:
    """Test that detect_active_encumbrances works with dataclass entries."""

    def test_with_dataclass_entries(self):
        from tsr_generator.extractors.entry_schema import (
            MortgageEntry, ReleaseEntry, EntryType,
        )
        from tsr_generator.extractors.findings import detect_active_encumbrances

        loan = MortgageEntry(
            entry_number="100",
            date="01/01/2020",
            type=EntryType.LOAN,
            lender="State Bank of India",
        )
        release = ReleaseEntry(
            entry_number="200",
            date="01/01/2022",
            type=EntryType.RELEASE,
            lender="State Bank of India",
            reference_entry_number="100",
        )
        active, nums = detect_active_encumbrances([loan, release])
        assert len(active) == 0
        assert len(nums) == 0

    def test_unreleased_loan(self):
        from tsr_generator.extractors.entry_schema import MortgageEntry, EntryType
        from tsr_generator.extractors.findings import detect_active_encumbrances

        loan = MortgageEntry(
            entry_number="100",
            date="01/01/2020",
            type=EntryType.LOAN,
            lender="Bank of Baroda",
        )
        active, nums = detect_active_encumbrances([loan])
        assert len(active) == 1
        assert nums == ["100"]

    def test_with_dict_entries_backward_compat(self):
        from tsr_generator.extractors.findings import detect_active_encumbrances

        entries = [
            {"entry_number": "100", "type": "LOAN",
             "description": "took a loan from State Bank of India"},
            {"entry_number": "200", "type": "RELEASE",
             "description": "exemption of burden of State Bank of India. Entry No. 100"},
        ]
        active, nums = detect_active_encumbrances(entries)
        assert len(active) == 0

    def test_seizure_not_separate_encumbrance(self):
        from tsr_generator.extractors.entry_schema import (
            MortgageEntry, SeizureEntry, EntryType,
        )
        from tsr_generator.extractors.findings import detect_active_encumbrances

        loan = MortgageEntry(
            entry_number="100",
            date="01/01/2020",
            type=EntryType.LOAN,
            lender="SBI",
        )
        seizure = SeizureEntry(
            entry_number="200",
            date="01/01/2022",
            type=EntryType.SEIZURE,
            bank="SBI",
            reference_entry_number="100",
        )
        active, nums = detect_active_encumbrances([loan, seizure])
        # Seizure is NOT treated as separate encumbrance; the LOAN stays active
        assert len(active) == 1
        assert nums == ["100"]
