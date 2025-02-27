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


def create_entry_from_dict(entry_dict):
    """
    Create a structured entry object from a dictionary of entry details
    
    Args:
        entry_dict (dict): Dictionary with entry details
        
    Returns:
        BaseEntry: A structured entry object
    """
    logger = logging.getLogger(__name__)
    entry_type_str = entry_dict.get('type', 'UNKNOWN').upper().strip()
    
    # Map certain entry types to their standard form
    type_mapping = {
        'MORTGAGE': 'LOAN',
        'LOAN CLOSE': 'RELEASE',
        'RELEASE OF MORTGAGE': 'RELEASE',
        'CHARGE REMOVED': 'RELEASE',
        'DEATH': 'INHERITANCE',
        'PERSONS ADD': 'PERSONS_ADD',
        'TO TRANSFER': 'TRANSFER'
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
    certification = entry_dict.get('certification', '')
    
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