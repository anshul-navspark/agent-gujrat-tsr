"""
API Client for Gujarat TSR Agent Cloud Run Backend

This module provides a client interface to communicate with the serverless
API for PDF fetching and TSR generation.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for imports
_project_root = str(Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
import logging
from typing import Optional, Dict, Any
import time
import io
import zipfile

# Import from core models
from core.models import APIResponse



class TSRAPIClient:
    """Client for interacting with the Gujarat TSR Agent API"""
    
    def __init__(self, api_url: str, timeout: int = 1200, max_retries: int = 2):
        """
        Initialize API client
        
        Args:
            api_url: Base URL of the API (e.g., https://your-service.run.app)
            timeout: Request timeout in seconds (default: 1200 = 20 minutes)
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
    
    def health_check(self) -> bool:
        """
        Check if the API is healthy and responding
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    def process_record(
        self,
        district: str,
        taluka: str,
        village: str,
        survey_number: str
    ) -> APIResponse:
        """
        Process a single land record via API
        
        Args:
            district: District name in Gujarati
            taluka: Taluka name in Gujarati
            village: Village name in Gujarati
            survey_number: Survey/Block number
            
        Returns:
            APIResponse object with success status, DOCX and PDF content or error
        """
        payload = {
            "district": district,
            "taluka": taluka,
            "village": village,
            "survey_number": survey_number
        }
        
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.info(
                    f"Processing record via API (attempt {attempt + 1}/{self.max_retries + 1}): "
                    f"{district}, {taluka}, {village}, {survey_number}"
                )
                
                response = requests.post(
                    f"{self.api_url}/process-record",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    # Check cache status from response headers
                    cache_status = response.headers.get('X-Cache-Status', 'UNKNOWN')
                    cache_timestamp = response.headers.get('X-Cache-Timestamp', '')
                    
                    if cache_status == 'HIT':
                        self.logger.info(
                            f"✅ CACHE HIT - Record served from cache "
                            f"(cached: {cache_timestamp})"
                        )
                    elif cache_status == 'MISS':
                        self.logger.info(f"❌ CACHE MISS - Record fetched from source")
                    
                    self.logger.info(f"Successfully processed record")
                    
                    docx_content = None
                    pdf_content = None
                    
                    # Check if response is a ZIP file
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/zip' in content_type:
                        try:
                            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                                for filename in zf.namelist():
                                    if filename.endswith('.docx') and not filename.startswith('~'):
                                        docx_content = zf.read(filename)
                                    elif filename.endswith('.pdf'):
                                        pdf_content = zf.read(filename)
                        except Exception as e:
                            self.logger.error(f"Failed to extract ZIP response: {e}")
                            return APIResponse(
                                success=False,
                                error=f"Failed to process response: {str(e)}",
                                status_code=200
                            )
                    else:
                        # Assume it's just the DOCX file (backward compatibility)
                        docx_content = response.content
                    
                    return APIResponse(
                        success=True,
                        docx_content=docx_content,
                        pdf_content=pdf_content,
                        status_code=200,
                        cache_hit=(cache_status == 'HIT')
                    )
                else:
                    error_msg = self._extract_error_message(response)
                    self.logger.error(f"API returned error: {error_msg}")
                    
                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        return APIResponse(
                            success=False,
                            error=error_msg,
                            status_code=response.status_code
                        )
                    
                    # Retry on server errors (5xx)
                    if attempt < self.max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        self.logger.warning(f"Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    
                    return APIResponse(
                        success=False,
                        error=error_msg,
                        status_code=response.status_code
                    )
                    
            except requests.exceptions.Timeout:
                error_msg = f"Request timed out after {self.timeout} seconds"
                self.logger.error(error_msg)
                
                if attempt < self.max_retries:
                    self.logger.warning(f"Retrying...")
                    continue
                    
                return APIResponse(
                    success=False,
                    error=error_msg
                )
                
            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error: {str(e)}"
                self.logger.error(error_msg)
                
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    self.logger.warning(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                    
                return APIResponse(
                    success=False,
                    error=error_msg
                )
                
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                self.logger.error(error_msg)
                return APIResponse(
                    success=False,
                    error=error_msg
                )
        
        # Should never reach here, but just in case
        return APIResponse(
            success=False,
            error="Max retries exceeded"
        )
    
    def _extract_error_message(self, response: requests.Response) -> str:
        """Extract error message from API response"""
        try:
            error_data = response.json()
            return error_data.get('detail', f"HTTP {response.status_code}")
        except:
            return f"HTTP {response.status_code}: {response.text[:200]}"
