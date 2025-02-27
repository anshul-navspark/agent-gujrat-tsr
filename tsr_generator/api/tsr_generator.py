import os
import traceback
import logging
from pathlib import Path

from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.utils.logging_utils import setup_logging
from tsr_generator.extractors.land_details import extract_land_details
from tsr_generator.extractors.entry_details import extract_entry_details, translate_entry_content
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document

def generate_tsr_from_pdf(pdf_path, output_path, logger=None):
    """
    Generate a TSR document from a PDF land record with enhanced entry processing
    
    Args:
        pdf_path (str): Path to the PDF file
        output_path (str): Path to save the output DOCX file
        logger (Logger, optional): Logger object
        
    Returns:
        dict: Result dictionary with success/failure information
    """
    # Set up logger if not provided
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        # Create console handler if no handlers exist
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
    
    try:
        # Extract text from PDF
        logger.info(f"Extracting text from PDF: {pdf_path}")
        pdf_text = extract_text_from_pdf(pdf_path)
        
        if pdf_text is None:
            logger.error("Failed to extract text from PDF")
            return {
                'success': False,
                'error': "Failed to extract text from PDF"
            }
        
        # Extract land details using dedicated AI approach
        logger.info("Extracting land details using dedicated AI approach")
        land_details = extract_land_details(pdf_text)
        
        # Extract entry details using enhanced structured approach
        logger.info("Extracting entry details using enhanced structured approach")
        entries = extract_entry_details(pdf_text)
        
        # No need for separate translation as it's handled in the extraction process
        logger.info("Entry translation is now handled within the extraction process")
        
        # Generate findings
        logger.info("Generating findings")
        findings = generate_findings_table(pdf_text)
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"Created output directory: {output_dir}")
        
        # Create DOCX report with structured entries
        logger.info(f"Creating DOCX report with enhanced entry formatting: {output_path}")
        output_file = create_tsr_document(entries, land_details, findings, output_path)
        logger.info(f"Report generated successfully: {output_file}")
        
        # Include entry type statistics in the result
        entry_types = {}
        for entry in entries:
            entry_type = entry.type.value if hasattr(entry.type, 'value') else str(entry.type)
            if entry_type in entry_types:
                entry_types[entry_type] += 1
            else:
                entry_types[entry_type] = 1
        
        return {
            'success': True,
            'tsr_path': output_file,
            'land_details': land_details,
            'entries_count': len(entries),
            'entry_types': entry_types
        }
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        } 