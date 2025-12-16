"""
Configuration management for Gujarat TSR Agent.

This module provides centralized, type-safe configuration management
with environment variable support and validation.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class Config:
    """Application configuration."""
    
    # API Configuration
    gemini_api_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''))
    gemini_model_name: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_NAME', 'gemini-3-pro-preview'))
    
    # AnyRoR Configuration
    anyror_url: str = 'https://anyror.gujarat.gov.in/LandRecordRural.aspx'
    anyror_wait_timeout: int = 20
    anyror_max_retries: int = 3
    
    # File Configuration
    temp_dir: Optional[str] = None
    
    # Logging Configuration
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    log_dir: str = 'logs'
    
    # Translation Configuration
    translation_json_path: str = 'anyror_hierarchy.json'
    
    # API Server Configuration
    api_timeout: int = 1200  # 20 minutes
    api_max_retries: int = 2
    
    # Streamlit Configuration
    max_workers: int = 20
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
    
    def validate(self) -> bool:
        """
        Validate configuration.
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        if self.anyror_wait_timeout <= 0:
            raise ValueError("anyror_wait_timeout must be positive")
        
        if self.api_timeout <= 0:
            raise ValueError("api_timeout must be positive")
        
        return True


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get or create the global configuration instance.
    
    Returns:
        Configuration instance
    """
    global _config
    if _config is None:
        _config = Config()
        _config.validate()
    return _config


def reset_config() -> None:
    """Reset the global configuration instance (useful for testing)."""
    global _config
    _config = None
