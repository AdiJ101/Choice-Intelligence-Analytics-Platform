"""
Qdrant point deletion for the content_embeddings collection.

This module provides functionality to delete embedding points from Qdrant
by source table and source record ID. Deletion is idempotent — deleting
points that do not exist is a safe no-op in Qdrant.
"""

import logging

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
)

from src.vector_db.collection import COLLECTION_NAME

logger = logging.getLogger(__name__)


def delete_points_by_source(client, source_table: str, source_record_id: int) -> None:
    """Delete all Qdrant points associated with a given source record.

    Matches points whose payload contains both ``source_table == source_table``
    and ``source_record_id == source_record_id`` and removes them from the
    ``content_embeddings`` collection.

    This operation is idempotent: if no matching points exist the call
    succeeds silently without raising an error.

    Args:
        client: An authenticated QdrantClient instance.
        source_table: The originating MySQL table name (e.g. ``"post"`` or
            ``"comment"``).
        source_record_id: The primary key of the originating MySQL row.
    """
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="source_table",
                        match=MatchValue(value=source_table),
                    ),
                    FieldCondition(
                        key="source_record_id",
                        match=MatchValue(value=source_record_id),
                    ),
                ]
            )
        ),
    )
    logger.info(
        "Deleted embeddings for source_table=%s, source_record_id=%s",
        source_table,
        source_record_id,
    )
