"""Fetch a Gujarat land record as a PDF.

Thin wrapper over the tested AnyRoRHttpFetcher. Everything hard-won about
talking to AnyRoR lives there and in references/anyror-operations.md; this
module only normalises inputs and shapes the result.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

log = logging.getLogger(__name__)


def fetch_record(district: str, taluka: str, village: str, survey: str,
                 out_dir: str = "output", filename: str | None = None) -> Dict[str, Any]:
    """Fetch one land record. Returns a JSON-shaped dict; never raises for an
    expected failure (bad name, WAF block, captcha miss) — those come back as
    {'success': False, 'error': ...} so a caller can report them verbatim.

    District/taluka/village accept English or Gujarati: the fetcher resolves a
    district through the hierarchy translator, and taluka/village are matched
    against the live dropdowns.
    """
    from anyror.http_fetch import AnyRoRHttpFetcher

    if not os.getenv("ANYROR_PROXY", "").strip():
        # Not fatal — a fresh residential IP works too — but it is nearly always
        # the reason a fetch fails, so say it up front rather than after a block.
        log.warning("ANYROR_PROXY is not set; AnyRoR blocks datacenter and "
                    "previously-burned IPs. Expect a WAF page.")

    safe = str(survey).replace("/", "_").strip()
    name = filename or f"Survey No.{safe}.pdf"
    output_path = os.path.join(out_dir, name)

    fetcher = AnyRoRHttpFetcher(logger=log)
    result = fetcher.fetch_record_pdf(district, taluka, village, survey, output_path)

    if result.get("success"):
        path = result["output_path"]
        result["size_bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
        result["request"] = {"district": district, "taluka": taluka,
                             "village": village, "survey": survey}
    return result
