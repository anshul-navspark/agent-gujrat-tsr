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
    

@dataclass
class SaleEntry(BaseEntry):
    """Represents a sale entry in the chain of title."""
    type: EntryType = EntryType.SALE
    sellers: List[Person] = field(default_factory=list)
    buyers: List[Person] = field(default_factory=list)
    consideration: Optional[str] = None
    property_details: Optional[str] = None
    

@dataclass
class MortgageEntry(BaseEntry):
    """Represents a mortgage or loan entry in the chain of title."""
    type: EntryType = EntryType.MORTGAGE
    mortgagor: List[Person] = field(default_factory=list)
    mortgagee: List[Person] = field(default_factory=list)
    amount: Optional[str] = None
    period: Optional[str] = None
    interest_rate: Optional[str] = None
    

@dataclass
class ReleaseEntry(BaseEntry):
    """Represents a release entry in the chain of title."""
    type: EntryType = EntryType.RELEASE
    releasor: List[Person] = field(default_factory=list)
    releasee: List[Person] = field(default_factory=list)
    reference_to_original: Optional[str] = None


@dataclass
class InheritanceEntry(BaseEntry):
    """Represents an inheritance entry in the chain of title."""
    type: EntryType = EntryType.INHERITANCE
    deceased: Optional[Person] = None
    heirs: List[Person] = field(default_factory=list)
    death_date: Optional[str] = None
    shares: Optional[Dict[str, str]] = None
    

@dataclass
class PartitionEntry(BaseEntry):
    """Represents a partition entry in the chain of title."""
    type: EntryType = EntryType.PARTITION
    original_owners: List[Person] = field(default_factory=list)
    resulting_allocations: Dict[str, str] = field(default_factory=dict)
    

@dataclass
class RelinquishmentEntry(BaseEntry):
    """Represents a relinquishment entry in the chain of title."""
    type: EntryType = EntryType.RELINQUISHMENT
    relinquisher: List[Person] = field(default_factory=list)
    beneficiary: List[Person] = field(default_factory=list)
    relationship: Optional[str] = None
    

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
    

@dataclass
class GenericEntry(BaseEntry):
    """Generic catch-all for other entry types."""
    parties: List[Person] = field(default_factory=list)
    additional_details: Dict[str, Any] = field(default_factory=dict)


# Type alias for any entry type
EntryUnion = Union[
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry, 
    PartitionEntry, RelinquishmentEntry, OrderEntry, 
    CorrectionEntry, GenericEntry, BaseEntry
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
    entry_type_str = str(entry_dict.get('type', 'UNKNOWN')).upper().strip()
    
    # Map certain entry types to their standard form
    type_mapping = {
        'MORTGAGE': 'LOAN',
        'LOAN CLOSE': 'RELEASE',
        'RELEASE OF MORTGAGE': 'RELEASE',
        'CHARGE REMOVED': 'RELEASE',
        'DEATH': 'INHERITANCE',
        'PERSONS ADD': 'PERSONS_ADD',
        'TO TRANSFER': 'TRANSFER',

        # New entry type variations
        'EXCHANGE': 'EXCHANGE',
        'LAND EXCHANGE': 'EXCHANGE',
        'LIFETIME DISTRIBUTION': 'LIFETIME_DISTRIBUTION',
        'LIFE TIME DISTRIBUTION': 'LIFETIME_DISTRIBUTION',
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
        'ચાર્જ': 'MORTGAGE',

        # Additional Gujarati entry types from logs
        'હયાતીમા વહચણી': 'PARTITION',
        'HAYATIMA VAHCHANI': 'PARTITION',
        'હયાતીમા હક દાખલ': 'INHERITANCE',
        'HAYATIMA HAK DAKHIL': 'INHERITANCE',
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
        'INHERITANCE CLAIM': 'INHERITANCE',
        'ENTRY CORRECTION': 'CORRECTION',
        'CLAIM REJECTED': 'CORRECTION',
        'DIVISION': 'PARTITION',
        'SUBDIVISION': 'PARTITION'
    }
    
    # Normalize the entry type
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
    
    # Handle both old format (certification string) and new format (structured fields)
    certification = entry_dict.get('certification', '').strip()
    # If certification is empty or just whitespace, try to construct from structured fields
    if not certification:
        # Try to construct from structured fields
        certification = _build_certification_string(entry_dict)
    
    # Create the appropriate entry object based on type
    if entry_type == EntryType.SALE:
        entry = SaleEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.LOAN or entry_type == EntryType.MORTGAGE:
        entry = MortgageEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.RELEASE:
        entry = ReleaseEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.INHERITANCE:
        entry = InheritanceEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.PARTITION:
        entry = PartitionEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.RELINQUISHMENT:
        entry = RelinquishmentEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.ORDER:
        entry = OrderEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    elif entry_type == EntryType.CORRECTION:
        entry = CorrectionEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    else:
        # For other or unknown types
        entry = GenericEntry(
            entry_number=entry_number,
            date=date,
            type=entry_type,
            raw_description=description,
            formatted_description=description,
            certification=certification
        )
    
    return entry 