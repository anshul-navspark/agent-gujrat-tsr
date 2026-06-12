"""Tests for the maintenance-window behavior in /process-record.

When AnyRoR is in its daily maintenance window (14:00-14:30 IST) and the
scraper fails, the API should return a friendly 503 explaining the outage
instead of leaking the chromedriver stacktrace through a 500.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.server import app
from api.dependencies import (
    get_cache_service_dependency,
    get_scraping_service_dependency,
    get_translation_service_dependency,
)


CHROMEDRIVER_NOISE = (
    "Error fetching land record: Message: \n"
    "Stacktrace:\n"
    "0   chromedriver                        0x00000001005bc3d4"
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mocked_scrape_failure():
    """Cache miss + scrape failure with a chromedriver-shaped error blob."""
    mock_scraper = MagicMock()
    mock_scraper.fetch_land_record.return_value = {
        "success": False,
        "error": CHROMEDRIVER_NOISE,
    }
    mock_scraper.__enter__ = MagicMock(return_value=mock_scraper)
    mock_scraper.__exit__ = MagicMock(return_value=False)

    mock_cache = MagicMock()
    mock_cache.generate_cache_key_from_translated.return_value = "fakekey"
    mock_cache.get_cached_pdf_by_key.return_value = None
    mock_cache.get_cached_docx_by_key.return_value = None

    # Translation is mocked so the request always clears the English->Gujarati
    # validation gate and reaches the scrape step — this test is about
    # scrape-failure handling, not about whether a village name resolves.
    mock_translation = MagicMock()
    mock_translation.translate_to_gujarati.side_effect = lambda text, *a, **k: f"{text}-guj"

    app.dependency_overrides[get_scraping_service_dependency] = lambda: mock_scraper
    app.dependency_overrides[get_cache_service_dependency] = lambda: mock_cache
    app.dependency_overrides[get_translation_service_dependency] = lambda: mock_translation
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _payload():
    return {
        "district": "Kutch",
        "taluka": "Bhuj",
        "village": "Trambo",
        "survey_number": "32",
    }


def test_scrape_failure_in_maintenance_window_returns_503_with_friendly_message(
    client, mocked_scrape_failure
):
    """During the daily outage window, return 503 with a user-friendly message."""
    with patch("api.server.is_anyror_maintenance_window", return_value=True):
        response = client.post("/process-record", json=_payload())

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert "AnyRoR" in detail
    assert ("2:00" in detail) or ("14:00" in detail)
    assert "chromedriver" not in detail
    assert "Stacktrace" not in detail


def test_scrape_failure_outside_maintenance_window_still_returns_500(
    client, mocked_scrape_failure
):
    """Outside the window, behavior is unchanged — surface the raw error."""
    with patch("api.server.is_anyror_maintenance_window", return_value=False):
        response = client.post("/process-record", json=_payload())

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "Scraping failed" in detail
