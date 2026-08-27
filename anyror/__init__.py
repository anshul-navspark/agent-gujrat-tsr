"""
AnyRoR - Gujarat Land Record Automation

Modular package for automating land record retrieval from Gujarat's AnyRoR portal.
"""

from .captcha_solver import CaptchaSolver
from .scraper import AnyRoRScraper
from .config import CONFIG

__all__ = ['CaptchaSolver', 'AnyRoRScraper', 'CONFIG']
__version__ = '2.0.0'
