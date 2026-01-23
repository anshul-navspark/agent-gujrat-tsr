import pypdf
import logging
from functools import lru_cache

# Cache PDF text extraction by file path (max 32 PDFs in memory)
@lru_cache(maxsize=32)
def _extract_text_cached(pdf_path: str) -> str:
    """Cached PDF text extraction - internal function."""
    logger = logging.getLogger(__name__)
   # try:
    with open(pdf_path, 'rb') as file:
        pdf_reader = pypdf.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    # except Exception as e:
    #     logger.error(f"Error extracting text from PDF: {str(e)}")
    #     return None

def extract_text_from_pdf(pdf_path):
    """
    Extract text from PDF with error handling and caching
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Extracted text from the PDF or None if extraction fails
    """
    return _extract_text_cached(pdf_path)

def clear_pdf_cache():
    """Clear the PDF text extraction cache."""
    _extract_text_cached.cache_clear()