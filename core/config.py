"""
Configuration management for Gujarat TSR Agent.

This module provides centralized, type-safe configuration management
with environment variable support and validation.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# The "Gemini unavailable" notice is informational, and Config is re-instantiated
# freely (reset_config() in tests, Streamlit reruns). Emit it once per process.
_gemini_notice_logged = False


@dataclass
class Config:
    """Application configuration."""
    
    # API Configuration
    gemini_api_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''))
    gemini_model_name: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL_NAME', 'gemini-3.1-pro-preview'))
    
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
        # GEMINI_API_KEY is OPTIONAL. It used to raise here, which made an API
        # key nobody has a hard startup dependency: with the captcha solver and
        # the default extraction backend both on the local `claude` CLI, and
        # Gemini credits at zero, that raise meant nothing booted at all.
        # Gemini-backed paths (EXTRACTION_BACKEND=gemini, translation, village
        # matching) must now fail at POINT OF USE with a clear message —
        # see require_gemini_api_key() — not at import time.
        if not self.gemini_api_key:
            global _gemini_notice_logged
            if not _gemini_notice_logged:
                logger.info(
                    "GEMINI_API_KEY is not set; Gemini-backed paths "
                    "(EXTRACTION_BACKEND=gemini, translation, village matching) "
                    "are unavailable. Captcha solving and the default extraction "
                    "backend use the local `claude` CLI and need no API key."
                )
                _gemini_notice_logged = True

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
        # NOTE: gemini_api_key is deliberately NOT checked here — see __post_init__.
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


def require_gemini_api_key(purpose: str = "this operation") -> str:
    """Return the Gemini API key, or fail with a clear point-of-use message.

    Call this from the Gemini-backed code paths that genuinely cannot run
    without a key. Startup no longer checks for it, so the failure has to
    happen here, where the message can say what was being attempted.

    Args:
        purpose: What needed the key, e.g. "Gemini extraction".

    Returns:
        The API key.

    Raises:
        ValueError: If GEMINI_API_KEY is unset or empty.
    """
    key = get_config().gemini_api_key
    if not key:
        raise ValueError(
            f"GEMINI_API_KEY is not set, but {purpose} requires it. Either set "
            "it in .env.local, or use the no-API-key path (the `claude` CLI: "
            "EXTRACTION_BACKEND=claude, which is the default)."
        )
    return key
