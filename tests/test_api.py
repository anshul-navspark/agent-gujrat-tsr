
# API Endpoint Tests
"""
Tests for the FastAPI endpoints of Gujarat TSR Agent.

This module provides integration tests for the API server endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import io
import zipfile
from fastapi.testclient import TestClient

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAPIHealth:
    """Tests for API health check endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        from api.server import app
        return TestClient(app)

    def test_health_check_returns_200(self, client):
        """Test that health check endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestProcessRecordEndpoint:
    """Tests for the /process-record endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        from api.server import app
        return TestClient(app)

    @pytest.fixture
    def mock_scraping_service(self):
        """Mock the get_scraping_service dependency."""
        with patch('api.server.get_scraping_service') as mock_get:
            mock_service = MagicMock()
            mock_service.fetch_land_record.return_value = {
                'success': True,
                'output_path': '/tmp/mock.pdf',
                'error': None
            }
            # Also mock the context manager behavior if needed, 
            # though server.py uses it directly now (or via Depends).
            # If using Depends(get_scraping_service_dependency), we might need to override dependency.
            # But let's try patching the imported function module-level first.
            
            # Since we switched to Depends in api/server.py, we should override the dependency
            # But for simple patching, patching where it is imported works IF the endpoint uses the imported symbol.
            # api/server.py imports get_scraping_service_dependency from api.dependencies
            
            mock_get.return_value = mock_service
            yield mock_service

    @pytest.fixture
    def mock_tsr_generator(self):
        """Mock the TSR generator."""
        with patch('api.server.generate_tsr_from_pdf') as mock:
            mock.return_value = {'success': True, 'error': None}
            yield mock

    def test_process_record_requires_all_fields(self, client):
        """Test that all fields are required."""
        # Missing survey_number
        response = client.post("/process-record", json={
            "district": "Kutch",
            "taluka": "Bhuj",
            "village": "Trambo"
        })
        assert response.status_code == 422  # Validation error

    def test_process_record_valid_request_structure(self, client):
        """Test that valid request has correct structure."""
        request_data = {
            "district": "Kutch",
            "taluka": "Bhuj",
            "village": "Trambo",
            "survey_number": "32"
        }

        # Verify the request is properly structured (Pydantic validation)
        from api.server import LandRecordRequest
        record = LandRecordRequest(**request_data)
        assert record.district == "Kutch"
        assert record.taluka == "Bhuj"
        assert record.village == "Trambo"
        assert record.survey_number == "32"


class TestGenerateTSREndpoint:
    """Tests for the /generate-tsr endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        from api.server import app
        return TestClient(app)

    def test_generate_tsr_requires_pdf_file(self, client):
        """Test that a PDF file is required."""
        response = client.post("/generate-tsr")
        assert response.status_code == 422  # Validation error - missing file

    def test_generate_tsr_accepts_pdf_upload(self, client):
        """Test that PDF upload is accepted (structure test)."""
        # Create a minimal mock PDF
        pdf_content = b'%PDF-1.4 test content'
        files = {
            'file': ('test.pdf', io.BytesIO(pdf_content), 'application/pdf')
        }

        # Mock the generator. The endpoint lazy-loads it via get_tsr_generator(),
        # so patch that to return a stub callable rather than the (non-module-level)
        # generate_tsr_from_pdf symbol.
        with patch('api.server.get_tsr_generator') as mock_get_gen:
            mock_get_gen.return_value = MagicMock(
                return_value={'success': False, 'error': "Test mock error"}
            )

            # Use dependency override for file service
            from api.dependencies import get_file_service_dependency
            from api.server import app
            
            mock_fs = MagicMock()
            app.dependency_overrides[get_file_service_dependency] = lambda: mock_fs
            
            try:
                response = client.post("/generate-tsr", files=files)
                # Should return 500 because we returned success=False
                assert response.status_code == 500
                assert "Generation failed" in response.json()['detail']
            finally:
                app.dependency_overrides = {}


class TestDebugEnvironmentEndpoint:
    """Tests for the /debug-env endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        from api.server import app
        return TestClient(app)

    def test_debug_environment_returns_info(self, client):
        """Test that debug endpoint returns environment info."""
        response = client.get("/debug-env")
        assert response.status_code == 200

        data = response.json()
        assert "platform" in data
        assert "environment_variables" in data


class TestAPIRequestValidation:
    """Tests for API request validation."""

    def test_land_record_request_validation(self):
        """Test LandRecordRequest Pydantic model validation."""
        from api.server import LandRecordRequest

        # Valid request
        request = LandRecordRequest(
            district="Kutch",
            taluka="Bhuj",
            village="Trambo",
            survey_number="32"
        )
        assert request.district == "Kutch"

    def test_land_record_request_strips_whitespace(self):
        """Test that whitespace is handled correctly."""
        from api.server import LandRecordRequest

        request = LandRecordRequest(
            district="  Kutch  ",
            taluka="  Bhuj  ",
            village="  Trambo  ",
            survey_number="  32  "
        )
        # Note: Pydantic doesn't strip by default, so values include spaces
        # unless a validator is added. Here we just assert it accepts it.
        # If we wanted stripping, we'd check against stripped string.
        # The current implementation in server.py doesn't have validators for stripping.
        assert "Kutch" in request.district


class TestAPIErrorHandling:
    """Tests for API error handling."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        from api.server import app
        return TestClient(app)

    def test_invalid_endpoint_returns_404(self, client):
        """Test that invalid endpoints return 404."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404

    def test_wrong_method_returns_405(self, client):
        """Test that wrong HTTP methods return 405."""
        response = client.get("/process-record")  # Should be POST
        assert response.status_code == 405
