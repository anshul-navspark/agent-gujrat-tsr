#!/usr/bin/env python3
"""Drive the Streamlit single-record form in a VISIBLE Chrome window, so a
screen recorder captures the whole flow: form fill -> Generate -> live scrape
(the scraper's own Chrome pops up) -> success screen.

Targets fields by their unique placeholders (see app/components/single_record_form.py):
    District -> "e.g., Kutch"   Taluka  -> "e.g., Bhuj"
    Village  -> "e.g., Trambo"  Survey  -> "e.g., 32 or 145/1"

Config via env (all optional, defaults are demo-ready):
    DEMO_URL       default http://localhost:8501
    DEMO_DISTRICT  default Kutch
    DEMO_TALUKA    default Lakhpat
    DEMO_VILLAGE   default Baranda
    DEMO_SURVEY    default 220
    DEMO_WAIT      default 300   (max seconds to wait for the TSR result)

Run: python demo/drive_ui.py
Exit code 0 on success (TSR generated), 1 otherwise.
"""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = os.getenv("DEMO_URL", "http://localhost:8501")
FIELDS = [
    ("e.g., Kutch", os.getenv("DEMO_DISTRICT", "Kutch")),
    ("e.g., Bhuj", os.getenv("DEMO_TALUKA", "Lakhpat")),
    ("e.g., Trambo", os.getenv("DEMO_VILLAGE", "Baranda")),
    ("e.g., 32 or 145/1", os.getenv("DEMO_SURVEY", "220")),
]
WAIT = int(os.getenv("DEMO_WAIT", "300"))


def type_slowly(el, text, delay=0.08):
    for ch in text:
        el.send_keys(ch)
        time.sleep(delay)


def main():
    opts = Options()
    opts.add_argument("--window-size=1500,1000")
    opts.add_argument("--window-position=40,40")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 60)
        # Wait for the first field to render (Streamlit boots async).
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[placeholder='e.g., Kutch']")))
        time.sleep(1.5)

        for placeholder, value in FIELDS:
            el = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, f"input[placeholder='{placeholder}']")))
            el.click()
            type_slowly(el, value)
            time.sleep(0.6)

        time.sleep(1.0)
        # Click the primary "Generate TSR" button (Streamlit wraps label in <p>).
        btn = driver.find_element(
            By.XPATH, "//button[.//*[contains(text(), 'Generate TSR')]]")
        btn.click()
        print("Clicked Generate TSR — waiting for the live scrape + extraction...")

        # The scraper's own Chrome window will appear and drive AnyRoR.
        # Wait for the success banner (or error) to show up.
        deadline = time.time() + WAIT
        ok = False
        while time.time() < deadline:
            body = driver.find_element(By.TAG_NAME, "body").text
            if "generated successfully" in body:
                ok = True
                break
            if "Failed:" in body or "⚠️" in body:
                print("UI reported an error:\n" + body[-400:])
                break
            time.sleep(2)

        if ok:
            print("TSR generated — holding the success screen for the camera.")
            time.sleep(6)
            return 0
        print("Did not see success within timeout.")
        return 1
    finally:
        # Keep window briefly so the recording catches the final frame, then close.
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
