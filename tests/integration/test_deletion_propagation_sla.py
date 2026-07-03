"""
Integration test: deletion propagation SLA.

Verifies that after a MySQL delete is recorded in ``content_deletions``, the
Qdrant ``content_embeddings`` points are cleaned up within 60 seconds by the
``poll_and_propagate_deletions`` worker.

Requires live MySQL and Qdrant services.  The entire module is skipped if
either ``MYSQL_DSN`` or ``QDRANT_URL`` is not set in the environment.

Validates: Requirements 8.5
"""

from __future__ import annotations

import os
import time
import urllib.parse
import uuid

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard — skip everything unless both env vars are present.
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "")

if not MYSQL_DSN:
    pytest.skip(
        "MYSQL_DSN environment variable not set — skipping deletion propagation SLA tests.",
        allow_module_level=True,
    )

if not QDRANT_URL:
    pytest.skip(
        "QDRANT_URL environment variable not set — skipping deletion propagation SLA tests.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Conditional imports (only reached when env vars are configured)
# ---------------------------------------------------------------------------

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed",
)

qdrant_module = pytest.importorskip(
    "qdrant_client",
    reason="qdrant-client package is not installed",
)
QdrantClient = qdrant_module.QdrantClient

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from src.pipeline.deletion_worker import poll_and_propagate_deletions  # noqa: E402
from src.vector_db.collection import COLLECTION_NAME  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None

# Unique marker used to identify test-created rows so teardown stays isolated.
_TEST_MARKER = f"__test_deletion_sla_{uuid.uuid4().hex[:8]}__"

# Polling parameters: 30 iterations × 2 s = 60-second window
_POLL_ITERATIONS = 30
_POLL_INTERVAL_SECONDS = 2


# ---------------------------------------------------------------------------
# DSN parser (same pattern as test_schema_smoke.py)
# ---------------------------------------------------------------------------


