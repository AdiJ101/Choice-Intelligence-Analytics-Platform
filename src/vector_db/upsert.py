"""
Qdrant upsert helpers for the content_embeddings collection.

This module provides two public functions:

- ``build_payload``: Constructs the full 14-field Qdrant payload dict from a
  MySQL row dict, a chunk index, a source-table discriminant, and the chunk
  text that was embedded.

- ``upsert_point``: Writes a single embedding point (vector + payload) into
  the Qdrant ``content_embeddings`` collection.  The operation is idempotent —
  Qdrant overwrites any existing point that shares the same ``embedding_id``.

Requirements addressed: 6.1, 6.2, 6.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client.models import PointStruct

from src.vector_db.collection import COLLECTION_NAME


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_payload(
    row: dict[str, Any],
    chunk_index: int,
    source_table: str,
    chunk_text: str,
) -> dict[str, Any]:
    """Construct the 14-field Qdrant payload from a MySQL row dict.

    Args:
        row: A dict whose keys match the column names returned by the query
             that fetched the row.  For ``source_table == 'post'`` the query
             must JOIN ``categories``, ``platforms``, and ``handles`` so that
             ``category_id``, ``category_name``, ``platform_code``, and
             ``handle_name`` are present alongside the native post columns.
             For ``source_table == 'comment'`` the same enriched columns are
             expected (the comment query should JOIN through its parent post).
        chunk_index: Zero-based integer identifying which chunk of the source
             text this embedding represents (0 for single-chunk records).
        source_table: Either ``"post"`` or ``"comment"``.
        chunk_text: The text fragment that was embedded.  The first 500
             characters are stored as ``content_preview``.

    Returns:
        A dict with exactly 14 keys matching the Qdrant payload schema
        defined in the design document.
    """
    # ------------------------------------------------------------------
    # publish_timestamp → Unix epoch int (UTC seconds)
    # ------------------------------------------------------------------
    ts: datetime = row["publish_timestamp"]
    if ts.tzinfo is None:
        # Naive datetime — treat as UTC
        epoch_seconds = int(ts.replace(tzinfo=timezone.utc).timestamp())
    else:
        # Timezone-aware datetime — convert directly
        epoch_seconds = int(ts.timestamp())

    # ------------------------------------------------------------------
    # source-table-specific fields
    # ------------------------------------------------------------------
    if source_table == "post":
        post_id: int = int(row["id"])
        post_type: str = row["post_type"]
    else:  # comment
        post_id = int(row["post_id"])
        post_type = "comment"

    return {
        "source_table": source_table,
        "source_record_id": int(row["id"]),
        "chunk_index": chunk_index,
        "category_id": int(row["category_id"]),
        "category_name": str(row["category_name"]),
        "platform_id": int(row["platform_id"]),
        "platform_code": str(row["platform_code"]),
        "handle_id": int(row["handle_id"]),
        "handle_name": str(row["handle_name"]),
        "post_id": post_id,
        "publish_timestamp": epoch_seconds,
        "post_type": post_type,
        "content_preview": chunk_text[:500],
        "embedding_id": str(uuid.uuid4()),
    }


def upsert_point(
    client: Any,
    embedding_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> None:
    """Write a single embedding point into the Qdrant collection.

    The call is idempotent: if a point with ``embedding_id`` already exists
    in the collection, Qdrant overwrites it in place.

    Args:
        client: An authenticated ``QdrantClient`` instance.
        embedding_id: The UUID string that uniquely identifies this point.
             Should match the ``embedding_id`` field already stored in
             ``payload`` so the two stay in sync.
        vector: A 1536-dimensional list of floats (the dense embedding).
        payload: The 14-field dict produced by :func:`build_payload`.
    """
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=embedding_id,
                vector=vector,
                payload=payload,
            )
        ],
    )
