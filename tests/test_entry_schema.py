"""Tests for tsr_generator.extractors.entry_schema module."""

import pytest
from tsr_generator.extractors.entry_schema import (
    EntryType,
    normalize_entry_type,
    create_entry_from_dict,
    BaseEntry,
    SaleEntry,
    MortgageEntry,
    LoanEntry,
    ReleaseEntry,
    InheritanceEntry,
    PartitionEntry,
    RelinquishmentEntry,
    OrderEntry,
    CorrectionEntry,
    ExchangeEntry,
    LifetimeDistributionEntry,
    GiftEntry,
    AllotmentEntry,
    TenureChangeEntry,
    LandAcquisitionEntry,
    LeaseEntry,
    SeizureEntry,
    PromulgationEntry,
    NotRelatedEntry,
    UnavailableEntry,
    GenericEntry,
)


# ---------------------------------------------------------------------------
# EntryType enum tests
# ---------------------------------------------------------------------------

class TestEntryTypeEnum:
    """Test that all 27 EntryType enum values exist (21 original + 6 new)."""

    EXPECTED_CANONICAL = [
        "SALE", "INHERITANCE", "DEATH", "MUTATION", "PARTITION",
        "LOAN", "LOAN_CLOSE", "REDEMPTION", "MORTGAGE", "RELEASE",
        "ORDER", "RELINQUISHMENT", "GIFT", "ACQUISITION", "PROMULGATION",
        "CORRECTION", "PERSONS_ADD", "TRANSFER", "EXCHANGE",
        "LIFETIME_DISTRIBUTION", "NOT_RELATED", "UNKNOWN",
        # 6 new ones
        "ALLOTMENT", "TENURE_CHANGE", "LAND_ACQUISITION", "LEASE",
        "SEIZURE", "UNAVAILABLE",
    ]

    def test_all_canonical_types_exist(self):
        for name in self.EXPECTED_CANONICAL:
            assert hasattr(EntryType, name), f"EntryType.{name} missing"

    def test_enum_count(self):
        # 22 original + 6 new = 28
        assert len(EntryType) == 28


# ---------------------------------------------------------------------------
# normalize_entry_type tests
# ---------------------------------------------------------------------------

class TestNormalizeEntryType:
    """Test normalize_entry_type for all required mappings."""

    @pytest.mark.parametrize("raw, expected", [
        ("MORTGAGE", "LOAN"),
        ("DEATH", "INHERITANCE"),
        ("LOAN_CLOSE", "RELEASE"),
        ("REDEMPTION", "RELEASE"),
        ("CHARGE_REMOVED", "RELEASE"),
        ("TRANSFER", "SALE"),
        ("MUTATION", "INHERITANCE"),
        ("PERSONS_ADD", "INHERITANCE"),
        ("SUBDIVISION", "PARTITION"),
        ("DIVISION", "PARTITION"),
        ("RELEASE_OF_MORTGAGE", "RELEASE"),
        ("HAYATIMA_VAHCHANI", "PARTITION"),
        ("HAYATIMA_HAK_DAKHIL", "INHERITANCE"),
    ])
    def test_english_mappings(self, raw, expected):
        assert normalize_entry_type(raw) == expected

    @pytest.mark.parametrize("raw, expected", [
        ("વેચાણ", "SALE"),
        ("મૃત્યુ", "INHERITANCE"),
        ("વારસાઈ", "INHERITANCE"),
        ("મુક્તિ", "RELEASE"),
        ("લોન", "LOAN"),
        ("ચાર્જ", "LOAN"),
        ("હુકમથી", "ORDER"),
        ("હયાતીમા વહચણી", "PARTITION"),
        ("હયાતીમા હક દાખલ", "INHERITANCE"),
    ])
    def test_gujarati_mappings(self, raw, expected):
        assert normalize_entry_type(raw) == expected

    @pytest.mark.parametrize("canonical", [
        "SALE", "INHERITANCE", "PARTITION", "LOAN", "RELEASE",
        "ORDER", "RELINQUISHMENT", "GIFT", "ALLOTMENT", "LEASE",
        "SEIZURE", "UNAVAILABLE", "PROMULGATION", "CORRECTION",
        "EXCHANGE", "LIFETIME_DISTRIBUTION", "NOT_RELATED",
        "LAND_ACQUISITION", "TENURE_CHANGE",
    ])
    def test_canonical_types_returned_unchanged(self, canonical):
        assert normalize_entry_type(canonical) == canonical

    def test_case_insensitive(self):
        assert normalize_entry_type("mortgage") == "LOAN"
        assert normalize_entry_type("Sale") == "SALE"

    def test_whitespace_handling(self):
        assert normalize_entry_type("  MORTGAGE  ") == "LOAN"

    def test_unknown_passthrough(self):
        result = normalize_entry_type("SOME_WEIRD_TYPE")
        assert result == "SOME_WEIRD_TYPE"


# ---------------------------------------------------------------------------
# Dataclass field tests
# ---------------------------------------------------------------------------

class TestSaleEntry:
    def test_default_fields(self):
        entry = SaleEntry(entry_number="1", date="2024-01-01")
        assert entry.seller_names == []
        assert entry.buyer_names == []
        assert entry.survey_numbers == []
        assert entry.area is None
        assert entry.consideration_amount is None
        assert entry.document_number is None
        assert entry.document_date is None
        # Existing fields still present
        assert entry.sellers == []
        assert entry.buyers == []
        assert entry.type == EntryType.SALE


