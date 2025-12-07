"""
Translation service for Gujarat TSR Agent.

This service provides a clean interface for translation operations,
wrapping the existing JSONTranslationSystem with better error handling
and dependency injection support.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
from typing import Optional

from core.interfaces import ITranslationService
from core.exceptions import TranslationException
from utils.json_translations import JSONTranslationSystem, TranslationNotFoundError



class TranslationService(ITranslationService):
    """Implementation of translation service."""
    
    def __init__(
        self,
        json_path: str = 'anyror_hierarchy.json',
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize translation service.
        
        Args:
            json_path: Path to translation JSON file
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        try:
            self.translator = JSONTranslationSystem(json_path=json_path)
            self.logger.info(f"Translation service initialized with {json_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize translation system: {e}")
            raise TranslationException(
                text='',
                context='initialization',
                message=f"Failed to initialize translation system: {str(e)}"
            )
    
    def translate_to_gujarati(self, text: str, context: str = 'village') -> str:
        """
        Translate English text to Gujarati.
        
        Args:
            text: English text to translate
            context: Context type ('district', 'taluka', 'village')
            
        Returns:
            Gujarati translation
            
        Raises:
            TranslationException: If translation fails
        """
        if not text or not text.strip():
            return text
        
        try:
            result = self.translator.translate(text, context)
            self.logger.debug(f"Translated '{text}' → '{result}' (context: {context})")
            return result
            
        except TranslationNotFoundError as e:
            self.logger.error(f"Translation not found: {e}")
            raise TranslationException(
                text=text,
                context=context,
                message=str(e)
            )
        except Exception as e:
            self.logger.error(f"Translation failed: {e}")
            raise TranslationException(
                text=text,
                context=context,
                message=f"Translation failed: {str(e)}"
            )


# Global instance
_translation_service: Optional[TranslationService] = None


def get_translation_service(
    json_path: str = 'anyror_hierarchy.json',
    logger: Optional[logging.Logger] = None
) -> TranslationService:
    """
    Get or create the global translation service instance.
    
    Args:
        json_path: Path to translation JSON file
        logger: Optional logger instance
        
    Returns:
        TranslationService instance
    """
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService(json_path=json_path, logger=logger)
    return _translation_service
