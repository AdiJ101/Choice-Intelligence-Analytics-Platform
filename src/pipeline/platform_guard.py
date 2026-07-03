"""
platform_guard.py — Platform configuration guard for the Customer Intelligence
& Analytics Platform.

Provides a guard function that verifies a platform has at least one row in the
``platform_config`` table before processing begins.  This prevents the Sync
Pipeline from silently operating on a platform whose metric-field mappings have
not yet been configured, which would produce incomplete or incorrect data.

* :class:`MissingPlatformConfigError` — custom exception raised when no config
  rows exist for a given ``platform_id``.
* :func:`assert_platform_config_exists` — queries ``platform_config`` and
  raises :class:`MissingPlatformConfigError` if the count is zero.

Requirements: 10.5
"""

from __future__ import annotations

import mysql.connector


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_COUNT_PLATFORM_CONFIG = (
    "SELECT COUNT(*) FROM platform_config WHERE platform_id = %s"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MissingPlatformConfigError(Exception):
    """Raised when no ``platform_config`` rows exist for a given platform.

    Attributes
    ----------
    platform_id : int
        The ``platform_id`` for which configuration was expected but absent.
    """

    def __init__(self, platform_id: int) -> None:
        self.platform_id: int = platform_id
        super().__init__(
            f"No platform_config rows found for platform_id={platform_id}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assert_platform_config_exists(
    conn: mysql.connector.MySQLConnection,
    platform_id: int,
) -> None:
    """Assert that at least one ``platform_config`` row exists for *platform_id*.

    Queries ``SELECT COUNT(*) FROM platform_config WHERE platform_id = %s`` and
    raises :class:`MissingPlatformConfigError` if the count is zero.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    platform_id:
        The ``platforms.id`` value to check.

    Raises
    ------
    MissingPlatformConfigError
        If no ``platform_config`` rows exist for *platform_id*.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_COUNT_PLATFORM_CONFIG, (platform_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()

    count: int = int(row[0]) if row else 0
    if count == 0:
        raise MissingPlatformConfigError(platform_id)
