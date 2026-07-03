"""
cooling.py — Pure function for cooling period eligibility check.

Requirement 6.1:
  A Post is within its Cooling_Period when:
    (UTC_NOW - posts.discovered_at) <= cooling_time_days * 86400 seconds

This is a pure function with no side effects, making it straightforward
to property-test with generated timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone


def is_within_cooling_period(
    discovered_at: datetime,
    cooling_time_days: int,
    now: datetime | None = None,
) -> bool:
    """Return True if the post discovered at *discovered_at* is still
    within its cooling period of *cooling_time_days* days.

    Parameters
    ----------
    discovered_at:
        The datetime when the post was first stored (``posts.discovered_at``).
        May be naive (assumed UTC) or timezone-aware.
    cooling_time_days:
        Number of days in the cooling window (from ``scraping_config``).
        Expected range: [1, 365].
    now:
        The current datetime. Defaults to ``datetime.now(tz=timezone.utc)``.
        Provide an explicit value to make behaviour deterministic in tests.
        May be naive (assumed UTC) or timezone-aware.

    Returns
    -------
    bool
        True  → post is within cooling period; engagement should be refreshed.
        False → cooling period has expired; skip engagement refresh.

    Formula
    -------
        age_seconds       = (now - discovered_at).total_seconds()
        threshold_seconds = cooling_time_days * 86400
        return age_seconds <= threshold_seconds

    Notes
    -----
    Naive datetimes are normalised to UTC before comparison so that
    mixed-awareness inputs are handled safely.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Normalise naive datetimes to UTC
    if discovered_at.tzinfo is None:
        discovered_at = discovered_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - discovered_at).total_seconds()
    threshold_seconds = cooling_time_days * 86400
    return age_seconds <= threshold_seconds
