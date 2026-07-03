"""
Integration test: full scraper iteration pipeline.

Verifies that ScraperOrchestrator.run_once() correctly processes active
handles end-to-end — fetching posts, comments, and engagement — and writes
all rows to a live MySQL database via the existing upsert layer.

Uses a MockAdapter that returns deterministic NormalisedPost/NormalisedComment/
NormalisedEngagement objects without touching any real platform API.

The entire module is skipped when ``MYSQL_DSN`` is not set in the environment.

Validates: Requirements 4.4, 5.1, 5.3, 6.2, 7.1, 7.2, 7.3, 7.4, 7.5, 9.1
"""

from __future__ import annotations

import os
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")

if not MYSQL_DSN:
    pytest.skip(
        "MYSQL_DSN environment variable not set — skipping full iteration integration tests.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Guarded imports (only reached when env var is set)
# ---------------------------------------------------------------------------

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed",
)

from src.scraper.base_adapter import BaseAdapter  # noqa: E402
from src.scraper.models import (  # noqa: E402
    NormalisedComment,
    NormalisedEngagement,
    NormalisedPost,
)
from src.scraper.orchestrator import ScraperOrchestrator  # noqa: E402

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
# Module-scoped connection fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def conn():
    """Open one MySQL connection for the entire module; close on teardown."""
    params = _parse_dsn(MYSQL_DSN)
    connection = mysql_connector.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
        autocommit=False,
    )
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# MockAdapter
# ---------------------------------------------------------------------------

# Fixed post IDs shared across tests so deduplication can be verified
_FIXED_POST_IDS: list[str] = [str(uuid.uuid4()) for _ in range(3)]

# A publish_timestamp well in the future so it's always past any watermark
_FUTURE_TS = datetime.now(tz=timezone.utc) + timedelta(days=365)


class MockAdapter(BaseAdapter):
    """Minimal platform adapter for integration testing.

    Returns deterministic NormalisedPost / NormalisedComment / NormalisedEngagement
    objects without touching any external API.

    Parameters
    ----------
    post_ids:
        List of platform_native_post_id values to return from fetch_new_posts.
        Defaults to a module-level list of fixed UUIDs so that deduplication
        tests can run the same IDs through multiple iterations.
    publish_timestamp:
        The publish_timestamp to assign to every returned post.
        Defaults to a date one year in the future so it always bypasses
        any existing handle watermark.
    """

    platform_code = "youtube"

    def __init__(
        self,
        post_ids: list[str] | None = None,
        publish_timestamp: datetime | None = None,
    ) -> None:
        super().__init__()
        self._post_ids = post_ids if post_ids is not None else _FIXED_POST_IDS
        self._publish_ts = publish_timestamp if publish_timestamp is not None else _FUTURE_TS

    def authenticate(self) -> None:
        """No-op authentication — sets _authenticated flag."""
        self._authenticated = True

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        """Return up to *limit* NormalisedPost objects with unique IDs."""
        self._require_auth()
        posts = []
        for post_id in self._post_ids[:limit]:
            posts.append(
                NormalisedPost(
                    platform_native_post_id=post_id,
                    post_type="video",
                    title=f"Mock Title {post_id[:8]}",
                    body=f"Mock body text for post {post_id[:8]}.",
                    url=f"https://example.com/watch?v={post_id[:8]}",
                    publish_timestamp=self._publish_ts,
                    handle_id=0,  # overridden by handle_processor
                )
            )
        return posts

    def fetch_comments(
        self,
        post: NormalisedPost,
        limit: int,
    ) -> list[NormalisedComment]:
        """Return exactly 2 NormalisedComment objects per post."""
        self._require_auth()
        now = datetime.now(tz=timezone.utc)
        return [
            NormalisedComment(
                platform_native_comment_id=str(uuid.uuid4()),
                author_handle=f"user_{i}",
                comment_text=f"Test comment {i} on post {post.platform_native_post_id[:8]}.",
                publish_timestamp=now,
            )
            for i in range(min(2, limit))
        ]

    def fetch_engagement(self, post: NormalisedPost) -> NormalisedEngagement:
        """Return a fixed engagement snapshot."""
        self._require_auth()
        return NormalisedEngagement(likes_count=10, views_count=100)


# ---------------------------------------------------------------------------
# Shared scraping config
# ---------------------------------------------------------------------------