class TestLoanEntry:
    def test_alias(self):
        assert LoanEntry is MortgageEntry

    def test_default_fields(self):
        entry = LoanEntry(entry_number="2", date="2024-01-01")
        assert entry.borrowers == []
        assert entry.lender is None
        assert entry.survey_numbers == []
        assert entry.amount is None
        # Existing fields
        assert entry.mortgagor == []
        assert entry.mortgagee == []


class TestReleaseEntry:
    def test_default_fields(self):
        entry = ReleaseEntry(entry_number="3", date="2024-01-01")
        assert entry.applicants == []
        assert entry.lender is None
        assert entry.survey_numbers == []
        assert entry.reference_entry_number is None
        # Existing
        assert entry.releasor == []
        assert entry.reference_to_original is None


class TestAllotmentEntry:
    def test_default_fields(self):
        entry = AllotmentEntry(entry_number="4", date="2024-01-01")
        assert entry.grantee == []
        assert entry.survey_numbers == []
        assert entry.area is None
        assert entry.authority is None
        assert entry.legal_basis is None
        assert entry.type == EntryType.ALLOTMENT


class TestInheritanceEntry:
    def test_new_fields(self):
        entry = InheritanceEntry(entry_number="5", date="2024-01-01")
        assert entry.survey_numbers == []
        assert entry.area is None


class TestPartitionEntry:
    def test_new_fields(self):
        entry = PartitionEntry(entry_number="6", date="2024-01-01")
        assert entry.survey_numbers == []
        assert entry.area is None
        assert entry.allocations == []


class TestRelinquishmentEntry:
    def test_new_fields(self):
        entry = RelinquishmentEntry(entry_number="7", date="2024-01-01")
        assert entry.survey_numbers == []
        assert entry.area is None


# ---------------------------------------------------------------------------
# create_entry_from_dict tests
# ---------------------------------------------------------------------------

class TestCreateEntryFromDict:
    """Test that create_entry_from_dict creates the correct entry types."""

    def _make(self, type_str, **kwargs):
        d = {"type": type_str, "entry_number": "1", "date": "2024-01-01", "description": "test"}
        d.update(kwargs)
        return create_entry_from_dict(d)

    def test_sale(self):
        entry = self._make("SALE")
        assert isinstance(entry, SaleEntry)
        assert entry.type == EntryType.SALE

    def test_mortgage_normalised_to_loan(self):
        entry = self._make("MORTGAGE")
        assert isinstance(entry, MortgageEntry)
        assert entry.type == EntryType.LOAN

    def test_loan(self):
        entry = self._make("LOAN")
        assert isinstance(entry, MortgageEntry)
        assert entry.type == EntryType.LOAN

    def test_release(self):
        entry = self._make("RELEASE")
        assert isinstance(entry, ReleaseEntry)

    def test_inheritance(self):
        entry = self._make("INHERITANCE")
        assert isinstance(entry, InheritanceEntry)

    def test_death_normalised_to_inheritance(self):
        entry = self._make("DEATH")
        assert isinstance(entry, InheritanceEntry)

    def test_partition(self):
        entry = self._make("PARTITION")
        assert isinstance(entry, PartitionEntry)

    def test_division_normalised_to_partition(self):
        entry = self._make("DIVISION")
        assert isinstance(entry, PartitionEntry)

    def test_exchange(self):
        entry = self._make("EXCHANGE")
        assert isinstance(entry, ExchangeEntry)

    def test_lifetime_distribution(self):
        entry = self._make("LIFETIME_DISTRIBUTION")
        assert isinstance(entry, LifetimeDistributionEntry)

    def test_gift(self):
        entry = self._make("GIFT")
        assert isinstance(entry, GiftEntry)

    def test_allotment(self):
        entry = self._make("ALLOTMENT")
        assert isinstance(entry, AllotmentEntry)

    def test_tenure_change(self):
        entry = self._make("TENURE_CHANGE")
        assert isinstance(entry, TenureChangeEntry)

    def test_land_acquisition(self):
        entry = self._make("LAND_ACQUISITION")
        assert isinstance(entry, LandAcquisitionEntry)

    def test_lease(self):
        entry = self._make("LEASE")
        assert isinstance(entry, LeaseEntry)

    def test_seizure(self):
        entry = self._make("SEIZURE")
        assert isinstance(entry, SeizureEntry)

    def test_promulgation(self):
        entry = self._make("PROMULGATION")
        assert isinstance(entry, PromulgationEntry)

    def test_not_related(self):
        entry = self._make("NOT_RELATED")
        assert isinstance(entry, NotRelatedEntry)

    def test_unavailable(self):
        entry = self._make("UNAVAILABLE")
        assert isinstance(entry, UnavailableEntry)

    def test_unknown_falls_back_to_generic(self):
        entry = self._make("SOMETHING_WEIRD")
        assert isinstance(entry, GenericEntry)
        assert entry.type == EntryType.UNKNOWN

    def test_gujarati_type(self):
        entry = self._make("વેચાણ")
        assert isinstance(entry, SaleEntry)

    def test_loan_close_normalised_to_release(self):
        entry = self._make("LOAN_CLOSE")
        assert isinstance(entry, ReleaseEntry)

    def test_redemption_normalised_to_release(self):
        entry = self._make("REDEMPTION")
        assert isinstance(entry, ReleaseEntry)
