"""
handle_processor.py — Per-handle collection logic.

process_handle() orchestrates:
  1. Adapter authentication
  2. Watermark retrieval
  3. New post fetching (up to cap)
  4. Language detection + upsert for each post
  5. Comment fetching + upsert for each post
  6. Cooling-period engagement refresh
  7. Watermark update

Requirement 5.7: The per-handle cap applies only to new Post insertions.
Engagement refreshes for posts within their cooling period are NOT counted
against the cap and are NOT limited by it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .cooling import is_within_cooling_period
from .language_detector import detect_language
from .retry import with_retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_GET_WATERMARK_SQL = """
SELECT last_post_timestamp FROM handle_watermarks
WHERE handle_id = %s AND platform_id = %s
"""

_UPSERT_WATERMARK_SQL = """
INSERT INTO handle_watermarks (handle_id, platform_id, last_post_timestamp, updated_at)
VALUES (%s, %s, %s, UTC_TIMESTAMP())
ON DUPLICATE KEY UPDATE
    last_post_timestamp = GREATEST(last_post_timestamp, VALUES(last_post_timestamp)),
    updated_at = UTC_TIMESTAMP()
"""

_GET_COOLING_POSTS_SQL = """
SELECT id, platform_id, platform_native_post_id, publish_timestamp, discovered_at
FROM posts
WHERE handle_id = %s
  AND discovered_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)
