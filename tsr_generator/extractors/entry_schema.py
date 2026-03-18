"""
Entry schema module for representing different types of chain of title entries.
Defines structured schemas for various entry types in the chain of title section.
"""

import enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import logging


class EntryType(enum.Enum):
    """Enum representing different types of entries in chain of title."""
    SALE = "Sale"
    INHERITANCE = "Inheritance"
    DEATH = "Death"
    MUTATION = "Mutation"
    PARTITION = "Partition"
    LOAN = "Loan"
    LOAN_CLOSE = "Loan close"
    REDEMPTION = "Redemption"
    MORTGAGE = "Mortgage"
    RELEASE = "Release"
    ORDER = "Order"
    RELINQUISHMENT = "Relinquishment"
    GIFT = "Gift"
    ACQUISITION = "Acquisition"
    PROMULGATION = "Promulgation"
    CORRECTION = "Correction"
    PERSONS_ADD = "Persons Add"
    TRANSFER = "To transfer"
    EXCHANGE = "Exchange"
    LIFETIME_DISTRIBUTION = "Lifetime Distribution"
    NOT_RELATED = "Not Related"
    UNKNOWN = "Unknown"
    # New canonical types
    ALLOTMENT = "Allotment"
    TENURE_CHANGE = "Tenure Change"
    LAND_ACQUISITION = "Land Acquisition"
    LEASE = "Lease"
    SEIZURE = "Seizure"
    UNAVAILABLE = "Unavailable"


# ---------------------------------------------------------------------------
# Normalization mapping: variant strings -> canonical EntryType enum name
# ---------------------------------------------------------------------------

_NORMALIZATION_MAP: Dict[str, str] = {
    # Canonical aliases / consolidations
    'MORTGAGE': 'LOAN',
    'DEATH': 'INHERITANCE',
    'LOAN_CLOSE': 'RELEASE',
    'REDEMPTION': 'RELEASE',
    'CHARGE_REMOVED': 'RELEASE',
    'TRANSFER': 'SALE',
    'MUTATION': 'INHERITANCE',
    'PERSONS_ADD': 'INHERITANCE',
    'SUBDIVISION': 'PARTITION',
    'DIVISION': 'PARTITION',
    'RELEASE_OF_MORTGAGE': 'RELEASE',
    'HAYATIMA_VAHCHANI': 'PARTITION',
    'HAYATIMA_HAK_DAKHIL': 'INHERITANCE',

    # Gujarati / transliterated variants
    'હુકમથી': 'ORDER',
    'મૃત્યુ': 'INHERITANCE',
    'વારસાઈ': 'INHERITANCE',
    'વેચાણ': 'SALE',
    'મુક્તિ': 'RELEASE',
    'લોન': 'LOAN',
    'ચાર્જ': 'LOAN',
    'હયાતીમા વહચણી': 'PARTITION',
    'હયાતીમા હક દાખલ': 'INHERITANCE',
    'હયાતીમા વહચણી નામંજૂર': 'PARTITION',
    'વારસા': 'INHERITANCE',
    'વહચણી': 'PARTITION',
    'હક દાખલ': 'INHERITANCE',
    'નામંજૂર': 'CORRECTION',
    'વતી': 'INHERITANCE',
    'રદ': 'CORRECTION',
    'સુધારો': 'CORRECTION',
}

# All canonical enum member names (for fast lookup)
_CANONICAL_NAMES = frozenset(member.name for member in EntryType)


def normalize_entry_type(type_str: str) -> str:
    """
    Normalize a raw entry-type string to one of the canonical EntryType enum names.

    - If the string (after stripping / uppercasing / replacing spaces with
      underscores) is already a canonical name it is returned unchanged.
    - Otherwise the normalization map is consulted.
    - Unrecognised strings are returned as-is so downstream code can decide
      how to handle them.

    Args:
        type_str: Raw type string (English, Gujarati, or transliterated).

    Returns:
        Canonical enum member name (e.g. ``"SALE"``, ``"LOAN"``).
    """
    stripped = type_str.strip()

    # Try exact match in normalization map first (handles Gujarati strings)
    if stripped in _NORMALIZATION_MAP:
        return _NORMALIZATION_MAP[stripped]

    # Upper-case + underscore-normalised form
    normalised = stripped.upper().replace(' ', '_')

    if normalised in _NORMALIZATION_MAP:
        return _NORMALIZATION_MAP[normalised]

    if normalised in _CANONICAL_NAMES:
        return normalised

    # Try upper-case with spaces (for legacy mapping compat)
    upper_spaced = stripped.upper()
    if upper_spaced in _NORMALIZATION_MAP:
        return _NORMALIZATION_MAP[upper_spaced]

    # Return the normalised form so caller can attempt EntryType[value]
    return normalised


