"""
Gujarat Land Record Automation Tool

This module provides functionality to automate the retrieval of land records
from the Gujarat government's AnyRoR (Any Record of Rights) portal.
"""

import os
import base64
import re
import io
import time
import logging
import traceback
import tempfile
import sys
from datetime import datetime
from functools import lru_cache
from typing import Dict, Any, Optional, List, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import SecretStr
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration constants
CONFIG = {
    'URL': 'https://anyror.gujarat.gov.in/LandRecordRural.aspx',
    'LAND_RECORD_TYPE_ID': 'ContentPlaceHolder1_drpLandRecord',
    'LAND_RECORD_TYPE_VALUE': '8',
    'DISTRICT_DROPDOWN_ID': 'ContentPlaceHolder1_ddlDistrict',
    'TALUKA_DROPDOWN_ID': 'ContentPlaceHolder1_ddlTaluka',
    'VILLAGE_DROPDOWN_ID': 'ContentPlaceHolder1_ddlVillage',
    'SURVEY_DROPDOWN_ID': 'ContentPlaceHolder1_ddlSurveyNo',
    'CAPTCHA_IMG_ID': 'ContentPlaceHolder1_i_captcha_1',
    'CAPTCHA_INPUT_ID': 'ContentPlaceHolder1_txt_captcha_1',
    'SUBMIT_BUTTON_ID': 'ContentPlaceHolder1_btnGo',
    'WAIT_TIMEOUT': 20,  # Reduced from 30 to 20 seconds
    'CAPTCHA_WAIT_TIMEOUT': 2,
    'MAX_RETRIES': 3,
    'DROPDOWN_WAIT_TIMEOUT': 3,  # Reduced from 5 to 3 seconds
    'PAGE_LOAD_WAIT': 3,  # Reduced wait time for page loading
    'CONSOLE_LOG_LEVEL': logging.WARNING,  # Only show warnings and errors in console
    'FILE_LOG_LEVEL': logging.INFO,  # Keep detailed logs in the file
}


