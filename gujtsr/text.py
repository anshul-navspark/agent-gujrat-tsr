"""PDF -> plain text. Deterministic, no model, no network."""
from __future__ import annotations

from typing import Any, Dict


def extract_text(pdf_path: str) -> Dict[str, Any]:
    """Return {'success', 'text', 'chars'} for a land-record PDF.

    Delegates to the existing extractor, which tries poppler `pdftotext` first,
    then PyMuPDF, then pypdf. That order matters: pypdf mangles Gujarati
    conjuncts and o-matras, so it is a last resort, not a peer.
    """
    from tsr_generator.utils.pdf_utils import extract_text_from_pdf

    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    if not (text or "").strip():
        return {"success": False,
                "error": "no text layer found — the PDF may be a pure scan"}
    return {"success": True, "text": text, "chars": len(text)}
