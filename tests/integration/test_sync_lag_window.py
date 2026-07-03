"""
Integration test: sync lag-window pipeline behavior.

Verifies that :func:`process_batch` picks up a freshly inserted post from
MySQL, embeds it with the provided embedder, and upserts the resulting vector
into the Qdrant ``content_embeddings`` collection — all within a single call
(simulating the lag-window behaviour without waiting real time).

The entire module is skipped when either ``MYSQL_DSN`` or ``QDRANT_URL`` is
not set in the environment, so it is safe to run in CI environments that lack
live backing services.

Validates: Requirements 7.1
"""

from __future__ import annotations

import math
import os
import re
import urllib.parse
import uuid
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "")

if not MYSQL_DSN or not QDRANT_URL:
    pytest.skip(
        "MYSQL_DSN and/or QDRANT_URL environment variables are not set — "
        "skipping sync lag-window integration tests.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Guarded imports (only reached when both env vars are set)
# ---------------------------------------------------------------------------

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed",
)

qdrant_client_mod = pytest.importorskip(
    "qdrant_client",
    reason="qdrant-client package is not installed",
)
QdrantClient = qdrant_client_mod.QdrantClient

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from src.pipeline.processor import process_batch  # noqa: E402
from src.pipeline.watermark import advance_watermark  # noqa: E402
from src.vector_db.collection import COLLECTION_NAME  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None

EMBED_DIM = 1536
# Unit-normalised constant vector: all dimensions equal 1/sqrt(1536)
_UNIT_VALUE = 1.0 / math.sqrt(EMBED_DIM)
_UNIT_VECTOR: list[float] = [_UNIT_VALUE] * EMBED_DIM

# The watermark source_table key used by process_batch for posts
_WATERMARK_KEY = "post"

# Existing seeded platform with platform_config rows (YouTube, id=1)
_PLATFORM_ID = 1

# A publish_timestamp that falls within a defined partition (p202501)
_PUBLISH_TS = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# DSN parser helper
# ---------------------------------------------------------------------------

_DSN_RE = re.compile(
    r"^(?:mysql\+mysqlconnector|mysql)://"
    r"(?P<user>[^:@]+)"
    r"(?::(?P<password>[^@]*))?"
    r"@(?P<host>[^:/]+)"
    r"(?::(?P<port>\d+))?"
    r"(?:/(?P<database>.+))?$"
)


def _parse_dsn(dsn: str) -> dict:
    """Parse a mysql:// or mysql+mysqlconnector:// DSN into connect kwargs."""
    # Try regex first (handles mysql+mysqlconnector:// or mysql://)
    match = _DSN_RE.match(dsn)
    if match:
        kwargs: dict = {
            "user": match.group("user"),
            "host": match.group("host"),
        }
        if match.group("password") is not None:
            kwargs["password"] = match.group("password")
        if match.group("port") is not None:
            kwargs["port"] = int(match.group("port"))
        if match.group("database") is not None:
            kwargs["database"] = match.group("database")
        return kwargs

    # Fallback: urllib urlparse (works for plain mysql:// with all components)
    parsed = urllib.parse.urlparse(dsn)
    return {
        "user": urllib.parse.unquote(parsed.username or "root"),
        "password": urllib.parse.unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "database": parsed.path.lstrip("/") or "choice_analytics",
    }


# ---------------------------------------------------------------------------
# Mock embedder
# ---------------------------------------------------------------------------


class _MockEmbedder:
    """Returns a deterministic unit-normalised 1536-dim vector for any input."""

    def embed(self, text: str) -> list[float]:  # noqa: ARG002
        return list(_UNIT_VECTOR)


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mysql_conn():
    """Open one MySQL connection for the entire module; close on teardown."""
    params = _parse_dsn(MYSQL_DSN)
    conn = mysql_connector.connect(**params)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def qdrant_client():
    """Return a QdrantClient connected to the configured Qdrant instance."""
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


