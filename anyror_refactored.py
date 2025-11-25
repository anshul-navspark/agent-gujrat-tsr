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
import subprocess
import platform

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pydantic import SecretStr
from dotenv import load_dotenv
from anyror_village_matcher import VillageNameMatcher

# Global flag to avoid repeated webdriver cache cleaning per process
WDM_CACHE_CLEANED = False

# Load environment variables from .env file
load_dotenv()

# Configuration for AnyRoR website
CONFIG = {
    'LAND_RECORD_TYPE_ID': 'ContentPlaceHolder1_drpLandRecord',
    'LAND_RECORD_TYPE_VALUE': '8',  # Value for "INTEGRATED SURVEY NO DETAILS"
    'DISTRICT_DROPDOWN_ID': 'ContentPlaceHolder1_ddlDistrict',
    'TALUKA_DROPDOWN_ID': 'ContentPlaceHolder1_ddlTaluka',
    'VILLAGE_DROPDOWN_ID': 'ContentPlaceHolder1_ddlVillage',
    'SURVEY_DROPDOWN_ID': 'ContentPlaceHolder1_ddlSurveyNo',
    'CAPTCHA_IMG_ID': 'ContentPlaceHolder1_i_captcha_1',
    'CAPTCHA_INPUT_ID': 'ContentPlaceHolder1_txtCaptcha',
    'SUBMIT_BUTTON_ID': 'ContentPlaceHolder1_btnGo',
    'WAIT_TIMEOUT': 20,
    'CAPTCHA_WAIT_TIMEOUT': 2,
    'MAX_RETRIES': 3,
    'DROPDOWN_WAIT_TIMEOUT': 3,
    'PAGE_LOAD_WAIT': 3,
    'URL': 'https://anyror.gujarat.gov.in/LandRecordRural.aspx'
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
    """Handles CAPTCHA recognition using Google Gemini."""
    
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
        api_key = SecretStr(os.getenv('GEMINI_API_KEY', ''))
        return ChatGoogleGenerativeAI(
            model=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.5-flash'),
            google_api_key=api_key.get_secret_value(),
            temperature=0.0,
            convert_system_message_to_human=True,
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
            
            try:
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
                
                # Direct LLM call (avoid signal and thread timers for Streamlit compatibility)
                try:
                    response = self.llm.invoke([message])
                except Exception as e:
                    self.logger.error(f"LLM request failed: {str(e)}")
                    import traceback as _tb
                    self.logger.error(_tb.format_exc())
                    return None
                
                # Clean up the temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
                
                # Extract only digits from the response
                captcha_text = ''.join(re.findall(r'\d', response.content))
                
                if len(captcha_text) == 6:  # Verify we got exactly 6 digits
                    self.logger.info(f"LLM recognized captcha: {captcha_text}")
                    return captcha_text
                else:
                    self.logger.warning(f"LLM returned invalid captcha format: {response.content}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Error in LLM processing: {str(e)}")
                self.logger.error(traceback.format_exc())
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
                return None
                
        except Exception as e:
            self.logger.error(f"Error recognizing captcha with LLM: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None


class WebDriverManager:
    """Manages WebDriver instances and browser interactions."""
    
    def __init__(self):
        self.driver = None
        self.headless = True  # Default to headless
        # Track whether webdriver-manager cache was cleaned in this process
        self._wdm_cache_cleaned = False
    
    def _kill_zombie_chromedrivers(self):
        """Kill any zombie chromedriver processes."""
        import platform
        import subprocess
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            if platform.system() == "Darwin":  # macOS
                logger.info("Checking for zombie chromedriver processes on macOS")
                subprocess.run(["pkill", "-f", "chromedriver"], check=False)
                logger.info("Killed any existing chromedriver processes")
            elif platform.system() == "Linux":
                logger.info("Checking for zombie chromedriver processes on Linux")
                subprocess.run(["pkill", "-f", "chromedriver"], check=False)
                logger.info("Killed any existing chromedriver processes")
            elif platform.system() == "Windows":
                logger.info("Checking for zombie chromedriver processes on Windows")
                subprocess.run(["taskkill", "/f", "/im", "chromedriver.exe"], check=False)
                logger.info("Killed any existing chromedriver processes")
        except Exception as e:
            logger.warning(f"Failed to kill zombie processes: {str(e)}")
    
    def _clean_chromedriver_cache(self):
        """Clean up ChromeDriver cache directory."""
        import os
        import shutil
        import logging
        from pathlib import Path
        
        logger = logging.getLogger(__name__)
        
        try:
            # Find the WebDriver cache location
            home_dir = str(Path.home())
            wdm_cache_dir = os.path.join(home_dir, ".wdm", "drivers", "chromedriver")
            
            if os.path.exists(wdm_cache_dir):
                logger.info(f"Removing chromedriver cache at {wdm_cache_dir}")
                shutil.rmtree(wdm_cache_dir, ignore_errors=True)
                logger.info("Chromedriver cache removed")
            else:
                logger.info(f"No chromedriver cache found at {wdm_cache_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean chromedriver cache: {str(e)}")
    
    def get_chrome_version(self):
        """Get the installed Chrome version."""
        import platform
        import subprocess
        import re
        import logging
        
        logger = logging.getLogger(__name__)
        chrome_version = None
        
        try:
            if platform.system() == "Darwin":  # macOS
                process = subprocess.Popen(
                    ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                    stdout=subprocess.PIPE
                )
                output, _ = process.communicate()
                match = re.search(r"Google Chrome ([\d\.]+)", output.decode("utf-8"))
                if match:
                    chrome_version = match.group(1)
            elif platform.system() == "Linux":
                process = subprocess.Popen(
                    ["google-chrome", "--version"],
                    stdout=subprocess.PIPE
                )
                output, _ = process.communicate()
                match = re.search(r"Google Chrome ([\d\.]+)", output.decode("utf-8"))
                if match:
                    chrome_version = match.group(1)
            elif platform.system() == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                chrome_version, _ = winreg.QueryValueEx(key, "version")
        except Exception as e:
            logger.warning(f"Failed to get Chrome version: {str(e)}")
            
        if chrome_version:
            logger.info(f"Detected Chrome version: {chrome_version}")
        else:
            logger.warning("Could not detect Chrome version")
            
            return chrome_version
    
    def _setup_chrome_options(self, headless=True):
        """Set up Chrome options."""
        chrome_options = webdriver.ChromeOptions()
        
        # For Streamlit Cloud and Linux systems, use chromium if available
        if platform.system() == "Linux":
            chromium_paths = [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome"
            ]
            for chromium_path in chromium_paths:
                if os.path.exists(chromium_path):
                    chrome_options.binary_location = chromium_path
                    break
        
        if headless:
            chrome_options.add_argument("--headless=new")
        
        # Common options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-browser-side-navigation")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        return chrome_options
    
    def initialize_webdriver(self, headless=True, timeout=30):
        """Initialize and return a Chrome WebDriver with various fallback mechanisms."""
        import logging
        import time
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        
        logger = logging.getLogger(__name__)
        self.headless = headless  # Store headless setting
        
        # First, kill any zombie chromedriver processes
        self._kill_zombie_chromedrivers()
        
        # Set up Chrome options
        chrome_options = self._setup_chrome_options(headless)
        
        # Try different approaches to initialize WebDriver
        approaches = [
            self._approach_selenium_manager,  # Try Selenium Manager first (Selenium 4.6+)
            self._approach_clean_cache_and_auto_manager,
            self._approach_specify_major_version,
            self._approach_non_headless_mode,
            self._approach_explicit_driver_path
        ]
        
        for approach in approaches:
            try:
                driver = approach(chrome_options)
                if driver:
                    # Set script timeout
                    driver.set_script_timeout(timeout)
                    # Test if driver is responsive
                    driver.execute_script("return document.readyState")
                    self.driver = driver
                    return driver
            except Exception as e:
                logger.error(f"Failed with approach {approach.__name__}: {str(e)}")
                # Clean up any failed driver instance
                try:
                    if self.driver:
                        self.driver.quit()
                        self.driver = None
                except:
                    pass
                # Give a pause before trying next approach
                time.sleep(1)
        
        logger.error("All WebDriver initialization approaches failed")
        raise Exception("All WebDriver initialization approaches failed. Please check Chrome and ChromeDriver compatibility.")
    
    def _approach_selenium_manager(self, chrome_options):
        """Initialize WebDriver using Selenium Manager (Selenium 4.6+).
        
        Selenium Manager automatically downloads and manages the correct ChromeDriver
        version for the installed Chrome/Chromium browser. This is ideal for Streamlit Cloud.
        """
        import logging
        from selenium import webdriver
        
        logger = logging.getLogger(__name__)
        logger.info(f"Trying approach: Selenium Manager (headless={self.headless})")
        
        try:
            # Let Selenium Manager handle the driver automatically
            # No need to specify Service - Selenium will use its built-in manager
            driver = webdriver.Chrome(options=chrome_options)
            
            logger.info("Successfully initialized WebDriver using Selenium Manager")
            return driver
        except Exception as e:
            logger.error(f"Selenium Manager approach failed: {str(e)}")
            raise
    
    def _approach_clean_cache_and_auto_manager(self, chrome_options):
        """Initialize WebDriver using webdriver_manager with a clean cache."""
        import logging
        import os
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        logger = logging.getLogger(__name__)
        logger.info(f"Trying approach: Clean cache and ChromeDriverManager auto-detect (headless={self.headless})")
        
        # Clean the ChromeDriver cache only once per process to avoid repeated downloads
        if not self._wdm_cache_cleaned:
            self._clean_chromedriver_cache()
            self._wdm_cache_cleaned = True
        
        try:
            # First try with the latest ChromeDriverManager API
            service = Service(ChromeDriverManager(cache_valid_range=30).install())
        except TypeError:
            # Fallback to older API if cache_valid_range is not supported
            logger.info("Fallback to standard ChromeDriverManager without cache_valid_range")
            service = Service(ChromeDriverManager().install())
        
        # Ensure proper permissions
        driver_path = service.path
        if os.path.exists(driver_path):
            os.chmod(driver_path, 0o755)
            logger.info(f"Set executable permissions for {driver_path}")
        
        # Create the driver
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        logger.info("Successfully initialized WebDriver using Clean cache and ChromeDriverManager auto-detect")
        return driver
    
    def _approach_specify_major_version(self, chrome_options):
        """Initialize WebDriver using webdriver_manager with specific version."""
        import logging
        import os
        import subprocess
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        logger = logging.getLogger(__name__)
        logger.info(f"Trying approach: ChromeDriverManager with major version {self.get_chrome_version()}")
        
        # Clean the ChromeDriver cache
        self._clean_chromedriver_cache()
        
        # Use the major version to find a compatible driver
        driver_path = ChromeDriverManager().install()
        
        # Ensure the chromedriver has execute permissions
        logger.info(f"Set executable permissions for {driver_path}")
        os.chmod(driver_path, 0o755)
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        logger.info(f"Successfully initialized WebDriver using ChromeDriverManager with major version {self.get_chrome_version()}")
        return driver
    
    def _approach_non_headless_mode(self, chrome_options):
        """Initialize WebDriver in non-headless mode."""
        import logging
        import os
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        logger = logging.getLogger(__name__)
        logger.info("Trying approach: Non-headless mode")
        
        # Modify options to disable headless mode
        non_headless_options = chrome_options
        
        # Loop through arguments to filter out headless
        filtered_args = []
        for arg in non_headless_options.arguments:
            if "--headless" not in arg:
                filtered_args.append(arg)
        
        # Replace arguments with filtered list
        non_headless_options.arguments = filtered_args
        
        # Install driver
        driver_path = ChromeDriverManager().install()
        
        # Ensure the chromedriver has execute permissions
        logger.info(f"Set executable permissions for {driver_path}")
        os.chmod(driver_path, 0o755)
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=non_headless_options)
        
        logger.info("Successfully initialized WebDriver using Non-headless mode")
        return driver
    
    def _approach_explicit_driver_path(self, chrome_options):
        """Initialize WebDriver with explicit path to chromedriver."""
        import logging
        import os
        import platform
        import subprocess
        from pathlib import Path
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        
        logger = logging.getLogger(__name__)
        logger.info("Trying approach: Explicit driver path")
        
        # Determine the default location of chromedriver
        home_dir = str(Path.home())
        
        if platform.system() == "Darwin":  # macOS
            if os.path.exists("/usr/local/bin/chromedriver"):
                driver_path = "/usr/local/bin/chromedriver"
            else:
                # If it doesn't exist, download it using curl
                logger.info("Downloading chromedriver using curl")
                driver_path = os.path.join(home_dir, "chromedriver")
                
                # Download latest version using chromedriver.storage.googleapis.com
                chrome_version = self.get_chrome_version()
                major_version = chrome_version.split('.')[0] if chrome_version else None
                
                # Determine architecture
                if platform.machine() == "arm64":
                    arch = "mac-arm64"
                else:
                    arch = "mac64"
                
                # Download URL for Chrome for Testing (CFT) versions
                # Format matches: https://storage.googleapis.com/chrome-for-testing-public/133.0.6943.141/mac-arm64/chromedriver-mac-arm64.zip
                download_url = f"https://storage.googleapis.com/chrome-for-testing-public/{major_version}.0.6943.141/{arch}/chromedriver-{arch}.zip"
                
                logger.info(f"Downloading ChromeDriver from: {download_url}")
                
                try:
                    # Download, unzip and set permissions
                    subprocess.run(["curl", "-L", download_url, "-o", f"{driver_path}.zip"], check=True)
                    subprocess.run(["unzip", "-o", f"{driver_path}.zip", "-d", home_dir], check=True)
                    # The unzipped path will be in a nested directory
                    unzipped_driver = os.path.join(home_dir, f"chromedriver-{arch}", "chromedriver")
                    if os.path.exists(unzipped_driver):
                        # Move to the expected location
                        subprocess.run(["mv", unzipped_driver, driver_path], check=True)
                        # Set executable permissions
                        subprocess.run(["chmod", "+x", driver_path], check=True)
                    else:
                        logger.error(f"ChromeDriver not found at expected path: {unzipped_driver}")
                        raise FileNotFoundError(f"ChromeDriver extraction failed")
                except subprocess.SubprocessError as e:
                    logger.error(f"Failed to download or extract ChromeDriver: {str(e)}")
                    raise
        elif platform.system() == "Linux":
            # Common locations for chromedriver on Linux (including Streamlit Cloud)
            possible_paths = [
                "/usr/bin/chromedriver",
                "/usr/lib/chromium-browser/chromedriver",
                "/usr/local/bin/chromedriver"
            ]
            
            found = False
            for path in possible_paths:
                if os.path.exists(path):
                    driver_path = path
                    found = True
                    break
            
            if not found:
                driver_path = os.path.join(home_dir, "chromedriver")
        elif platform.system() == "Windows":
            driver_path = os.path.join(home_dir, "chromedriver.exe")
        else:
            raise Exception(f"Unsupported platform: {platform.system()}")
        
        # Ensure the chromedriver has execute permissions
        if os.path.exists(driver_path):
            logger.info(f"Using explicit chromedriver path: {driver_path}")
            os.chmod(driver_path, 0o755)
            
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            logger.info("Successfully initialized WebDriver using explicit driver path")
            return driver
        else:
            raise FileNotFoundError(f"ChromeDriver not found at {driver_path}")
    
    def close(self):
        """Close the WebDriver and clean up resources."""
        import time
        logger = logging.getLogger(__name__)
        
        if self.driver:
            try:
                # Close all windows first
                for window_handle in self.driver.window_handles:
                    self.driver.switch_to.window(window_handle)
                    self.driver.close()
                
                # Quit the driver
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.warning(f"Error closing WebDriver gracefully: {e}")
                try:
                    # Force quit if graceful close fails
                    self.driver.quit()
                except:
                    pass
            finally:
                self.driver = None
        
        # Small delay to allow processes to cleanup
        time.sleep(1)
        
        # Kill any zombie chromedriver processes
        self._kill_zombie_chromedrivers()
        
        # Optionally clean the cache at close if explicitly requested
        try:
            if os.getenv("WDM_CLEAN_ON_CLOSE", "0") in ("1", "true", "True"):
                self._clean_chromedriver_cache()
        except Exception:
            pass


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
        
        try:
            # First try the direct land record URL
            self.driver.get(CONFIG['URL'])
            time.sleep(2)  # Wait for initial load
            
            # Check if we need to navigate to the correct page
            current_url = self.driver.current_url
            if 'LandRecordRural.aspx' not in current_url:
                self.logger.info("Not on land record page, trying alternative navigation")
                
                # Try clicking the land record link if present
                try:
                    land_record_link = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Land Record')]")
                    land_record_link.click()
                    time.sleep(2)
                except Exception as e:
                    self.logger.warning(f"Could not find land record link: {str(e)}")
            
            # Wait for the page to load and verify we're on the correct page
            try:
                # Wait for the land record type dropdown
                self.wait.until(
                    EC.presence_of_element_located((By.ID, CONFIG['LAND_RECORD_TYPE_ID']))
                )
                
                # Log the current URL and page title for debugging
                self.logger.info(f"Current URL: {self.driver.current_url}")
                self.logger.info(f"Page Title: {self.driver.title}")
                
                # Check if the dropdown is actually visible
                dropdown = self.driver.find_element(By.ID, CONFIG['LAND_RECORD_TYPE_ID'])
                if not dropdown.is_displayed():
                    self.logger.warning("Land record dropdown is present but not visible")
                    
                # Get all dropdown options for debugging
                select = Select(dropdown)
                options = [f"{o.get_attribute('value')}: {o.text}" for o in select.options]
                self.logger.debug(f"Available options in land record dropdown: {options}")
                
            except Exception as e:
                self.logger.error(f"Error waiting for land record form: {str(e)}")
                self.logger.error(traceback.format_exc())
                
                # Try to get the page source for debugging
                try:
                    self.logger.debug(f"Page source: {self.driver.page_source[:1000]}...")
                except:
                    pass
                
                raise
            
            self.logger.info("Successfully navigated to the land record form page")
            
        except Exception as e:
            self.logger.error(f"Error navigating to form page: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise
    
    def select_land_record_type(self):
        """Select the land record type."""
        self.logger.info("Selecting Land Record Type")
        
        try:
            # Wait for the dropdown to be present in the DOM
            dropdown_id = CONFIG['LAND_RECORD_TYPE_ID']
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.ID, dropdown_id))
                )
            except Exception as e:
                # Log all select elements and their IDs for debugging
                self.logger.error(f"Dropdown with id {dropdown_id} not found. Listing all select elements on page.")
                selects = self.driver.find_elements(By.TAG_NAME, 'select')
                for sel in selects:
                    self.logger.error(f"Select element id: {sel.get_attribute('id')}, name: {sel.get_attribute('name')}, outerHTML: {sel.get_attribute('outerHTML')[:200]}")
                raise
            
            # Try multiple approaches to select the land record type
            success = False
            
            # Approach 1: Direct JavaScript execution
            try:
                js_script = """
                    var select = document.getElementById(arguments[0]);
                    if(select) {
                        select.value = arguments[1];
                        var event = new Event('change', { bubbles: true });
                        select.dispatchEvent(event);
                        if(typeof jQuery !== 'undefined') {
                            jQuery(select).trigger('change');
                        }
                        return true;
                    }
                    return false;
                """
                result = self.driver.execute_script(js_script, dropdown_id, CONFIG['LAND_RECORD_TYPE_VALUE'])
                if result:
                    self.logger.info("Successfully selected land record type using JavaScript")
                    success = True
            except Exception as e:
                self.logger.debug(f"JavaScript selection failed: {str(e)}")
            
            # Approach 2: Use Selenium's Select class
            if not success:
                try:
                    dropdown = self.wait.until(
                        EC.element_to_be_clickable((By.ID, dropdown_id))
                    )
                    select = Select(dropdown)
                    select.select_by_value(CONFIG['LAND_RECORD_TYPE_VALUE'])
                    self.logger.info("Successfully selected land record type using Selenium Select")
                    success = True
                except Exception as e:
                    self.logger.debug(f"Selenium Select failed: {str(e)}")
                    # Log all options for debugging
                    try:
                        dropdown = self.driver.find_element(By.ID, dropdown_id)
                        select = Select(dropdown)
                        for option in select.options:
                            self.logger.error(f"Option value: {option.get_attribute('value')}, text: {option.text}")
                    except Exception as inner:
                        self.logger.error(f"Could not log dropdown options: {inner}")
            
            # Approach 3: Click and select using JavaScript
            if not success:
                try:
                    js_click_script = """
                        var select = document.getElementById(arguments[0]);
                        if(select) {
                            select.click();
                            setTimeout(function() {
                                select.value = arguments[1];
                                select.dispatchEvent(new Event('change', { bubbles: true }));
                            }, 500);
                            return true;
                        }
                        return false;
                    """
                    result = self.driver.execute_script(js_click_script, dropdown_id, CONFIG['LAND_RECORD_TYPE_VALUE'])
                    if result:
                        self.logger.info("Successfully selected land record type using click and JavaScript")
                        success = True
                except Exception as e:
                    self.logger.debug(f"Click and JavaScript selection failed: {str(e)}")
            
            # Wait for any AJAX requests to complete
            time.sleep(2)
            
            try:
                # Wait for AJAX to complete using jQuery if available
                self.wait.until(
                    lambda driver: driver.execute_script('return (typeof jQuery === "undefined") || (jQuery.active === 0);')
                )
            except Exception as e:
                self.logger.debug(f"jQuery wait failed, using time delay: {str(e)}")
                time.sleep(CONFIG['DROPDOWN_WAIT_TIMEOUT'])
            
            # Verify the selection was successful
            selected_value = self.driver.execute_script(
                'return document.getElementById(arguments[0]).value;',
                dropdown_id
            )
            
            if selected_value != CONFIG['LAND_RECORD_TYPE_VALUE']:
                raise Exception(f"Land record type selection failed. Expected {CONFIG['LAND_RECORD_TYPE_VALUE']} but got {selected_value}")
            
            self.logger.info("Land record type selection verified successfully")
            
        except Exception as e:
            self.logger.error(f"Error selecting land record type: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise
    
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
        # Ensure option_text is a string
        option_text = str(option_text).strip()
        
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
        
        # Wait for the dropdown to be clickable and handle stale elements
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Wait for the dropdown to be clickable
                dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, CONFIG['DISTRICT_DROPDOWN_ID']))
                )
                
                # Create Select object
                select_district = Select(dropdown)
                
                # Try to find the district in the options
                found_district = False
                for option in select_district.options:
                    if district_name in option.text:
                        select_district.select_by_visible_text(option.text)
                        found_district = True
                        self.logger.info(f"Successfully selected district: {option.text}")
                        break
                
                if not found_district:
                    self.logger.error(f"District not found: {district_name}")
                    return False
                    
                # Wait for the page to update after selection
                try:
                    WebDriverWait(self.driver, CONFIG['DROPDOWN_WAIT_TIMEOUT']).until(
                        EC.staleness_of(dropdown)
                    )
                except TimeoutException:
                    # If staleness check times out, just wait a bit and continue
                    self.logger.debug("Staleness check timed out, continuing anyway")
                    time.sleep(0.5)  # Reduced from 1 second to 0.5 seconds
                    
                return True
                
            except StaleElementReferenceException:
                self.logger.warning(f"Stale element encountered on attempt {attempt + 1}, retrying...")
                if attempt == max_attempts - 1:
                    self.logger.error("Failed to select district after all attempts due to stale elements")
                    return False
                time.sleep(1)  # Wait before retrying
            except Exception as e:
                self.logger.error(f"Error selecting district on attempt {attempt + 1}: {str(e)}")
                if attempt == max_attempts - 1:
                    return False
                time.sleep(1)  # Wait before retrying
        
        return False
    
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
        
        # First try exact/partial match
        result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], village_name, partial_match=True)
        
        if not result:
            # If failed, try some common village name variations and debug
            self.logger.warning(f"Initial village selection failed for: {village_name}")
            
            # Enhanced village matching using the VillageNameMatcher
            try:
                dropdown = self.wait.until(EC.element_to_be_clickable((By.ID, CONFIG['VILLAGE_DROPDOWN_ID'])))
                select = Select(dropdown)
                available_options = [opt.text.strip() for opt in select.options if opt.text.strip()]
                
                self.logger.debug(f"Available village options (first 10): {available_options[:10]}")
                
                # Use enhanced village matcher
                matcher = VillageNameMatcher(self.logger)
                best_match = matcher.find_best_match(village_name, available_options)
                
                if best_match:
                    self.logger.info(f"VillageNameMatcher found best match: '{best_match}' for '{village_name}'")
                    result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], best_match, partial_match=False)
                    if result:
                        self.logger.info(f"Successfully selected matched village: {best_match}")
                else:
                    # Generate detailed matching report for debugging
                    report = matcher.get_match_strategies_report(village_name, available_options)
                    self.logger.warning(f"VillageNameMatcher could not find suitable match:\n{report}")
                
            except Exception as e:
                self.logger.warning(f"Error during enhanced village matching: {e}")
        
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
        # Convert survey_block_number to string to fix issues with integer survey numbers
        survey_block_number = str(survey_block_number).strip()
        
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
        
        try:
            # Wait a bit for the page to fully load after survey selection
            time.sleep(2)
            
            # Try multiple approaches to find the CAPTCHA image
            captcha_img = None
            captcha_id = CONFIG['CAPTCHA_IMG_ID']
            
            # Approach 1: Try the configured ID
            try:
                captcha_img = self.wait.until(
                    EC.visibility_of_element_located((By.ID, captcha_id))
                )
                self.logger.info(f"Found CAPTCHA image with ID: {captcha_id}")
            except Exception as e:
                self.logger.warning(f"Could not find CAPTCHA with ID {captcha_id}: {str(e)}")
                
                # Approach 2: Try common CAPTCHA image patterns
                captcha_selectors = [
                    "img[src*='captcha']",
                    "img[src*='Captcha']", 
                    "img[src*='CAPTCHA']",
                    "img[alt*='captcha']",
                    "img[alt*='Captcha']",
                    "img[alt*='CAPTCHA']",
                    "#ContentPlaceHolder1_imgCaptcha",
                    "#ctl00_ContentPlaceHolder1_imgCaptcha",
                    "img[src*='.ashx']",  # ASP.NET handler for CAPTCHA
                ]
                
                for selector in captcha_selectors:
                    try:
                        captcha_img = self.driver.find_element(By.CSS_SELECTOR, selector)
                        self.logger.info(f"Found CAPTCHA image with selector: {selector}")
                        break
                    except:
                        continue
                
                # Approach 3: Find any img element that might be a CAPTCHA
                if not captcha_img:
                    try:
                        all_images = self.driver.find_elements(By.TAG_NAME, "img")
                        for img in all_images:
                            src = img.get_attribute('src') or ''
                            alt = img.get_attribute('alt') or ''
                            if 'captcha' in src.lower() or 'captcha' in alt.lower():
                                captcha_img = img
                                self.logger.info(f"Found CAPTCHA image with src: {src}")
                                break
                    except Exception as e:
                        self.logger.warning(f"Error searching for CAPTCHA images: {str(e)}")
            
            if not captcha_img:
                self.logger.error("Could not find CAPTCHA image element")
                # Log all img elements for debugging
                try:
                    all_images = self.driver.find_elements(By.TAG_NAME, "img")
                    self.logger.error(f"Found {len(all_images)} img elements on page:")
                    for i, img in enumerate(all_images[:10]):  # Log first 10 images
                        src = img.get_attribute('src') or 'No src'
                        alt = img.get_attribute('alt') or 'No alt'
                        id_attr = img.get_attribute('id') or 'No id'
                        self.logger.error(f"  Image {i}: id='{id_attr}', src='{src}', alt='{alt}'")
                except Exception as e:
                    self.logger.error(f"Error logging images: {str(e)}")
                return None
            
            # Convert captcha to base64
            try:
                captcha_base64 = self.driver.execute_script("""
                    var canvas = document.createElement('canvas');
                    var context = canvas.getContext('2d');
                    var img = arguments[0];
                    canvas.width = img.width;
                    canvas.height = img.height;
                    context.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').replace(/^data:image\\/(png|jpg);base64,/, '');
                """, captcha_img)
                
                # Decode base64 to binary data
                captcha_data = base64.b64decode(captcha_base64)
                
                # Solve the captcha
                captcha_value = self.captcha_solver.solve(captcha_data)
                
                if captcha_value:
                    # Find and fill the CAPTCHA input field
                    captcha_input_id = CONFIG['CAPTCHA_INPUT_ID']
                    try:
                        captcha_input = self.wait.until(
                            EC.visibility_of_element_located((By.ID, captcha_input_id))
                        )
                    except:
                        # Try alternative input field selectors
                        input_selectors = [
                            "input[name*='captcha']",
                            "input[name*='Captcha']",
                            "input[placeholder*='captcha']",
                            "input[placeholder*='Captcha']",
                            "#ContentPlaceHolder1_txtCaptcha",
                            "#ctl00_ContentPlaceHolder1_txtCaptcha"
                        ]
                        
                        captcha_input = None
                        for selector in input_selectors:
                            try:
                                captcha_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                                break
                            except:
                                continue
                        
                        if not captcha_input:
                            self.logger.error("Could not find CAPTCHA input field")
                            return None
                    
                    captcha_input.clear()
                    captcha_input.send_keys(captcha_value)
                    self.logger.info(f"Entered captcha value: {captcha_value}")
                    return captcha_value
                else:
                    self.logger.error("CAPTCHA recognition failed - no value returned")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Error processing CAPTCHA image: {str(e)}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error during CAPTCHA solving: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
    
    def submit_form(self):
        """Submit the form and handle any alerts.
        
        Returns:
            A tuple (success, error_message) where success is True if the form was submitted
            successfully, and error_message is None or the error message if submission failed.
        """
        self.logger.info("Submitting the form")
        try:
            submit_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, CONFIG['SUBMIT_BUTTON_ID']))
            )
            self.logger.info("Found submit button, clicking...")
            submit_button.click()
            self.logger.info("Submit button clicked successfully")
        except Exception as e:
            self.logger.error(f"Error clicking submit button: {str(e)}")
            return False, f"Submit button error: {str(e)}"
        
        # Check for alert (captcha error)
        try:
            self.logger.info("Checking for alerts...")
            WebDriverWait(self.driver, CONFIG['CAPTCHA_WAIT_TIMEOUT']).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            self.logger.warning(f"Alert present: {alert_text}")
            alert.accept()
            
            return False, alert_text
        except TimeoutException:
            # No alert means success
            self.logger.info("Form submitted successfully - no alerts found")
            
            # Log current state
            try:
                current_url = self.driver.current_url
                self.logger.info(f"Current URL after submission: {current_url}")
                
                page_title = self.driver.title
                self.logger.info(f"Page title after submission: {page_title}")
                
                # Check if page is still responsive
                ready_state = self.driver.execute_script("return document.readyState")
                self.logger.info(f"Page ready state: {ready_state}")
                
            except Exception as e:
                self.logger.error(f"Error checking page state after submission: {str(e)}")
            
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
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            self.logger.info(f"Output directory created/verified: {os.path.dirname(output_path)}")
        except Exception as e:
            self.logger.error(f"Error creating output directory: {str(e)}")
            return False, f"Directory creation error: {str(e)}"
        
        try:
            # Log current state before PDF generation
            self.logger.info("Checking page state before PDF generation...")
            try:
                current_url = self.driver.current_url
                self.logger.info(f"Current URL before PDF generation: {current_url}")
                
                page_title = self.driver.title
                self.logger.info(f"Page title before PDF generation: {page_title}")
                
                ready_state = self.driver.execute_script("return document.readyState")
                self.logger.info(f"Page ready state before PDF generation: {ready_state}")
                
            except Exception as e:
                self.logger.error(f"Error checking page state before PDF generation: {str(e)}")
            
            # Wait for the page to load completely
            self.logger.info(f"Waiting {CONFIG['PAGE_LOAD_WAIT']} seconds for page to load...")
            time.sleep(CONFIG['PAGE_LOAD_WAIT'])
            
            # Check if driver is still responsive
            self.logger.info("Testing driver responsiveness...")
            try:
                test_result = self.driver.execute_script("return 'Driver is responsive'")
                self.logger.info(f"Driver test result: {test_result}")
            except Exception as e:
                self.logger.error(f"Driver not responsive: {str(e)}")
                return False, f"Driver not responsive: {str(e)}"
            
            # Generate PDF
            self.logger.info("Executing PDF generation command...")
            try:
                result = self.driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
                self.logger.info("PDF generation command executed successfully")
                
                pdf_data = result.get("data")
                if pdf_data:
                    self.logger.info(f"PDF data received, length: {len(pdf_data)} characters")
                    
                    # Save PDF
                    self.logger.info(f"Saving PDF to: {output_path}")
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(pdf_data))
                    
                    # Verify file was created
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        self.logger.info(f"PDF saved successfully to: {output_path} (size: {file_size} bytes)")
                        return True, None
                    else:
                        error_msg = "PDF file was not created"
                        self.logger.error(error_msg)
                        return False, error_msg
                else:
                    error_msg = "PDF generation did not return any data"
                    self.logger.error(error_msg)
                    self.logger.error(f"Full result object: {result}")
                    return False, error_msg
                    
            except Exception as e:
                error_msg = f"PDF generation command failed: {str(e)}"
                self.logger.error(error_msg)
                self.logger.error(traceback.format_exc())
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
        self.web_driver_manager = WebDriverManager()
        self.captcha_solver = CaptchaSolver(logger=self.logger)
        self.form_filler = None
        self.headless = headless  # Store headless setting
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
                self.logger.info("AnyRoRScraper: WebDriver cleaned up")
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
        """Fetch a land record from the AnyRoR portal."""
        # Ensure all parameters are strings
        district_name = str(district_name).strip()
        taluka_name = str(taluka_name).strip()
        village_name = str(village_name).strip()
        survey_block_number = str(survey_block_number).strip()
        
        self.logger.info(f"Fetching land record for {district_name}, {taluka_name}, {village_name}, {survey_block_number}")
        
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
                self.logger.debug(f"Page source: {page_source[:1000]}...")  # Log first 1000 chars
            
            # Try to select land record type multiple times
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    self.logger.info(f"Attempt {attempt + 1} to select land record type")
                    
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
                        self.logger.info("Successfully selected land record type using JavaScript")
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
                        self.logger.info("Successfully verified land record type selection")
                        break
                    else:
                        self.logger.warning(f"Land record type selection verification failed. Got value: {selected_value}")
                        
                except Exception as e:
                    self.logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(2)
            
            # Continue with rest of the form...
            self.logger.info("Starting district selection...")
            district_selected = self.form_filler.select_district(district_name)
            if not district_selected:
                self.logger.error(f"Failed to select district: {district_name}")
                return {'success': False, 'error': f"District not found: {district_name}"}
            
            self.logger.info("Starting taluka selection...")
            taluka_selected = self.form_filler.select_taluka(taluka_name)
            if not taluka_selected:
                self.logger.error(f"Failed to select taluka: {taluka_name}")
                return {'success': False, 'error': f"Taluka not found: {taluka_name}"}
                
            self.logger.info("Starting village selection...")
            village_selected = self.form_filler.select_village(village_name)
            if not village_selected:
                self.logger.error(f"Failed to select village: {village_name}")
                return {'success': False, 'error': f"Village not found: {village_name}"}
                
            # Retry if survey selection fails
            self.logger.info("Starting survey selection...")
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
            
            # Solve captcha
            self.logger.info("Starting CAPTCHA solving...")
            captcha_solved = self.form_filler.solve_captcha()
            if not captcha_solved:
                self.logger.error("Failed to solve captcha")
                return {'success': False, 'error': "Captcha could not be solved"}
                
            # Submit the form
            self.logger.info("Starting form submission...")
            submission_success = self.form_filler.submit_form()
            if not submission_success:
                self.logger.error("Form submission failed")
                return {'success': False, 'error': "Form submission failed"}
                
            # Generate PDF
            self.logger.info("Starting PDF generation...")
            pdf_success = self.form_filler.generate_pdf(output_path)
            if not pdf_success:
                self.logger.error("PDF generation failed")
                return {'success': False, 'error': "PDF generation failed"}
                
            self.logger.info(f"Successfully fetched land record and saved to {output_path}")
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
    
    # Create scraper and fetch land record with non-headless mode
    scraper = AnyRoRScraper(headless=False, logger=logger)  # Set headless=False
    result = scraper.fetch_land_record(
        district_name=district_name,
        taluka_name=taluka_name,
        village_name=village_name,
        survey_block_number=survey_block_number,
        output_path=output_path
    )
    
    if result['success']:
        print(f"Land record fetched successfully: {result['output_path']}")
    else:
        print(f"Failed to fetch land record: {result['error']}")


if __name__ == "__main__":
    main() 