@dataclass
class Person:
    """Represents a person involved in a chain of title entry."""
    name: str
    role: Optional[str] = None
    relationship: Optional[str] = None
    description: Optional[str] = None


@dataclass
class BaseEntry:
    """Base class for all entry types."""
    entry_number: str
    date: str
    type: EntryType = EntryType.UNKNOWN
    raw_description: str = ""
    formatted_description: str = ""
    certification: str = ""
    entry_status: str = ""  # certified, rejected, not_accepted, cancelled
    certification_official: Optional[str] = None
    certification_date: Optional[str] = None


@dataclass
class SaleEntry(BaseEntry):
    """Represents a sale entry in the chain of title."""
    type: EntryType = EntryType.SALE
    # Existing fields (Person-based)
    sellers: List[Person] = field(default_factory=list)
    buyers: List[Person] = field(default_factory=list)
    consideration: Optional[str] = None
    property_details: Optional[str] = None
    # New structured fields
    seller_names: List[str] = field(default_factory=list)
    buyer_names: List[str] = field(default_factory=list)
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    consideration_amount: Optional[str] = None
    document_number: Optional[str] = None
    document_date: Optional[str] = None


@dataclass
class MortgageEntry(BaseEntry):
    """Represents a mortgage or loan entry in the chain of title."""
    type: EntryType = EntryType.MORTGAGE
    # Existing fields (Person-based)
    mortgagor: List[Person] = field(default_factory=list)
    mortgagee: List[Person] = field(default_factory=list)
    amount: Optional[str] = None
    period: Optional[str] = None
    interest_rate: Optional[str] = None
    # New structured fields
    borrowers: List[str] = field(default_factory=list)
    lender: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)

# Alias so callers can use either name
LoanEntry = MortgageEntry


@dataclass
class ReleaseEntry(BaseEntry):
    """Represents a release entry in the chain of title."""
    type: EntryType = EntryType.RELEASE
    # Existing fields (Person-based)
    releasor: List[Person] = field(default_factory=list)
    releasee: List[Person] = field(default_factory=list)
    reference_to_original: Optional[str] = None
    # New structured fields
    applicants: List[str] = field(default_factory=list)
    lender: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)
    reference_entry_number: Optional[str] = None


@dataclass
class InheritanceEntry(BaseEntry):
    """Represents an inheritance entry in the chain of title."""
    type: EntryType = EntryType.INHERITANCE
    deceased: Optional[Person] = None
    heirs: List[Person] = field(default_factory=list)
    death_date: Optional[str] = None
    shares: Optional[Dict[str, str]] = None
    # New structured fields
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None


@dataclass
class PartitionEntry(BaseEntry):
    """Represents a partition entry in the chain of title."""
    type: EntryType = EntryType.PARTITION
    original_owners: List[Person] = field(default_factory=list)
    resulting_allocations: Dict[str, str] = field(default_factory=dict)
    # New structured fields
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    allocations: List[Dict] = field(default_factory=list)


@dataclass
class RelinquishmentEntry(BaseEntry):
    """Represents a relinquishment entry in the chain of title."""
    type: EntryType = EntryType.RELINQUISHMENT
    relinquisher: List[Person] = field(default_factory=list)
    beneficiary: List[Person] = field(default_factory=list)
    relationship: Optional[str] = None
    # New structured fields
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None


@dataclass
class OrderEntry(BaseEntry):
    """Represents an order entry in the chain of title."""
    type: EntryType = EntryType.ORDER
    authority: Optional[str] = None
    order_details: Optional[str] = None
    affected_parties: List[Person] = field(default_factory=list)


@dataclass
class CorrectionEntry(BaseEntry):
    """Represents a correction entry in the chain of title."""
    type: EntryType = EntryType.CORRECTION
    original_entry: Optional[str] = None
    correction_details: Optional[str] = None


# ---------------------------------------------------------------------------
# New entry dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ExchangeEntry(BaseEntry):
    """Represents an exchange entry in the chain of title."""
    type: EntryType = EntryType.EXCHANGE
    party_a: List[str] = field(default_factory=list)
    party_b: List[str] = field(default_factory=list)
    survey_a: List[str] = field(default_factory=list)
    survey_b: List[str] = field(default_factory=list)
    area_a: Optional[str] = None
    area_b: Optional[str] = None


