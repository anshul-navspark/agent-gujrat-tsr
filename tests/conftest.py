"""
Test configuration and shared fixtures for Gujarat TSR Agent.

This module provides pytest fixtures and configuration for testing.
"""

import pytest
import os
import tempfile
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_config, reset_config
from services.file_service import get_file_service
from services.translation_service import get_translation_service


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_land_record():
    """Provide sample land record data for testing."""
    return {
        'district': 'Kutch',
        'taluka': 'Bhuj',
        'village': 'Trambo',
        'survey_number': '32'
    }


@pytest.fixture
def config():
    """Provide a fresh configuration instance for each test."""
    reset_config()
    config = get_config()
    yield config
    reset_config()


@pytest.fixture
def file_service():
    """Provide a file service instance for testing."""
    return get_file_service()


@pytest.fixture
def translation_service():
    """Provide a translation service instance for testing."""
    return get_translation_service()
