"""
AnyRoR scraper microservice (Cloud Run).

The one component that cannot run inside the managed agent runtime: it needs a
headless browser AND India-routable egress to reach the AnyRoR portal. Deploy it
to Cloud Run with Cloud NAT / a VPN connector for egress; the Agent Engine agent
calls it via ``ANYROR_SCRAPER_URL`` (see ``adk_agent/skills/scrape.py``).

Contract:
    POST /scrape   {district, taluka, village, survey_number}
       headers: Authorization: Bearer <ANYROR_SCRAPER_TOKEN>   (if token configured)
       -> 200 {success: true, pdf_base64, g_district, g_taluka, g_village, survey_number}
       -> 200 {success: false, error}
    GET  /healthz  -> {status: "ok"}

It reuses the in-process Selenium path (``_local_scrape_to_pdf``) verbatim, so the
scrape logic stays in one place.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anyror_scraper")

app = FastAPI(title="AnyRoR scraper", version="1.0")


class ScrapeRequest(BaseModel):
    district: str
    taluka: str
    village: str
    survey_number: str


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


def _check_auth(authorization: str | None) -> None:
    token = os.getenv("ANYROR_SCRAPER_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/scrape")
def scrape(req: ScrapeRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)
    # Imported here so the module loads even where Selenium isn't installed.
    from adk_agent.skills.scrape import _local_scrape_to_pdf

    with tempfile.TemporaryDirectory() as d:
        pdf_path = os.path.join(d, "record.pdf")
        try:
            meta = _local_scrape_to_pdf(
                req.district, req.taluka, req.village, req.survey_number, pdf_path, headless=True
            )
            with open(meta["pdf_path"], "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("ascii")
            return {
                "success": True,
                "pdf_base64": pdf_b64,
                "g_district": meta.get("g_district", ""),
                "g_taluka": meta.get("g_taluka", ""),
                "g_village": meta.get("g_village", ""),
                "survey_number": meta.get("survey_number", req.survey_number),
            }
        except Exception as e:  # surface as a structured error, not a 500
            logger.exception("scrape failed")
            return {"success": False, "error": str(e)}