@dataclass
class LifetimeDistributionEntry(BaseEntry):
    """Represents a lifetime distribution entry in the chain of title."""
    type: EntryType = EntryType.LIFETIME_DISTRIBUTION
    distributor: Optional[str] = None
    recipients: List[str] = field(default_factory=list)
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    allocations: List[Dict] = field(default_factory=list)


@dataclass
class GiftEntry(BaseEntry):
    """Represents a gift entry in the chain of title."""
    type: EntryType = EntryType.GIFT
    donor: Optional[str] = None
    recipients: List[str] = field(default_factory=list)
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    document_number: Optional[str] = None
    document_date: Optional[str] = None


@dataclass
class AllotmentEntry(BaseEntry):
    """Represents an allotment entry in the chain of title."""
    type: EntryType = EntryType.ALLOTMENT
    grantee: List[str] = field(default_factory=list)
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    authority: Optional[str] = None
    legal_basis: Optional[str] = None


@dataclass
class TenureChangeEntry(BaseEntry):
    """Represents a tenure change entry in the chain of title."""
    type: EntryType = EntryType.TENURE_CHANGE
    authority: Optional[str] = None
    order_number: Optional[str] = None
    order_date: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)
    from_tenure: Optional[str] = None
    to_tenure: Optional[str] = None


@dataclass
class LandAcquisitionEntry(BaseEntry):
    """Represents a land acquisition entry in the chain of title."""
    type: EntryType = EntryType.LAND_ACQUISITION
    authority: Optional[str] = None
    award_number: Optional[str] = None
    award_date: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    purpose: Optional[str] = None


@dataclass
class LeaseEntry(BaseEntry):
    """Represents a lease entry in the chain of title."""
    type: EntryType = EntryType.LEASE
    lessor: List[str] = field(default_factory=list)
    lessee: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)
    area: Optional[str] = None
    period: Optional[str] = None
    purpose: Optional[str] = None


@dataclass
class SeizureEntry(BaseEntry):
    """Represents a seizure entry in the chain of title."""
    type: EntryType = EntryType.SEIZURE
    bank: Optional[str] = None
    survey_numbers: List[str] = field(default_factory=list)
    borrowers: List[str] = field(default_factory=list)
    reference_entry_number: Optional[str] = None


@dataclass
class PromulgationEntry(BaseEntry):
    """Represents a promulgation entry in the chain of title."""
    type: EntryType = EntryType.PROMULGATION
    authority: Optional[str] = None
    survey_number_mapping: Dict[str, List[str]] = field(default_factory=dict)
    effective_date: Optional[str] = None


@dataclass
class NotRelatedEntry(BaseEntry):
    """Represents an entry not related to the subject survey."""
    type: EntryType = EntryType.NOT_RELATED


@dataclass
class UnavailableEntry(BaseEntry):
    """Represents an entry whose details are unavailable."""
    type: EntryType = EntryType.UNAVAILABLE


@dataclass
class GenericEntry(BaseEntry):
    """Generic catch-all for other entry types."""
    parties: List[Person] = field(default_factory=list)
    additional_details: Dict[str, Any] = field(default_factory=dict)


# Type alias for any entry type
EntryUnion = Union[
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry,
    CorrectionEntry, ExchangeEntry, LifetimeDistributionEntry,
    GiftEntry, AllotmentEntry, TenureChangeEntry, LandAcquisitionEntry,
    LeaseEntry, SeizureEntry, PromulgationEntry, NotRelatedEntry,
    UnavailableEntry, GenericEntry, BaseEntry
]


def _build_certification_string(entry_dict: Dict[str, Any]) -> str:
    """
    Build certification string from structured fields.

    Args:
        entry_dict: Dictionary with certification_status, certification_official, certification_date fields

    Returns:
        Certification string like "The Entry is certified by C.O. Porbandar on 21/06/2005."
    """
    status = entry_dict.get('certification_status', '').strip()
    official = entry_dict.get('certification_official', '').strip()
    cert_date = entry_dict.get('certification_date', '').strip()

    if not status:
        if official or cert_date:
            status = 'certified'
        else:
            return ""

    # Fix: If LLM put a full sentence in certification_status instead of a keyword,
    # extract just the keyword (e.g. "The Entry is certified by..." -> "certified")
    import re
    if len(status) > 20 or ' ' in status:
        status_extract = re.search(r'(?:entry\s+is\s+)(certified|rejected|cancelled|not\s*accepted|not\s*approved)', status, re.IGNORECASE)
        if status_extract:
            status = status_extract.group(1).strip()
        else:
            entry_status = entry_dict.get('entry_status', '').strip()
            if entry_status and len(entry_status) < 20:
                status = entry_status

    # Map status to display text
    status_map = {
        'certified': 'certified',
        'rejected': 'rejected',
        'not_accepted': 'not accepted',
        'not_approved': 'not accepted',
        'not accepted': 'not accepted',
        'cancelled': 'cancelled'
    }
    display_status = status_map.get(status.lower(), status)

    # Build the certification string
    if official and cert_date:
        return f"The Entry is {display_status} by {official} on {cert_date}."
    elif official:
        return f"The Entry is {display_status} by {official}."
    elif cert_date:
        return f"The Entry is {display_status} on {cert_date}."
    else:
        return f"The Entry is {display_status}."

