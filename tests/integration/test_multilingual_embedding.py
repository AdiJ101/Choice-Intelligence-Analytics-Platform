"""
Integration test: multilingual post embedding with content_preview validation.

Verifies that posts whose body text is written in Hindi (Devanagari),
Simplified Chinese (CJK), Arabic, and English:
  (a) embed without exceptions,
  (b) produce a Qdrant point whose ``content_preview`` payload field is a
      byte-for-byte match to ``text[:500]``, and
  (c) yield a 1536-dimensional embedding vector.

The entire module is skipped when MYSQL_DSN or QDRANT_URL is not set,
so the tests are safe to run in any CI environment that lacks live services.

Requirements: 7.6, 9.1, 9.4, 9.5
"""

import os
import urllib.parse
import uuid
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guards — must happen before any service imports
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "")

if not MYSQL_DSN:
    pytest.skip(
        "MYSQL_DSN environment variable is not set — skipping multilingual embedding tests.",
        allow_module_level=True,
    )

if not QDRANT_URL:
    pytest.skip(
        "QDRANT_URL environment variable is not set — skipping multilingual embedding tests.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Conditional imports (only reached when both env vars are set)
# ---------------------------------------------------------------------------

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed.",
)
qdrant_client_module = pytest.importorskip(
    "qdrant_client",
    reason="qdrant-client is not installed.",
)
QdrantClient = qdrant_client_module.QdrantClient

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from src.pipeline.processor import process_batch  # noqa: E402
from src.vector_db.collection import COLLECTION_NAME  # noqa: E402

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

MULTILINGUAL_TEXTS: list[tuple[str, str]] = [
    (
        "hi",
        "नमस्ते, यह एक परीक्षण पोस्ट है। ग्राहक सेवा के बारे में जानकारी।",
    ),
    (
        "zh",
        "你好，这是一个测试帖子。关于客户服务的信息。",
    ),
    (
        "ar",
        "مرحبا، هذا منشور اختبار. معلومات حول خدمة العملاء.",
    ),
    (
        "en",
        "Hello, this is a test post about customer service and product feedback.",
    ),
]

QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None

# ---------------------------------------------------------------------------
# DSN parser (mirrors the pattern used in test_schema_smoke.py)
# ---------------------------------------------------------------------------


def _parse_dsn(dsn: str) -> dict:
    """Parse mysql://user:password@host:port/database into a dict."""
    parsed = urllib.parse.urlparse(dsn)
    return {
        "user": urllib.parse.unquote(parsed.username or "root"),
        "password": urllib.parse.unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "database": parsed.path.lstrip("/") or "choice_analytics",
    }


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mysql_conn():
    """Open one MySQL connection shared by all tests in this module."""
    params = _parse_dsn(MYSQL_DSN)
    conn = mysql_connector.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
    )
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def qdrant_client():
    """Return an authenticated QdrantClient for the configured Qdrant instance."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


# ---------------------------------------------------------------------------
# Mock embedder — deterministic 1536-dim vector, no external model calls
# ---------------------------------------------------------------------------


class _MockEmbedder:
    """Deterministic mock that returns a 1536-dimensional unit-ish vector.

    The vector is built from the hash of the input text so different texts
    produce different (but reproducible) vectors, which is sufficient for
    round-trip integration testing.
    """

    DIM = 1536

    def embed(self, text: str) -> list[float]:  # noqa: D401
        """Return a deterministic 1536-dim vector for *text*."""
        seed = hash(text) & 0xFFFFFFFF
        values: list[float] = []
        state = seed
        for _ in range(self.DIM):
            # Simple LCG to generate pseudo-random floats in [-1, 1]
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            values.append((state / 0x7FFFFFFF) - 1.0)
        return values


@pytest.fixture(scope="module")
def mock_embedder() -> _MockEmbedder:
    return _MockEmbedder()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_create_category(conn) -> int:
    """Return the id of a test category, creating it if necessary."""
    name = "Integration Test Category — Multilingual"
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM categories WHERE name = %s", (name,))
        row = cursor.fetchone()
        if row:
            return int(row[0])
        cursor.execute(
            "INSERT INTO categories (name) VALUES (%s)",
            (name,),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def _get_or_create_handle(conn, category_id: int, platform_id: int) -> int:
    """Return the id of a test handle, creating it if necessary."""
    native_handle = "test_multilingual_handle"
    display_name = "Test Multilingual Handle"
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM handles WHERE platform_id = %s AND platform_native_handle = %s",
            (platform_id, native_handle),
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
        cursor.execute(
            "INSERT INTO handles (category_id, platform_id, platform_native_handle, display_name) "
            "VALUES (%s, %s, %s, %s)",
            (category_id, platform_id, native_handle, display_name),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def _get_platform_id(conn, platform_code: str = "youtube") -> int:
    """Return the id for a platform by its code (assumes seed data present)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM platforms WHERE platform_code = %s", (platform_code,)
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(
                f"Platform '{platform_code}' not found — ensure migrations have run."
            )
        return int(row[0])
    finally:
        cursor.close()


