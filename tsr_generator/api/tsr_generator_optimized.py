"""
Optimized TSR Generator - Token-Efficient Version

This module provides the same functionality as tsr_generator.py but uses
the unified extraction approach to minimize LLM API token usage.

Token savings: ~50-70% reduction per document processed.
"""

import os
import traceback
import logging
from typing import Dict, Any, Optional

# Use relative imports to avoid circular import with tsr_generator.__init__
from ..utils.pdf_utils import extract_text_from_pdf
from ..extractors.unified_extractor import (
    extract_all_unified,
    extract_land_details_optimized,
    extract_entry_table_optimized,
    extract_entry_details_optimized,
    estimate_token_savings,
    UnifiedExtractionResult
)
from ..extractors.findings import generate_findings_table
from ..document.tsr_document import create_tsr_document


def generate_tsr_from_pdf_optimized(
    pdf_path: str,
    output_path: str,
    logger: Optional[logging.Logger] = None,
    log_tokens: bool = True,
    request_metadata: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Generate a TSR document from a PDF land record using OPTIMIZED extraction.

    This function reduces token usage by ~50-70% compared to the original
    by consolidating 3 separate LLM calls into 1.

    Args:
        pdf_path: Path to the PDF file
        output_path: Path to save the output DOCX file
        logger: Logger object (optional)
        log_tokens: Whether to log token usage statistics

    Returns:
        dict: Result dictionary with success/failure information and token stats
    """
    # Set up logger if not provided
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    try:
        # Extract text from PDF
        logger.debug(f"Extracting text from PDF: {pdf_path}")
        pdf_text = extract_text_from_pdf(pdf_path)

        if pdf_text is None:
            logger.error("Failed to extract text from PDF")
            return {
                'success': False,
                'error': "Failed to extract text from PDF"
            }

        # Log token savings estimate
        if log_tokens:
            token_stats = estimate_token_savings(pdf_text)
            logger.info(f"Token optimization: ~{token_stats['savings']['percentage']}% reduction "
                       f"({token_stats['savings']['tokens_saved']} tokens saved, "
                       f"{token_stats['savings']['api_calls_saved']} fewer API calls)")

        # ============================================
        # OPTIMIZED: Single unified extraction call
        # ============================================
        logger.debug("Running unified extraction (single LLM call)")
        unified_result = extract_all_unified(pdf_text)

        if not unified_result.success:
            logger.warning(f"Unified extraction failed: {unified_result.error}")
            # Fall back to individual calls if unified fails
            return _fallback_generation(pdf_path, output_path, pdf_text, logger)

        # Use results from unified extraction
        land_details = unified_result.land_details
        entry_table = sorted([int(n) for n in unified_result.entry_numbers if n.isdigit()])

        # Override land details with request metadata if provided
        old_survey = None
        if request_metadata:
            if request_metadata.get('survey_number'):
                old_survey = land_details.get('survey_number', '')
                land_details['survey_number'] = request_metadata['survey_number']
                logger.info(f"Overriding survey_number: '{old_survey}' -> '{request_metadata['survey_number']}'")
            if request_metadata.get('village'):
                land_details['village_name'] = request_metadata['village']
            if request_metadata.get('taluka'):
                land_details['taluka_name'] = request_metadata['taluka']
            if request_metadata.get('district'):
                land_details['district_name'] = request_metadata['district']

        # Fix entry descriptions to use the correct survey number if it was overridden
        if old_survey and old_survey != land_details.get('survey_number'):
            import re as _re_survey
            new_survey = land_details['survey_number']
            for me in unified_result.mutation_entries:
                if isinstance(me, dict) and me.get('description'):
                    me['description'] = _re_survey.sub(
                        r'Survey\s+No\.\s*' + _re_survey.escape(old_survey),
                        f'Survey No. {new_survey}',
                        me['description']
                    )

        # Process mutation entries into structured objects
        from ..extractors.entry_details import process_entry_details
        entries = []
        if unified_result.mutation_entries:
            entries = process_entry_details(unified_result.mutation_entries)
            # Filter empty entries
            entries = [e for e in entries if getattr(e, 'formatted_description', '').strip()]

        logger.debug(f"Extracted: land_details, {len(entry_table)} entry numbers, {len(entries)} detailed entries")

        # Generate placeholder findings — will be regenerated with cross-references
        # inside create_tsr_document after chain of title table is built
        logger.debug("Generating findings with encumbrance analysis")
        findings = generate_findings_table("", unified_result.mutation_entries, land_details)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.debug(f"Created output directory: {output_dir}")

        # Create DOCX report
        logger.debug(f"Creating DOCX report: {output_path}")
        output_file = create_tsr_document(entry_table, entries, land_details, findings, output_path, mutation_entries=unified_result.mutation_entries)
        logger.debug(f"Report generated successfully: {output_file}")

        # Build entry type statistics
        entry_types = {}
        for entry in entries:
            entry_type = entry.type.value if hasattr(entry.type, 'value') else str(entry.type)
            entry_types[entry_type] = entry_types.get(entry_type, 0) + 1

        result = {
            'success': True,
            'tsr_path': output_file,
            'land_details': land_details,
            'entries_count': len(entries),
            'entry_types': entry_types,
            'optimized': True
        }

        # Add token statistics if available
        if log_tokens:
            result['token_stats'] = {
                'input_tokens': unified_result.input_tokens,
                'output_tokens': unified_result.output_tokens,
                'total_tokens': unified_result.input_tokens + unified_result.output_tokens,
                'api_calls': 1,
                'estimated_savings': token_stats['savings']
            }

        return result

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        }


def _fallback_generation(
    pdf_path: str,
    output_path: str,
    pdf_text: str,
    logger: logging.Logger
) -> Dict[str, Any]:
    """
    Fallback to original extraction methods if unified fails.
    """
    logger.info("Using fallback extraction methods")

    # Import original functions
    from ..extractors.land_details import extract_land_details
    from ..extractors.entry_details import extract_entry_details, extract_entry_table

    try:
        # Extract using original methods
        land_details = extract_land_details(pdf_text)
        entry_table = extract_entry_table(pdf_text)
        entries = extract_entry_details(pdf_text)
        # Convert entries to dict for findings
        entries_for_findings = [
            {
                'entry_number': str(e.entry_number),
                'type': e.type.value if hasattr(e.type, 'value') else str(e.type),
                'description': getattr(e, 'formatted_description', ''),
                'entry_status': getattr(e, 'entry_status', 'certified')
            }
            for e in entries
        ]
        findings = generate_findings_table(pdf_text, entries_for_findings, land_details)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create document
        output_file = create_tsr_document(entry_table, entries, land_details, findings, output_path)

        entry_types = {}
        for entry in entries:
            entry_type = entry.type.value if hasattr(entry.type, 'value') else str(entry.type)
            entry_types[entry_type] = entry_types.get(entry_type, 0) + 1

        return {
            'success': True,
            'tsr_path': output_file,
            'land_details': land_details,
            'entries_count': len(entries),
            'entry_types': entry_types,
            'optimized': False,
            'fallback_used': True
        }

    except Exception as e:
        logger.error(f"Fallback generation failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# =============================================================================
# DROP-IN REPLACEMENT FUNCTION
# =============================================================================

def generate_tsr_from_pdf(pdf_path: str, output_path: str, logger=None, request_metadata=None) -> Dict[str, Any]:
    """
    Drop-in replacement for original generate_tsr_from_pdf.

    This function has the same signature and return format as the original,
    but uses optimized extraction internally.
    """
    return generate_tsr_from_pdf_optimized(pdf_path, output_path, logger, log_tokens=False, request_metadata=request_metadata)


# =============================================================================
# COMPARISON UTILITY
# =============================================================================

def compare_extraction_methods(pdf_path: str) -> Dict[str, Any]:
    """
    Compare token usage between original and optimized methods.

    Useful for validating savings claims.

    Args:
        pdf_path: Path to a PDF file

    Returns:
        Comparison statistics
    """
    pdf_text = extract_text_from_pdf(pdf_path)
    if not pdf_text:
        return {'error': 'Failed to extract PDF text'}

    return estimate_token_savings(pdf_text)
