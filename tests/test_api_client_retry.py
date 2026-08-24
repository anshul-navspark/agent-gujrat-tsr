"""Tests for TSRAPIClient retry behavior on specific HTTP statuses.

503 from /process-record is the maintenance-window signal — the server already
knows the cause, so the client should surface it immediately instead of
retrying with backoff and making the user wait.
"""

from unittest.mock import MagicMock, patch

from app.api_client import TSRAPIClient


def _mock_response(status_code, body="AnyRoR is in its daily maintenance window..."):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = {"detail": body}
    resp.text = body
    return resp


def test_503_is_not_retried():
    """503 means scheduled outage — no retries, surface the message now."""
    client = TSRAPIClient(api_url="http://example.test", max_retries=3)
    response_503 = _mock_response(503, "AnyRoR maintenance window 2:00-2:30 PM IST")

    with patch("app.api_client.requests.post", return_value=response_503) as mock_post, \
         patch("app.api_client.time.sleep"):
        result = client.process_record(
            district="Kutch", taluka="Bhuj", village="Trambo", survey_number="32"
        )

    assert mock_post.call_count == 1, \
        f"503 must not be retried (got {mock_post.call_count} attempts)"
    assert result.success is False
    assert result.status_code == 503
    assert "maintenance" in result.error.lower() or "AnyRoR" in result.error


def test_500_is_still_retried():
    """Control test: generic 500 keeps the existing retry behavior."""
    client = TSRAPIClient(api_url="http://example.test", max_retries=2)
    response_500 = _mock_response(500, "something broke")

    with patch("app.api_client.requests.post", return_value=response_500) as mock_post, \
         patch("app.api_client.time.sleep"):
        result = client.process_record(
            district="Kutch", taluka="Bhuj", village="Trambo", survey_number="32"
        )

    assert mock_post.call_count == 3, \
        f"500 should be retried max_retries+1 times (got {mock_post.call_count})"
    assert result.success is False
    assert result.status_code == 500
