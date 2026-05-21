"""
Form Filler for Gujarat Land Record Automation

Handles form filling operations on the AnyRoR website.
"""

import os
import time
import base64
import logging
import traceback
from functools import lru_cache
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from .village_matcher import VillageNameMatcher
from .config import CONFIG


class FormFiller:
    """Handles form filling operations on the AnyRoR website."""
    
    def __init__(self, driver, wait, captcha_solver, logger=None):
        """
        Initialize the form filler.
        
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
    
    def _log_page_diagnostics(self, context: str):
        """Log diagnostic info about the current page state for debugging Cloud failures."""
        try:
            current_url = self.driver.current_url
            page_title = self.driver.title
            ready_state = self.driver.execute_script("return document.readyState")
            body_length = self.driver.execute_script("return document.body ? document.body.innerHTML.length : 0")
            select_ids = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('select')).map(s => s.id)"
            )
            self.logger.error(
                f"[{context}] URL={current_url} | title={page_title} | "
                f"readyState={ready_state} | bodyLen={body_length} | selects={select_ids}"
            )
            # If the body is tiny, the page probably didn't load at all
            if body_length < 500:
                snippet = self.driver.execute_script(
                    "return document.body ? document.body.innerHTML.substring(0, 500) : '(no body)'"
                )
                self.logger.error(f"[{context}] Page body snippet: {snippet}")
        except Exception as diag_err:
            self.logger.error(f"[{context}] Failed to collect diagnostics: {diag_err}")

    def _preflight_check(self):
        """Check if the AnyRoR site is reachable via Python and Chrome.

        Tests both Python sockets (informational) and Chrome's own network stack
        (authoritative for scraping).  On IPv6-only hosts (e.g. Streamlit Cloud)
        the Python TCP check may fail while Chrome succeeds via NAT64 — the Chrome
        result is what determines the return value.
        """
        import socket
        import urllib.request
        import urllib.error
        url = CONFIG['URL']
        host = 'anyror.gujarat.gov.in'
        python_ok = False

        # Step 1: DNS resolution — AF_UNSPEC so DNS64 returns NAT64-mapped
        # addresses on IPv6-only hosts instead of raw IPv4.
        try:
            addrs = socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
            addr_strs = [sa[0] for (af, _st, _pr, _cn, sa) in addrs]
            self.logger.info(f"Preflight DNS OK: {host} -> {addr_strs}")
        except socket.gaierror as e:
            self.logger.error(f"Preflight DNS FAILED: {host} cannot be resolved: {e}")
            addrs = []

        # Step 2: TCP connection — try every resolved address so NAT64-mapped
        # IPv6 addresses are attempted on IPv6-only hosts.
        if addrs:
            for af, socktype, proto, _cn, sa in addrs:
                try:
                    sock = socket.socket(af, socktype, proto)
                    sock.settimeout(10)
                    sock.connect(sa)
                    sock.close()
                    self.logger.info(f"Preflight TCP OK: {host}:443 reachable via {sa[0]}")
                    python_ok = True
                    break
                except OSError as e:
                    self.logger.warning(f"Preflight TCP: {sa[0]}:{sa[1]} failed: {e}")
            if not python_ok:
                self.logger.error(
                    f"Preflight TCP FAILED: {host}:443 unreachable from Python "
                    f"(all addresses tried). May be an IPv6-only host without NAT64."
                )

        # Step 3: Python HTTP (only if TCP worked — otherwise skip to Chrome)
        if python_ok:
            try:
                req = urllib.request.Request(url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0')
                resp = urllib.request.urlopen(req, timeout=15)
                self.logger.info(f"Preflight HTTP OK: {url} returned HTTP {resp.status}")
            except Exception as e:
                self.logger.warning(f"Preflight HTTP FAILED: {url}: {e}")
                python_ok = False

        # Step 4: Chrome connectivity test (authoritative).
        # Only run when Python TCP failed — on IPv6-only hosts (e.g. Streamlit Cloud)
        # Python sockets can't reach IPv4 sites but Chrome can via NAT64.
        # When Python already confirmed reachability, skip this — the JS fetch()
        # to anyror.gujarat.gov.in always hangs in headless Chrome (the site stalls
        # HEAD requests from automated browsers), wasting 120s and risking session
        # corruption when the script timeout fires.
        if python_ok:
            self.logger.info("Preflight: Python confirmed reachability, skipping Chrome test")
            return True

        try:
            script = """
            var done = arguments[0];
            fetch(arguments[1], {method: 'HEAD', mode: 'no-cors', cache: 'no-store'})
                .then(function() { done({ok: true, error: null}); })
                .catch(function(e) { done({ok: false, error: e.toString()}); });
            """
            # Use a short timeout so a hung fetch() aborts cleanly without
            # blocking ChromeDriver's HTTP server for 120s (which corrupts the session).
            self.driver.set_script_timeout(10)
            try:
                result = self.driver.execute_async_script(script, url)
            finally:
                self.driver.set_script_timeout(120)
            if result and result.get('ok'):
                self.logger.info("Preflight Chrome OK: fetch() reached the site")
                return True
            else:
                err = result.get('error') if result else 'no result'
                self.logger.error(f"Preflight Chrome FAILED: fetch() error: {err}")
        except Exception as e:
            self.logger.warning(f"Preflight Chrome test inconclusive: {e}")

        # Fall back to Python result if Chrome test was inconclusive
        return python_ok

    def navigate_to_form(self):
        """Navigate to the AnyRoR form page with retry logic for slow connections."""
        self.logger.info(f"Navigating to AnyRoR website: {CONFIG['URL']}")

        # Diagnostic: check if the site is reachable outside Chrome
        site_reachable = self._preflight_check()
        if not site_reachable:
            self.logger.error(
                "AnyRoR site is unreachable via both Python and Chrome. "
                "Likely cause: IPv6-only host without NAT64, or site blocking cloud IPs."
            )

        max_nav_retries = 3
        for attempt in range(max_nav_retries):
            try:
                if attempt > 0:
                    self.logger.warning(f"Retry attempt {attempt+1}/{max_nav_retries}")
                    # On retry, do a fresh driver.get() instead of JS navigation
                    # JS navigation doesn't trigger a full page reload and can leave
                    # the page in a broken state if the previous load timed out
                    self.driver.delete_all_cookies()

                try:
                    self.driver.get(CONFIG['URL'])
                except TimeoutException:
                    # page_load_timeout fired - the page is still loading but we
                    # can check what we have so far (eager strategy may have given
                    # us a partial DOM)
                    self.logger.warning(
                        f"Page load timed out on attempt {attempt+1}, "
                        f"checking if DOM is usable anyway"
                    )

                # Wait for initial load
                time.sleep(3)

                # Check if we need to navigate to the correct page
                current_url = self.driver.current_url
                if 'LandRecordRural.aspx' not in current_url:
                    self.logger.warning(f"Not on land record page (URL: {current_url}), trying alternative navigation")

                    try:
                        land_record_link = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Land Record')]")
                        land_record_link.click()
                        time.sleep(2)
                    except Exception as e:
                        self.logger.warning(f"Could not find land record link: {str(e)}")

                # Wait for the page to load and verify we're on the correct page
                # Use a shorter per-attempt timeout (30s) so retries happen faster
                per_attempt_wait = WebDriverWait(self.driver, 30)
                try:
                    per_attempt_wait.until(
                        EC.presence_of_element_located((By.ID, CONFIG['LAND_RECORD_TYPE_ID']))
                    )

                    self.logger.info(f"Page loaded: URL={self.driver.current_url}, title={self.driver.title}")

                    dropdown = self.driver.find_element(By.ID, CONFIG['LAND_RECORD_TYPE_ID'])
                    if not dropdown.is_displayed():
                        self.logger.warning("Land record dropdown is present but not visible")

                    select = Select(dropdown)
                    options = [f"{o.get_attribute('value')}: {o.text}" for o in select.options]
                    self.logger.debug(f"Available options in land record dropdown: {options}")

                    self.logger.info("Successfully navigated to the land record form page")
                    return

                except Exception as e:
                    self._log_page_diagnostics(f"attempt {attempt+1}")
                    self.logger.error(f"Error waiting for land record form (attempt {attempt+1}): {str(e)}")
                    if attempt == max_nav_retries - 1:
                        raise

            except Exception as e:
                if attempt == max_nav_retries - 1:
                    self._log_page_diagnostics("final failure")
                    self.logger.error(f"Navigation attempt {attempt+1} failed: {str(e)}")
                    raise
                self.logger.error(f"Navigation attempt {attempt+1} failed: {str(e)}")
                time.sleep(2 ** attempt)  # Exponential backoff
    
    def select_land_record_type(self):
        """Select the land record type."""
        self.logger.debug("Selecting Land Record Type")
        
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
                    self.logger.debug("Successfully selected land record type using JavaScript")
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
                    self.logger.debug("Successfully selected land record type using Selenium Select")
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
                        self.logger.debug("Successfully selected land record type using click and JavaScript")
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
            
            self.logger.debug("Land record type selection verified successfully")
            
        except Exception as e:
            self.logger.error(f"Error selecting land record type: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise
    
    @lru_cache(maxsize=64)
    def _get_dropdown_options(self, dropdown_id):
        """
        Get options from a dropdown.
        
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
        """
        Select an option from a dropdown.
        
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
                    time.sleep(0.5)
                
                return True
        
        return False
    
    def select_district(self, district_name):
        """
        Select a district from the dropdown.
        
        Args:
            district_name: The name of the district to select.
            
        Returns:
            True if the district was found and selected, False otherwise.
        """
        self.logger.debug(f"Selecting District: {district_name}")
        
        # Wait for the dropdown to be clickable and handle stale elements
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Wait for the dropdown to be clickable
                dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, CONFIG['DISTRICT_DROPDOWN_ID']))
                )
                
                # Wait for dropdown to be populated with options (more than just the default "Select" option)
                try:
                    def dropdown_has_options(driver):
                        element = driver.find_element(By.ID, CONFIG['DISTRICT_DROPDOWN_ID'])
                        s = Select(element)
                        return len(s.options) > 1

                    WebDriverWait(self.driver, 10).until(dropdown_has_options)
                except TimeoutException:
                    self.logger.warning("District dropdown options did not populate in time")

                # Create Select object
                select_district = Select(dropdown)
                
                # Log options for debugging if needed
                if attempt == max_attempts - 1:
                    options_text = [o.text for o in select_district.options[:5]] # Log first 5 options
                    self.logger.debug(f"Available district options: {options_text}...")

                # Try to find the district in the options
                found_district = False
                for option in select_district.options:
                    if district_name in option.text:
                        select_district.select_by_visible_text(option.text)
                        found_district = True
                        self.logger.debug(f"Successfully selected district: {option.text}")
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
                    time.sleep(0.5)
                    
                return True
                
            except StaleElementReferenceException:
                self.logger.warning(f"Stale element encountered on attempt {attempt + 1}, retrying...")
                if attempt == max_attempts - 1:
                    self.logger.error("Failed to select district after all attempts due to stale elements")
                    return False
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Error selecting district on attempt {attempt + 1}: {str(e)}")
                if attempt == max_attempts - 1:
                    return False
                time.sleep(1)
        
        return False
    
    def select_taluka(self, taluka_name):
        """
        Select a taluka from the dropdown.
        
        Args:
            taluka_name: The name of the taluka to select.
            
        Returns:
            True if the taluka was found and selected, False otherwise.
        """
        self.logger.debug(f"Selecting Taluka: {taluka_name}")
        
        # Wait for dropdown to be populated with options
        try:
            def dropdown_has_options(driver):
                try:
                    element = driver.find_element(By.ID, CONFIG['TALUKA_DROPDOWN_ID'])
                    s = Select(element)
                    return len(s.options) > 1
                except (StaleElementReferenceException, Exception):
                    return False

            WebDriverWait(self.driver, 10).until(dropdown_has_options)
        except TimeoutException:
            self.logger.warning("Taluka dropdown options did not populate in time")

        result = self.select_dropdown_option(CONFIG['TALUKA_DROPDOWN_ID'], taluka_name, partial_match=True)
        if result:
            self.logger.debug("Taluka selected successfully")
        else:
            self.logger.error(f"Taluka '{taluka_name}' not found in dropdown")
        return result
    
    def select_village(self, village_name):
        """
        Select a village from the dropdown.
        
        Args:
            village_name: The name of the village to select.
            
        Returns:
            True if the village was found and selected, False otherwise.
        """
        self.logger.debug(f"Selecting Village: {village_name}")
        
        # First try exact/partial match
        result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], village_name, partial_match=True)
        
        if not result:
            # If failed, try some common village name variations and debug
            self.logger.warning(f"Initial village selection failed for: {village_name}")
            
            # Wait for dropdown to be populated with options (more than just the default "Select" option)
            # This is critical because the dropdown might still be loading after Taluka selection
            try:
                def dropdown_has_options(driver):
                    try:
                        element = driver.find_element(By.ID, CONFIG['VILLAGE_DROPDOWN_ID'])
                        s = Select(element)
                        # Log options count for debugging
                        options_count = len(s.options)
                        if options_count <= 1:
                            return False
                        return True
                    except (StaleElementReferenceException, Exception):
                        return False

                # Wait specifically for options to populate
                WebDriverWait(self.driver, 10).until(dropdown_has_options)
                
                # Retry selection after waiting
                self.logger.debug("Village dropdown options populated, retrying selection...")
                result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], village_name, partial_match=True)
                if result:
                    self.logger.info(f"Successfully selected village after waiting for options: {village_name}")
                    return True
            except TimeoutException:
                self.logger.warning("Village dropdown options did not populate in time or only contained default option")

            # Enhanced village matching using the VillageNameMatcher
            try:
                # Optimized way to get all options using JavaScript
                # accessing select.options one by one is very slow and can cause timeouts
                available_options = self.driver.execute_script("""
                    var select = document.getElementById(arguments[0]);
                    var options = [];
                    for (var i = 0; i < select.options.length; i++) {
                        var text = select.options[i].text;
                        if (text && text.trim().length > 0) {
                            options.push(text.trim());
                        }
                    }
                    return options;
                """, CONFIG['VILLAGE_DROPDOWN_ID'])
                
                self.logger.debug(f"Available village options (first 10): {available_options[:10]}")
                
                # Use enhanced village matcher
                matcher = VillageNameMatcher(self.logger)
                best_match = matcher.find_best_match(village_name, available_options)
                
                if best_match:
                    self.logger.debug(f"VillageNameMatcher found best match: '{best_match}' for '{village_name}'")
                    result = self.select_dropdown_option(CONFIG['VILLAGE_DROPDOWN_ID'], best_match, partial_match=False)
                    if result:
                        self.logger.debug(f"Successfully selected matched village: {best_match}")
                else:
                    # Generate detailed matching report for debugging
                    report = matcher.get_match_strategies_report(village_name, available_options)
                    self.logger.warning(f"VillageNameMatcher could not find suitable match:\n{report}")
                
            except Exception as e:
                self.logger.warning(f"Error during enhanced village matching: {e}")
        
        if result:
            self.logger.debug("Village selected successfully")
        else:
            self.logger.error(f"Village '{village_name}' not found in dropdown")
        
        return result
    
    def select_survey(self, survey_block_number):
        """
        Select a survey/block number from the dropdown.
        
        Args:
            survey_block_number: The survey/block number to select.
            
        Returns:
            True if the survey/block number was found and selected, False otherwise.
        """
        # Convert survey_block_number to string to fix issues with integer survey numbers
        survey_block_number = str(survey_block_number).strip()
        
        self.logger.debug(f"Selecting Survey/Block Number: {survey_block_number}")
        
        # Wait for dropdown to be populated with options (replacing fixed sleep)
        try:
            def dropdown_has_options(driver):
                try:
                    element = driver.find_element(By.ID, CONFIG['SURVEY_DROPDOWN_ID'])
                    s = Select(element)
                    return len(s.options) > 1
                except (StaleElementReferenceException, Exception):
                    return False

            # Use a slightly longer timeout for survey numbers as there can be many
            WebDriverWait(self.driver, 15).until(dropdown_has_options)
        except TimeoutException:
            self.logger.warning("Survey dropdown options did not populate in time")
            
        # Build a list of candidate strings to try, including paiki variants.
        # Gujarat AnyRoR may display "569/p1" as "569/1", "569 પૈકી 1", "569 paiki 1",
        # "569pk1", or with Gujarati digits. Picking the wrong/first option silently
        # has caused the wrong parcel (e.g. Gauchar wasteland) to be scraped, so we
        # try several normalised forms and fail loudly if none match.
        candidates = self._build_survey_candidates(survey_block_number)

        try:
            for candidate in candidates:
                if self.select_dropdown_option(
                    CONFIG['SURVEY_DROPDOWN_ID'], candidate, partial_match=True
                ):
                    self.logger.debug(
                        f"Survey/Block Number selected successfully via candidate: {candidate}"
                    )
                    return True

            # No candidate matched. Log the available options to aid debugging
            # and return False rather than silently selecting the first option,
            # which previously caused the wrong parcel to be scraped.
            try:
                dropdown = self.driver.find_element(By.ID, CONFIG['SURVEY_DROPDOWN_ID'])
                available = [o.text.strip() for o in Select(dropdown).options]
            except Exception:
                available = []
            self.logger.error(
                f"Survey/Block Number '{survey_block_number}' not found. "
                f"Tried candidates: {candidates}. Available options: {available}"
            )
            return False
        except Exception as e:
            self.logger.error(f"Error selecting survey number: {str(e)}")
            return False

    def _build_survey_candidates(self, survey_block_number):
        """Generate candidate strings for matching a survey number in the dropdown.

        AnyRoR dropdowns mix Latin and Gujarati digits. A plain subdivision like
        "38/3" is rendered as "38/૩"; paiki entries like "569/p1" render as
        "569/p૧". The digit 5 is sometimes shown as the letter "પ" instead of
        the digit "૫" (an AnyRoR quirk), so both are tried.

        Examples:
            "569/p1" → ["569/p1", "569/p૧", "૫૬૯/p૧", "569/1", ...]
            "38/3"   → ["38/3", "38/૩", "૩૮/૩"]
            "568"    → ["568", "૫૬૮"]
        """
        import re

        s = str(survey_block_number).strip()
        candidates = [s]

        gujarati_digits = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
        # AnyRoR sometimes renders the digit 5 as the letter પ rather than ૫
        gujarati_digits_pa = str.maketrans("0123456789", "૦૧૨૩૪પ૬૭૮૯")

        def add(v):
            if v and v not in candidates:
                candidates.append(v)

        # Always try full Gujarati-digit translations of the raw input
        add(s.translate(gujarati_digits))
        add(s.translate(gujarati_digits_pa))

        # Plain subdivision form: "38/3" → also try "38/૩"
        m_plain = re.match(r"^(\d+)\s*/\s*(\d+)$", s)
        if m_plain:
            base, part = m_plain.group(1), m_plain.group(2)
            part_g = part.translate(gujarati_digits)
            part_g_pa = part.translate(gujarati_digits_pa)
            base_g = base.translate(gujarati_digits)
            add(f"{base}/{part_g}")
            add(f"{base}/{part_g_pa}")
            add(f"{base_g}/{part_g}")
            add(f"{base_g}/{part_g_pa}")

        # Paiki forms: "569/p1", "569/P2", "569p1", "569pk1"
        m = re.match(r"^(\d+)\s*/?\s*p(?:k)?\s*(\d+)$", s, re.IGNORECASE)
        if m:
            base, part = m.group(1), m.group(2)
            base_g = base.translate(gujarati_digits)
            part_g = part.translate(gujarati_digits)
            part_g_pa = part.translate(gujarati_digits_pa)
            variants = [
                # AnyRoR commonly uses Latin "p" + Gujarati digit, e.g. "569/p૧"
                f"{base}/p{part_g}",
                f"{base}/p{part_g_pa}",
                f"{base_g}/p{part_g}",
                f"{base}/{part_g}",
                f"{base}/{part}",
                f"{base} પૈકી {part}",
                f"{base} પેકી {part}",
                f"{base} paiki {part}",
                f"{base} Paiki {part}",
                f"{base}pk{part}",
                f"{base}/p{part}",
                f"{base}/P{part}",
                f"{base}{part}",
                f"{base_g} પૈકી {part_g}",
            ]
            for v in variants:
                add(v)

        return candidates
    
    def solve_captcha(self):
        """
        Solve the CAPTCHA.
        
        Returns:
            The recognized CAPTCHA text or None if recognition failed.
        """
        self.logger.debug("Starting captcha recognition process")
        
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
                self.logger.debug(f"Found CAPTCHA image with ID: {captcha_id}")
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
                        self.logger.debug(f"Found CAPTCHA image with selector: {selector}")
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
                                self.logger.debug(f"Found CAPTCHA image with src: {src}")
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
                    self.logger.debug(f"Entered captcha value: {captcha_value}")
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
        """
        Submit the form and handle any alerts.
        
        Returns:
            A tuple (success, error_message) where success is True if the form was submitted
            successfully, and error_message is None or the error message if submission failed.
        """
        self.logger.debug("Submitting the form")
        try:
            submit_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, CONFIG['SUBMIT_BUTTON_ID']))
            )
            self.logger.debug("Found submit button, clicking...")
            
            # Use JavaScript click to avoid "Read timed out" error if the page load is slow/blocking
            # "Read timed out" often happens with standard .click() if the browser blocks waiting for response
            try:
                self.driver.execute_script("arguments[0].click();", submit_button)
                self.logger.debug("Submit button clicked successfully via JavaScript")
            except Exception as js_e:
                self.logger.warning(f"JS click failed, falling back to standard click: {js_e}")
                submit_button.click()
                self.logger.debug("Submit button clicked successfully via standard click")
                
            # Wait a bit for any immediate reactions (like alerts or page reload init)
            time.sleep(2)
            
        except Exception as e:
            self.logger.error(f"Error clicking submit button: {str(e)}")
            return False, f"Submit button error: {str(e)}"
        
        # Check for alert (captcha error)
        try:
            self.logger.debug("Checking for alerts...")
            WebDriverWait(self.driver, CONFIG['CAPTCHA_WAIT_TIMEOUT']).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            self.logger.warning(f"Alert present: {alert_text}")
            alert.accept()
            
            return False, alert_text
        except TimeoutException:
            # No alert means success (likely)
            self.logger.debug("Form submitted successfully - no alerts found")
            
            # Log current state
            try:
                current_url = self.driver.current_url
                self.logger.debug(f"Current URL after submission: {current_url}")
                
                # Check for "invalid input" error messages on page usually shown in labels
                # Example: ContentPlaceHolder1_lblMsg
                try:
                    error_lbl = self.driver.find_element(By.ID, "ContentPlaceHolder1_lblMsg")
                    if error_lbl.is_displayed() and error_lbl.text.strip():
                        self.logger.warning(f"Error message on page: {error_lbl.text}")
                        # Sometimes it's not a hard failure, but worth noting
                except:
                    pass
                
                page_title = self.driver.title
                self.logger.debug(f"Page title after submission: {page_title}")
                
                # Check if page is still responsive
                ready_state = self.driver.execute_script("return document.readyState")
                self.logger.debug(f"Page ready state: {ready_state}")
                
            except Exception as e:
                self.logger.error(f"Error checking page state after submission: {str(e)}")
            
            return True, None
    
    def generate_pdf(self, output_path):
        """
        Generate a PDF of the land record.
        
        Args:
            output_path: The path where the PDF will be saved.
            
        Returns:
            A tuple (success, error_message) where success is True if the PDF was generated
            successfully, and error_message is None or the error message if generation failed.
        """
        self.logger.debug("Attempting to generate PDF")
        
        # Create output directory if it doesn't exist
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            self.logger.debug(f"Output directory created/verified: {os.path.dirname(output_path)}")
        except Exception as e:
            self.logger.error(f"Error creating output directory: {str(e)}")
            return False, f"Directory creation error: {str(e)}"
        
        try:
            # Log current state before PDF generation
            self.logger.debug("Checking page state before PDF generation...")
            try:
                current_url = self.driver.current_url
                self.logger.debug(f"Current URL before PDF generation: {current_url}")
                
                page_title = self.driver.title
                self.logger.debug(f"Page title before PDF generation: {page_title}")
                
                ready_state = self.driver.execute_script("return document.readyState")
                self.logger.debug(f"Page ready state before PDF generation: {ready_state}")
                
            except Exception as e:
                self.logger.error(f"Error checking page state before PDF generation: {str(e)}")
            
            # Wait for the page to load completely
            self.logger.debug(f"Waiting {CONFIG['PAGE_LOAD_WAIT']} seconds for page to load...")
            time.sleep(CONFIG['PAGE_LOAD_WAIT'])
            
            # Check if driver is still responsive
            self.logger.debug("Testing driver responsiveness...")
            try:
                test_result = self.driver.execute_script("return 'Driver is responsive'")
                self.logger.debug(f"Driver test result: {test_result}")
            except Exception as e:
                self.logger.error(f"Driver not responsive: {str(e)}")
                return False, f"Driver not responsive: {str(e)}"
            
            # Generate PDF
            self.logger.debug("Executing PDF generation command...")
            try:
                result = self.driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
                self.logger.debug("PDF generation command executed successfully")
                
                pdf_data = result.get("data")
                if pdf_data:
                    self.logger.debug(f"PDF data received, length: {len(pdf_data)} characters")
                    
                    # Save PDF
                    self.logger.debug(f"Saving PDF to: {output_path}")
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(pdf_data))
                    
                    # Verify file was created
                    if os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        self.logger.debug(f"PDF saved successfully to: {output_path} (size: {file_size} bytes)")
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
