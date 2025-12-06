"""
High-level processing service wrapping AnyRoR scraping and TSR generation.

Provides simple functions to fetch a single record (PDF) and generate a
Title Search Report (DOCX), as well as batch helpers for DataFrames.
"""

from __future__ import annotations

import os
import math
import logging
import traceback
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

import pandas as pd

from anyror import AnyRoRScraper
from selenium.common.exceptions import InvalidSessionIdException, TimeoutException, WebDriverException
from tsr_generator import generate_tsr_from_pdf
from utils.json_translations import translate_to_gujarati, TranslationNotFoundError
from utils.survey_utils import convert_survey_number


def ensure_dir(path: str) -> None:
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


@dataclass
class ProcessResult:
    success: bool
    pdf_path: Optional[str] = None
    tsr_path: Optional[str] = None
    error: Optional[str] = None


class LandRecordProcessor:
    """Facade around scraping and TSR generation for single or batch runs."""

    def __init__(self, output_base_dir: str = "output", headless: bool = True, logger: Optional[logging.Logger] = None) -> None:
        self.output_base_dir = output_base_dir
        self.pdf_dir = os.path.join(self.output_base_dir, "pdfs")
        self.tsr_dir = os.path.join(self.output_base_dir, "tsr")
        ensure_dir(self.pdf_dir)
        ensure_dir(self.tsr_dir)
        self.logger = logger or logging.getLogger(__name__)
        self.headless = headless

    def _build_paths(self, survey_number: str) -> Dict[str, str]:
        # Sanitize filename
        safe = str(survey_number).replace("/", "_").replace(" ", "")
        return {
            "pdf": os.path.join(self.pdf_dir, f"Survey No.{safe}.pdf"),
            "tsr": os.path.join(self.tsr_dir, f"Survey No.{safe}.docx"),
        }

    def fetch_pdf_and_tsr(
        self,
        *,
        district_guj: str,
        taluka_guj: str,
        village_guj: str,
        survey_number_guj: str,
        regenerate_pdf: bool = False,
        generate_tsr: bool = True,
    ) -> ProcessResult:
        """Fetch PDF from AnyRoR and optionally generate TSR.

        Assumes Gujarati strings for location and survey inputs.
        """
        paths = self._build_paths(survey_number_guj)
        scraper: Optional[AnyRoRScraper] = None
        try:
            # Function to create a fresh scraper instance
            def _new_scraper() -> AnyRoRScraper:
                return AnyRoRScraper(headless=self.headless, logger=self.logger)

            # Fetch PDF with at most one retry on InvalidSessionIdException
            if regenerate_pdf or not os.path.exists(paths["pdf"]):
                attempts = 0
                while attempts < 2:
                    try:
                        if scraper is None:
                            scraper = _new_scraper()
                        self.logger.debug(
                            f"Fetching land record for {district_guj}, {taluka_guj}, {village_guj}, {survey_number_guj}"
                        )
                        result = scraper.fetch_land_record(
                            district_name=district_guj,
                            taluka_name=taluka_guj,
                            village_name=village_guj,
                            survey_block_number=survey_number_guj,
                            output_path=paths["pdf"],
                        )
                        if not result.get("success"):
                            return ProcessResult(success=False, error=result.get("error") or "Unknown scrape error")
                        break
                    except (InvalidSessionIdException, TimeoutException, WebDriverException) as e:
                        # Recreate session once on WebDriver issues
                        self.logger.warning(f"WebDriver issue ({type(e).__name__}); recreating browser and retrying once: {e}")
                        if scraper:
                            try:
                                scraper.cleanup()
                            except Exception:
                                pass
                        scraper = None
                        attempts += 1
                    except Exception as exc:
                        # Clean up scraper on any other exception
                        if scraper:
                            try:
                                scraper.cleanup()
                            except Exception:
                                pass
                        raise exc

            # Generate TSR
            tsr_path = None
            if generate_tsr:
                self.logger.debug(f"Generating TSR from {paths['pdf']}")
                generate_tsr_from_pdf(paths["pdf"], paths["tsr"])
                tsr_path = paths["tsr"]

            return ProcessResult(success=True, pdf_path=paths["pdf"], tsr_path=tsr_path)

        except Exception as exc:
            self.logger.error(f"Processing error: {exc}")
            self.logger.debug(traceback.format_exc())
            return ProcessResult(success=False, error=str(exc))
        finally:
            # Ensure browser is closed after each fetch to avoid stale sessions
            try:
                if scraper and getattr(scraper, "driver", None):
                    scraper.driver.quit()
            except Exception:
                pass

    def process_dataframe(
        self,
        df: pd.DataFrame,
        *,
        col_map: Dict[str, str],
        regenerate_pdf: bool = False,
        generate_tsr: bool = True,
    ) -> List[ProcessResult]:
        """Batch process a DataFrame using provided column mapping.

        col_map keys: 'district', 'taluka', 'village', 'survey'. Values are actual df column names.
        """
        results: List[ProcessResult] = []
        for idx, row in df.iterrows():
            # Read raw values
            d_raw = row.get(col_map["district"])
            t_raw = row.get(col_map["taluka"])
            v_raw = row.get(col_map["village"])
            s_raw = row.get(col_map["survey"])

            # Validate presence
            def _is_bad(x: Any) -> bool:
                if x is None:
                    return True
                try:
                    if isinstance(x, float) and math.isnan(x):
                        return True
                except Exception:
                    pass
                xs = str(x).strip()
                return xs == "" or xs.lower() == "nan"

            if _is_bad(d_raw) or _is_bad(t_raw) or _is_bad(v_raw) or _is_bad(s_raw):
                results.append(ProcessResult(success=False, error=f"Row {idx}: Missing essential data"))
                continue

            # Cast to strings
            district_guj = str(d_raw).strip()
            taluka_guj = str(t_raw).strip()
            village_guj = str(v_raw).strip()
            survey_guj = str(s_raw).strip()

            # Auto-translate common English names to Gujarati for batch inputs
            try:
                district_guj = translate_to_gujarati(district_guj, context='district')
                taluka_guj = translate_to_gujarati(taluka_guj, context='taluka')
                village_guj = translate_to_gujarati(village_guj, context='village')
                survey_guj = convert_survey_number(survey_guj)
            except TranslationNotFoundError as e:
                results.append(ProcessResult(success=False, error=f"Row {idx}: {str(e)}"))
                continue
            except Exception:
                # Soft-fallback: leave values as-is on any other error
                pass

            # Skip placeholder rows like 'New' survey
            if survey_guj.lower() == "new":
                results.append(ProcessResult(success=False, error=f"Row {idx}: Skipped placeholder 'New'"))
                continue

            res = self.fetch_pdf_and_tsr(
                district_guj=district_guj,
                taluka_guj=taluka_guj,
                village_guj=village_guj,
                survey_number_guj=survey_guj,
                regenerate_pdf=regenerate_pdf,
                generate_tsr=generate_tsr,
            )
            results.append(res)
        return results



