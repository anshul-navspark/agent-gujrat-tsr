"""Tests for the deterministic template renderer."""

import pytest

from tsr_generator.extractors.template_renderer import (
    RENDERERS,
    render_entry_description,
)
from tsr_generator.extractors.type_configs import TYPE_CONFIGS


# ---------------------------------------------------------------------------
# SALE
# ---------------------------------------------------------------------------


def test_render_sale_all_fields():
    fields = {
        "sellers": ["Thakor Chaturji Gelaji", "Thakor Amartji Gelaji"],
        "buyers": ["Bharwad Nagjibhai"],
        "survey_numbers": ["105"],
        "area": "0-80-94 Hectare",
        "consideration_amount": "2,50,000",
        "document_number": "484/2022",
        "document_date": "16/06/2022",
    }
    result = render_entry_description("SALE", fields)
    assert result == (
        "That Thakor Chaturji Gelaji, Thakor Amartji Gelaji sold land "
        "bearing Survey No. 105 measuring 0-80-94 Hectare to Bharwad Nagjibhai "
        "through document no. 484/2022 dated 16/06/2022 "
        "in consideration of Rs. 2,50,000/-."
    )


def test_render_sale_missing_document():
    fields = {
        "sellers": ["Name A"],
        "buyers": ["Name B"],
        "survey_numbers": ["100"],
        "consideration_amount": "1,00,000",
    }
    result = render_entry_description("SALE", fields)
    assert result == (
        "That Name A sold land bearing Survey No. 100 to Name B "
        "in consideration of Rs. 1,00,000/-."
    )


def test_render_sale_missing_all_fields():
    result = render_entry_description("SALE", {})
    assert result == ""


def test_render_sale_empty_lists():
    result = render_entry_description("SALE", {
        "sellers": [],
        "buyers": [],
        "survey_numbers": [],
        "area": "",
        "consideration_amount": "",
    })
    assert result == ""


# ---------------------------------------------------------------------------
# LOAN
# ---------------------------------------------------------------------------


def test_render_loan():
    fields = {
        "borrowers": ["Thakor Chaturji"],
        "lender": "Bank of Baroda",
        "survey_numbers": ["105", "141"],
        "amount": "1,50,000",
    }
    result = render_entry_description("LOAN", fields)
    assert result == (
        "That Thakor Chaturji created a charge on land "
        "bearing Survey No. 105, 141 by taking loan from Bank of Baroda "
        "for a sum of Rs. 1,50,000/-. "
        "Therefore a charge in favour of Bank of Baroda was registered "
        "in the revenue records."
    )


def test_render_loan_no_lender():
    fields = {
        "borrowers": ["Person A"],
        "survey_numbers": ["50"],
        "amount": "10,000",
    }
    result = render_entry_description("LOAN", fields)
    assert "Therefore a charge" not in result
    assert result.endswith(".")


# ---------------------------------------------------------------------------
# RELEASE
# ---------------------------------------------------------------------------


def test_render_release():
    fields = {
        "applicants": ["Thakor Chaturji"],
        "lender": "Bank of Baroda",
        "reference_entry_number": "3521",
    }
    result = render_entry_description("RELEASE", fields)
    assert result == (
        "That upon receiving an application from Thakor Chaturji for exemption "
        "of burden of Bank of Baroda (Entry No. 3521), the said exemption of "
        "burden has been recorded."
    )


def test_render_release_no_ref():
    fields = {
        "applicants": ["Person A"],
        "lender": "Some Bank",
    }
    result = render_entry_description("RELEASE", fields)
    assert "Entry No." not in result
    assert "Some Bank" in result


# ---------------------------------------------------------------------------
# INHERITANCE
# ---------------------------------------------------------------------------


def test_render_inheritance():
    fields = {
        "deceased": "Thakor Sukhaji Karmal",
        "heirs": ["Sonaji Sukhaji", "Puriben Sukhaji", "Hamirji Sukhaji"],
        "survey_numbers": ["102"],
        "area": "",
    }
    result = render_entry_description("INHERITANCE", fields)
    assert result.startswith("That upon the demise of Thakor Sukhaji Karmal")
    assert "Survey No. 102" in result
    assert "Sonaji Sukhaji, Puriben Sukhaji, Hamirji Sukhaji" in result


