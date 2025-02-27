import PyPDF2
import logging

def extract_text_from_pdf(pdf_path):
    """
    Extract text from PDF with error handling
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Extracted text from the PDF or None if extraction fails
    """
    logger = logging.getLogger(__name__)
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return None 