def _insert_post(conn, handle_id: int, platform_id: int, body: str, lang: str) -> int:
    """Insert a test post and return its id."""
    native_post_id = f"multilingual_test_{uuid.uuid4().hex}"
    publish_ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO posts
                (handle_id, platform_id, platform_native_post_id, post_type,
                 body, language_code, publish_timestamp)
            VALUES (%s, %s, %s, 'post', %s, %s, %s)
            """,
            (handle_id, platform_id, native_post_id, body, lang, publish_ts),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()


def _delete_post(conn, post_id: int) -> None:
    """Hard-delete a test post by primary key."""
    cursor = conn.cursor()
    try:
        # Partition key (publish_timestamp) must be specified for DELETE on
        # partitioned table; use a range that covers the test date.
        cursor.execute(
            "DELETE FROM posts WHERE id = %s AND publish_timestamp >= '2025-01-01'",
            (post_id,),
        )
        conn.commit()
    finally:
        cursor.close()


def _reset_watermark(conn) -> None:
    """Reset the post watermark to 0 so process_batch picks up all test rows."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE sync_watermarks SET last_pk = 0, last_ts = '1970-01-01 00:00:00' "
            "WHERE source_table = 'posts'",
        )
        conn.commit()
    finally:
        cursor.close()


def _scroll_points_by_source_record_id(
    client: QdrantClient, source_record_id: int
) -> list:
    """Return all Qdrant points whose payload.source_record_id == source_record_id."""
    result = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="source_record_id",
                    match=MatchValue(value=source_record_id),
                )
            ]
        ),
        with_payload=True,
        with_vectors=True,
        limit=20,
    )
    # scroll() returns (list[ScoredPoint], next_page_offset)
    points, _next = result
    return points


# ---------------------------------------------------------------------------
# Main integration test
# ---------------------------------------------------------------------------


def test_multilingual_posts_embed_with_correct_content_preview(
    mysql_conn,
    qdrant_client,
    mock_embedder,
):
    """
    For each language in MULTILINGUAL_TEXTS:
      1. Insert a post with that body text.
      2. Run process_batch() with the mock embedder.
      3. Assert the Qdrant point exists, content_preview == text[:500],
         and the vector dimension is 1536.

    Validates: Requirements 7.6, 9.1, 9.4, 9.5
    """
    platform_id = _get_platform_id(mysql_conn, "youtube")
    category_id = _get_or_create_category(mysql_conn)
    handle_id = _get_or_create_handle(mysql_conn, category_id, platform_id)

    inserted_post_ids: list[int] = []

    try:
        for lang, text in MULTILINGUAL_TEXTS:
            # ------------------------------------------------------------------
            # Reset watermark so process_batch sees this fresh post
            # ------------------------------------------------------------------
            _reset_watermark(mysql_conn)

            # ------------------------------------------------------------------
            # Insert test post
            # ------------------------------------------------------------------
            post_id = _insert_post(mysql_conn, handle_id, platform_id, text, lang)
            inserted_post_ids.append(post_id)

            # ------------------------------------------------------------------
            # Run the sync pipeline
            # ------------------------------------------------------------------
            process_batch(mysql_conn, qdrant_client, mock_embedder, "post")

            # ------------------------------------------------------------------
            # Query Qdrant for the embedded point
            # ------------------------------------------------------------------
            points = _scroll_points_by_source_record_id(qdrant_client, post_id)

            assert len(points) >= 1, (
                f"Expected at least 1 Qdrant point for post_id={post_id} "
                f"(lang={lang!r}), found {len(points)}."
            )

            point = points[0]

            # (b) content_preview must be byte-for-byte identical to text[:500]
            expected_preview = text[:500]
            actual_preview = point.payload.get("content_preview")
            assert actual_preview == expected_preview, (
                f"content_preview mismatch for lang={lang!r}.\n"
                f"  Expected: {expected_preview!r}\n"
                f"  Actual:   {actual_preview!r}"
            )

            # (c) vector dimension must be 1536
            vector = point.vector
            assert len(vector) == 1536, (
                f"Expected 1536-dimensional vector for lang={lang!r}, "
                f"got {len(vector)}."
            )

    finally:
        # ------------------------------------------------------------------
        # Teardown: delete all test posts inserted during this test
        # ------------------------------------------------------------------
        for post_id in inserted_post_ids:
            _delete_post(mysql_conn, post_id)