def test_render_inheritance_with_area():
    fields = {
        "deceased": "Person X",
        "heirs": ["Heir A"],
        "survey_numbers": ["50"],
        "area": "1-00-00 Hectare",
    }
    result = render_entry_description("INHERITANCE", fields)
    assert "measuring 1-00-00 Hectare" in result


# ---------------------------------------------------------------------------
# PARTITION
# ---------------------------------------------------------------------------


def test_render_partition_with_allocations():
    fields = {
        "original_owner": "Vadher Jivabhai Sukhabhai",
        "recipients": ["Vadher Jalabhai Jivabhai", "Vadher Bachubhai Jivabhai"],
        "survey_numbers": ["121", "71/1p1"],
        "area": "",
        "allocations": [
            {"name": "Vadher Jalabhai Jivabhai", "survey_number": "121", "area": "1-56-82 Hectare"},
            {"name": "Vadher Bachubhai Jivabhai", "survey_number": "71/1p1", "area": "1-40-00 Hectare"},
        ],
    }
    result = render_entry_description("PARTITION", fields)
    assert result.startswith("That Vadher Jivabhai Sukhabhai distributed the land")
    assert "1. Vadher Jalabhai Jivabhai - Survey No. 121 - 1-56-82 Hectare" in result
    assert "2. Vadher Bachubhai Jivabhai - Survey No. 71/1p1 - 1-40-00 Hectare" in result
    assert "partition was recorded" in result


# ---------------------------------------------------------------------------
# NOT_RELATED and UNAVAILABLE
# ---------------------------------------------------------------------------


def test_render_not_related():
    result = render_entry_description("NOT_RELATED", {})
    assert result == "This entry is not related to the present survey number(s)."


def test_render_not_related_with_extra_fields():
    result = render_entry_description("NOT_RELATED", {"foo": "bar"})
    assert result == "This entry is not related to the present survey number(s)."


def test_render_unavailable():
    result = render_entry_description("UNAVAILABLE", {})
    assert result == "The data for this entry is not available."


# ---------------------------------------------------------------------------
# Empty / unknown
# ---------------------------------------------------------------------------


def test_render_empty_fields_returns_empty():
    """All types except NOT_RELATED/UNAVAILABLE return '' when fields are empty."""
    for entry_type in RENDERERS:
        if entry_type in ("NOT_RELATED", "UNAVAILABLE"):
            continue
        result = render_entry_description(entry_type, {})
        assert result == "", f"{entry_type} should return '' for empty fields"


def test_render_unknown_type_returns_empty():
    result = render_entry_description("NONEXISTENT_TYPE", {"foo": "bar"})
    assert result == ""


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


def test_all_19_types_have_renderers():
    """Every key in TYPE_CONFIGS must have a renderer."""
    for type_key in TYPE_CONFIGS:
        assert type_key in RENDERERS, f"Missing renderer for {type_key}"


def test_renderer_count():
    """We should have exactly 19 renderers."""
    assert len(RENDERERS) == 19


# ---------------------------------------------------------------------------
# Other types - basic smoke tests
# ---------------------------------------------------------------------------


def test_render_relinquishment():
    fields = {
        "relinquisher": "Person A",
        "beneficiaries": ["Person B", "Person C"],
        "survey_numbers": ["50"],
    }
    result = render_entry_description("RELINQUISHMENT", fields)
    assert result.startswith("That Person A relinquished")
    assert "Survey No. 50" in result
    assert "Person B, Person C" in result


def test_render_exchange():
    fields = {
        "party_a": ["Person A"],
        "party_b": ["Person B"],
        "survey_a": ["100"],
        "survey_b": ["200"],
        "area_a": "1 Acre",
        "area_b": "2 Acre",
    }
    result = render_entry_description("EXCHANGE", fields)
    assert "exchanged their lands" in result
    assert "Survey No. 100" in result
    assert "Survey No. 200" in result


