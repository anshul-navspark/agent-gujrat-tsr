"""
Gujarat TSR Generator package

This package contains modules for extracting information from PDF land records
and generating Title Search Reports.
"""

import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Import for direct access
from tsr_generator.api.tsr_generator import generate_tsr_from_pdf
from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.land_details import extract_land_details
from tsr_generator.extractors.entry_details import extract_entry_details
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document
from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion, 
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry, 
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)

__all__ = [
    'generate_tsr_from_pdf',
    'extract_text_from_pdf',
    'extract_land_details',
    'extract_entry_details',
    'generate_findings_table',
    'create_tsr_document',
    # Schema classes
    'EntryType',
    'Person',
    'BaseEntry',
    'EntryUnion',
    'SaleEntry',
    'MortgageEntry',
    'ReleaseEntry',
    'InheritanceEntry',
    'PartitionEntry',
    'RelinquishmentEntry',
    'OrderEntry',
    'CorrectionEntry',
    'GenericEntry'
]
