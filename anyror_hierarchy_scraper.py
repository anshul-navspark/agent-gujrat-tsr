"""
Utility to scrape the AnyRoR dropdown hierarchy (district → taluka → village)
and build a nested dictionary with Gujarati names, their possible English
variants, and child relationships.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)

from anyror_refactored import CONFIG, Logger, WebDriverManager

# ---------------------------------------------------------------------------
# Transliteration helpers
# ---------------------------------------------------------------------------

GUJARATI_TO_LATIN = {
    "અ": "a",
    "આ": "aa",
    "ઇ": "i",
    "ઈ": "ee",
    "ઉ": "u",
    "ઊ": "oo",
    "ઋ": "ri",
    "એ": "e",
    "ઐ": "ai",
    "ઓ": "o",
    "ઔ": "au",
    "ા": "a",
    "િ": "i",
    "ી": "ee",
    "ુ": "u",
    "ૂ": "oo",
    "ે": "e",
    "ૈ": "ai",
    "ો": "o",
    "ૌ": "au",
    "ક": "k",
    "ખ": "kh",
    "ગ": "g",
    "ઘ": "gh",
    "ઙ": "n",
    "ચ": "ch",
    "છ": "chh",
    "જ": "j",
    "ઝ": "jh",
    "ઞ": "n",
    "ટ": "t",
    "ઠ": "th",
    "ડ": "d",
    "ઢ": "dh",
    "ણ": "n",
    "ત": "t",
    "થ": "th",
    "દ": "d",
    "ધ": "dh",
    "ન": "n",
    "પ": "p",
    "ફ": "ph",
    "બ": "b",
    "ભ": "bh",
    "મ": "m",
    "ય": "y",
    "ર": "r",
    "લ": "l",
    "વ": "v",
    "શ": "sh",
    "ષ": "sh",
    "સ": "s",
    "હ": "h",
    "ળ": "l",
    "ક્ષ": "ksh",
    "જ્ઞ": "gy",
    "ઁ": "n",
    "ં": "n",
    "ઃ": "h",
    "઼": "",
}

GUJARATI_DIGITS = {
    "૦": "0",
    "૧": "1",
    "૨": "2",
    "૩": "3",
    "૪": "4",
    "૫": "5",
    "૬": "6",
    "૭": "7",
    "૮": "8",
    "૯": "9",
}

MANUAL_NAME_OVERRIDES: Dict[str, List[str]] = {
    "પાટણ": ["Patan"],
    "કચ્છ": ["Kutch", "Kachchh", "Kutchh"],
    "ભુજ": ["Bhuj"],
    "બનાસકાંઠા": ["Banaskantha"],
    "ભાવનગર": ["Bhavnagar"],
    "જામનગર": ["Jamnagar"],
    "અનાવાડા - 091": ["Anavada", "Anawada"],
    "ત્રંબો - 033": ["Trambo", "Trambau"],
    "હોથીજી ખડબા - 034": ["Hothiji Khadba", "Hothiji Khadaba"],
    "અબડાસા": ["Abdasa"],
    "અંજાર": ["Anjar"],
}


def transliterate_gujarati(text: str) -> str:
    """Best-effort ASCII transliteration."""
    if not text:
        return ""

    result = []
    idx = 0
    while idx < len(text):
        # Handle multi-character ligatures first
        if text[idx : idx + 2] in ("ક્ષ", "જ્ઞ"):
            result.append(GUJARATI_TO_LATIN[text[idx : idx + 2]])
            idx += 2
            continue

        char = text[idx]

        if char in GUJARATI_DIGITS:
            result.append(GUJARATI_DIGITS[char])
        elif char in GUJARATI_TO_LATIN:
            result.append(GUJARATI_TO_LATIN[char])
        elif char.isascii():
            result.append(char)
        elif char in "-/()&,":
            result.append(char)
        else:
            result.append(" ")

        idx += 1

    transliterated = "".join(result)
    transliterated = re.sub(r"\s+", " ", transliterated)
    return transliterated.strip().title()


def generate_possible_english_names(source: str) -> List[str]:
    candidates: List[str] = []

    if source in MANUAL_NAME_OVERRIDES:
        candidates.extend(MANUAL_NAME_OVERRIDES[source])

    transliterated = transliterate_gujarati(source)
    if transliterated:
        candidates.append(transliterated)
        without_codes = re.sub(r"\s*-\s*\d+\s*$", "", transliterated).strip()
        if without_codes and without_codes != transliterated:
            candidates.append(without_codes)

        ascii_only = re.sub(r"[^A-Za-z0-9\s/-]", "", transliterated).strip()
        if ascii_only and ascii_only not in candidates:
            candidates.append(ascii_only)

    # Remove empty entries and deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for cand in candidates:
        normalized = cand.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            unique_candidates.append(normalized)

    return unique_candidates or [source]


# ---------------------------------------------------------------------------
# Scraper implementation
# ---------------------------------------------------------------------------

@dataclass
class DropdownOption:
    text: str
    value: str


class AnyRoRHierarchyScraper:
    def __init__(
        self,
        headless: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or Logger.setup()
        self.headless = headless
        self.web_driver_manager = WebDriverManager()
        self.driver = None
        self.wait: Optional[WebDriverWait] = None

    def __enter__(self) -> "AnyRoRHierarchyScraper":
        self.driver = self.web_driver_manager.initialize_webdriver(
            headless=self.headless,
            timeout=CONFIG.get("WAIT_TIMEOUT", 20),
        )
        self.driver.set_page_load_timeout(120)
        self.wait = WebDriverWait(self.driver, CONFIG.get("WAIT_TIMEOUT", 20))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.web_driver_manager.close()
        return False

    # ---- navigation helpers ------------------------------------------------
    def open_form(self):
        assert self.driver and self.wait
        self.logger.info("Opening AnyRoR rural land record page...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.driver.get(CONFIG["URL"])
                self.wait.until(
                    EC.presence_of_element_located((By.ID, CONFIG["LAND_RECORD_TYPE_ID"]))
                )
                break
            except (TimeoutException, Exception) as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Page load attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(2)
                else:
                    self.logger.error(f"Failed to load page after {max_retries} attempts")
                    raise
        
        self.logger.info("Selecting land record type...")
        self._select_option_by_value(
            CONFIG["LAND_RECORD_TYPE_ID"], CONFIG["LAND_RECORD_TYPE_VALUE"]
        )
        self._wait_for_settle()

    def _wait_for_settle(self):
        assert self.driver
        time.sleep(CONFIG.get("DROPDOWN_WAIT_TIMEOUT", 3))
        try:
            self.wait.until(
                lambda drv: drv.execute_script(
                    'return (typeof jQuery === "undefined") || (jQuery.active === 0);'
                )
            )
        except Exception:
            pass

    def _select_option_by_value(self, dropdown_id: str, value: str):
        assert self.wait
        for attempt in range(3):
            try:
                element = self.wait.until(
                    EC.element_to_be_clickable((By.ID, dropdown_id))
                )
                select = Select(element)
                select.select_by_value(value)
                return
            except (StaleElementReferenceException, NoSuchElementException):
                time.sleep(0.5)
        raise RuntimeError(f"Could not select value {value} in {dropdown_id}")

    def _select_option_by_text(self, dropdown_id: str, text: str):
        assert self.wait
        for attempt in range(3):
            try:
                element = self.wait.until(
                    EC.element_to_be_clickable((By.ID, dropdown_id))
                )
                select = Select(element)
                select.select_by_visible_text(text)
                return
            except (StaleElementReferenceException, NoSuchElementException):
                time.sleep(0.5)
        raise RuntimeError(f"Could not select text '{text}' in {dropdown_id}")

    def _get_dropdown_options(self, dropdown_id: str) -> List[DropdownOption]:
        assert self.wait
        element = self.wait.until(
            EC.presence_of_element_located((By.ID, dropdown_id))
        )
        select = Select(element)
        options: List[DropdownOption] = []
        for option in select.options:
            text = option.text.strip()
            value = (option.get_attribute("value") or "").strip()
            if not text or not value or value in {"0", "-1"}:
                continue
            options.append(DropdownOption(text=text, value=value))
        return options

    # ---- scraping ----------------------------------------------------------
    def scrape(
        self,
        district_limit: Optional[int] = None,
        taluka_limit: Optional[int] = None,
    ) -> Dict[str, Dict[str, object]]:
        self.open_form()
        hierarchy: Dict[str, Dict[str, object]] = {}

        district_options = self._get_dropdown_options(CONFIG["DISTRICT_DROPDOWN_ID"])
        self.logger.info("Found %d districts", len(district_options))

        for idx, district in enumerate(district_options):
            if district_limit and idx >= district_limit:
                break

            self.logger.info("Processing district %s (%d/%d)", district.text, idx + 1, len(district_options))
            self._select_option_by_text(CONFIG["DISTRICT_DROPDOWN_ID"], district.text)
            self._wait_for_settle()

            talukas = self._scrape_talukas(taluka_limit)
            hierarchy[district.text] = {
                "english_names": generate_possible_english_names(district.text),
                "talukas": talukas,
            }

        return hierarchy

    def _scrape_talukas(
        self,
        taluka_limit: Optional[int] = None,
    ) -> Dict[str, Dict[str, object]]:
        taluka_options = self._get_dropdown_options(CONFIG["TALUKA_DROPDOWN_ID"])
        taluka_map: Dict[str, Dict[str, object]] = {}
        self.logger.info("  Found %d talukas", len(taluka_options))

        for idx, taluka in enumerate(taluka_options):
            if taluka_limit and idx >= taluka_limit:
                break

            self.logger.info("  Taluka %s (%d/%d)", taluka.text, idx + 1, len(taluka_options))
            self._select_option_by_text(CONFIG["TALUKA_DROPDOWN_ID"], taluka.text)
            self._wait_for_settle()

            villages = self._scrape_villages()
            taluka_map[taluka.text] = {
                "english_names": generate_possible_english_names(taluka.text),
                "villages": villages,
            }

        return taluka_map

    def _scrape_villages(self) -> Dict[str, List[str]]:
        try:
            village_options = self._get_dropdown_options(CONFIG["VILLAGE_DROPDOWN_ID"])
        except TimeoutException:
            self.logger.warning("    Village dropdown did not populate in time")
            return {}

        villages = {}
        self.logger.info("    Found %d villages", len(village_options))
        for village in village_options:
            villages[village.text] = generate_possible_english_names(village.text)
        return villages


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape AnyRoR dropdown hierarchy into a JSON dictionary.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="anyror_hierarchy.json",
        help="Path to save the hierarchy JSON (UTF-8, default: anyror_hierarchy.json)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (default: False)",
    )
    parser.add_argument(
        "--district-limit",
        type=int,
        default=None,
        help="Optional limit for number of districts to scrape (for testing).",
    )
    parser.add_argument(
        "--taluka-limit",
        type=int,
        default=None,
        help="Optional limit for number of talukas per district (for testing).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None):
    args = parse_args(argv)
    logger = Logger.setup(console_log_level=logging.INFO)

    logger.info("Starting AnyRoR hierarchy scrape...")
    with AnyRoRHierarchyScraper(headless=args.headless, logger=logger) as scraper:
        hierarchy = scraper.scrape(
            district_limit=args.district_limit,
            taluka_limit=args.taluka_limit,
        )

    logger.info("Writing hierarchy to %s", args.output)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(hierarchy, fh, ensure_ascii=False, indent=2)

    logger.info("Done. Total districts captured: %d", len(hierarchy))


if __name__ == "__main__":
    main(sys.argv[1:])