class Logger:
    """Handles logging configuration and operations."""
    
    @staticmethod
    def setup(console_log_level=None, file_log_level=None):
        """Setup logging configuration.
        
        Args:
            console_log_level: The logging level to use for console output.
            file_log_level: The logging level to use for file output.
            
        Returns:
            A configured logger instance.
        """
        # Use config values if not specified
        console_log_level = console_log_level or CONFIG.get('CONSOLE_LOG_LEVEL', logging.WARNING)
        file_log_level = file_log_level or CONFIG.get('FILE_LOG_LEVEL', logging.INFO)
        
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # Create a timestamp for the log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f'logs/anyror_{timestamp}.log'

        # Create logger
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)  # Set to lowest level to capture everything
        
        # Remove existing handlers if any
        if logger.handlers:
            logger.handlers.clear()
            
        # Create file handler with UTF-8 encoding
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(file_log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # Create console handler with minimal output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_log_level)
        console_formatter = logging.Formatter('%(message)s')  # Simplified format for console
        console_handler.setFormatter(console_formatter)
        
        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Disable verbose logging from Selenium/urllib3/webdriver-manager
        logging.getLogger('selenium').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('WDM').setLevel(logging.ERROR)  # Suppress webdriver-manager logs
        
        return logger


class CaptchaSolver:
    """Handles CAPTCHA recognition using Azure OpenAI."""
    
    def __init__(self, logger=None):
        """Initialize the CAPTCHA solver.
        
        Args:
            logger: Logger instance for logging.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.llm = self._initialize_llm()
        
    def _initialize_llm(self):
        """Initialize the LLM client.
        
        Returns:
            An initialized LLM client.
        """
        return AzureChatOpenAI(
            model="gpt-4o",
            api_version='2024-02-15-preview',
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
            temperature=0.0
        )
    
    def solve(self, image_data):
        """Recognize CAPTCHA from image data.
        
        Args:
            image_data: Binary image data of the CAPTCHA.
            
        Returns:
            The recognized CAPTCHA text or None if recognition failed.
        """
        self.logger.info("Using LLM to recognize captcha")
        try:
            # Convert image data to base64 for sending to the LLM
            img = Image.open(io.BytesIO(image_data))
            
            # Save to a temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                img.save(temp_file, format='PNG')
                temp_file_path = temp_file.name
            
            # Create a message with the image
            message = HumanMessage(
                content=[
                    {
                        "type": "text", 
                        "text": "This is a captcha image. Please identify the 6 digits shown in the image. Return ONLY the digits with no additional text or explanation."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64.b64encode(open(temp_file_path, 'rb').read()).decode('utf-8')}"
                        }
                    }
                ]
            )
            
            # Get response from LLM
            response = self.llm.invoke([message])
            
            # Clean up the temporary file
            os.unlink(temp_file_path)
            
            # Extract only digits from the response
            captcha_text = ''.join(re.findall(r'\d', response.content))
            
            self.logger.info(f"LLM recognized captcha: {captcha_text}")
            return captcha_text
            
        except Exception as e:
            self.logger.error(f"Error recognizing captcha with LLM: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None


class WebDriverManager:
    """Manages WebDriver initialization and operations."""
    
    def __init__(self, headless=True, logger=None):
        """Initialize the WebDriver manager.
        
        Args:
            headless: Whether to run the browser in headless mode.
            logger: Logger instance for logging.
        """
        self.headless = headless
        self.logger = logger or logging.getLogger(__name__)
        self.driver = None
        self.wait = None
        
    def initialize(self):
        """Initialize the WebDriver.
        
        Returns:
            The initialized WebDriver and WebDriverWait instances.
        """
        self.logger.info("Initializing WebDriver")
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        
        if self.headless:
            options.add_argument("--headless")
            
        # Add additional options to fix potential issues and improve performance
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")  # Suppress browser logs
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])  # Disable DevTools logging
        
        # Use ChromeDriverManager with silent output
        os.environ['WDM_LOG_LEVEL'] = '0'  # Suppress webdriver-manager logs
        os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, CONFIG['WAIT_TIMEOUT'])
        
        return self.driver, self.wait
    
    def close(self):
        """Close the WebDriver."""
        if self.driver:
            self.logger.info("Closing WebDriver")
            self.driver.quit()


class FormFiller:
    """Handles form filling operations on the AnyRoR website."""
    
    def __init__(self, driver, wait, captcha_solver, logger=None):
        """Initialize the form filler.
        
        Args:
            driver: WebDriver instance.
            wait: WebDriverWait instance.
            captcha_solver: CaptchaSolver instance.
            logger: Logger instance for logging.
        """
        self.driver = driver
        self.wait = wait
        self.captcha_solver = captcha_solver
        self.logger = logger or logging.getLogger(__name__)
    
    def navigate_to_form(self):
        """Navigate to the AnyRoR form page."""
        self.logger.info(f"Navigating to AnyRoR website: {CONFIG['URL']}")
        self.driver.get(CONFIG['URL'])
    
    def select_land_record_type(self):
        """Select the land record type."""
        self.logger.info("Selecting Land Record Type")
        land_record_dropdown = self.wait.until(
            EC.visibility_of_element_located((By.ID, CONFIG['LAND_RECORD_TYPE_ID']))
        )
        select_land_record = Select(land_record_dropdown)
        select_land_record.select_by_value(CONFIG['LAND_RECORD_TYPE_VALUE'])
        self.logger.info("Selected Land Record Type: INTEGRATED SURVEY NO DETAILS")
        
        # Wait for the page to update after selection
        try:
            # Use a shorter timeout for this wait
            WebDriverWait(self.driver, CONFIG['DROPDOWN_WAIT_TIMEOUT']).until(
                EC.staleness_of(land_record_dropdown)
            )
        except TimeoutException:
            # If staleness check times out, just wait a bit and continue
            self.logger.debug("Staleness check timed out, continuing anyway")
            time.sleep(0.5)  # Reduced from 1 second to 0.5 seconds
    
    @lru_cache(maxsize=64)  # Increased cache size for better performance
    def _get_dropdown_options(self, dropdown_id):
        """Get options from a dropdown.
        
        Args:
            dropdown_id: The ID of the dropdown element.
            
        Returns:
            A list of options in the dropdown.
        """
        dropdown = self.wait.until(
            EC.element_to_be_clickable((By.ID, dropdown_id))
        )
        select = Select(dropdown)
        return select.options
    
    def select_dropdown_option(self, dropdown_id, option_text, partial_match=False):
        """Select an option from a dropdown.
        
        Args:
            dropdown_id: The ID of the dropdown element.
            option_text: The text of the option to select.
            partial_match: Whether to use partial matching for the option text.
            
        Returns:
            True if the option was found and selected, False otherwise.
        """
        dropdown = self.wait.until(
            EC.element_to_be_clickable((By.ID, dropdown_id))
        )
        select = Select(dropdown)
        
        for option in select.options:
            option_text_stripped = option.text.strip()
            if (partial_match and option_text in option_text_stripped) or option_text_stripped == option_text:
                select.select_by_visible_text(option_text_stripped)
                
                # Wait for the page to update after selection
                try:
                    # Use a shorter timeout for this wait
                    WebDriverWait(self.driver, CONFIG['DROPDOWN_WAIT_TIMEOUT']).until(
                        EC.staleness_of(dropdown)
                    )
                except (TimeoutException, StaleElementReferenceException):
                    # If staleness check times out or element is already stale, just wait a bit and continue
                    self.logger.debug("Staleness check timed out or element already stale, continuing anyway")
                    time.sleep(0.5)  # Reduced from 1 second to 0.5 seconds
                
                return True
        
        return False
    
    def select_district(self, district_name):
        """Select a district from the dropdown.
        
        Args:
            district_name: The name of the district to select.
            
        Returns:
            True if the district was found and selected, False otherwise.
        """
        self.logger.info(f"Selecting District: {district_name}")
        result = self.select_dropdown_option(CONFIG['DISTRICT_DROPDOWN_ID'], district_name)
        if result:
            self.logger.info("District selected successfully")
        else:
            self.logger.error(f"District '{district_name}' not found in dropdown")
        return result
    
    def select_taluka(self, taluka_name):
        """Select a taluka from the dropdown.
        
        Args:
            taluka_name: The name of the taluka to select.
            
        Returns:
            True if the taluka was found and selected, False otherwise.
        """
        self.logger.info(f"Selecting Taluka: {taluka_name}")
        result = self.select_dropdown_option(CONFIG['TALUKA_DROPDOWN_ID'], taluka_name, partial_match=True)
        if result:
            self.logger.info("Taluka selected successfully")
        else:
            self.logger.error(f"Taluka '{taluka_name}' not found in dropdown")
        return result
    
    def select_village(self, village_name):
        """Select a village from the dropdown.
        
        Args:
            village_name: The name of the village to select.
            
        Returns:
            True if the village was found and selected, False otherwise.
        """
        self.logger.info(f"Selecting Village: {village_name}")
        result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], village_name, partial_match=True)
        if result:
            self.logger.info("Village selected successfully")
        else:
            self.logger.error(f"Village '{village_name}' not found in dropdown")
        return result
    
    def select_survey(self, survey_block_number):
        """Select a survey/block number from the dropdown.
        
        Args:
            survey_block_number: The survey/block number to select.
            
        Returns:
            True if the survey/block number was found and selected, False otherwise.
        """
        self.logger.info(f"Selecting Survey/Block Number: {survey_block_number}")
        
        # Wait a bit for the dropdown to be populated - reduced wait time
        time.sleep(1)  # Reduced from 2 seconds to 1 second
        
        try:
            result = self.select_dropdown_option(CONFIG['SURVEY_DROPDOWN_ID'], survey_block_number, partial_match=True)
            if result:
                self.logger.info("Survey/Block Number selected successfully")
            else:
                self.logger.warning(f"Survey/Block Number not found matching: {survey_block_number}")
                
                # If not found by partial match, try to select the first option as fallback
                dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, CONFIG['SURVEY_DROPDOWN_ID']))
                )
                select = Select(dropdown)
                if len(select.options) > 1:  # Skip the first option if it's a placeholder
                    select.select_by_index(1)
                    self.logger.info("Selected first available Survey/Block Number as fallback")
                    return True
            return result
        except Exception as e:
            self.logger.error(f"Error selecting survey number: {str(e)}")
            # Try to select the first option as fallback
            try:
                dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, CONFIG['SURVEY_DROPDOWN_ID']))
                )
                select = Select(dropdown)
                if len(select.options) > 1:  # Skip the first option if it's a placeholder
                    select.select_by_index(1)
                    self.logger.info("Selected first available Survey/Block Number as fallback after error")
                    return True
            except Exception as inner_e:
                self.logger.error(f"Error in fallback survey selection: {str(inner_e)}")
            return False
    
    def solve_captcha(self):
        """Solve the CAPTCHA.
        
        Returns:
            The recognized CAPTCHA text or None if recognition failed.
        """
        self.logger.info("Starting captcha recognition process")
        
        # Capture captcha image data
        captcha_img = self.wait.until(
            EC.visibility_of_element_located((By.ID, CONFIG['CAPTCHA_IMG_ID']))
        )
        
        # Convert captcha to base64 - fix the invalid escape sequence
        captcha_base64 = self.driver.execute_script("""
            var canvas = document.createElement('canvas');
            var context = canvas.getContext('2d');
            var img = document.getElementById('ContentPlaceHolder1_i_captcha_1');
            canvas.width = img.width;
            canvas.height = img.height;
            context.drawImage(img, 0, 0);
            return canvas.toDataURL('image/png').replace(/^data:image\\/(png|jpg);base64,/, '');
        """)
        
        # Decode base64 to binary data
        captcha_data = base64.b64decode(captcha_base64)
        
        # Solve the captcha
        captcha_value = self.captcha_solver.solve(captcha_data)
        
        if captcha_value:
            # Enter the captcha value
            captcha_input = self.wait.until(
                EC.visibility_of_element_located((By.ID, CONFIG['CAPTCHA_INPUT_ID']))
            )
            captcha_input.clear()
            captcha_input.send_keys(captcha_value)
            self.logger.info(f"Entered captcha value: {captcha_value}")
        
        return captcha_value
    
    def submit_form(self):
        """Submit the form and handle any alerts.
        
        Returns:
            A tuple (success, error_message) where success is True if the form was submitted
            successfully, and error_message is None or the error message if submission failed.
        """
        self.logger.info("Submitting the form")
        submit_button = self.wait.until(
            EC.element_to_be_clickable((By.ID, CONFIG['SUBMIT_BUTTON_ID']))
        )
        submit_button.click()
        
        # Check for alert (captcha error)
        try:
            WebDriverWait(self.driver, CONFIG['CAPTCHA_WAIT_TIMEOUT']).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            self.logger.warning(f"Alert present: {alert_text}")
            alert.accept()
            
            return False, alert_text
        except TimeoutException:
            # No alert means success
            self.logger.info("Form submitted successfully")
            return True, None
    
    def generate_pdf(self, output_path):
        """Generate a PDF of the land record.
        
        Args:
            output_path: The path where the PDF will be saved.
            
        Returns:
            A tuple (success, error_message) where success is True if the PDF was generated
            successfully, and error_message is None or the error message if generation failed.
        """
        self.logger.info("Attempting to generate PDF")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            # Wait for the page to load completely - reduced wait time
            time.sleep(CONFIG['PAGE_LOAD_WAIT'])  # Using config value instead of hardcoded 5 seconds
            
            result = self.driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
            pdf_data = result.get("data")
            if pdf_data:
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(pdf_data))
                self.logger.info(f"PDF saved successfully to: {output_path}")
                return True, None
            else:
                error_msg = "PDF generation did not return any data"
                self.logger.error(error_msg)
                return False, error_msg
        except Exception as e:
            error_msg = f"PDF generation error: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            return False, error_msg


class AnyRoRScraper:
    """Main class for scraping land records from the AnyRoR website."""
    
    def __init__(self, headless=True, logger=None):
        """Initialize the AnyRoR scraper.
        
        Args:
            headless: Whether to run the browser in headless mode.
            logger: Logger instance for logging.
        """
        self.logger = logger or Logger.setup()
        self.webdriver_manager = WebDriverManager(headless=headless, logger=self.logger)
        self.captcha_solver = CaptchaSolver(logger=self.logger)
        self.form_filler = None
    
    def fetch_land_record(self, district_name, taluka_name, village_name, survey_block_number, output_path):
        """Fetch a land record from the AnyRoR website.
        
        Args:
            district_name: The name of the district.
            taluka_name: The name of the taluka.
            village_name: The name of the village.
            survey_block_number: The survey/block number.
            output_path: The path where the PDF will be saved.
            
        Returns:
            A dictionary with the result of the operation.
        """
        self.logger.info("Starting AnyRoR automation script")
        self.logger.info(f"Parameters - District: {district_name}, Taluka: {taluka_name}, "
                    f"Village: {village_name}, Survey/Block: {survey_block_number}")
        
        try:
            # Initialize WebDriver
            driver, wait = self.webdriver_manager.initialize()
            self.form_filler = FormFiller(driver, wait, self.captcha_solver, self.logger)
            
            # Navigate to the form
            self.form_filler.navigate_to_form()
            
            # Select land record type
            self.form_filler.select_land_record_type()
            
            # Select district
            if not self.form_filler.select_district(district_name):
                return {
                    'success': False,
                    'error': f"District '{district_name}' not found in dropdown"
                }
            
            # Select taluka
            if not self.form_filler.select_taluka(taluka_name):
                return {
                    'success': False,
                    'error': f"Taluka '{taluka_name}' not found in dropdown"
                }
            
            # Select village
            if not self.form_filler.select_village(village_name):
                return {
                    'success': False,
                    'error': f"Village '{village_name}' not found in dropdown"
                }
            
            # Select survey/block number
            if not self.form_filler.select_survey(survey_block_number):
                self.logger.warning("Could not select exact survey number, but continuing with fallback")
            
            # Try to solve CAPTCHA and submit form with retries
            for attempt in range(CONFIG['MAX_RETRIES']):
                self.logger.info(f"CAPTCHA attempt {attempt + 1}/{CONFIG['MAX_RETRIES']}")
                
                # Solve CAPTCHA
                captcha_value = self.form_filler.solve_captcha()
                if not captcha_value:
                    continue
                
                # Submit form
                success, error_message = self.form_filler.submit_form()
                if success:
                    break
                
                if "Capcha is not matched" in error_message:
                    self.logger.warning(f"CAPTCHA not matched, retrying ({attempt + 1}/{CONFIG['MAX_RETRIES']})")
                    continue
                else:
                    return {
                        'success': False,
                        'error': f"Form submission error: {error_message}"
                    }
            else:
                return {
                    'success': False,
                    'error': f"Failed to solve CAPTCHA after {CONFIG['MAX_RETRIES']} attempts"
                }
            
            # Generate PDF
            success, error_message = self.form_filler.generate_pdf(output_path)
            if success:
                return {
                    'success': True,
                    'pdf_path': output_path
                }
            else:
                return {
                    'success': False,
                    'error': error_message
                }
            
        except Exception as e:
            self.logger.error(f"An error occurred: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if self.webdriver_manager:
                self.webdriver_manager.close()
            self.logger.info("Script execution completed")


def fetch_land_record(district_name, taluka_name, village_name, survey_block_number, output_path, logger=None):
    """
    Fetch a land record from the AnyRoR website (module-level function).
    
    Args:
        district_name: The name of the district.
        taluka_name: The name of the taluka.
        village_name: The name of the village.
        survey_block_number: The survey/block number.
        output_path: The path where the PDF will be saved.
        logger: Optional logger instance
        
    Returns:
        A dictionary with the result of the operation.
    """
    scraper = AnyRoRScraper(headless=True, logger=logger)
    return scraper.fetch_land_record(
        district_name=district_name,
        taluka_name=taluka_name,
        village_name=village_name,
        survey_block_number=survey_block_number,
        output_path=output_path
    )


def main():
    """Main function to run the script."""
    # --- User-defined parameters ---
    district_name = "પાટણ"         # Desired District (જીલ્લો)
    taluka_name = "પાટણ"           # Desired Taluka (તાલુકો)
    village_name = "અનાવાડા - 091"  # Desired Village (ગામ)
    survey_block_number = "0z૧"     # Survey/Block Number
    output_path = os.path.join(os.path.expanduser("~"), "Downloads", "land_record.pdf")
    
    # Setup logger with minimal console output
    logger = Logger.setup()
    
    # Print startup message
    print(f"Fetching land record for {district_name}, {taluka_name}, {village_name}, {survey_block_number}...")
    
    # Create scraper and fetch land record
    scraper = AnyRoRScraper(headless=True, logger=logger)
    result = scraper.fetch_land_record(
        district_name=district_name,
        taluka_name=taluka_name,
        village_name=village_name,
        survey_block_number=survey_block_number,
        output_path=output_path
    )
    
    if result['success']:
        print(f"Land record fetched successfully: {result['pdf_path']}")
    else:
        print(f"Failed to fetch land record: {result['error']}")


if __name__ == "__main__":
    main() 