"""


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------


@dataclass
class HandleStats:
    posts_inserted: int = 0
    posts_updated: int = 0
    comments_inserted: int = 0
    engagement_snapshots_inserted: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def process_handle(
    handle_row: dict,
    adapter: Any,
    conn: Any,
    config: dict,
) -> HandleStats:
    """Process one Handle: fetch new posts, comments, and refresh engagement.

    Parameters
    ----------
    handle_row:
        Row dict from the handles table (must include id, platform_id,
        platform_native_handle, platform_code).
    adapter:
        Pre-constructed (but not yet authenticated) BaseAdapter instance.
    conn:
        Open MySQL connection.
    config:
        Validated scraping config dict.

    Returns
    -------
    HandleStats
        Counters for this handle's operations.
    """
    from src.db.upsert import upsert_post, upsert_comment, insert_engagement_snapshot

    sc = config["scraping_config"]
    cap: int = sc["max_new_content_per_handle_per_iteration"]
    cooling_days: int = sc["cooling_time_days"]
    collection_days: int = sc.get("post_collection_days", 15)

    handle_id: int = handle_row["id"]
    platform_id: int = handle_row["platform_id"]
    native_handle: str = handle_row["platform_native_handle"]
    # Normalize: extract clean handle from URL if a full URL was stored
    from .url_normalizer import normalize_handle as _normalize
    platform_code_for_norm: str = handle_row.get("platform_code", "")
    native_handle = _normalize(platform_code_for_norm, native_handle)

    stats = HandleStats()

    # 1. Authenticate
    adapter.authenticate()

    # 2. Get watermark and compute effective since_timestamp.
    # post_collection_days enforces a hard lookback ceiling — we never
    # fetch posts older than that, even on a first run with no watermark.
    watermark_ts = _get_watermark(conn, handle_id, platform_id)
    now_utc = datetime.now(tz=timezone.utc)
    cutoff_ts: datetime = now_utc - timedelta(days=collection_days)

    if watermark_ts is None:
        # First run for this handle — backfill up to post_collection_days ago
        effective_since_ts: datetime = cutoff_ts
    else:
        # Subsequent runs — use whichever is more recent: the watermark or
        # the collection cutoff (prevents fetching content older than the window)
        wm = watermark_ts
        if wm.tzinfo is None:
            wm = wm.replace(tzinfo=timezone.utc)
        effective_since_ts = max(wm, cutoff_ts)

    logger.debug(
        "handle=%r  watermark=%s  cutoff=%s  effective_since=%s",
        native_handle,
        watermark_ts,
        cutoff_ts.date(),
        effective_since_ts.date(),
    )

    # 3. Fetch new posts with retry
    @with_retry(max_attempts=3)
    def _fetch_posts():
        return adapter.fetch_new_posts(
            native_handle, limit=cap, since_timestamp=effective_since_ts
        )

    new_posts = _fetch_posts()
    logger.debug(
        "Fetched %d posts for handle=%r platform=%r",
        len(new_posts),
        native_handle,
        handle_row.get("platform_code"),
    )

    newest_ts: datetime | None = None
    inserted_count = 0

    # 4. Process each NormalisedPost up to cap
    for norm_post in new_posts:
        if inserted_count >= cap:
            logger.debug(
                "Per-handle cap (%d) reached for handle=%r — stopping post insertion.",
                cap,
                native_handle,
            )
            break

        # Detect language from title + body
        text_for_lang = (
            " ".join(t for t in [norm_post.title, norm_post.body] if t) or None
        )
        lang_code = detect_language(text_for_lang)

        # Build post_data dict
        post_data = {
            "handle_id": handle_id,
            "platform_id": platform_id,
            "platform_native_post_id": norm_post.platform_native_post_id,
            "post_type": norm_post.post_type,
            "title": norm_post.title,
            "body": norm_post.body,
            "url": norm_post.url,
            "language_code": lang_code,
            "publish_timestamp": norm_post.publish_timestamp,
            "discovered_at": datetime.now(tz=timezone.utc),
        }

        # Upsert post with retry
        @with_retry(max_attempts=3)
        def _upsert_post():
            return upsert_post(conn, post_data)

        post_id = _upsert_post()
        inserted_count += 1
        stats.posts_inserted += 1

        # Track newest publish_timestamp seen
        if newest_ts is None or norm_post.publish_timestamp > newest_ts:
            newest_ts = norm_post.publish_timestamp

        # 5. Fetch and upsert comments with retry
        @with_retry(max_attempts=3)
        def _fetch_comments():
            return adapter.fetch_comments(norm_post, limit=50)

        comments = _fetch_comments()
        for norm_comment in comments:
            lang_code_c = detect_language(norm_comment.comment_text)
            comment_data = {
                "post_id": post_id,
                "platform_native_comment_id": norm_comment.platform_native_comment_id,
                "author_handle": norm_comment.author_handle,
                "comment_text": norm_comment.comment_text,
                "language_code": lang_code_c,
                "publish_timestamp": norm_comment.publish_timestamp,
                "discovered_at": datetime.now(tz=timezone.utc),
            }

            @with_retry(max_attempts=3)
            def _upsert_comment():
                return upsert_comment(conn, comment_data)

            _upsert_comment()
            stats.comments_inserted += 1

    # 6. Update watermark if we saw any posts
    if newest_ts is not None:
        _update_watermark(conn, handle_id, platform_id, newest_ts)

    # 7. Engagement refresh for all posts within their cooling period.
    # NOTE: engagement refresh does NOT count against the cap (Requirement 5.7).
    cooling_posts = _get_cooling_posts(conn, handle_id, cooling_days)
    now_utc = datetime.now(tz=timezone.utc)

    for post_row in cooling_posts:
        if not is_within_cooling_period(
            post_row["discovered_at"], cooling_days, now_utc
        ):
            continue

        # Reconstruct a minimal NormalisedPost for fetch_engagement
        from .models import NormalisedPost

        cooling_norm = NormalisedPost(
            platform_native_post_id=post_row["platform_native_post_id"],
            post_type="post",
            title=None,
            body=None,
            url=None,
            publish_timestamp=post_row["publish_timestamp"],
            handle_id=handle_id,
        )

        @with_retry(max_attempts=3)
        def _fetch_engagement():
            return adapter.fetch_engagement(cooling_norm)

        engagement = _fetch_engagement()
        metrics = {
            "likes_count": engagement.likes_count,
            "comments_count": engagement.comments_count,
            "shares_count": engagement.shares_count,
            "views_count": engagement.views_count,
            "reactions_count": engagement.reactions_count,
        }

        @with_retry(max_attempts=3)
        def _insert_snapshot():
            return insert_engagement_snapshot(
                conn, "post", post_row["id"], post_row["platform_id"], metrics
            )

        _insert_snapshot()
        stats.engagement_snapshots_inserted += 1

    return stats


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_watermark(conn: Any, handle_id: int, platform_id: int) -> datetime | None:
    """Query handle_watermarks for the last seen post timestamp."""
    cursor = conn.cursor()
    try:
        cursor.execute(_GET_WATERMARK_SQL, (handle_id, platform_id))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def _update_watermark(
    conn: Any, handle_id: int, platform_id: int, ts: datetime
) -> None:
    """Upsert handle_watermarks, advancing the timestamp with GREATEST()."""
    cursor = conn.cursor()
    try:
        cursor.execute(_UPSERT_WATERMARK_SQL, (handle_id, platform_id, ts))
        conn.commit()
    finally:
        cursor.close()


def _get_cooling_posts(conn: Any, handle_id: int, cooling_days: int) -> list[dict]:
    """Fetch posts discovered within the cooling window for this handle."""
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(_GET_COOLING_POSTS_SQL, (handle_id, cooling_days))
        return cursor.fetchall()
    finally:
        cursor.close()
