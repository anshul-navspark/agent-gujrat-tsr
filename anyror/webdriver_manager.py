"""
WebDriver Manager for Gujarat Land Record Automation

Manages WebDriver instances and browser interactions with thread-safe operations.
"""

import os
import platform
import subprocess
import logging
import time
import threading
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# Thread-safe global cache cleaning tracker
_cache_clean_lock = threading.Lock()
_cache_cleaned = False


class WebDriverManager:
    """Manages WebDriver instances and browser interactions with thread-safety."""
    
    def __init__(self):
        self.driver = None
        self.headless = True  # Default to headless
        # Instance-level lock for safe parallel initialization
        self._init_lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
    
    def _kill_zombie_chromedrivers(self):
        """Kill any zombie chromedriver processes."""
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["pkill", "-f", "chromedriver"], check=False)
            elif platform.system() == "Linux":
                subprocess.run(["pkill", "-f", "chromedriver"], check=False)
            elif platform.system() == "Windows":
                subprocess.run(["taskkill", "/f", "/im", "chromedriver.exe"], check=False)
        except Exception as e:
            self.logger.warning(f"Failed to kill zombie processes: {str(e)}")
    
    def _clean_chromedriver_cache(self):
        """Clean up ChromeDriver cache directory (thread-safe)."""
        global _cache_cleaned
        
        # Use global lock to ensure only one thread cleans the cache
        with _cache_clean_lock:
            if _cache_cleaned:
                self.logger.debug("Cache already cleaned by another thread, skipping")
                return
            
            try:
                # Find the WebDriver cache location
                home_dir = str(Path.home())
                wdm_cache_dir = os.path.join(home_dir, ".wdm", "drivers", "chromedriver")
                
                if os.path.exists(wdm_cache_dir):
                    import shutil
                    shutil.rmtree(wdm_cache_dir, ignore_errors=True)
                    self.logger.debug(f"Cleaned ChromeDriver cache: {wdm_cache_dir}")
                
                _cache_cleaned = True
            except Exception as e:
                self.logger.warning(f"Failed to clean chromedriver cache: {str(e)}")
    
    def get_chrome_version(self):
        """Get the installed Chrome version."""
        chrome_version = None
        
        try:
            if platform.system() == "Darwin":  # macOS
                process = subprocess.Popen(
                    ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                    stdout=subprocess.PIPE
                )
                output, _ = process.communicate()
                import re
                match = re.search(r"Google Chrome ([\d\.]+)", output.decode("utf-8"))
                if match:
                    chrome_version = match.group(1)
            elif platform.system() == "Linux":
                process = subprocess.Popen(
                    ["google-chrome", "--version"],
                    stdout=subprocess.PIPE
                )
                output, _ = process.communicate()
                import re
                match = re.search(r"Google Chrome ([\d\.]+)", output.decode("utf-8"))
                if match:
                    chrome_version = match.group(1)
            elif platform.system() == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                chrome_version, _ = winreg.QueryValueEx(key, "version")
        except Exception as e:
            self.logger.warning(f"Failed to get Chrome version: {str(e)}")
            
        if chrome_version:
            self.logger.debug(f"Detected Chrome version: {chrome_version}")
        else:
            self.logger.warning("Could not detect Chrome version")
            
        return chrome_version
    
    def _setup_chrome_options(self, headless=True):
        """Set up Chrome options."""
        import random
        
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
        
        # CRITICAL FIX: Use random port for remote debugging to prevent port conflicts
        # when running multiple ChromeDriver instances in parallel
        random_port = random.randint(9222, 9999)
        chrome_options.add_argument(f"--remote-debugging-port={random_port}")
        
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
        self.headless = headless  # Store headless setting
        
        # Use lock to prevent race conditions during parallel initialization
        with self._init_lock:
            self.logger.debug("Acquired initialization lock")
            
            # First, kill any zombie chromedriver processes
            # self._kill_zombie_chromedrivers()  # DISABLED: This kills concurrent drivers in parallel processing
            
            # Set up Chrome options (with random port for parallel instances)
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
                        self.logger.debug(f"Successfully initialized driver with {approach.__name__}")
                        return driver
                except Exception as e:
                    self.logger.error(f"Failed with approach {approach.__name__}: {str(e)}")
                    # Clean up any failed driver instance
                    try:
                        if self.driver:
                            self.driver.quit()
                            self.driver = None
                    except:
                        pass
                    # Give a pause before trying next approach
                    time.sleep(1)
            
            self.logger.error("All WebDriver initialization approaches failed")
            raise Exception("All WebDriver initialization approaches failed. Please check Chrome and ChromeDriver compatibility.")
    
    def _approach_selenium_manager(self, chrome_options):
        """Initialize WebDriver using Selenium Manager (Selenium 4.6+)."""
        self.logger.debug(f"Trying approach: Selenium Manager (headless={self.headless})")
        
        try:
            # Let Selenium Manager handle the driver automatically
            driver = webdriver.Chrome(options=chrome_options)
            self.logger.debug("Successfully initialized WebDriver using Selenium Manager")
            return driver
        except Exception as e:
            self.logger.error(f"Selenium Manager approach failed: {str(e)}")
            raise
    
    def _approach_clean_cache_and_auto_manager(self, chrome_options):
        """Initialize WebDriver using webdriver_manager with a clean cache."""
        self.logger.debug(f"Trying approach: Clean cache and ChromeDriverManager auto-detect (headless={self.headless})")
        
        # Clean the ChromeDriver cache (thread-safe)
        self._clean_chromedriver_cache()
        
        try:
            # First try with the latest ChromeDriverManager API
            service = Service(ChromeDriverManager(cache_valid_range=30).install())
        except TypeError:
            # Fallback to older API if cache_valid_range is not supported
            self.logger.debug("Fallback to standard ChromeDriverManager without cache_valid_range")
            service = Service(ChromeDriverManager().install())
        
        # Ensure proper permissions
        driver_path = service.path
        if os.path.exists(driver_path):
            os.chmod(driver_path, 0o755)
        
        # Create the driver
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        self.logger.debug("Successfully initialized WebDriver using Clean cache and ChromeDriverManager auto-detect")
        return driver
    
    def _approach_specify_major_version(self, chrome_options):
        """Initialize WebDriver using webdriver_manager with specific version."""
        self.logger.debug(f"Trying approach: ChromeDriverManager with major version {self.get_chrome_version()}")
        
        # Clean the ChromeDriver cache
        self._clean_chromedriver_cache()
        
        # Use the major version to find a compatible driver
        driver_path = ChromeDriverManager().install()
        
        # Ensure the chromedriver has execute permissions
        os.chmod(driver_path, 0o755)
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        self.logger.debug(f"Successfully initialized WebDriver using ChromeDriverManager with major version {self.get_chrome_version()}")
        return driver
    
    def _approach_non_headless_mode(self, chrome_options):
        """Initialize WebDriver in non-headless mode."""
        self.logger.debug("Trying approach: Non-headless mode")
        
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
        os.chmod(driver_path, 0o755)
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=non_headless_options)
        
        self.logger.debug("Successfully initialized WebDriver using Non-headless mode")
        return driver
    
    def _approach_explicit_driver_path(self, chrome_options):
        """Initialize WebDriver with explicit path to chromedriver."""
        self.logger.debug("Trying approach: Explicit driver path")
        
        # Determine the default location of chromedriver
        home_dir = str(Path.home())
        
        if platform.system() == "Darwin":  # macOS
            if os.path.exists("/usr/local/bin/chromedriver"):
                driver_path = "/usr/local/bin/chromedriver"
            else:
                # If it doesn't exist, download it using curl
                self.logger.debug("Downloading chromedriver using curl")
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
                download_url = f"https://storage.googleapis.com/chrome-for-testing-public/{major_version}.0.6943.141/{arch}/chromedriver-{arch}.zip"
                
                self.logger.debug(f"Downloading ChromeDriver from: {download_url}")
                
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
                        self.logger.error(f"ChromeDriver not found at expected path: {unzipped_driver}")
                        raise FileNotFoundError(f"ChromeDriver extraction failed")
                except subprocess.SubprocessError as e:
                    self.logger.error(f"Failed to download or extract ChromeDriver: {str(e)}")
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
            self.logger.debug(f"Using explicit chromedriver path: {driver_path}")
            os.chmod(driver_path, 0o755)
            
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.logger.debug("Successfully initialized WebDriver using explicit driver path")
            return driver
        else:
            raise FileNotFoundError(f"ChromeDriver not found at {driver_path}")
    
    def close(self):
        """Close the WebDriver and clean up resources."""
        if self.driver:
            try:
                # Close all windows first
                for window_handle in self.driver.window_handles:
                    self.driver.switch_to.window(window_handle)
                    self.driver.close()
                
                # Quit the driver
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
            except Exception as e:
                self.logger.warning(f"Error closing WebDriver gracefully: {e}")
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
        # self._kill_zombie_chromedrivers() # DISABLED: This kills concurrent drivers in parallel processing
        
        # Optionally clean the cache at close if explicitly requested
        try:
            if os.getenv("WDM_CLEAN_ON_CLOSE", "0") in ("1", "true", "True"):
                self._clean_chromedriver_cache()
        except Exception:
            pass
