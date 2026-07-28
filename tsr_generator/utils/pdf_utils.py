"""PDF text extraction.

Extractor choice matters a great deal for Gujarati. `pypdf` mis-decodes the
AnyRoR record PDFs: it drops conjunct consonants and reph outright and writes
every o-matra as `ા`+`ે`, which corrupts title-holder names
(`હિતેષભાઈ` -> `હતેષભાઈ`). Measured on one 16-page record: 587 mid-word gaps and
0/242 correct o-matras for pypdf, versus 88 gaps and 242/242 for poppler
`pdftotext` reading the identical file. Across the whole local cache (61 PDFs)
poppler never lost or invented a digit - the digit streams are identical for
29/61 and a pure reordering of the entry-index column for the other 32.

So the order is: poppler `pdftotext` -> PyMuPDF -> pypdf (last resort).

Plain `pdftotext` is used deliberately, NOT `-layout`: `-layout` preserves the
physical column layout but reorders the reading sequence, which changes the
digit order relative to every previously generated TSR.
"""
import logging
import shutil
import subprocess
from functools import lru_cache

import pypdf

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 120


def _extract_with_pdftotext(pdf_path: str):
    """poppler pdftotext - correct Gujarati conjuncts and matras."""
    binary = shutil.which("pdftotext")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, pdf_path, "-"],
            capture_output=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning("pdftotext exited %s for %s", result.returncode, pdf_path)
            return None
        return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("pdftotext failed for %s: %s", pdf_path, e)
        return None


def _extract_with_pymupdf(pdf_path: str):
    """PyMuPDF - correct conjuncts, but doubles the `ા` matra in ર-conjuncts."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        with fitz.open(pdf_path) as doc:
            return "".join(page.get_text() for page in doc)
    except Exception as e:
        logger.warning("PyMuPDF failed for %s: %s", pdf_path, e)
        return None


def _extract_with_pypdf(pdf_path: str):
    """pypdf - LAST RESORT. Mangles Gujarati; see module docstring."""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            return "".join((page.extract_text() or "") + "\n"
                           for page in pdf_reader.pages)
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return None


# Ordered best -> worst. Each returns str or None.
_EXTRACTORS = (
    ("pdftotext", _extract_with_pdftotext),
    ("pymupdf", _extract_with_pymupdf),
    ("pypdf", _extract_with_pypdf),
)


# Cache PDF text extraction by file path (max 32 PDFs in memory)
@lru_cache(maxsize=32)
def _extract_text_cached(pdf_path: str) -> str:
    """Cached PDF text extraction - internal function."""
    for name, extractor in _EXTRACTORS:
        text = extractor(pdf_path)
        if text and text.strip():
            if name == "pypdf":
                logger.warning(
                    "Falling back to pypdf for %s - Gujarati conjuncts and "
                    "o-matras will be corrupted. Install poppler-utils "
                    "(pdftotext) or pymupdf for correct extraction.", pdf_path
                )
            else:
                logger.debug("Extracted %s with %s (%d chars)",
                             pdf_path, name, len(text))
            return text
    logger.error("All PDF extractors failed for %s", pdf_path)
    return None


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
