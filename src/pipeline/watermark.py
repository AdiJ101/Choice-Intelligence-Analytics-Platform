"""
watermark.py — Sync-watermark helpers for the Customer Intelligence & Analytics Platform.

Provides two functions that read and advance the ``sync_watermarks`` table, which
the Sync Pipeline uses to track incremental progress per source table:

* :func:`get_watermark` — reads the current ``(last_pk, last_ts)`` for a given
  source table, raising :exc:`KeyError` if no row is found.
* :func:`advance_watermark` — updates ``last_pk`` and ``last_ts`` to the supplied
  values, enforcing a monotonicity guarantee (``new_pk`` must not be less than
  the existing ``last_pk``).

Both functions use ``mysql.connector`` cursor objects obtained from the supplied
connection and commit any mutations before returning.

Requirements: 7.2, 7.3
"""

from __future__ import annotations

from datetime import datetime

import mysql.connector


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_SELECT_WATERMARK = (
    "SELECT last_pk, last_ts FROM sync_watermarks WHERE source_table = %s"
)

_UPDATE_WATERMARK = (
    "UPDATE sync_watermarks "
    "SET last_pk = %s, last_ts = %s, updated_at = NOW() "
    "WHERE source_table = %s"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_watermark(conn: mysql.connector.MySQLConnection, source_table: str) -> tuple[int, datetime]:
    """Return the current ``(last_pk, last_ts)`` watermark for *source_table*.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    source_table:
        The ``source_table`` value to look up in ``sync_watermarks``
        (e.g. ``"posts"`` or ``"comments"``).

    Returns
    -------
    tuple[int, datetime]
        A two-element tuple ``(last_pk, last_ts)`` where ``last_pk`` is a
        non-negative integer and ``last_ts`` is a :class:`~datetime.datetime`.

    Raises
    ------
    KeyError
        If no row exists in ``sync_watermarks`` for *source_table*.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(_SELECT_WATERMARK, (source_table,))
        row = cursor.fetchone()
    finally:
        cursor.close()

    if row is None:
        raise KeyError(
            f"No watermark row found for source_table={source_table!r}"
        )

    last_pk: int = int(row[0])
    last_ts: datetime = row[1]
    return last_pk, last_ts


def advance_watermark(
    conn: mysql.connector.MySQLConnection,
    source_table: str,
    new_pk: int,
    new_ts: datetime,
) -> None:
    """Advance the watermark for *source_table* to ``(new_pk, new_ts)``.

    The function first reads the current ``last_pk`` and enforces a monotonicity
    guarantee: ``new_pk`` must be greater than or equal to the current value.
    If the guard is violated a :exc:`ValueError` is raised and the database is
    left unchanged.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    source_table:
        The ``source_table`` value to update in ``sync_watermarks``.
    new_pk:
        The new ``last_pk`` value.  Must be >= the current ``last_pk``.
    new_ts:
        The new ``last_ts`` value (typically the ``updated_at`` of the most
        recently processed row).

    Raises
    ------
    ValueError
        If ``new_pk`` is less than the current ``last_pk`` (monotonicity
        violation).
    KeyError
        If no row exists in ``sync_watermarks`` for *source_table* (propagated
        from :func:`get_watermark`).
    """
    current_pk, _ = get_watermark(conn, source_table)

    if new_pk < current_pk:
        raise ValueError(
            f"Monotonicity violation for source_table={source_table!r}: "
            f"new_pk={new_pk} is less than current last_pk={current_pk}"
        )

    cursor = conn.cursor()
    try:
        cursor.execute(_UPDATE_WATERMARK, (new_pk, new_ts, source_table))
        conn.commit()
    finally:
        cursor.close()
