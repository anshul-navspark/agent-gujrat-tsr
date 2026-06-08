"""
Gujarat TSR Generator package

This package contains modules for extracting information from PDF land records
and generating Title Search Reports.

EXTRACTION:
The token-efficient unified extractor (a SINGLE LLM call; ~50-70% fewer tokens
than the retired 3-call path) is the only extraction path. ``USE_OPTIMIZED`` is
kept as a constant (always ``True``) purely for backward-compatible imports.
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

# The legacy 3-call extraction path (USE_OPTIMIZED_EXTRACTION=false) was removed.
# Unified extraction is now the only path; the constant is retained (always True)
# so existing imports of ``USE_OPTIMIZED`` keep working.
USE_OPTIMIZED = True

# Import utilities (always available)
from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document
from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)

# Optimized unified extraction (single LLM call) — the sole extraction path.
from tsr_generator.api.tsr_generator_optimized import (
    generate_tsr_from_pdf_optimized as generate_tsr_from_pdf,
)
from tsr_generator.extractors.unified_extractor import (
    extract_all_unified,
    extract_land_details_optimized as extract_land_details,
    extract_entry_table_optimized as extract_entry_table,
    extract_entry_details_optimized as extract_entry_details,
    estimate_token_savings,
)
_extraction_mode = "optimized"

# Log the extraction mode being used
_logger = logging.getLogger(__name__)
_logger.info(f"TSR Generator initialized with {_extraction_mode} extraction mode")

__all__ = [
    # Main generation function
    'generate_tsr_from_pdf',

    # Extraction functions
    'extract_text_from_pdf',
    'extract_land_details',
    'extract_entry_details',
    'generate_findings_table',
    'create_tsr_document',

    # Optimized extraction
    'extract_all_unified',
    'estimate_token_savings',

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

    # Configuration
    'USE_OPTIMIZED'
]
