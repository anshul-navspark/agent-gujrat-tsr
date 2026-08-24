"""Tests for the AnyRoR daily maintenance-window helper.

AnyRoR portal is unavailable every day between 14:00 and 14:30 IST. The helper
lets the UI/API surface a friendly notice during that window instead of letting
scrape-timeout stacktraces leak through.
"""

from datetime import datetime, timezone, timedelta

import pytest

from core.anyror_maintenance import (
    IST,
    is_anyror_maintenance_window,
    maintenance_window_message,
)


# ---------------------------------------------------------------------------
# is_anyror_maintenance_window
# ---------------------------------------------------------------------------


def _ist(year, month, day, hour, minute, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=IST)


def test_inside_window_returns_true():
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 14, 15)) is True


def test_at_start_of_window_is_inside():
    """14:00:00 IST is the first second of the window."""
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 14, 0, 0)) is True


def test_one_second_before_window_is_outside():
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 13, 59, 59)) is False


def test_at_end_of_window_is_outside():
    """14:30:00 IST is the first second AFTER the window (half-open interval)."""
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 14, 30, 0)) is False


def test_after_window_returns_false():
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 15, 0)) is False


def test_morning_returns_false():
    assert is_anyror_maintenance_window(_ist(2026, 5, 20, 9, 0)) is False


def test_utc_input_inside_window_returns_true():
    """14:15 IST == 08:45 UTC. A caller passing UTC must get the same answer."""
    utc_time = datetime(2026, 5, 20, 8, 45, tzinfo=timezone.utc)
    assert is_anyror_maintenance_window(utc_time) is True


def test_utc_input_outside_window_returns_false():
    """13:00 IST == 07:30 UTC — well outside the IST 14:00-14:30 window."""
    utc_time = datetime(2026, 5, 20, 7, 30, tzinfo=timezone.utc)
    assert is_anyror_maintenance_window(utc_time) is False


def test_naive_datetime_raises():
    """Naive datetimes are ambiguous — force callers to be explicit."""
    naive = datetime(2026, 5, 20, 14, 15)  # no tzinfo
    with pytest.raises(ValueError):
        is_anyror_maintenance_window(naive)


# ---------------------------------------------------------------------------
# maintenance_window_message
# ---------------------------------------------------------------------------


def test_message_mentions_window_times():
    msg = maintenance_window_message()
    assert "2:00" in msg or "14:00" in msg
    assert "2:30" in msg or "14:30" in msg


def test_message_mentions_ist():
    assert "IST" in maintenance_window_message()


def test_message_mentions_anyror():
    assert "AnyRoR" in maintenance_window_message()
