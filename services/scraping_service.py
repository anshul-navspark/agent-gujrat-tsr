"""
Scraping service for Gujarat TSR Agent.

This service provides a clean interface for web scraping operations,
wrapping the existing AnyRoR scraper with better error handling.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
from typing import Optional, Dict, Any

from core.interfaces import IScrapingService
from core.exceptions import ScrapingException
from anyror import AnyRoRScraper



class ScrapingService(IScrapingService):
    """Implementation of scraping service."""
    
    def __init__(
        self,
        headless: bool = True,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize scraping service.
        
        Args:
            headless: Whether to run browser in headless mode
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.headless = headless
        self._scraper: Optional[AnyRoRScraper] = None
    
    def _get_scraper(self) -> AnyRoRScraper:
        """Get or create scraper instance."""
        if self._scraper is None:
            try:
                self._scraper = AnyRoRScraper(headless=self.headless, logger=self.logger)
                self.logger.debug("Initialized AnyRoR scraper")
            except Exception as e:
                self.logger.error(f"Failed to initialize scraper: {e}")
                raise ScrapingException(
                    message=f"Failed to initialize scraper: {str(e)}"
                )
        return self._scraper
    
    def fetch_land_record(
        self,
        district: str,
        taluka: str,
        village: str,
        survey_number: str,
        output_path: str
    ) -> Dict[str, Any]:
        """
        Fetch land record PDF from AnyRoR portal.
        
        Args:
            district: District name (in Gujarati)
            taluka: Taluka name (in Gujarati)
            village: Village name (in Gujarati)
            survey_number: Survey/block number
            output_path: Path to save the PDF
            
        Returns:
            Dictionary with 'success' status and optional 'error' message
            
        Raises:
            ScrapingException: If scraping fails
        """
        try:
            scraper = self._get_scraper()
            
            self.logger.info(
                f"Fetching land record: {district}, {taluka}, {village}, {survey_number}"
            )
            
            result = scraper.fetch_land_record(
                district_name=district,
                taluka_name=taluka,
                village_name=village,
                survey_block_number=survey_number,
                output_path=output_path
            )
            
            if result.get('success'):
                self.logger.info(f"Successfully fetched land record to {output_path}")
            else:
                self.logger.error(f"Scraping failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Scraping exception: {e}")
            raise ScrapingException(
                message=f"Failed to fetch land record: {str(e)}",
                details={
                    'district': district,
                    'taluka': taluka,
                    'village': village,
                    'survey_number': survey_number
                }
            )
    
    def close(self):
        """Close the scraper and clean up resources."""
        if self._scraper:
            try:
                self._scraper.web_driver_manager.close()
                self.logger.debug("Closed scraper")
            except Exception as e:
                self.logger.warning(f"Error closing scraper: {e}")
            finally:
                self._scraper = None
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()


def get_scraping_service(
    headless: bool = True,
    logger: Optional[logging.Logger] = None
) -> ScrapingService:
    """
    Create a new scraping service instance.
    
    Note: Unlike other services, we don't use a global singleton here
    because scraping services maintain browser state and should be
    created per-request in concurrent scenarios.
    
    Args:
        headless: Whether to run browser in headless mode
        logger: Optional logger instance
        
    Returns:
        ScrapingService instance
    """
    return ScrapingService(headless=headless, logger=logger)
