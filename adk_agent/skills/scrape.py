"""
Scrape skill (optional) — fetch a land-record PDF from the AnyRoR portal.

Two interchangeable implementations, auto-dispatched by :func:`scrape_to_pdf`:

* **local** (dev / India-reachable host): drive the Selenium scraper in-process —
  translate English place names to Gujarati, then solve the CAPTCHA with Gemini.
  Needs a browser, live portal access, and ``GEMINI_API_KEY`` at runtime.

* **remote** (enterprise / managed agent): call a separate **Cloud Run scraper
  service** over HTTPS (set ``ANYROR_SCRAPER_URL``). The managed agent runtime
  (Vertex AI Agent Engine) can't run a headless browser and its egress IP isn't
  India-routable, so scraping is factored out into a service that *can* (deployed
  with Cloud NAT / VPN egress). See ``adk_agent/deploy/scraper_service/``.

The contract is a single ``POST {url}/scrape`` with
``{district, taluka, village, survey_number}`` (optional ``Authorization: Bearer``)
returning ``{success, pdf_base64, ...}``.

Heavy dependencies (Selenium, the 2 MB translation hierarchy) are imported lazily
so the common PDF path never needs them.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def scrape_to_pdf(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    output_pdf_path: str,
    *,
    headless: bool = True,
    scraper_url: Optional[str] = None,
    scraper_token: Optional[str] = None,
) -> Dict[str, str]:
    """
    Fetch the land-record PDF for the given location into *output_pdf_path*.

    Dispatches to the **remote** Cloud Run scraper when ``scraper_url`` (or
    ``ANYROR_SCRAPER_URL``) is set, otherwise runs the **local** Selenium scrape.
    Returns a dict with the resolved place names and the PDF path; raises on
    failure.
    """
    url = scraper_url or os.getenv("ANYROR_SCRAPER_URL")
    if url:
        token = scraper_token or os.getenv("ANYROR_SCRAPER_TOKEN")
        logger.info("Scrape via remote scraper service: %s", url)
        return _remote_scrape_to_pdf(
            url, token, district, taluka, village, survey_number, output_pdf_path
        )
    return _local_scrape_to_pdf(
        district, taluka, village, survey_number, output_pdf_path, headless=headless
    )


# --------------------------------------------------------------------------- #
# Remote: call the Cloud Run scraper service (the managed-agent path).
# --------------------------------------------------------------------------- #

def _remote_scrape_to_pdf(
    url: str,
    token: Optional[str],
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    output_pdf_path: str,
    *,
    timeout: int = 300,
) -> Dict[str, str]:
    """POST to the scraper service and write the returned PDF (stdlib only)."""
    payload = json.dumps(
        {"district": district, "taluka": taluka, "village": village, "survey_number": survey_number}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url.rstrip("/") + "/scrape", data=payload, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - url is operator-configured
        data = json.loads(resp.read().decode("utf-8"))

    if not data.get("success"):
        raise RuntimeError(f"remote scraper failed: {data.get('error', 'unknown error')}")
    pdf_b64 = data.get("pdf_base64")
    if not pdf_b64:
        raise RuntimeError("remote scraper returned no PDF content")

    out = Path(output_pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(pdf_b64))
    return {
        "pdf_path": str(out),
        "remote": True,
        "g_district": data.get("g_district", ""),
        "g_taluka": data.get("g_taluka", ""),
        "g_village": data.get("g_village", ""),
        "survey_number": data.get("survey_number", survey_number),
    }


# --------------------------------------------------------------------------- #
# Local: in-process Selenium scrape (dev / India-reachable host).
# --------------------------------------------------------------------------- #

def _local_scrape_to_pdf(
    district: str,
    taluka: str,
    village: str,
    survey_number: str,
    output_pdf_path: str,
    *,
    headless: bool = True,
) -> Dict[str, str]:
    """Drive the Selenium AnyRoR scraper in-process. Reused by the scraper service."""
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
