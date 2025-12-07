"""
Centralized logging configuration for Gujarat TSR Agent.

This module provides consistent logging setup across all components.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
    log_dir: str = 'logs',
    module_name: str = None
) -> logging.Logger:
    """
    Setup logging configuration with both console and file handlers.
    
    Args:
        console_level: Logging level for console output (default: WARNING)
        file_level: Logging level for file output (default: INFO)
        log_dir: Directory for log files (default: 'logs')
        module_name: Name for the logger (default: __name__ of caller)
        
    Returns:
        Configured logger instance
    """
    # Default levels
    console_level = console_level or logging.WARNING
    file_level = file_level or logging.INFO
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_path / f'tsr_agent_{timestamp}.log'
    
    # Create logger
    logger_name = module_name or __name__
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)  # Capture everything
    
    # Remove existing handlers if any
    if logger.handlers:
        logger.handlers.clear()
    
    # Create file handler with UTF-8 encoding
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Suppress verbose logging from third-party libraries
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('WDM').setLevel(logging.ERROR)
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (default: calling module name)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name or __name__)
