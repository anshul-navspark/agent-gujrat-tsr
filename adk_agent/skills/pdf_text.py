"""PDF-text skill — extract raw text from a land-record PDF."""

from __future__ import annotations

from tsr_generator.utils.pdf_utils import extract_text_from_pdf


def extract_pdf_text(pdf_path: str) -> str:
    """Return the text content of *pdf_path* (raises on failure)."""
    text = extract_text_from_pdf(pdf_path)
    if not text:
        raise ValueError(f"Failed to extract text from PDF: {pdf_path}")
    return text
