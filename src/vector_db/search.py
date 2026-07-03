"""
Filtered approximate nearest-neighbour search for the content_embeddings collection.

This module provides a single entry-point for ANN search against Qdrant with
optional payload filtering. Supported filter keys are ``category_id``,
``platform_id``, ``publish_timestamp_gte``, and ``publish_timestamp_lte``.
Any unrecognised keys in the ``filters`` dict are silently ignored.
"""

import logging
from typing import Optional

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    Range,
    SearchParams,
)

from src.vector_db.collection import COLLECTION_NAME

logger = logging.getLogger(__name__)


def filtered_ann_search(
    client,
    query_vector: list[float],
    filters: Optional[dict],
    limit: int = 100,
) -> list:
    """Perform a filtered approximate nearest-neighbour search in Qdrant.

    Builds a Qdrant :class:`~qdrant_client.models.Filter` from the provided
    ``filters`` dict and executes a vector similarity search against the
    ``content_embeddings`` collection.

    Supported filter keys
    ---------------------
    ``category_id`` (int)
        Exact match on the ``category_id`` payload field.
    ``platform_id`` (int)
        Exact match on the ``platform_id`` payload field.
    ``publish_timestamp_gte`` (int, Unix epoch seconds)
        Range lower bound (inclusive) on the ``publish_timestamp`` payload field.
    ``publish_timestamp_lte`` (int, Unix epoch seconds)
        Range upper bound (inclusive) on the ``publish_timestamp`` payload field.

    Any other keys present in ``filters`` are silently ignored.

    Args:
        client: An authenticated QdrantClient instance.
        query_vector: A 1536-dimensional query embedding.
        filters: A dict of filter criteria, or ``None`` / empty dict for an
            unfiltered search.
        limit: Maximum number of results to return. Capped internally at 100.

    Returns:
        A list of :class:`~qdrant_client.models.ScoredPoint` results ordered
        by descending cosine similarity score.
    """
    must_conditions = []

    if filters:
        if "category_id" in filters:
            must_conditions.append(
                FieldCondition(
                    key="category_id",
                    match=MatchValue(value=filters["category_id"]),
                )
            )

        if "platform_id" in filters:
            must_conditions.append(
                FieldCondition(
                    key="platform_id",
                    match=MatchValue(value=filters["platform_id"]),
                )
            )

        range_kwargs: dict = {}
        if "publish_timestamp_gte" in filters:
            range_kwargs["gte"] = filters["publish_timestamp_gte"]
        if "publish_timestamp_lte" in filters:
            range_kwargs["lte"] = filters["publish_timestamp_lte"]

        if range_kwargs:
            must_conditions.append(
                FieldCondition(
                    key="publish_timestamp",
                    range=Range(**range_kwargs),
                )
            )

    filter_obj = Filter(must=must_conditions) if must_conditions else None

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=filter_obj,
        limit=min(limit, 100),
        with_payload=True,
        search_params=SearchParams(hnsw_ef=128),
    )

    return results
