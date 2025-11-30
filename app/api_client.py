"""
API Client for Gujarat TSR Agent Cloud Run Backend

This module provides a client interface to communicate with the serverless
API for PDF fetching and TSR generation.
"""

import requests
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import time


@dataclass
class APIResponse:
    """Response from API processing"""
    success: bool
    docx_content: Optional[bytes] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class TSRAPIClient:
    """Client for interacting with the Gujarat TSR Agent API"""
    
    def __init__(self, api_url: str, timeout: int = 600, max_retries: int = 2):
        """
        Initialize API client
        
        Args:
            api_url: Base URL of the API (e.g., https://your-service.run.app)
            timeout: Request timeout in seconds (default: 600 = 10 minutes)
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
            APIResponse object with success status and DOCX content or error
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
                    self.logger.info(f"Successfully processed record")
                    return APIResponse(
                        success=True,
                        docx_content=response.content,
                        status_code=200
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
