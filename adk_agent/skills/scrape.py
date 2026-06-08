"""
Scrape skill (optional) — fetch a land-record PDF from the AnyRoR portal.

Mirrors the FastAPI ``/process-record`` flow: translate English place names to
Gujarati, then drive the Selenium scraper (which solves the CAPTCHA with Gemini).
Heavy dependencies (Selenium, the translation hierarchy) are imported lazily so
the common PDF path never needs them.

Requires live portal access, a browser, and ``GEMINI_API_KEY`` (for the CAPTCHA
solver) at runtime — it is therefore not exercised by the offline dry-run.
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def scrape_to_pdf(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    output_pdf_path: str,
    *,
    headless: bool = True,
) -> Dict[str, str]:
    """
    Fetch the land-record PDF for the given location into *output_pdf_path*.

    Returns a dict with the resolved (Gujarati) place names and the PDF path.
    Raises on failure.
    """
    # Lazy imports: keep Selenium / 2MB translation hierarchy out of the hot path.
    from services.translation_service import get_translation_service
    from anyror.scraper import AnyRoRScraper

    translator = get_translation_service()
    g_district = translator.translate_to_gujarati(district, context="district")
    g_taluka = translator.translate_to_gujarati(
        taluka, context="taluka", parent_district=g_district
    )
    g_village = translator.translate_to_gujarati(
        village, context="village", parent_district=g_district, parent_taluka=g_taluka
    )
    logger.info(
        "Scrape: %s/%s/%s/%s -> %s/%s/%s",
        district, taluka, village, survey_number, g_district, g_taluka, g_village,
    )

    scraper = AnyRoRScraper(headless=headless, logger=logger)
    try:
        result = scraper.fetch_land_record(
            g_district, g_taluka, g_village, survey_number, output_pdf_path
        )
    finally:
        # AnyRoRScraper manages its own driver lifecycle in fetch_land_record,
        # but make sure nothing is left dangling.
        close = getattr(scraper, "close", None) or getattr(scraper, "cleanup", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - best effort
                pass

    if not result.get("success"):
        raise RuntimeError(f"AnyRoR scrape failed: {result.get('error', 'unknown error')}")

    return {
        "pdf_path": result.get("output_path", output_pdf_path),
        "g_district": g_district,
        "g_taluka": g_taluka,
        "g_village": g_village,
        "survey_number": survey_number,
    }
