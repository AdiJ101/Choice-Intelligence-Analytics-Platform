"""
update_handler.py — Content update handler for the Sync Pipeline.

When a Post or Comment is updated in MySQL, any previously-embedded Qdrant
points for that record are stale.  This module deletes those stale points and
re-embeds the updated record from scratch, replacing old embeddings with fresh
ones that reflect the current content.

The public function :func:`handle_content_update` orchestrates the full
delete-then-re-embed cycle and returns the number of new embedding points
written to the Qdrant ``content_embeddings`` collection.

Requirements: 7.4
"""

from __future__ import annotations

import logging
from typing import Any

import mysql.connector

from src.pipeline.chunker import chunk_text
from src.vector_db.delete import delete_points_by_source
from src.vector_db.upsert import build_payload, upsert_point

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_SELECT_POST = (
    "SELECT "
    "  p.id, p.handle_id, p.platform_id, p.post_type, p.body, p.title, "
    "  p.publish_timestamp, h.category_id, c.name AS category_name, "
    "  pl.platform_code, h.display_name AS handle_name "
    "FROM posts p "
    "JOIN handles h   ON p.handle_id   = h.id "
    "JOIN categories c ON h.category_id = c.id "
    "JOIN platforms pl ON p.platform_id  = pl.id "
    "WHERE p.id = %s"
)

_SELECT_COMMENT = (
    "SELECT "
    "  cm.id, cm.post_id, cm.comment_text, cm.publish_timestamp, "
    "  p.handle_id, p.platform_id, p.post_type, "
    "  h.category_id, c.name AS category_name, "
    "  pl.platform_code, h.display_name AS handle_name "
    "FROM comments cm "
    "JOIN posts p      ON cm.post_id     = p.id "
    "JOIN handles h    ON p.handle_id    = h.id "
    "JOIN categories c ON h.category_id  = c.id "
    "JOIN platforms pl ON p.platform_id  = pl.id "
    "WHERE cm.id = %s"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_content_update(
    conn: mysql.connector.MySQLConnection,
    qdrant_client: Any,
    embedder: Any,
    source_table: str,
    record_id: int,
) -> int:
    """Delete stale embeddings for a record and re-embed its current content.

    The function performs the following steps in order:

    1. Deletes all existing Qdrant points whose payload matches
       ``source_table`` and ``source_record_id == record_id``.
    2. Fetches the current row from MySQL (with necessary JOINs to obtain
       all payload fields required by the vector store schema).
    3. Raises :exc:`ValueError` if the record no longer exists in MySQL
       (e.g. it was deleted between the update event and this call).
    4. Extracts the embeddable text from the row, chunks it with
       :func:`~src.pipeline.chunker.chunk_text`, and embeds each chunk.
    5. Builds a Qdrant payload for each chunk via
       :func:`~src.vector_db.upsert.build_payload` and writes the point
       via :func:`~src.vector_db.upsert.upsert_point`.
    6. Returns the total number of new embedding points written.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection`.
    qdrant_client:
        An authenticated :class:`qdrant_client.QdrantClient` instance.
    embedder:
        An object with an ``embed(text: str) -> list[float]`` method
        (e.g. :class:`~src.pipeline.embedder.EmbedderClient`).
    source_table:
        Either ``"post"`` or ``"comment"`` — identifies which MySQL table
        holds the updated record.
    record_id:
        Primary key of the updated record in the named table.

    Returns
    -------
    int
        The number of new Qdrant embedding points created for this record.

    Raises
    ------
    ValueError
        If no row with ``record_id`` exists in ``{source_table}s``.
    mysql.connector.Error
        On any MySQL connectivity or query error.
    """
    logger.info(
        "Handling content update: source_table=%s, record_id=%s",
        source_table,
        record_id,
    )

    # ------------------------------------------------------------------
    # Step 1: Remove stale embeddings
    # ------------------------------------------------------------------
    delete_points_by_source(qdrant_client, source_table, record_id)
    logger.debug(
        "Stale embeddings deleted for source_table=%s, record_id=%s",
        source_table,
        record_id,
    )

    # ------------------------------------------------------------------
    # Step 2: Fetch the updated record from MySQL
    # ------------------------------------------------------------------
    if source_table == "post":
        query = _SELECT_POST
    elif source_table == "comment":
        query = _SELECT_COMMENT
    else:
        raise ValueError(
            f"Unknown source_table {source_table!r}. Expected 'post' or 'comment'."
        )

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, (record_id,))
        row: dict[str, Any] | None = cursor.fetchone()
    finally:
        cursor.close()

    # ------------------------------------------------------------------
    # Step 3: Guard — record must exist
    # ------------------------------------------------------------------
    if row is None:
        raise ValueError(
            f"Record {record_id} not found in {source_table}s"
        )

    # ------------------------------------------------------------------
    # Step 4: Determine embeddable text and chunk it
    # ------------------------------------------------------------------
    if source_table == "post":
        # Combine title and body; fall back gracefully if either is NULL
        title_part = row.get("title") or ""
        body_part = row.get("body") or ""
        text = f"{title_part}\n{body_part}".strip() if title_part else body_part
    else:  # comment
        text = row.get("comment_text") or ""

    chunks = chunk_text(text)

    # ------------------------------------------------------------------
    # Step 5: Embed each chunk and upsert into Qdrant
    # ------------------------------------------------------------------
    points_created = 0
    for chunk_index, chunk_str in chunks:
        vector = embedder.embed(chunk_str)
        payload = build_payload(row, chunk_index, source_table, chunk_str)
        upsert_point(qdrant_client, payload["embedding_id"], vector, payload)
        points_created += 1
        logger.debug(
            "Upserted chunk %d for source_table=%s, record_id=%s",
            chunk_index,
            source_table,
            record_id,
        )

    logger.info(
        "Re-embedding complete: source_table=%s, record_id=%s, points_created=%d",
        source_table,
        record_id,
        points_created,
    )

    # ------------------------------------------------------------------
    # Step 6: Return count
    # ------------------------------------------------------------------
    return points_created
