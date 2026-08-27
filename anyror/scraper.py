"""
Main Scraper for Gujarat Land Record Automation

Main class for scraping land records from the AnyRoR website.

Browser-free by design. AnyRoR's WAF serves a JS challenge to browser-shaped
clients — driving the portal with Selenium/Chrome draws a WAF Attack ID and
burns the source IP (journal 2026-07-31) — but it lets plain `requests`
through. The Selenium scraper that used to back this class as a fallback has
been removed for exactly that reason; `anyror/http_fetch.py` is the only path.
"""

import logging
import traceback

from .captcha_solver import CaptchaSolver


class AnyRoRScraper:
    """Main class for scraping land records from the AnyRoR website."""

    def __init__(self, headless=True, logger=None):
        """
        Initialize the AnyRoR scraper.

        Args:
            headless: Retained for call-site compatibility; the HTTP fetch
                never opens a browser on AnyRoR, so it has no effect.
            logger: Logger instance for logging.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.captcha_solver = CaptchaSolver(logger=self.logger)
        self.headless = headless

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        return False

    def cleanup(self):
        """Centralized cleanup method.

        Nothing persistent is held any more (the HTTP fetcher owns its own
        short-lived requests session), but callers still invoke this, so it
        stays as an explicit no-op rather than disappearing.
        """
        return None

    def fetch_land_record(self, district_name, taluka_name, village_name, survey_block_number, output_path):
        """
        Fetch a land record from the AnyRoR portal.

        Args:
            district_name: Name of the district (in Gujarati)
            taluka_name: Name of the taluka (in Gujarati)
            village_name: Name of the village (in Gujarati)
            survey_block_number: Survey/block number
            output_path: Path where the PDF will be saved

        Returns:
            dict: Result dictionary with 'success' boolean and either 'output_path' or 'error'
        """
        # Ensure all parameters are strings
        district_name = str(district_name).strip()
        taluka_name = str(taluka_name).strip()
        village_name = str(village_name).strip()
        survey_block_number = str(survey_block_number).strip()

        self.logger.debug(f"Fetching land record for {district_name}, {taluka_name}, {village_name}, {survey_block_number}")

        try:
            from .http_fetch import AnyRoRHttpFetcher
            result = AnyRoRHttpFetcher(logger=self.logger).fetch_record_pdf(
                district_name, taluka_name, village_name,
                survey_block_number, output_path)
        except Exception as e:
            error_message = f"Error fetching land record: {e}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            return {'success': False, 'error': error_message}

        if result.get('success'):
            self.logger.info("Land record fetched via http_fetch")
            return result

        # Fail loudly. There is deliberately no browser fallback: retrying this
        # through Selenium is what got the source IP WAF-blocked.
        error = result.get('error') or 'unknown error'
        self.logger.error(f"http_fetch failed: {error}")
        return {'success': False, 'error': f"http_fetch failed: {error}"}
