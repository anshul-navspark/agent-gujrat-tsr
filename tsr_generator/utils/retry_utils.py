"""
Retry utility functions for handling transient errors in TSR generation.
"""

import time
import logging
import functools
from typing import Callable, Type, Union, Tuple, Any


def retry_with_backoff(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    logger: logging.Logger = None
):
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each failure
        exceptions: Exception types to catch and retry on
        logger: Logger instance for logging retry attempts
    
    Returns:
        Decorated function that retries on failure
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal logger
            if logger is None:
                logger = logging.getLogger(func.__module__)
            
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        # Last attempt failed, raise the exception
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise e
                    
                    logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}")
                    logger.info(f"Retrying in {current_delay} seconds...")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
            
            # This should never be reached, but just in case
            raise last_exception
        
        return wrapper
    return decorator


def safe_execute(func: Callable, *args, default_return=None, logger=None, **kwargs):
    """
    Safely execute a function and return a default value on failure.
    
    Args:
        func: Function to execute
        *args: Arguments to pass to the function
        default_return: Value to return if function fails
        logger: Logger instance for logging errors
        **kwargs: Keyword arguments to pass to the function
    
    Returns:
        Function result or default_return on failure
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Safe execution of {func.__name__} failed: {e}")
        logger.debug(f"Exception details:", exc_info=True)
        return default_return


class RetryableError(Exception):
    """Exception that indicates an operation should be retried."""
    pass


class NonRetryableError(Exception):
    """Exception that indicates an operation should not be retried."""
    pass
