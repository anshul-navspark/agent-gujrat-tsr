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
                self.driver = self.web_driver_manager.initialize_webdriver(headless=self.headless, timeout=30)
                self.form_filler = FormFiller(self.driver, WebDriverWait(self.driver, 30), self.captcha_solver, self.logger)
            
            # Navigate to the form
            self.form_filler.navigate_to_form()
            
            # Add a longer wait after page load
            time.sleep(3)
            
            # Get page source for debugging
            page_source = self.driver.page_source
            if 'drpLandRecord' not in page_source:
                self.logger.error("Land record dropdown not found in page source")
                self.logger.debug(f"Page source: {page_source[:1000]}...")
            
            # Try to select land record type multiple times
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    self.logger.debug(f"Attempt {attempt + 1} to select land record type")
                    
                    # Try direct JavaScript execution first
                    js_script = """
                        var select = document.getElementById('ContentPlaceHolder1_drpLandRecord');
                        if(select) {
                            select.value = '8';
                            var event = new Event('change', { bubbles: true });
                            select.dispatchEvent(event);
                            return true;
                        }
                        return false;
                    """
                    result = self.driver.execute_script(js_script)
                    if result:
                        self.logger.debug("Successfully selected land record type using JavaScript")
                        time.sleep(2)
                        break
                    
                    # If JavaScript fails, try Selenium Select
                    self.form_filler.select_land_record_type()
                    time.sleep(2)
                    
                    # Verify selection
                    selected_value = self.driver.execute_script(
                        'return document.getElementById("ContentPlaceHolder1_drpLandRecord").value;'
                    )
                    if selected_value == '8':
                        self.logger.debug("Successfully verified land record type selection")
                        break
                    else:
                        self.logger.warning(f"Land record type selection verification failed. Got value: {selected_value}")
                        
                except Exception as e:
                    self.logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2)
            
            # Continue with rest of the form...
            self.logger.debug("Starting district selection...")
            district_selected = self.form_filler.select_district(district_name)
            if not district_selected:
                self.logger.error(f"Failed to select district: {district_name}")
                return {'success': False, 'error': f"District not found: {district_name}"}
            
            self.logger.debug("Starting taluka selection...")
            taluka_selected = self.form_filler.select_taluka(taluka_name)
            if not taluka_selected:
                self.logger.error(f"Failed to select taluka: {taluka_name}")
                return {'success': False, 'error': f"Taluka not found: {taluka_name}"}
                
            self.logger.debug("Starting village selection...")
            village_selected = self.form_filler.select_village(village_name)
            if not village_selected:
                self.logger.error(f"Failed to select village: {village_name}")
                return {'success': False, 'error': f"Village not found: {village_name}"}
                
            # Retry if survey selection fails
            self.logger.debug("Starting survey selection...")
            for attempt in range(3):  # Try up to 3 times
                survey_selected = self.form_filler.select_survey(survey_block_number)
                if survey_selected:
                    break
                    
                self.logger.warning(f"Survey selection failed on attempt {attempt+1}, retrying...")
                # Refresh the page and navigate through the form again
                self.driver.refresh()
                
                # Wait for page to load after refresh
                time.sleep(CONFIG['PAGE_LOAD_WAIT'])
                
                # Select the land record type again
                self.form_filler.select_land_record_type()
                
                # Select district, taluka, village again
                self.form_filler.select_district(district_name)
                self.form_filler.select_taluka(taluka_name)
                self.form_filler.select_village(village_name)
                
            if not survey_selected:
                self.logger.error(f"Failed to select survey number: {survey_block_number}")
                return {'success': False, 'error': f"Survey number not found: {survey_block_number}"}
            
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
