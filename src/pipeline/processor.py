"""
processor.py — Batch sync processor for the Customer Intelligence & Analytics Platform.

Provides :func:`process_batch`, the core incremental-sync routine that reads
new rows from MySQL (``posts`` or ``comments``), embeds their text, and upserts
the resulting vectors into the Qdrant ``content_embeddings`` collection.

Execution model
---------------
1. Read the current watermark (``last_pk``, ``last_ts``) for the given source
   table.
2. Fetch up to ``SYNC_BATCH_SIZE`` rows from MySQL where ``id > last_pk``,
   ordered by ``id`` ascending (this gives a deterministic, gap-free
   incremental window).
3. For each row:
   a. Skip immediately if the platform has no ``platform_config`` rows.
   b. Skip if the record was previously permanently failed (``retry_count ≥ 5``
      in ``dead_letter_queue``).
   c. Chunk the row's text content.
   d. Embed each chunk, retrying up to ``DLQ_MAX_RETRIES`` times on transient
      errors.
   e. Upsert the resulting Qdrant point.
   f. After all chunks are done (or a permanent embed failure), advance the
      watermark so the record is not re-processed on the next run.
4. Return the count of rows that were fully processed (no permanent embed
   failure).

Requirements: 7.1, 7.2, 7.3, 7.7
"""

from __future__ import annotations

import logging
from typing import Any

import mysql.connector

from config.settings import DLQ_MAX_RETRIES, SYNC_BATCH_SIZE
from src.pipeline.chunker import chunk_text
from src.pipeline.dlq import is_permanently_failed, log_failure
from src.pipeline.platform_guard import (
    MissingPlatformConfigError,
    assert_platform_config_exists,
)
from src.pipeline.watermark import advance_watermark, get_watermark
from src.vector_db.upsert import build_payload, upsert_point

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_QUERY_POSTS = (
    "SELECT p.id, p.handle_id, p.platform_id, p.post_type, p.body, p.title,"
    " p.publish_timestamp, p.language_code,"
    " h.category_id, c.name AS category_name,"
    " pl.platform_code, h.display_name AS handle_name"
    " FROM posts p"
    " JOIN handles h ON p.handle_id = h.id"
    " JOIN categories c ON h.category_id = c.id"
    " JOIN platforms pl ON p.platform_id = pl.id"
    " WHERE p.id > %s"
    " ORDER BY p.id ASC"
    " LIMIT %s"
)

