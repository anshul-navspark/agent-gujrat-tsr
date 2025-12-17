
"""
FastAPI Dependencies.
"""
from fastapi import Depends
import logging
from typing import Generator, Optional

from services.file_service import FileService, get_file_service
from services.translation_service import TranslationService, get_translation_service
from services.scraping_service import ScrapingService, get_scraping_service
from services.cache_service import CacheService, get_cache_service

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

def get_cache_service_dependency() -> Optional[CacheService]:
    """Dependency for CacheService.
    
    Returns None if caching is not configured (GCS_CACHE_BUCKET not set).
    This allows the application to work without caching when not configured.
    """
    return get_cache_service(logger=logger)