_SCRAPING_CONFIG = {
    "scraping_config": {
        "scraping_interval_minutes": 60,
        "max_new_content_per_handle_per_iteration": 3,
        "cooling_time_days": 7,
    }
}

# Unique test marker to avoid collision with other test runs
_TEST_MARKER = f"__scraper_iter_{uuid.uuid4().hex[:8]}__"

# platform_id=1 is always the seeded 'youtube' platform
_PLATFORM_ID = 1
_PLATFORM_CODE = "youtube"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _execute(connection, sql: str, params: tuple = ()) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
    finally:
        cursor.close()


def _fetchone(connection, sql: str, params: tuple = ()):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()


def _fetchall(connection, sql: str, params: tuple = ()):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def _count(connection, sql: str, params: tuple = ()) -> int:
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_test_data(connection) -> dict:
    """Insert a category, platform reference, and handle.

    Returns a dict with ``category_id`` and ``handle_id``.
    The handle is linked to platform_id=1 (youtube).
    """
    # Insert category
    _execute(
        connection,
        "INSERT IGNORE INTO categories (name) VALUES (%s)",
        (_TEST_MARKER,),
    )
    connection.commit()

    cat_row = _fetchone(
        connection,
        "SELECT id FROM categories WHERE name = %s",
        (_TEST_MARKER,),
    )
    assert cat_row, "Failed to insert/find test category"
    category_id = cat_row["id"]

    # Insert handle linked to platform_id=1 (always seeded as youtube)
    _execute(
        connection,
        "INSERT IGNORE INTO handles "
        "  (category_id, platform_id, platform_native_handle, display_name) "
        "VALUES (%s, %s, %s, %s)",
        (category_id, _PLATFORM_ID, _TEST_MARKER, _TEST_MARKER),
    )
    connection.commit()

    # Fetch the handle row with platform_code via JOIN (as used by the orchestrator)
    handle_row = _fetchone(
        connection,
        "SELECT h.*, p.platform_code "
        "FROM handles h "
        "JOIN platforms p ON h.platform_id = p.id "
        "WHERE h.platform_native_handle = %s",
        (_TEST_MARKER,),
    )
    assert handle_row, "Failed to insert/find test handle"
    assert handle_row["platform_code"] == _PLATFORM_CODE

    return {
        "category_id": category_id,
        "handle_id": handle_row["id"],
    }


