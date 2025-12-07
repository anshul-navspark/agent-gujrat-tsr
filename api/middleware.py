
"""
FastAPI Middleware.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from typing import Callable

logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request processing time."""
    
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            logger.info(
                f"Path: {request.url.path} Method: {request.method} "
                f"Status: {response.status_code} Duration: {process_time:.4f}s"
            )
            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Path: {request.url.path} Method: {request.method} "
                f"Failed with error: {str(e)} Duration: {process_time:.4f}s"
            )
            raise
