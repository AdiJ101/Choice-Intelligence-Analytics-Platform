"""
Qdrant collection management for the content_embeddings collection.

This module provides functionality to create and configure the Qdrant vector
collection used to store content embeddings for the Customer Intelligence &
Analytics Platform. Collection creation is idempotent — calling create_collection
when the collection already exists is a safe no-op.
"""

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "content_embeddings"


def create_collection(client: QdrantClient) -> None:
    """Create the content_embeddings Qdrant collection if it does not already exist.

    The collection is configured with:
    - 1536-dimensional vectors using cosine distance
    - HNSW index with m=16, ef_construct=200, full_scan_threshold=10000
    - Optimizer with 4 default segments for balanced throughput

    This function is idempotent: if the collection already exists it returns
    immediately without making any changes.

    Args:
        client: An authenticated QdrantClient instance pointing at the target
                Qdrant server.
    """
    if client.collection_exists(COLLECTION_NAME):
        logger.info("Collection '%s' already exists — skipping creation.", COLLECTION_NAME)
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=200,
            full_scan_threshold=10000,
        ),
        optimizers_config=OptimizersConfigDiff(default_segment_number=4),
    )
    logger.info("Collection '%s' created successfully.", COLLECTION_NAME)
