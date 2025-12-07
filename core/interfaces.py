"""
Service interfaces for Gujarat TSR Agent.

This module defines abstract base classes (interfaces) for all services,
enabling dependency injection and loose coupling.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .models import LandRecordRequest, TSRDocument, ProcessingResult


class ITranslationService(ABC):
    """Interface for translation services."""
    
    @abstractmethod
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
        pass


class IScrapingService(ABC):
    """Interface for web scraping services."""
    
    @abstractmethod
    def fetch_land_record(
        self,
        district: str,
        taluka: str,
        village: str,
        survey_number: str,
        output_path: str
    ) -> Dict[str, Any]:
        """
        Fetch land record PDF from AnyRoR portal.
        
        Args:
            district: District name (in Gujarati)
            taluka: Taluka name (in Gujarati)
            village: Village name (in Gujarati)
            survey_number: Survey/block number
            output_path: Path to save the PDF
            
        Returns:
            Dictionary with 'success' status and optional 'error' message
        """
        pass


class ITSRGenerationService(ABC):
    """Interface for TSR generation services."""
    
    @abstractmethod
    def generate_tsr(self, pdf_path: str, output_path: str) -> Dict[str, Any]:
        """
        Generate TSR document from land record PDF.
        
        Args:
            pdf_path: Path to input PDF
            output_path: Path to save generated DOCX
            
        Returns:
            Dictionary with 'success' status and optional 'error' message
        """
        pass


class IFileService(ABC):
    """Interface for file operation services."""
    
    @abstractmethod
    def create_zip(
        self,
        files: Dict[str, bytes],
        zip_name: Optional[str] = None
    ) -> bytes:
        """
        Create a ZIP file from multiple files.
        
        Args:
            files: Dictionary mapping filenames to file contents
            zip_name: Optional name for the ZIP file
            
        Returns:
            ZIP file content as bytes
        """
        pass
    
    @abstractmethod
    def generate_filename(
        self,
        request: LandRecordRequest,
        file_type: str = 'docx',
        prefix: str = 'TSR'
    ) -> str:
        """
        Generate a safe filename for a document.
        
        Args:
            request: Land record request
            file_type: File extension (without dot)
            prefix: Filename prefix
            
        Returns:
            Sanitized filename
        """
        pass
    
    @abstractmethod
    def save_temp_file(self, content: bytes, filename: str) -> str:
        """
        Save content to a temporary file.
        
        Args:
            content: File content
            filename: Desired filename
            
        Returns:
            Path to saved file
        """
        pass
    
    @abstractmethod
    def cleanup_temp_file(self, path: str) -> None:
        """
        Clean up a temporary file.
        
        Args:
            path: Path to file to delete
        """
        pass