def _parse_dsn(dsn: str) -> dict:
    """Parse a DSN of the form ``mysql://user:password@host:port/database``."""
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
    """Open one MySQL connection for the entire module; close on teardown."""
    params = _parse_dsn(MYSQL_DSN)
    conn = mysql_connector.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
        autocommit=False,
    )
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def qdrant_client():
    """Return a QdrantClient connected to the configured Qdrant instance."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


# ---------------------------------------------------------------------------
# Helper: run a query with optional parameters
# ---------------------------------------------------------------------------


def _execute(conn, sql: str, params: tuple = ()) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
    finally:
        cursor.close()


def _fetchone(conn, sql: str, params: tuple = ()):
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestDeletionPropagationSLA:
    """Validate that deletion propagation reaches Qdrant within 60 seconds."""

    def test_deletion_propagates_to_qdrant_within_60_seconds(
        self, mysql_conn, qdrant_client
    ):
        """
        End-to-end SLA test:

        1. Insert a category, handle (using platform_id=1 from seeded data),
           and post into MySQL.
        2. Manually upsert a matching Qdrant point for that post (so there is
           something to delete).
        3. Insert a ``content_deletions`` row with ``propagated_at=NULL``.
        4. Poll ``poll_and_propagate_deletions`` every 2 seconds for up to 60
           seconds and assert that the Qdrant point count drops to 0.
        5. Teardown: remove all test-specific rows from MySQL.

        Validates: Requirements 8.5
        """
        conn = mysql_conn
        client = qdrant_client

        # ------------------------------------------------------------------
        # 1. Seed: category
        # ------------------------------------------------------------------
        _execute(
            conn,
            "INSERT IGNORE INTO categories (name) VALUES (%s)",
            (_TEST_MARKER,),
        )
        conn.commit()

        cat_row = _fetchone(
            conn,
            "SELECT id FROM categories WHERE name = %s",
            (_TEST_MARKER,),
        )
        assert cat_row, "Failed to insert/find test category"
        category_id = cat_row["id"]

        # ------------------------------------------------------------------
        # 2. Seed: handle (platform_id=1 is always seeded as 'youtube')
        # ------------------------------------------------------------------
        platform_id = 1
        _execute(
            conn,
            "INSERT IGNORE INTO handles "
            "  (category_id, platform_id, platform_native_handle, display_name) "
            "VALUES (%s, %s, %s, %s)",
            (category_id, platform_id, _TEST_MARKER, _TEST_MARKER),
        )
        conn.commit()

        handle_row = _fetchone(
            conn,
            "SELECT id FROM handles WHERE platform_native_handle = %s",
            (_TEST_MARKER,),
        )
        assert handle_row, "Failed to insert/find test handle"
        handle_id = handle_row["id"]

        # ------------------------------------------------------------------
        # 3. Seed: post
        # ------------------------------------------------------------------
        _execute(
            conn,
            "INSERT IGNORE INTO posts "
            "  (handle_id, platform_id, platform_native_post_id,"
            "   post_type, body, publish_timestamp) "
            "VALUES (%s, %s, %s, 'post', %s, NOW())",
            (handle_id, platform_id, _TEST_MARKER, _TEST_MARKER),
        )
        conn.commit()

        post_row = _fetchone(
            conn,
            "SELECT id FROM posts WHERE platform_native_post_id = %s",
            (_TEST_MARKER,),
        )
        assert post_row, "Failed to insert/find test post"
        post_id = int(post_row["id"])

        # ------------------------------------------------------------------
        # 4. Manually insert a Qdrant point so there is something to delete
        # ------------------------------------------------------------------
        embedding_id = str(uuid.uuid4())
        dummy_vector = [0.0] * 1536
        payload = {
            "embedding_id": embedding_id,
            "source_table": "post",
            "source_record_id": post_id,
            "chunk_index": 0,
            "content_preview": _TEST_MARKER,
            "category_id": category_id,
            "category_name": _TEST_MARKER,
            "platform_id": platform_id,
            "platform_code": "youtube",
            "handle_id": handle_id,
            "handle_name": _TEST_MARKER,
            "post_id": post_id,
            "publish_timestamp": int(time.time()),
            "post_type": "post",
        }
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                qdrant_module.models.PointStruct(
                    id=embedding_id,
                    vector=dummy_vector,
                    payload=payload,
                )
            ],
        )

        # Confirm the point was inserted
        initial_count = client.count(
            collection_name=COLLECTION_NAME,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_table",
                        match=MatchValue(value="post"),
                    ),
                    FieldCondition(
                        key="source_record_id",
                        match=MatchValue(value=post_id),
                    ),
                ]
            ),
            exact=True,
        ).count
        assert initial_count >= 1, (
            f"Expected at least 1 Qdrant point for post_id={post_id} before deletion, "
            f"got {initial_count}"
        )

        # ------------------------------------------------------------------
        # 5. Record deletion in content_deletions (propagated_at=NULL)
        # ------------------------------------------------------------------
        _execute(
            conn,
            "INSERT INTO content_deletions "
            "  (source_table, source_record_id, propagated_at) "
            "VALUES ('post', %s, NULL)",
            (post_id,),
        )
        conn.commit()

        # ------------------------------------------------------------------
        # 6. Poll and assert the point is removed within 60 seconds
        # ------------------------------------------------------------------
        propagated = False
        for _ in range(_POLL_ITERATIONS):
            poll_and_propagate_deletions(conn, client)

            current_count = client.count(
                collection_name=COLLECTION_NAME,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="source_table",
                            match=MatchValue(value="post"),
                        ),
                        FieldCondition(
                            key="source_record_id",
                            match=MatchValue(value=post_id),
                        ),
                    ]
                ),
                exact=True,
            ).count

            if current_count == 0:
                propagated = True
                break

            time.sleep(_POLL_INTERVAL_SECONDS)

        assert propagated, (
            f"Qdrant point for post_id={post_id} was not removed within "
            f"{_POLL_ITERATIONS * _POLL_INTERVAL_SECONDS} seconds."
        )

        # ------------------------------------------------------------------
        # 7. Teardown: remove test data from MySQL
        # ------------------------------------------------------------------
        # content_deletions
        _execute(
            conn,
            "DELETE FROM content_deletions WHERE source_table = 'post' AND source_record_id = %s",
            (post_id,),
        )
        # posts (must delete before handle/category due to FK RESTRICT)
        _execute(
            conn,
            "DELETE FROM posts WHERE platform_native_post_id = %s",
            (_TEST_MARKER,),
        )
        # handles
        _execute(
            conn,
            "DELETE FROM handles WHERE platform_native_handle = %s",
            (_TEST_MARKER,),
        )
        # categories
        _execute(
            conn,
            "DELETE FROM categories WHERE name = %s",
            (_TEST_MARKER,),
        )
        conn.commit()
