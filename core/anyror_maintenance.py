"""AnyRoR daily-maintenance window helpers.

The Gujarat AnyRoR portal is unavailable every day from 14:00 to 14:30 IST.
During that window scrapes time out with confusing chromedriver stacktraces.
These helpers let the UI/API show a friendly notice instead.
"""

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

_WINDOW_START = time(14, 0, 0)
_WINDOW_END = time(14, 30, 0)


def is_anyror_maintenance_window(now: datetime) -> bool:
    """Return True if ``now`` falls inside the daily AnyRoR maintenance window
    (14:00 inclusive – 14:30 exclusive, IST).

    Raises ``ValueError`` if ``now`` is naive — timezone must be explicit.
    """
    if now.tzinfo is None:
        raise ValueError("is_anyror_maintenance_window requires a timezone-aware datetime")
    local = now.astimezone(IST).time()
    return _WINDOW_START <= local < _WINDOW_END


def maintenance_window_message() -> str:
    """User-facing copy explaining the daily outage."""
    return (
        "AnyRoR is in its daily maintenance window (2:00–2:30 PM IST). "
        "Please try again after 2:30 PM IST."
    )
