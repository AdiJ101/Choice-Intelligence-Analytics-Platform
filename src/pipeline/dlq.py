"""
dlq.py — Dead-letter queue helpers for the Customer Intelligence & Analytics Platform.

Provides three functions that manage rows in the ``dead_letter_queue`` table,
which the Sync Pipeline uses to track records that have failed embedding/upsert
after the maximum number of retries:

* :func:`log_failure` — inserts a new failure row with the supplied metadata.
* :func:`is_permanently_failed` — returns ``True`` if a non-cleared failure
  row exists with ``retry_count >= 5``.
* :func:`clear_failure` — marks matching non-cleared rows as cleared (sets
  ``cleared_at = NOW()``) and returns the count of rows updated.

All mutations are committed before the function returns.  Use
``mysql.connector`` connection objects as the ``conn`` argument.

Requirements: 7.7
"""

from __future__ import annotations

import mysql.connector


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_FAILURE = (
    "INSERT INTO dead_letter_queue "
    "(source_table, source_record_id, failure_reason, retry_count, failed_at) "
    "VALUES (%s, %s, %s, %s, NOW())"
)

_SELECT_PERMANENTLY_FAILED = (
    "SELECT COUNT(*) FROM dead_letter_queue "
    "WHERE source_table = %s "
    "  AND source_record_id = %s "
    "  AND retry_count >= 5 "
    "  AND cleared_at IS NULL"
)

_CLEAR_FAILURE = (
    "UPDATE dead_letter_queue "
    "SET cleared_at = NOW() "
    "WHERE source_table = %s "
    "  AND source_record_id = %s "
    "  AND cleared_at IS NULL"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_failure(
    conn: mysql.connector.MySQLConnection,
    source_table: str,
    source_record_id: int,
    reason: str,
    retry_count: int,
) -> None:
    """Insert a failure row into ``dead_letter_queue`` and commit.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    source_table:
        The originating table name (e.g. ``"posts"`` or ``"comments"``).
    source_record_id:
        The primary key of the failing record in *source_table*.
    reason:
        Human-readable description of the failure (stored in
        ``failure_reason``).
    retry_count:
        Number of attempts made before recording the failure.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_INSERT_FAILURE, (source_table, source_record_id, reason, retry_count))
        conn.commit()
    finally:
        cursor.close()


def is_permanently_failed(
    conn: mysql.connector.MySQLConnection,
    source_table: str,
    source_record_id: int,
) -> bool:
    """Return ``True`` if a non-cleared failure row exists with ``retry_count >= 5``.

    A record is considered permanently failed when it has reached or exceeded the
    maximum retry threshold (5) and has not been manually cleared.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    source_table:
        The originating table name.
    source_record_id:
        The primary key of the record to check.

    Returns
    -------
    bool
        ``True`` if at least one non-cleared row satisfies the criteria;
        ``False`` otherwise.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_SELECT_PERMANENTLY_FAILED, (source_table, source_record_id))
        row = cursor.fetchone()
    finally:
        cursor.close()

    count: int = int(row[0]) if row else 0
    return count > 0


def clear_failure(
    conn: mysql.connector.MySQLConnection,
    source_table: str,
    source_record_id: int,
) -> int:
    """Set ``cleared_at = NOW()`` for all matching non-cleared failure rows.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    source_table:
        The originating table name.
    source_record_id:
        The primary key of the record whose failures should be cleared.

    Returns
    -------
    int
        The number of rows whose ``cleared_at`` was updated (may be 0 if no
        matching non-cleared rows were found).
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_CLEAR_FAILURE, (source_table, source_record_id))
        rows_updated: int = cursor.rowcount
        conn.commit()
    finally:
        cursor.close()

    return rows_updated
