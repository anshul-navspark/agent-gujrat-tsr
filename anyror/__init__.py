"""
AnyRoR - Gujarat Land Record Automation

Modular package for automating land record retrieval from Gujarat's AnyRoR portal.
"""

from .webdriver_manager import WebDriverManager
from .captcha_solver import CaptchaSolver
from .form_filler import FormFiller
from .scraper import AnyRoRScraper
from .config import CONFIG

__all__ = ['WebDriverManager', 'CaptchaSolver', 'FormFiller', 'AnyRoRScraper', 'CONFIG']
__version__ = '2.0.0'
