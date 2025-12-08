"""
Gujarat TSR Generator package

This package contains modules for extracting information from PDF land records
and generating Title Search Reports.

TOKEN OPTIMIZATION:
Set USE_OPTIMIZED_EXTRACTION=true environment variable to enable token-efficient
unified extraction (reduces API calls from 3 to 1, ~50-70% token savings).
"""

import logging
import sys
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Check if optimized extraction is enabled (default: True for new code)
USE_OPTIMIZED = os.getenv('USE_OPTIMIZED_EXTRACTION', 'true').lower() in ('true', '1', 'yes')

# Import utilities (always available)
from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document
from tsr_generator.extractors.entry_schema import (
    EntryType, Person, BaseEntry, EntryUnion,
    SaleEntry, MortgageEntry, ReleaseEntry, InheritanceEntry,
    PartitionEntry, RelinquishmentEntry, OrderEntry, CorrectionEntry, GenericEntry
)

# Import based on optimization flag
if USE_OPTIMIZED:
    # Use optimized unified extraction (recommended)
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
    _extraction_mode = "optimized"
else:
    # Use original extraction (for comparison/debugging)
    from tsr_generator.api.tsr_generator import generate_tsr_from_pdf
    from tsr_generator.extractors.land_details import extract_land_details
    from tsr_generator.extractors.entry_details import extract_entry_details, extract_entry_table
    _extraction_mode = "original"
    # Placeholder for API compatibility
    extract_all_unified = None
    estimate_token_savings = None
    compare_extraction_methods = None

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

    # Configuration
    'USE_OPTIMIZED'
]
