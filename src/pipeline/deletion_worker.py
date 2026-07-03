"""
deletion_worker.py — Deletion propagation worker for the Sync Pipeline.

Polls the ``content_deletions`` tombstone table for records whose Qdrant
embeddings have not yet been removed (``propagated_at IS NULL``) and
propagates each deletion to the Qdrant ``content_embeddings`` collection.

Two public functions are provided:

* :func:`poll_and_propagate_deletions` — processes a single poll cycle and
  returns.  The caller is responsible for scheduling repeated invocations and
  any inter-call sleep.

* :func:`run_deletion_worker` — convenience wrapper that runs the poll cycle
  in a ``while True`` loop, sleeping ``poll_interval_seconds`` between
  iterations and catching unexpected exceptions so the loop never terminates.

Requirements: 8.5
"""

from __future__ import annotations

import logging
import time
from typing import Any

import mysql.connector

from src.vector_db.delete import delete_points_by_source

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_SELECT_PENDING = (
    "SELECT id, source_table, source_record_id "
    "FROM content_deletions "
    "WHERE propagated_at IS NULL "
    "ORDER BY deleted_at ASC "
    "LIMIT 100"
)

_MARK_PROPAGATED = (
    "UPDATE content_deletions "
    "SET propagated_at = NOW() "
    "WHERE id = %s"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def poll_and_propagate_deletions(
    conn: mysql.connector.MySQLConnection,
    qdrant_client: Any,
    poll_interval_seconds: float = 10.0,  # noqa: ARG001 — kept for API symmetry
) -> None:
    """Process one batch of pending deletion records and propagate to Qdrant.

    Fetches up to 100 rows from ``content_deletions`` where
    ``propagated_at IS NULL``, ordered by ``deleted_at`` ascending.  For each
    row:

    * Calls :func:`~src.vector_db.delete.delete_points_by_source` to remove
      matching Qdrant points.
    * On success, marks the row as propagated with ``propagated_at = NOW()``
      and immediately commits.
    * On failure, logs the error and continues to the next row — partial
      progress is preserved because each successful propagation is committed
      independently.

    This function processes exactly one poll cycle and returns.  The caller is
    responsible for invoking it repeatedly (e.g. inside a loop with
    :func:`time.sleep`) to achieve continuous deletion propagation.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection`.
    qdrant_client:
        An authenticated :class:`qdrant_client.QdrantClient` instance.
    poll_interval_seconds:
        Accepted for API symmetry with :func:`run_deletion_worker` but not
        used internally (sleeping between cycles is the caller's
        responsibility).
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(_SELECT_PENDING)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    if not rows:
        logger.debug("No pending deletions found in this poll cycle.")
        return

    logger.info("Processing %d pending deletion(s).", len(rows))

    for row in rows:
        deletion_id: int = row["id"]
        source_table: str = row["source_table"]
        source_record_id: int = row["source_record_id"]

        try:
            delete_points_by_source(qdrant_client, source_table, source_record_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "Failed to delete Qdrant points for deletion_id=%s "
                "(source_table=%s, source_record_id=%s): %s",
                deletion_id,
                source_table,
                source_record_id,
                exc,
            )
            continue

        # Mark as propagated and commit immediately so that partial progress
        # is not lost if a subsequent row fails.
        update_cursor = conn.cursor()
        try:
            update_cursor.execute(_MARK_PROPAGATED, (deletion_id,))
            conn.commit()
        except mysql.connector.Error as db_exc:
            logger.error(
                "Failed to mark deletion_id=%s as propagated: %s",
                deletion_id,
                db_exc,
            )
            conn.rollback()
        finally:
            update_cursor.close()

        logger.info(
            "Propagated deletion_id=%s (source_table=%s, source_record_id=%s).",
            deletion_id,
            source_table,
            source_record_id,
        )


def run_deletion_worker(
    conn: mysql.connector.MySQLConnection,
    qdrant_client: Any,
    poll_interval_seconds: float = 10.0,
) -> None:
    """Run the deletion propagation worker indefinitely.

    Calls :func:`poll_and_propagate_deletions` in a ``while True`` loop,
    sleeping ``poll_interval_seconds`` between iterations.  Any unhandled
    :exc:`Exception` raised during a poll cycle is caught and logged so that
    the loop never terminates due to a transient error.

    This function blocks forever; run it in a dedicated thread or process.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection`.
    qdrant_client:
        An authenticated :class:`qdrant_client.QdrantClient` instance.
    poll_interval_seconds:
        Seconds to sleep between poll cycles (default: ``10.0``).  Must be
        a positive number to avoid a busy loop.
    """
    logger.info(
        "Deletion worker started (poll_interval=%.1fs).", poll_interval_seconds
    )

    while True:
        try:
            poll_and_propagate_deletions(conn, qdrant_client, poll_interval_seconds)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "Unexpected error in deletion worker poll cycle: %s", exc
            )

        time.sleep(poll_interval_seconds)