def test_new_post_is_embedded_after_process_batch(mysql_conn, qdrant_client):
    """
    A post inserted into MySQL is picked up by process_batch() and upserted
    into the Qdrant content_embeddings collection within a single call.

    Validates: Requirements 7.1
    """
    mock_embedder = _MockEmbedder()

    # ------------------------------------------------------------------ #
    # 1. Seed prerequisite rows                                            #
    # ------------------------------------------------------------------ #

    cursor = mysql_conn.cursor()

    # Unique names to avoid collisions with other test runs
    unique_suffix = uuid.uuid4().hex[:8]
    category_name = f"test_category_{unique_suffix}"
    handle_name = f"test_handle_{unique_suffix}"
    platform_native_handle = f"test_native_handle_{unique_suffix}"
    platform_native_post_id = str(uuid.uuid4())

    # Insert a test category
    cursor.execute(
        "INSERT INTO categories (name) VALUES (%s)",
        (category_name,),
    )
    category_id = cursor.lastrowid

    # Insert a test handle (uses seeded platform id=1 / YouTube)
    cursor.execute(
        "INSERT INTO handles (category_id, platform_id, platform_native_handle, display_name)"
        " VALUES (%s, %s, %s, %s)",
        (category_id, _PLATFORM_ID, platform_native_handle, handle_name),
    )
    handle_id = cursor.lastrowid

    # Insert a test post
    cursor.execute(
        "INSERT INTO posts"
        " (handle_id, platform_id, platform_native_post_id, post_type,"
        "  body, publish_timestamp)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (
            handle_id,
            _PLATFORM_ID,
            platform_native_post_id,
            "post",
            "Integration test post body for sync lag-window test.",
            _PUBLISH_TS.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    post_id = cursor.lastrowid
    mysql_conn.commit()
    cursor.close()

    # ------------------------------------------------------------------ #
    # 2. Ensure the sync_watermarks row for "post" exists and is reset     #
    # ------------------------------------------------------------------ #

    cursor = mysql_conn.cursor()
    # Upsert the watermark row so last_pk = 0 (ensures our new post is found)
    cursor.execute(
        "INSERT INTO sync_watermarks (source_table, last_pk, last_ts)"
        " VALUES (%s, 0, '1970-01-01 00:00:00')"
        " ON DUPLICATE KEY UPDATE last_pk = 0, last_ts = '1970-01-01 00:00:00'",
        (_WATERMARK_KEY,),
    )
    mysql_conn.commit()
    cursor.close()

    try:
        # -------------------------------------------------------------- #
        # 3. Run process_batch                                             #
        # -------------------------------------------------------------- #

        processed = process_batch(mysql_conn, qdrant_client, mock_embedder, "post")

        # -------------------------------------------------------------- #
        # 4. At least one row must have been processed                    #
        # -------------------------------------------------------------- #

        assert processed >= 1, (
            f"process_batch returned {processed}; expected at least 1 row processed"
        )

        # -------------------------------------------------------------- #
        # 5. Verify the point landed in Qdrant                           #
        # -------------------------------------------------------------- #

        result = qdrant_client.count(
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
        )

        assert result.count >= 1, (
            f"Expected at least 1 Qdrant point for source_table='post' and "
            f"source_record_id={post_id}, but found {result.count}"
        )

    finally:
        # -------------------------------------------------------------- #
        # 6. Teardown: remove test data and reset watermark               #
        # -------------------------------------------------------------- #

        cursor = mysql_conn.cursor()

        # Delete the test post (must be done before deleting handle/category)
        if post_id:
            cursor.execute(
                "DELETE FROM posts WHERE id = %s AND publish_timestamp = %s",
                (post_id, _PUBLISH_TS.strftime("%Y-%m-%d %H:%M:%S")),
            )

        # Delete the test handle
        if handle_id:
            cursor.execute("DELETE FROM handles WHERE id = %s", (handle_id,))

        # Delete the test category
        if category_id:
            cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))

        # Reset watermark back to 0 so subsequent test runs start fresh
        cursor.execute(
            "UPDATE sync_watermarks SET last_pk = 0, last_ts = '1970-01-01 00:00:00'"
            " WHERE source_table = %s",
            (_WATERMARK_KEY,),
        )

        mysql_conn.commit()
        cursor.close()
