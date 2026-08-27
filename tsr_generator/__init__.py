"""
Gujarat TSR Generator package

This package contains modules for extracting information from PDF land records
and generating Title Search Reports.

Extraction runs through the token-efficient unified path: a single LLM call
covering land details, entry numbers and mutation entries (~50-70% cheaper
than the retired 3-call pipeline).
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

# Import utilities (always available)
from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document
from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)

# Unified single-call extraction — the only supported pipeline.
from tsr_generator.api.tsr_generator_optimized import (
    generate_tsr_from_pdf_optimized as generate_tsr_from_pdf,
    compare_extraction_methods
)
from tsr_generator.extractors.unified_extractor import (
    extract_all_unified,
    extract_land_details_optimized as extract_land_details,
    extract_entry_table_optimized as extract_entry_table,
    extract_entry_details_optimized as extract_entry_details,
    estimate_token_savings
)

_logger = logging.getLogger(__name__)
_logger.info("TSR Generator initialized with unified extraction")

__all__ = [
    # Main generation function
    'generate_tsr_from_pdf',

    # Extraction functions
    'extract_text_from_pdf',
    'extract_land_details',
    'extract_entry_details',
    'generate_findings_table',
    'create_tsr_document',

    # Optimized extraction (if enabled)
    'extract_all_unified',
    'estimate_token_savings',
    'compare_extraction_methods',

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
    'GenericEntry',
]
