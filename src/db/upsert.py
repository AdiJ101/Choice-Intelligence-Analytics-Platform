"""
upsert.py — MySQL upsert and insert helpers for the Customer Intelligence
& Analytics Platform.

Provides three public functions that write scraped content and engagement
snapshots into the MySQL relational store:

* :func:`upsert_post`                — INSERT … ON DUPLICATE KEY UPDATE on
                                       the ``posts`` table; returns the
                                       resolved ``posts.id``.
* :func:`upsert_comment`             — INSERT … ON DUPLICATE KEY UPDATE on
                                       the ``comments`` table; returns
                                       ``comments.id``.
* :func:`insert_engagement_snapshot` — Plain INSERT into
                                       ``engagement_metrics``; returns the new
                                       row ``id``.

All three functions commit the transaction before returning and close the
cursor in a ``finally`` block regardless of success or failure.

**Deduplication keys**

* Posts:    ``(platform_id, platform_native_post_id, publish_timestamp)``
  — the unique key ``uq_posts_dedup`` in the partitioned ``posts`` table.
* Comments: ``(post_id, platform_native_comment_id)``
  — the unique key ``uq_comments_dedup`` in the ``comments`` table.

**Engagement metrics referential integrity**

``engagement_metrics`` uses a polymorphic ``(source_table, source_record_id)``
pattern with no true foreign-key constraint to both parent tables
simultaneously.  Referential integrity is therefore enforced here at the
application layer: :func:`insert_engagement_snapshot` raises
:class:`ValueError` when the referenced source record does not exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import mysql.connector

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_UPSERT_POST_SQL = """
INSERT INTO posts (
    handle_id,
    platform_id,
    platform_native_post_id,
    post_type,
    title,
    body,
    url,
    language_code,
    publish_timestamp,
    discovered_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    title      = VALUES(title),
    body       = VALUES(body),
    url        = VALUES(url),
    updated_at = NOW()
"""

_SELECT_POST_ID_SQL = """
SELECT id
FROM   posts
WHERE  platform_id              = %s
  AND  platform_native_post_id  = %s
  AND  publish_timestamp        = %s
"""

_UPSERT_COMMENT_SQL = """
INSERT INTO comments (
    post_id,
    platform_native_comment_id,
    author_handle,
    comment_text,
    language_code,
    publish_timestamp,
    discovered_at
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    comment_text = VALUES(comment_text),
    updated_at   = NOW()
"""

_SELECT_COMMENT_ID_SQL = """
SELECT id
FROM   comments
WHERE  post_id                     = %s
  AND  platform_native_comment_id  = %s
"""

_CHECK_POST_EXISTS_SQL    = "SELECT id FROM posts    WHERE id = %s"
_CHECK_COMMENT_EXISTS_SQL = "SELECT id FROM comments WHERE id = %s"

_INSERT_ENGAGEMENT_SQL = """
INSERT INTO engagement_metrics (
    source_table,
    source_record_id,
    platform_id,
    likes_count,
    comments_count,
    shares_count,
    views_count,
    reactions_count,
    snapshot_timestamp
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_post(conn: mysql.connector.MySQLConnection, post_data: dict) -> int:
    """Upsert a post row and return the resolved ``posts.id``.

    Executes ``INSERT … ON DUPLICATE KEY UPDATE`` on the ``posts`` table.
    When the row is new, ``cursor.lastrowid`` carries the auto-generated id.
    When the row already existed (duplicate key), MySQL sets ``lastrowid`` to
    0; a follow-up ``SELECT`` query is used to retrieve the pre-existing id.

    Parameters
    ----------
    conn:
        An open ``mysql.connector`` connection.  The caller retains ownership;
        this function does **not** close it.
    post_data:
        Dictionary with the following keys:

        * ``handle_id``              (int, required)
        * ``platform_id``            (int, required)
        * ``platform_native_post_id`` (str, required, ≤ 255 chars)
        * ``post_type``              (str, required — ``'post'``, ``'video'``, or ``'text'``)
        * ``title``                  (str or None)
        * ``body``                   (str or None)
        * ``url``                    (str or None)
        * ``language_code``          (str or None, 2 chars)
        * ``publish_timestamp``      (:class:`~datetime.datetime`, required, UTC)
        * ``discovered_at``          (:class:`~datetime.datetime`, optional — defaults to UTC now)

    Returns
    -------
    int
        The ``posts.id`` of the upserted row.

    Raises
    ------
    KeyError
        If a required key is missing from *post_data*.
    mysql.connector.Error
        On any database error.
    """
    discovered_at: datetime = post_data.get(
        "discovered_at", datetime.now(tz=timezone.utc)
    )

    params: tuple[Any, ...] = (
        post_data["handle_id"],
        post_data["platform_id"],
        post_data["platform_native_post_id"],
        post_data["post_type"],
        post_data.get("title"),
        post_data.get("body"),
        post_data.get("url"),
        post_data.get("language_code"),
        post_data["publish_timestamp"],
        discovered_at,
    )

    cursor = conn.cursor()
    try:
        cursor.execute(_UPSERT_POST_SQL, params)
        conn.commit()

        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        if row_id:
            return row_id

        # Duplicate-key path: lastrowid is 0 — fetch the pre-existing id.
        cursor.execute(
            _SELECT_POST_ID_SQL,
            (
                post_data["platform_id"],
                post_data["platform_native_post_id"],
                post_data["publish_timestamp"],
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(
                "upsert_post: could not resolve posts.id after ON DUPLICATE KEY UPDATE "
                f"(platform_id={post_data['platform_id']!r}, "
                f"platform_native_post_id={post_data['platform_native_post_id']!r}, "
                f"publish_timestamp={post_data['publish_timestamp']!r})"
            )
        return int(row[0])
    finally:
        cursor.close()


def upsert_comment(conn: mysql.connector.MySQLConnection, comment_data: dict) -> int:
    """Upsert a comment row and return the resolved ``comments.id``.

    Executes ``INSERT … ON DUPLICATE KEY UPDATE`` on the ``comments`` table.
    The deduplication key is ``(post_id, platform_native_comment_id)``.

    Parameters
    ----------
    conn:
        An open ``mysql.connector`` connection.
    comment_data:
        Dictionary with the following keys:

        * ``post_id``                    (int, required)
        * ``platform_native_comment_id`` (str, required, ≤ 255 chars)
        * ``author_handle``              (str, required, ≤ 255 chars)
        * ``comment_text``               (str, required, ≤ 10 000 chars)
        * ``language_code``              (str or None, 2 chars)
        * ``publish_timestamp``          (:class:`~datetime.datetime`, required, UTC)
        * ``discovered_at``              (:class:`~datetime.datetime`, optional)

    Returns
    -------
    int
        The ``comments.id`` of the upserted row.

    Raises
    ------
    KeyError
        If a required key is missing from *comment_data*.
    mysql.connector.Error
        On any database error.
    """
    discovered_at: datetime | None = comment_data.get("discovered_at")

    params: tuple[Any, ...] = (
        comment_data["post_id"],
        comment_data["platform_native_comment_id"],
        comment_data["author_handle"],
        comment_data["comment_text"],
        comment_data.get("language_code"),
        comment_data["publish_timestamp"],
        discovered_at,
    )

    cursor = conn.cursor()
    try:
        cursor.execute(_UPSERT_COMMENT_SQL, params)
        conn.commit()

        row_id: int = cursor.lastrowid  # type: ignore[assignment]
        if row_id:
            return row_id

        # Duplicate-key path: fetch the pre-existing id.
        cursor.execute(
            _SELECT_COMMENT_ID_SQL,
            (
                comment_data["post_id"],
                comment_data["platform_native_comment_id"],
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(
                "upsert_comment: could not resolve comments.id after ON DUPLICATE KEY UPDATE "
                f"(post_id={comment_data['post_id']!r}, "
                f"platform_native_comment_id={comment_data['platform_native_comment_id']!r})"
            )
        return int(row[0])
    finally:
        cursor.close()


def insert_engagement_snapshot(
    conn: mysql.connector.MySQLConnection,
    source_table: str,
    source_record_id: int,
    platform_id: int,
    metrics: dict,
) -> int:
    """Insert a new engagement-metric snapshot and return its ``id``.

    This is a plain INSERT (no upsert); every call creates a new immutable
    snapshot row, which is intentional — the ``engagement_metrics`` table is
    append-only by design (Requirement 2.1 / Property 4).

    Before inserting, the function verifies that the referenced source record
    exists in the appropriate table (``posts`` or ``comments``).  If the
    record is not found, :class:`ValueError` is raised.

    Parameters
    ----------
    conn:
        An open ``mysql.connector`` connection.
    source_table:
        Either ``'post'`` or ``'comment'``.
    source_record_id:
        Primary key of the originating row in ``posts`` or ``comments``.
    platform_id:
        Foreign key into ``platforms``.
    metrics:
        Dictionary with optional keys (all default to 0; ``reactions_count``
        may also be ``None`` where not supported by the platform):

        * ``likes_count``     (int, default 0)
        * ``comments_count``  (int, default 0)
        * ``shares_count``    (int, default 0)
        * ``views_count``     (int, default 0)
        * ``reactions_count`` (int or None, default 0)

    Returns
    -------
    int
        The ``engagement_metrics.id`` of the newly inserted row.

    Raises
    ------
    ValueError
        If *source_table* is not ``'post'`` or ``'comment'``, or if the
        referenced source record does not exist.
    mysql.connector.Error
        On any database error.
    """
    if source_table not in ("post", "comment"):
        raise ValueError(
            f"source_table must be 'post' or 'comment', got {source_table!r}"
        )

    check_sql = (
        _CHECK_POST_EXISTS_SQL if source_table == "post" else _CHECK_COMMENT_EXISTS_SQL
    )

    likes_count: int = metrics.get("likes_count", 0) or 0
    comments_count: int = metrics.get("comments_count", 0) or 0
    shares_count: int = metrics.get("shares_count", 0) or 0
    views_count: int = metrics.get("views_count", 0) or 0
    # reactions_count may legitimately be None (platform does not support it).
    reactions_count: int | None = metrics.get("reactions_count", 0)

    cursor = conn.cursor()
    try:
        # Verify the source record exists (application-layer referential integrity).
        cursor.execute(check_sql, (source_record_id,))
        if cursor.fetchone() is None:
            raise ValueError(
                f"source_record_id {source_record_id} not found in {source_table}s"
            )

        cursor.execute(
            _INSERT_ENGAGEMENT_SQL,
            (
                source_table,
                source_record_id,
                platform_id,
                likes_count,
                comments_count,
                shares_count,
                views_count,
                reactions_count,
            ),
        )
        conn.commit()

        new_id: int = cursor.lastrowid  # type: ignore[assignment]
        return new_id
    finally:
        cursor.close()
