"""
Core module for Gujarat TSR Agent.

This module contains domain models, interfaces, configuration, and exceptions
that form the foundation of the application architecture.
"""

from .models import (
    LandRecordRequest,
    TSRDocument,
    ProcessingResult,
    APIResponse
)

from .interfaces import (
    ITranslationService,
    IScrapingService,
    ITSRGenerationService,
    IFileService
)

from .config import Config, get_config
from .exceptions import (
    TSRAgentException,
    TranslationException,
    ScrapingException,
    ValidationException,
    FileOperationException
)

__all__ = [
    # Models
    'LandRecordRequest',
    'TSRDocument',
    'ProcessingResult',
    'APIResponse',
    # Interfaces
    'ITranslationService',
    'IScrapingService',
    'ITSRGenerationService',
    'IFileService',
    # Config
    'Config',
    'get_config',
    # Exceptions
    'TSRAgentException',
    'TranslationException',
    'ScrapingException',
    'ValidationException',
    'FileOperationException',
]