def create_entry_from_dict(entry_dict):
    """
    Create a structured entry object from a dictionary of entry details

    Args:
        entry_dict (dict): Dictionary with entry details

    Returns:
        BaseEntry: A structured entry object
    """
    logger = logging.getLogger(__name__)
    raw_type_str = str(entry_dict.get('type', 'UNKNOWN')).strip()

    # Use normalize_entry_type for the primary normalization pass
    entry_type_str = normalize_entry_type(raw_type_str)

    # Legacy mapping kept for additional variations not covered by normalize_entry_type
    type_mapping = {
        'MORTGAGE': 'LOAN',
        'LOAN CLOSE': 'RELEASE',
        'LOAN_CLOSE': 'RELEASE',
        'RELEASE OF MORTGAGE': 'RELEASE',
        'RELEASE_OF_MORTGAGE': 'RELEASE',
        'CHARGE REMOVED': 'RELEASE',
        'CHARGE_REMOVED': 'RELEASE',
        'DEATH': 'INHERITANCE',
        'PERSONS ADD': 'INHERITANCE',
        'PERSONS_ADD': 'INHERITANCE',
        'TO TRANSFER': 'SALE',
        'TRANSFER': 'SALE',
        'MUTATION': 'INHERITANCE',

        # New entry type variations
        'EXCHANGE': 'EXCHANGE',
        'LAND EXCHANGE': 'EXCHANGE',
        'LAND_EXCHANGE': 'EXCHANGE',
        'LIFETIME DISTRIBUTION': 'LIFETIME_DISTRIBUTION',
        'LIFE TIME DISTRIBUTION': 'LIFETIME_DISTRIBUTION',
        'LIFE_TIME_DISTRIBUTION': 'LIFETIME_DISTRIBUTION',
        'NOT RELATED': 'NOT_RELATED',
        'NOT RELATED TO SURVEY': 'NOT_RELATED',
        'NOT RELATED TO PRESENT SURVEY': 'NOT_RELATED',

        # Gujarati/translated variants normalization
        'હુકમથી': 'ORDER',
        'ORDER': 'ORDER',
        'મૃત્યુ': 'INHERITANCE',
        'વારસાઈ': 'INHERITANCE',
        'વેચાણ': 'SALE',
        'મુક્તિ': 'RELEASE',
        'લોન': 'LOAN',
        'ચાર્જ': 'LOAN',

        # Additional Gujarati entry types from logs
        'હયાતીમા વહચણી': 'PARTITION',
        'HAYATIMA VAHCHANI': 'PARTITION',
        'HAYATIMA_VAHCHANI': 'PARTITION',
        'હયાતીમા હક દાખલ': 'INHERITANCE',
        'HAYATIMA HAK DAKHIL': 'INHERITANCE',
        'HAYATIMA_HAK_DAKHIL': 'INHERITANCE',
        'હયાતીમા વહચણી નામંજૂર': 'PARTITION',
        'HAYATIMA VAHCHANI NAMANJUR': 'PARTITION',
        'વારસા': 'INHERITANCE',
        'VARSA': 'INHERITANCE',
        'વહચણી': 'PARTITION',
        'VAHCHANI': 'PARTITION',
        'હક દાખલ': 'INHERITANCE',
        'HAK DAKHIL': 'INHERITANCE',
        'નામંજૂર': 'CORRECTION',
        'NAMANJUR': 'CORRECTION',
        'વતી': 'INHERITANCE',
        'VATI': 'INHERITANCE',
        'રદ': 'CORRECTION',
        'RAD': 'CORRECTION',
        'સુધારો': 'CORRECTION',
        'SUDHARO': 'CORRECTION',

        # Common variations
        'PARTITION AMONG HEIRS': 'PARTITION',
        'PARTITION_AMONG_HEIRS': 'PARTITION',
        'INHERITANCE CLAIM': 'INHERITANCE',
        'INHERITANCE_CLAIM': 'INHERITANCE',
        'ENTRY CORRECTION': 'CORRECTION',
        'ENTRY_CORRECTION': 'CORRECTION',
        'CLAIM REJECTED': 'CORRECTION',
        'CLAIM_REJECTED': 'CORRECTION',
        'DIVISION': 'PARTITION',
        'SUBDIVISION': 'PARTITION',

        # New type variations
        'ALLOTMENT': 'ALLOTMENT',
        'TENURE CHANGE': 'TENURE_CHANGE',
        'TENURE_CHANGE': 'TENURE_CHANGE',
        'LAND ACQUISITION': 'LAND_ACQUISITION',
        'LAND_ACQUISITION': 'LAND_ACQUISITION',
        'LEASE': 'LEASE',
        'SEIZURE': 'SEIZURE',
        'UNAVAILABLE': 'UNAVAILABLE',
    }

    # Apply legacy mapping as fallback
    if entry_type_str in type_mapping:
        entry_type_str = type_mapping[entry_type_str]

    # Get the corresponding entry type enum
    try:
        entry_type = EntryType[entry_type_str]
    except KeyError:
        logger.warning(f"Unknown entry type: {entry_type_str}, using UNKNOWN")
        entry_type = EntryType.UNKNOWN

    # Get basic entry details
    entry_number = entry_dict.get('entry_number', '')
    date = entry_dict.get('date', '')
    description = entry_dict.get('description', '')

    # Get structured certification details
    certification_official = entry_dict.get('certification_official', '').strip()
    certification_date = entry_dict.get('certification_date', '').strip()
    entry_status = entry_dict.get('entry_status', '').strip()

    # Handle both old format (certification string) and new format (structured fields)
    certification = entry_dict.get('certification', '').strip()
    # If certification is empty or just whitespace, try to construct from structured fields
    if not certification:
        # Try to construct from structured fields
        certification = _build_certification_string(entry_dict)

    # Common kwargs shared by all entry constructors
    _common = dict(
        entry_number=entry_number,
        date=date,
        type=entry_type,
        raw_description=description,
        formatted_description=description,
        certification=certification,
        entry_status=entry_status,
        certification_official=certification_official,
        certification_date=certification_date,
    )

    # Create the appropriate entry object based on type
    if entry_type == EntryType.SALE:
        entry = SaleEntry(**_common)
    elif entry_type == EntryType.LOAN or entry_type == EntryType.MORTGAGE:
        entry = MortgageEntry(**_common)
    elif entry_type == EntryType.RELEASE:
        entry = ReleaseEntry(**_common)
    elif entry_type == EntryType.INHERITANCE:
        entry = InheritanceEntry(**_common)
    elif entry_type == EntryType.PARTITION:
        entry = PartitionEntry(**_common)
    elif entry_type == EntryType.RELINQUISHMENT:
        entry = RelinquishmentEntry(**_common)
    elif entry_type == EntryType.ORDER:
        entry = OrderEntry(**_common)
    elif entry_type == EntryType.CORRECTION:
        entry = CorrectionEntry(**_common)
    elif entry_type == EntryType.EXCHANGE:
        entry = ExchangeEntry(**_common)
    elif entry_type == EntryType.LIFETIME_DISTRIBUTION:
        entry = LifetimeDistributionEntry(**_common)
    elif entry_type == EntryType.GIFT:
        entry = GiftEntry(**_common)
    elif entry_type == EntryType.ALLOTMENT:
        entry = AllotmentEntry(**_common)
    elif entry_type == EntryType.TENURE_CHANGE:
        entry = TenureChangeEntry(**_common)
    elif entry_type == EntryType.LAND_ACQUISITION:
        entry = LandAcquisitionEntry(**_common)
    elif entry_type == EntryType.LEASE:
        entry = LeaseEntry(**_common)
    elif entry_type == EntryType.SEIZURE:
        entry = SeizureEntry(**_common)
    elif entry_type == EntryType.PROMULGATION:
        entry = PromulgationEntry(**_common)
    elif entry_type == EntryType.NOT_RELATED:
        entry = NotRelatedEntry(**_common)
    elif entry_type == EntryType.UNAVAILABLE:
        entry = UnavailableEntry(**_common)
    else:
        # For other or unknown types
        entry = GenericEntry(**_common)

    return entry
