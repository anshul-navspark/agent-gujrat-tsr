
"""
FastAPI Dependencies.
"""
from fastapi import Depends
import logging
from typing import Generator

from services.file_service import FileService, get_file_service
from services.translation_service import TranslationService, get_translation_service
from services.scraping_service import ScrapingService, get_scraping_service

logger = logging.getLogger(__name__)

def get_file_service_dependency() -> FileService:
    """Dependency for FileService."""
    return get_file_service(logger=logger)

def get_translation_service_dependency() -> TranslationService:
    """Dependency for TranslationService."""
    return get_translation_service(logger=logger)

def get_scraping_service_dependency() -> Generator[ScrapingService, None, None]:
    """Dependency for ScrapingService.
    
    Yields a scraping service instance and ensures cleanup.
    """
    service = get_scraping_service(headless=True, logger=logger)
    try:
        yield service
    finally:
        service.close()