_QUERY_COMMENTS = (
    "SELECT cm.id, cm.post_id, cm.comment_text, cm.language_code,"
    " p.platform_id, p.handle_id, p.post_type, p.publish_timestamp,"
    " h.category_id, c.name AS category_name,"
    " pl.platform_code, h.display_name AS handle_name"
    " FROM comments cm"
    " JOIN posts p ON cm.post_id = p.id"
    " JOIN handles h ON p.handle_id = h.id"
    " JOIN categories c ON h.category_id = c.id"
    " JOIN platforms pl ON p.platform_id = pl.id"
    " WHERE cm.id > %s"
    " ORDER BY cm.id ASC"
    " LIMIT %s"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_batch(
    conn: mysql.connector.MySQLConnection,
    qdrant_client: Any,
    embedder: Any,
    source_table: str,
) -> int:
    """Fetch new rows from *source_table*, embed them, and upsert into Qdrant.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` instance.
    qdrant_client:
        An authenticated ``QdrantClient`` instance.
    embedder:
        An object with an ``embed(text: str) -> list[float]`` method
        (typically :class:`src.pipeline.embedder.EmbedderClient`).
    source_table:
        Either ``"post"`` or ``"comment"``.  Selects the query template and
        drives all source-table-specific branching.

    Returns
    -------
    int
        The number of rows from this batch that were successfully processed
        (i.e. no permanent embedding failure occurred for that row).

    Raises
    ------
    ValueError
        If *source_table* is not ``"post"`` or ``"comment"``.
    """
    if source_table not in ("post", "comment"):
        raise ValueError(
            f"source_table must be 'post' or 'comment', got {source_table!r}"
        )

    # ------------------------------------------------------------------
    # Step 1: read watermark
    # ------------------------------------------------------------------
    last_pk, _last_ts = get_watermark(conn, source_table)
    logger.debug(
        "process_batch: source_table=%r last_pk=%d batch_size=%d",
        source_table,
        last_pk,
        SYNC_BATCH_SIZE,
    )

    # ------------------------------------------------------------------
    # Step 2: fetch rows from MySQL
    # ------------------------------------------------------------------
    query = _QUERY_POSTS if source_table == "post" else _QUERY_COMMENTS
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (last_pk, SYNC_BATCH_SIZE))
        rows: list[dict[str, Any]] = cursor.fetchall()
    finally:
        cursor.close()

    logger.info(
        "process_batch: fetched %d rows from %r (last_pk=%d)",
        len(rows),
        source_table,
        last_pk,
    )

    if not rows:
        return 0

    # ------------------------------------------------------------------
    # Step 3: process each row
    # ------------------------------------------------------------------
    processed_count = 0

    for row in rows:
        row_id: int = int(row["id"])

        # ---- 3a. platform config guard --------------------------------
        try:
            assert_platform_config_exists(conn, row["platform_id"])
        except MissingPlatformConfigError as exc:
            logger.error(
                "process_batch: skipping %s id=%d — %s",
                source_table,
                row_id,
                exc,
            )
            # Advance watermark so this row is not retried indefinitely
            advance_watermark(conn, source_table, row_id, row["publish_timestamp"])
            continue

        # ---- 3b. permanent failure check ------------------------------
        if is_permanently_failed(conn, source_table, row_id):
            logger.debug(
                "process_batch: %s id=%d is permanently failed — skipping",
                source_table,
                row_id,
            )
            advance_watermark(conn, source_table, row_id, row["publish_timestamp"])
            continue

        # ---- 3c. extract text content ---------------------------------
        if source_table == "post":
            text: str = row.get("body") or row.get("title") or ""
        else:
            text = row["comment_text"]

        # ---- 3d. chunk text -------------------------------------------
        try:
            chunks = chunk_text(text)
        except Exception as chunk_exc:  # noqa: BLE001
            logger.error(
                "process_batch: chunking failed for %s id=%d — %s",
                source_table,
                row_id,
                chunk_exc,
            )
            log_failure(conn, source_table, row_id, str(chunk_exc), DLQ_MAX_RETRIES)
            advance_watermark(conn, source_table, row_id, row["publish_timestamp"])
            continue

        # ---- 3e. embed + upsert each chunk ----------------------------
        embed_failed = False

        for chunk_index, chunk_str in chunks:
            vector: list[float] | None = None
            last_embed_exc: Exception | None = None

            for attempt in range(DLQ_MAX_RETRIES):
                try:
                    vector = embedder.embed(chunk_str)
                    last_embed_exc = None
                    break
                except Exception as embed_exc:  # noqa: BLE001
                    last_embed_exc = embed_exc
                    logger.warning(
                        "process_batch: embed attempt %d/%d failed for "
                        "%s id=%d chunk=%d — %s",
                        attempt + 1,
                        DLQ_MAX_RETRIES,
                        source_table,
                        row_id,
                        chunk_index,
                        embed_exc,
                    )

            if last_embed_exc is not None:
                # All retries exhausted — record permanent failure and stop
                # processing further chunks for this row.
                logger.error(
                    "process_batch: all %d embed retries exhausted for "
                    "%s id=%d chunk=%d — logging to DLQ",
                    DLQ_MAX_RETRIES,
                    source_table,
                    row_id,
                    chunk_index,
                )
                log_failure(
                    conn,
                    source_table,
                    row_id,
                    str(last_embed_exc),
                    DLQ_MAX_RETRIES,
                )
                embed_failed = True
                break  # break out of chunk loop

            # Embed succeeded — build payload and upsert into Qdrant.
            assert vector is not None  # narrowing for type checkers
            payload = build_payload(row, chunk_index, source_table, chunk_str)
            upsert_point(qdrant_client, payload["embedding_id"], vector, payload)
            logger.debug(
                "process_batch: upserted %s id=%d chunk=%d embedding_id=%s",
                source_table,
                row_id,
                chunk_index,
                payload["embedding_id"],
            )

        # ---- 3f. advance watermark ------------------------------------
        advance_watermark(conn, source_table, row_id, row["publish_timestamp"])

        if not embed_failed:
            processed_count += 1

    logger.info(
        "process_batch: completed — source_table=%r processed=%d/%d",
        source_table,
        processed_count,
        len(rows),
    )
    return processed_count
