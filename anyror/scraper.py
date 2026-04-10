"""
Main Scraper for Gujarat Land Record Automation

Main class for scraping land records from the AnyRoR website.
"""

import os
import time
import logging
import traceback
from selenium.webdriver.support.ui import WebDriverWait
from .webdriver_manager import WebDriverManager
from .captcha_solver import CaptchaSolver
from .form_filler import FormFiller
from .config import CONFIG


class AnyRoRScraper:
    """Main class for scraping land records from the AnyRoR website."""
    
    def __init__(self, headless=True, logger=None):
        """
        Initialize the AnyRoR scraper.
        
        Args:
            headless: Whether to run the browser in headless mode.
            logger: Logger instance for logging.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.web_driver_manager = WebDriverManager()
        self.captcha_solver = CaptchaSolver(logger=self.logger)
        self.form_filler = None
        self.headless = headless
        self.driver = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        return False
    
    def __del__(self):
        """Cleanup when the scraper is destroyed."""
        self.cleanup()
    
    def cleanup(self):
        """Centralized cleanup method."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.debug("AnyRoRScraper: WebDriver cleaned up")
            except Exception as e:
                self.logger.warning(f"AnyRoRScraper: Error during cleanup: {e}")
            finally:
                self.driver = None
        
        if self.web_driver_manager:
            try:
                self.web_driver_manager.close()
            except Exception as e:
                self.logger.warning(f"AnyRoRScraper: Error closing WebDriverManager: {e}")
    
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
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                
            # Initialize WebDriver if not already done
            if not self.driver:
                # Use longer timeout for Streamlit Cloud (120s)
                self.driver = self.web_driver_manager.initialize_webdriver(headless=self.headless, timeout=120)
                self.form_filler = FormFiller(self.driver, WebDriverWait(self.driver, 120), self.captcha_solver, self.logger)
            
            # Navigate to the form
            self.form_filler.navigate_to_form()
            
            # Add a longer wait after page load
            time.sleep(3)
            
            # Get page source for debugging
            page_source = self.driver.page_source
            if 'drpLandRecord' not in page_source:
                self.logger.error("Land record dropdown not found in page source")
                self.logger.debug(f"Page source: {page_source[:1000]}...")
            
            # Unified retry loop for all form selections
            max_attempts = 3
            form_filled = False
            last_error = None

            for attempt in range(max_attempts):
                try:
                    self.logger.debug(f"Form filling attempt {attempt + 1}/{max_attempts}")
                    
                    if attempt > 0:
                        self.logger.info("Refreshing page for retry...")
                        self.driver.refresh()
                        time.sleep(CONFIG.get('PAGE_LOAD_WAIT', 5))  # Use get() just in case
                        self.form_filler.navigate_to_form()
                        time.sleep(2)

                    # 1. Select Land Record Type
                    # Using form_filler's method which is robust
                    self.form_filler.select_land_record_type()
                    
                    # 2. Select District
                    self.logger.debug("Starting district selection...")
                    if not self.form_filler.select_district(district_name):
                        raise Exception(f"District not found: {district_name}")
                    
                    # 3. Select Taluka
                    self.logger.debug("Starting taluka selection...")
                    if not self.form_filler.select_taluka(taluka_name):
                        raise Exception(f"Taluka not found: {taluka_name}")
                    
                    # 4. Select Village
                    self.logger.debug("Starting village selection...")
                    if not self.form_filler.select_village(village_name):
                        raise Exception(f"Village not found: {village_name}")
                    
                    # 5. Select Survey
                    self.logger.debug("Starting survey selection...")
                    if not self.form_filler.select_survey(survey_block_number):
                        raise Exception(f"Survey number not found: {survey_block_number}")
                    
                    form_filled = True
                    break
                    
                except Exception as e:
                    last_error = str(e)
                    self.logger.warning(f"Form filling attempt {attempt + 1} failed: {last_error}")
                    if attempt == max_attempts - 1:
                        self.logger.error(f"All form filling attempts failed. Last error: {last_error}")
                    else:
                        time.sleep(2)
            
            if not form_filled:
                return {'success': False, 'error': f"Scraping failed: {last_error}"}
            
            # Retry loop for CAPTCHA/Submission
            max_captcha_attempts = 3
            submission_success = False
            error_msg = None
            
            for captcha_attempt in range(max_captcha_attempts):
                self.logger.debug(f"CAPTCHA attempt {captcha_attempt + 1}/{max_captcha_attempts}")
                
                # Solve captcha
                self.logger.debug("Starting CAPTCHA solving...")
                captcha_solved = self.form_filler.solve_captcha()
                
                if not captcha_solved:
                    self.logger.error("Failed to solve captcha")
                    if captcha_attempt < max_captcha_attempts - 1:
                        self.logger.info("Retrying CAPTCHA solving...")
                        # Wait a bit before retry
                        time.sleep(2)
                        continue
                    else:
                        return {'success': False, 'error': "Captcha could not be solved"}
                    
                # Submit the form
                self.logger.debug("Starting form submission...")
                submission_success, error_msg = self.form_filler.submit_form()
                
                if submission_success:
                    break
                    
                # Check if it is a captcha error
                if error_msg and ("matched" in str(error_msg).lower() or "code" in str(error_msg).lower() or "કેપ્ચા" in str(error_msg)):
                     self.logger.warning(f"CAPTCHA mismatch: {error_msg}. Retrying...")
                     # Wait for page update/captcha refresh
                     time.sleep(2)
                else:
                    # Some other error, break immediately
                    self.logger.error(f"Form submission failed with non-captcha error: {error_msg}")
                    break
            
            if not submission_success:
                self.logger.error(f"Form submission failed: {error_msg}")
                return {'success': False, 'error': f"Form submission failed: {error_msg}"}
                
            # Generate PDF
            self.logger.debug("Starting PDF generation...")
            pdf_success, error_msg = self.form_filler.generate_pdf(output_path)
            if not pdf_success:
                self.logger.error(f"PDF generation failed: {error_msg}")
                return {'success': False, 'error': f"PDF generation failed: {error_msg}"}
                
            self.logger.debug(f"Successfully fetched land record and saved to {output_path}")
            return {
                'success': True,
                'output_path': output_path,
                'message': 'Land record fetched successfully'
            }
                
        except Exception as e:
            error_message = f"Error fetching land record: {str(e)}"
            self.logger.error(error_message)
            self.logger.debug(traceback.format_exc())
            return {'success': False, 'error': error_message}
