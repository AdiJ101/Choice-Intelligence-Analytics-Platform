"""
Qdrant payload index management for the content_embeddings collection.

This module creates the five payload indexes required for efficient filtered
ANN search on the content_embeddings collection.  All index creation calls
are idempotent — if an index already exists the call is treated as a no-op.
"""

import logging

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import PayloadSchemaType

from src.vector_db.collection import COLLECTION_NAME

logger = logging.getLogger(__name__)

# Ordered list of (field_name, schema_type) pairs for the five payload indexes.
_PAYLOAD_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("category_id", PayloadSchemaType.INTEGER),
    ("platform_id", PayloadSchemaType.INTEGER),
    ("publish_timestamp", PayloadSchemaType.INTEGER),
    ("source_table", PayloadSchemaType.KEYWORD),
    ("source_record_id", PayloadSchemaType.INTEGER),
]


def create_payload_indexes(client: QdrantClient) -> None:
    """Create the required payload indexes on the content_embeddings collection.

    Creates five indexes that enable efficient filtered ANN queries by
    category, platform, timestamp, source type, and source record ID.

    Each index creation is idempotent: if the index already exists on the
    collection the error is caught and the call is treated as a no-op.

    Args:
        client: An authenticated QdrantClient instance pointing at the target
                Qdrant server.
    """
    for field_name, field_schema in _PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=field_schema,
            )
            logger.info("Created payload index on %s", field_name)
        except UnexpectedResponse as exc:
            # Qdrant returns a 4xx response when the index already exists;
            # treat this as a no-op rather than a hard failure.
            logger.info("Payload index on %s already exists", field_name)
            logger.debug(
                "UnexpectedResponse suppressed for field '%s': %s", field_name, exc
            )