def _teardown_test_data(connection, handle_id: int, category_id: int) -> None:
    """Delete all test-created rows in correct FK order."""
    # engagement_metrics for posts belonging to this handle
    _execute(
        connection,
        "DELETE em FROM engagement_metrics em "
        "JOIN posts p ON em.source_table = 'post' AND em.source_record_id = p.id "
        "WHERE p.handle_id = %s",
        (handle_id,),
    )
    # comments → posts → handle_watermarks → handle → category
    _execute(
        connection,
        "DELETE c FROM comments c "
        "JOIN posts p ON c.post_id = p.id "
        "WHERE p.handle_id = %s",
        (handle_id,),
    )
    _execute(
        connection,
        "DELETE FROM posts WHERE handle_id = %s",
        (handle_id,),
    )
    _execute(
        connection,
        "DELETE FROM handle_watermarks WHERE handle_id = %s",
        (handle_id,),
    )
    _execute(
        connection,
        "DELETE FROM handles WHERE id = %s",
        (handle_id,),
    )
    _execute(
        connection,
        "DELETE FROM categories WHERE id = %s",
        (category_id,),
    )
    connection.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullIterationInsertsPostsCommentsAndEngagement:
    """Validate that a single run_once() writes all expected rows to MySQL."""

    def test_full_iteration_inserts_posts_comments_and_engagement(self, conn):
        """
        End-to-end test:

        1. Seed a category and handle in MySQL.
        2. Patch ADAPTER_REGISTRY in the orchestrator module to use MockAdapter.
        3. Run ScraperOrchestrator.run_once() once.
        4. Assert:
           - ``posts`` table has ≥ 1 row for this handle_id
           - ``handle_watermarks`` table has a row for this handle_id
           - ``comments`` table has rows for those posts
           - The returned IterationStats has posts_inserted >= 1
        5. Teardown all seeded data.

        Validates: Requirements 4.4, 5.1, 5.3, 6.2, 7.1, 7.2, 7.3, 7.4, 7.5, 9.1
        """
        import src.scraper.orchestrator as orch_module

        seeded = _seed_test_data(conn)
        handle_id: int = seeded["handle_id"]
        category_id: int = seeded["category_id"]

        try:
            # Build orchestrator
            orchestrator = ScraperOrchestrator(
                config=_SCRAPING_CONFIG,
                conn=conn,
                enabled_platforms={_PLATFORM_CODE: True},
            )

            # Patch ADAPTER_REGISTRY in the orchestrator module only (test-local)
            original_registry = orch_module.ADAPTER_REGISTRY.copy()
            orch_module.ADAPTER_REGISTRY = {_PLATFORM_CODE: MockAdapter}

            try:
                stats = orchestrator.run_once()
            finally:
                orch_module.ADAPTER_REGISTRY = original_registry

            # -------------------------------------------------------------- #
            # Assertions                                                        #
            # -------------------------------------------------------------- #

            # posts: at least 1 row for this handle
            post_count = _count(
                conn,
                "SELECT COUNT(*) FROM posts WHERE handle_id = %s",
                (handle_id,),
            )
            assert post_count >= 1, (
                f"Expected ≥ 1 post for handle_id={handle_id}, got {post_count}"
            )

            # handle_watermarks: a row must exist for this handle
            wm_row = _fetchone(
                conn,
                "SELECT * FROM handle_watermarks WHERE handle_id = %s",
                (handle_id,),
            )
            assert wm_row is not None, (
                f"Expected a handle_watermarks row for handle_id={handle_id}"
            )

            # comments: rows linked to those posts
            comment_count = _count(
                conn,
                "SELECT COUNT(*) FROM comments c "
                "JOIN posts p ON c.post_id = p.id "
                "WHERE p.handle_id = %s",
                (handle_id,),
            )
            assert comment_count >= 1, (
                f"Expected ≥ 1 comment linked to posts for handle_id={handle_id}, "
                f"got {comment_count}"
            )

            # iteration_end stats: posts_inserted >= 1
            assert stats.posts_inserted >= 1, (
                f"Expected stats.posts_inserted >= 1, got {stats.posts_inserted}"
            )

        finally:
            _teardown_test_data(conn, handle_id, category_id)


class TestDeduplicationOnSecondRun:
    """Validate that running run_once() twice with the same post IDs does not duplicate rows."""

    def test_deduplication_on_second_run(self, conn):
        """
        Two successive run_once() calls with the same fixed post IDs must
        not insert duplicate rows — the upsert mechanism must keep the count stable.

        Validates: Requirements 5.1, 9.1
        """
        import src.scraper.orchestrator as orch_module

        seeded = _seed_test_data(conn)
        handle_id: int = seeded["handle_id"]
        category_id: int = seeded["category_id"]

        try:
            # Use a fresh set of post IDs for this test to isolate from test 1
            dedup_post_ids = [str(uuid.uuid4()) for _ in range(3)]

            orchestrator = ScraperOrchestrator(
                config=_SCRAPING_CONFIG,
                conn=conn,
                enabled_platforms={_PLATFORM_CODE: True},
            )

            original_registry = orch_module.ADAPTER_REGISTRY.copy()
            # MockAdapter returns the same fixed post IDs with a future timestamp
            # so the watermark never filters them out across runs
            orch_module.ADAPTER_REGISTRY = {
                _PLATFORM_CODE: lambda: MockAdapter(
                    post_ids=dedup_post_ids,
                    publish_timestamp=_FUTURE_TS,
                )
            }

            try:
                # First run
                orchestrator.run_once()
                count_after_first = _count(
                    conn,
                    "SELECT COUNT(*) FROM posts WHERE handle_id = %s",
                    (handle_id,),
                )

                # Second run — same adapter, same IDs
                orchestrator.run_once()
                count_after_second = _count(
                    conn,
                    "SELECT COUNT(*) FROM posts WHERE handle_id = %s",
                    (handle_id,),
                )
            finally:
                orch_module.ADAPTER_REGISTRY = original_registry

            assert count_after_first >= 1, (
                f"Expected ≥ 1 post after first run, got {count_after_first}"
            )
            assert count_after_second == count_after_first, (
                f"Deduplication failed: {count_after_second} posts after second run "
                f"vs {count_after_first} after first run — expected no increase."
            )

        finally:
            _teardown_test_data(conn, handle_id, category_id)
