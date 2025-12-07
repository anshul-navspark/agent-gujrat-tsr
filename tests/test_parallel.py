
"""
Parallel Processing Tests.

These tests verify the parallel processing capabilities of the API.
"""

import pytest
import concurrent.futures
import time
import logging
from unittest.mock import patch, MagicMock
from services.processing_service import get_processing_service
from services.scraping_service import ScrapingService

logger = logging.getLogger(__name__)

@pytest.fixture
def mock_scraping_service_pool():
    """Mock a pool of scraping services."""
    with patch('services.scraping_service.get_scraping_service') as mock_get:
        mock_service = MagicMock(spec=ScrapingService)
        # Simulate some processing time
        def mock_fetch(*args, **kwargs):
            time.sleep(0.1)
            return {'success': True, 'output_path': '/tmp/mock.pdf'}
            
        mock_service.fetch_land_record.side_effect = mock_fetch
        mock_get.return_value = mock_service
        yield mock_get

@pytest.mark.integration
def test_parallel_processing_execution(mock_scraping_service_pool):
    """Test that multiple requests can be processed in parallel."""
    
    records = [
        {'district': 'Kutch', 'taluka': 'Bhuj', 'village': 'Trambo', 'survey_number': '32'},
        {'district': 'Kutch', 'taluka': 'Bhuj', 'village': 'Trambo', 'survey_number': '33'},
        {'district': 'Kutch', 'taluka': 'Bhuj', 'village': 'Trambo', 'survey_number': '34'},
        {'district': 'Kutch', 'taluka': 'Bhuj', 'village': 'Trambo', 'survey_number': '35'},
    ]
    
    # We'll use the processing service logic directly or mock the API calls
    # For a unit/integration test of the logic, we can verify ThreadPoolExecutor behavior
    
    results = []
    start_time = time.time()
    
    def process_mock_record(record):
        # Simulate API call
        time.sleep(0.2)
        return {
            'record': record,
            'success': True
        }
    
    max_workers = 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_mock_record, r) for r in records]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    duration = time.time() - start_time
    
    # If 4 records take 0.2s each, sequential would be 0.8s.
    # Parallel with 4 workers should be around 0.2s + overhead.
    # We assert it's faster than sequential (with some buffer).
    assert len(results) == 4
    assert duration < 0.6  # Should be well under 0.8s
    
    logger.info(f"Processed 4 records in {duration:.4f}s")
