"""
Custom exception hierarchy for Gujarat TSR Agent.

This module defines application-specific exceptions for better error handling
and debugging.
"""


class TSRAgentException(Exception):
    """Base exception for all TSR Agent errors."""
    
    def __init__(self, message: str, details: dict = None):
        """
        Initialize exception.
        
        Args:
            message: Error message
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self):
        """String representation of the exception."""
        if self.details:
            details_str = ', '.join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class TranslationException(TSRAgentException):
    """Exception raised when translation fails."""
    
    def __init__(self, text: str, context: str, message: str = None):
        """
        Initialize translation exception.
        
        Args:
            text: Text that failed to translate
            context: Translation context ('district', 'taluka', 'village')
            message: Optional custom error message
        """
        msg = message or f"Failed to translate '{text}' (context: {context})"
        super().__init__(msg, {'text': text, 'context': context})


class ScrapingException(TSRAgentException):
    """Exception raised when web scraping fails."""
    
    def __init__(self, message: str, url: str = None, details: dict = None):
        """
        Initialize scraping exception.
        
        Args:
            message: Error message
            url: URL that failed to scrape
            details: Additional error details
        """
        error_details = details or {}
        if url:
            error_details['url'] = url
        super().__init__(message, error_details)


class ValidationException(TSRAgentException):
    """Exception raised when input validation fails."""
    
    def __init__(self, field: str, value: any, message: str = None):
        """
        Initialize validation exception.
        
        Args:
            field: Field name that failed validation
            value: Invalid value
            message: Optional custom error message
        """
        msg = message or f"Invalid value for field '{field}': {value}"
        super().__init__(msg, {'field': field, 'value': str(value)})


class FileOperationException(TSRAgentException):
    """Exception raised when file operations fail."""
    
    def __init__(self, operation: str, path: str = None, message: str = None):
        """
        Initialize file operation exception.
        
        Args:
            operation: Operation that failed ('read', 'write', 'delete', etc.)
            path: File path involved in the operation
            message: Optional custom error message
        """
        msg = message or f"File operation '{operation}' failed"
        if path:
            msg += f" for path: {path}"
        
        details = {'operation': operation}
        if path:
            details['path'] = path
        
        super().__init__(msg, details)


class TSRGenerationException(TSRAgentException):
    """Exception raised when TSR generation fails."""
    
    def __init__(self, message: str, pdf_path: str = None, details: dict = None):
        """
        Initialize TSR generation exception.
        
        Args:
            message: Error message
            pdf_path: Path to PDF that failed to process
            details: Additional error details
        """
        error_details = details or {}
        if pdf_path:
            error_details['pdf_path'] = pdf_path
        super().__init__(message, error_details)
