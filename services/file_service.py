"""
File operation service for Gujarat TSR Agent.

This service consolidates all file-related operations including ZIP creation,
filename generation, and temporary file management.
"""

import os
import io
import zipfile
import tempfile
import logging
from typing import Dict, Optional
from pathlib import Path

from core.interfaces import IFileService
from core.models import LandRecordRequest
from core.exceptions import FileOperationException
from utils.survey_utils import sanitize_filename


class FileService(IFileService):
    """Implementation of file operation service."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize file service.
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def create_zip(
        self,
        files: Dict[str, bytes],
        zip_name: Optional[str] = None
    ) -> bytes:
        """
        Create a ZIP file from multiple files.
        
        Args:
            files: Dictionary mapping filenames to file contents
            zip_name: Optional name for the ZIP file (not used in memory creation)
            
        Returns:
            ZIP file content as bytes
            
        Raises:
            FileOperationException: If ZIP creation fails
        """
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename, content in files.items():
                    zf.writestr(filename, content)
            
            zip_data = zip_buffer.getvalue()
            self.logger.debug(f"Created ZIP with {len(files)} files, size: {len(zip_data)} bytes")
            return zip_data
            
        except Exception as e:
            self.logger.error(f"Failed to create ZIP: {e}")
            raise FileOperationException(
                operation='create_zip',
                message=f"Failed to create ZIP file: {str(e)}"
            )
    
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
        try:
            # Sanitize each component
            district_safe = sanitize_filename(request.district)
            taluka_safe = sanitize_filename(request.taluka)
            village_safe = sanitize_filename(request.village)
            survey_safe = sanitize_filename(request.survey_number)
            
            # Build filename
            filename = f"{prefix}_{district_safe}_{taluka_safe}_{village_safe}_{survey_safe}.{file_type}"
            
            # Additional cleanup: replace spaces and slashes
            filename = filename.replace(" ", "_").replace("/", "_")
            
            self.logger.debug(f"Generated filename: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Failed to generate filename: {e}")
            # Fallback to a generic name
            return f"{prefix}_document.{file_type}"
    
    def save_temp_file(self, content: bytes, filename: str) -> str:
        """
        Save content to a temporary file.
        
        Args:
            content: File content
            filename: Desired filename
            
        Returns:
            Path to saved file
            
        Raises:
            FileOperationException: If save fails
        """
        try:
            temp_dir = tempfile.gettempdir()
            filepath = os.path.join(temp_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(content)
            
            self.logger.debug(f"Saved temporary file: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to save temporary file: {e}")
            raise FileOperationException(
                operation='save',
                path=filename,
                message=f"Failed to save temporary file: {str(e)}"
            )
    
    def cleanup_temp_file(self, path: str) -> None:
        """
        Clean up a temporary file.
        
        Args:
            path: Path to file to delete
        """
        try:
            if os.path.exists(path):
                os.remove(path)
                self.logger.debug(f"Cleaned up temporary file: {path}")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup file {path}: {e}")
            # Don't raise exception for cleanup failures


# Global instance
_file_service: Optional[FileService] = None


def get_file_service(logger: Optional[logging.Logger] = None) -> FileService:
    """
    Get or create the global file service instance.
    
    Args:
        logger: Optional logger instance
        
    Returns:
        FileService instance
    """
    global _file_service
    if _file_service is None:
        _file_service = FileService(logger=logger)
    return _file_service
