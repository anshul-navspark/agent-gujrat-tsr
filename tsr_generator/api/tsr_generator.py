import logging
import traceback

from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.utils.logging_utils import setup_logging
from tsr_generator.extractors.land_details import extract_land_details
from tsr_generator.extractors.entry_details import extract_entry_details, translate_entry_content
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document

def generate_tsr_from_pdf(pdf_path, output_path, logger=None):
    """
    Generate a TSR document from a PDF file
    
    Args:
        pdf_path (str): Path to the PDF file
        output_path (str): Path to save the TSR document
        logger (logging.Logger, optional): Logger instance
        
    Returns:
        dict: Result dictionary with success status and additional information
    """
    if logger is None:
        logger = setup_logging()
    
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
        
        # Extract entry details using dedicated AI approach
        logger.info("Extracting entry details using dedicated AI approach")
        entries = extract_entry_details(pdf_text)
        
        # Translate any remaining Gujarati content to English
        logger.info("Translating Gujarati content to English")
        entries = translate_entry_content(entries)
        
        # Generate findings
        logger.info("Generating findings")
        findings = generate_findings_table(pdf_text)
        
        # Create DOCX report
        logger.info(f"Creating DOCX report: {output_path}")
        output_file = create_tsr_document(entries, land_details, findings, output_path)
        logger.info(f"Report generated successfully: {output_file}")
        
        return {
            'success': True,
            'tsr_path': output_file,
            'land_details': land_details,
            'entries_count': len(entries)
        }
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e)
        } 