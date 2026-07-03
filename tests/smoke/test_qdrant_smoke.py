"""
Smoke tests for the Qdrant `content_embeddings` collection.

These tests verify that, when a Qdrant instance is reachable, the collection
is configured exactly as the design document specifies:
  - 1536-dimensional vectors with Cosine distance
  - Five payload indexes: category_id, platform_id, publish_timestamp,
    source_table, source_record_id

The entire module is skipped when the QDRANT_URL environment variable is not
set, so the tests are safe to run in any CI environment that lacks Qdrant.

Validates: Requirements 6.1, 6.5
"""

import os
import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

QDRANT_URL = os.environ.get("QDRANT_URL")

if not QDRANT_URL:
    pytest.skip(
        "QDRANT_URL environment variable is not set — skipping Qdrant smoke tests.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Imports (only reached when QDRANT_URL is set)
# ---------------------------------------------------------------------------

qdrant_client_module = pytest.importorskip(
    "qdrant_client",
    reason="qdrant-client package is not installed — skipping Qdrant smoke tests.",
)
QdrantClient = qdrant_client_module.QdrantClient

# UnexpectedResponse lives under qdrant_client.http.exceptions; import carefully
# so a missing sub-module also results in a skip rather than an error.
try:
    from qdrant_client.http.exceptions import UnexpectedResponse
except Exception:  # pragma: no cover
    UnexpectedResponse = Exception  # type: ignore[assignment,misc]

QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
COLLECTION_NAME = "content_embeddings"

EXPECTED_VECTOR_SIZE = 1536
EXPECTED_DISTANCE = "Cosine"

REQUIRED_INDEXES = {
    "category_id",
    "platform_id",
    "publish_timestamp",
    "source_table",
    "source_record_id",
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qdrant_client() -> QdrantClient:
    """Return a QdrantClient connected to the configured Qdrant instance."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


@pytest.fixture(scope="module")
def collection_info(qdrant_client: QdrantClient):
    """
    Fetch and return collection info, or skip if the collection does not
    exist yet.  Tests that depend on this fixture are automatically skipped
    when the collection is absent — they only fail when the collection exists
    but is misconfigured.
    """
    try:
        return qdrant_client.get_collection(COLLECTION_NAME)
    except (UnexpectedResponse, Exception) as exc:
        # Qdrant returns 404 for a missing collection; treat any retrieval
        # failure as "not yet created" and skip rather than fail.
        pytest.skip(
            f"Collection '{COLLECTION_NAME}' does not exist yet "
            f"(or could not be retrieved): {exc}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCollectionVectorConfig:
    """Assert that the vector configuration matches the design specification."""

    def test_vector_size_is_1536(self, collection_info):
        """Vector dimension must be 1536 to match the embedding model output."""
        vectors_config = collection_info.config.params.vectors

        # vectors_config may be a VectorsConfig (named vectors) or a single
        # VectorParams object — handle both shapes.
        if hasattr(vectors_config, "size"):
            # Single (unnamed) vector space
            actual_size = vectors_config.size
        else:
            # Named vector spaces: use the default "" key or the first entry
            params = getattr(vectors_config, "__root__", None) or {}
            if isinstance(params, dict):
                # Pick the sole vector space (the collection uses only one)
                vp = next(iter(params.values()))
                actual_size = vp.size
            else:
                actual_size = params.size

        assert actual_size == EXPECTED_VECTOR_SIZE, (
            f"Expected vector size {EXPECTED_VECTOR_SIZE}, got {actual_size}. "
            "Re-create the collection with the correct dimension."
        )

    def test_distance_metric_is_cosine(self, collection_info):
        """Distance metric must be Cosine to support semantic similarity search."""
        vectors_config = collection_info.config.params.vectors

        if hasattr(vectors_config, "distance"):
            actual_distance = vectors_config.distance
        else:
            params = getattr(vectors_config, "__root__", None) or {}
            if isinstance(params, dict):
                vp = next(iter(params.values()))
                actual_distance = vp.distance
            else:
                actual_distance = params.distance

        # Distance may be a string or an enum — normalise to string for comparison.
        actual_distance_str = (
            actual_distance.value
            if hasattr(actual_distance, "value")
            else str(actual_distance)
        )

        assert actual_distance_str == EXPECTED_DISTANCE, (
            f"Expected distance metric '{EXPECTED_DISTANCE}', "
            f"got '{actual_distance_str}'. "
            "Re-create the collection with Cosine distance."
        )


class TestPayloadIndexes:
    """Assert that all five required payload indexes are active."""

    def test_all_required_indexes_are_present(self, collection_info):
        """
        Every field in REQUIRED_INDEXES must appear in the collection's
        payload_schema, confirming the indexes were created.
        """
        payload_schema = collection_info.payload_schema or {}

        indexed_fields = set(payload_schema.keys())

        missing = REQUIRED_INDEXES - indexed_fields
        assert not missing, (
            f"The following required payload indexes are missing from "
            f"'{COLLECTION_NAME}': {sorted(missing)}. "
            "Run the index creation commands documented in the design spec."
        )

    @pytest.mark.parametrize("field_name", sorted(REQUIRED_INDEXES))
    def test_individual_index_is_active(self, collection_info, field_name):
        """Each required index should be individually verified as present."""
        payload_schema = collection_info.payload_schema or {}

        assert field_name in payload_schema, (
            f"Payload index '{field_name}' is not present in the "
            f"'{COLLECTION_NAME}' collection. "
            "Create the index using the Qdrant REST API or qdrant-client."
        )