def test_render_lifetime_distribution():
    fields = {
        "distributor": "Father Name",
        "recipients": ["Son A", "Son B"],
        "survey_numbers": ["10"],
        "allocations": [
            {"name": "Son A", "survey_number": "10", "area": "1 Hectare"},
        ],
    }
    result = render_entry_description("LIFETIME_DISTRIBUTION", fields)
    assert "during their lifetime" in result
    assert "1. Son A - Survey No. 10 - 1 Hectare" in result


def test_render_gift():
    fields = {
        "donor": "Person A",
        "recipients": ["Person B"],
        "survey_numbers": ["45"],
        "area": "0-50-00 Hectare",
        "document_number": "312/2018",
        "document_date": "10/03/2018",
    }
    result = render_entry_description("GIFT", fields)
    assert result.startswith("That Person A gifted land")
    assert "Survey No. 45" in result
    assert "document no. 312/2018 dated 10/03/2018" in result


def test_render_seizure():
    fields = {
        "bank": "SBI",
        "survey_numbers": ["37", "68"],
        "borrowers": ["Person A"],
        "reference_entry_number": "100",
    }
    result = render_entry_description("SEIZURE", fields)
    assert "SBI seized the land" in result
    assert "Entry No. 100" in result


def test_render_order():
    fields = {
        "authority": "Mamlatdar",
        "order_number": "123/2020",
        "order_date": "01/01/2020",
        "order_summary": "cancellation of entries",
    }
    result = render_entry_description("ORDER", fields)
    assert "Mamlatdar" in result
    assert "Order No. 123/2020 dated 01/01/2020" in result
    assert "cancellation of entries" in result


def test_render_allotment():
    fields = {
        "grantee": ["Person A"],
        "survey_numbers": ["102"],
        "authority": "Mamlatdar Sami",
        "legal_basis": "Section 43",
    }
    result = render_entry_description("ALLOTMENT", fields)
    assert "granted land" in result
    assert "by Mamlatdar Sami" in result
    assert "under Section 43" in result


def test_render_tenure_change():
    fields = {
        "authority": "Mamlatdar Sami",
        "order_number": "ABC/123",
        "order_date": "09/09/1997",
        "from_tenure": "New Tenure",
        "to_tenure": "Old Tenure",
    }
    result = render_entry_description("TENURE_CHANGE", fields)
    assert "changed the condition" in result
    assert "from New Tenure to Old Tenure" in result
    assert "free from the restrictions of New Tenure" in result


def test_render_land_acquisition():
    fields = {
        "authority": "Land Acquisition Officer",
        "award_number": "115/2010",
        "award_date": "07/12/2011",
        "survey_numbers": ["220", "230 P"],
        "purpose": "road construction",
    }
    result = render_entry_description("LAND_ACQUISITION", fields)
    assert "Award No. 115/2010 dated 07/12/2011" in result
    assert "Survey No. 220, 230 P" in result
    assert "road construction" in result


def test_render_lease():
    fields = {
        "lessor": ["Person A"],
        "lessee": "Company X",
        "survey_numbers": ["848/313"],
        "area": "3.8850 Hectare",
        "period": "29 years",
    }
    result = render_entry_description("LEASE", fields)
    assert "leased land" in result
    assert "to Company X" in result
    assert "for a period of 29 years" in result


def test_render_promulgation():
    fields = {
        "authority": "Settlement Commissioner",
        "survey_number_mapping": {"266p2": ["1235"]},
        "effective_date": "19/02/2025",
    }
    result = render_entry_description("PROMULGATION", fields)
    assert "re-survey" in result
    assert "Old Survey No. 266p2 became new Survey No. 1235" in result


def test_render_correction():
    fields = {
        "correction_type": "Area correction",
        "original_value": "4-00-00 Hectares",
        "corrected_value": "4-04-69 Hectares",
        "reference_entry_number": "422",
    }
    result = render_entry_description("CORRECTION", fields)
    assert "Area correction was corrected" in result
    assert "'4-00-00 Hectares'" in result
    assert "'4-04-69 Hectares'" in result
    assert "Entry No. 422" in result
