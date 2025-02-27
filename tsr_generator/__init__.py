"""
TSR Generator Package

This package provides functionality to generate Title Search Reports (TSR) from PDF land records.
"""

__version__ = '1.0.0'

from tsr_generator.api.tsr_generator import generate_tsr_from_pdf
from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.utils.logging_utils import setup_logging
from tsr_generator.extractors.land_details import extract_land_details
from tsr_generator.extractors.entry_details import extract_entry_details, translate_entry_content
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document

__all__ = [
    'generate_tsr_from_pdf',
    'extract_text_from_pdf',
    'setup_logging',
    'extract_land_details',
    'extract_entry_details',
    'translate_entry_content',
    'generate_findings_table',
    'create_tsr_document'
]
