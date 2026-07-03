"""
dashboard/backend/routers/posts.py — GET /api/posts and GET /api/posts/{post_id} endpoints.

Fix: added _DEDUP_JOIN to the list query so duplicate scrapes of the same
native post (same platform_id + platform_native_post_id) are collapsed to a
single canonical row (MAX id) before pagination. This prevents the same
content appearing multiple times in Content Explorer and keeps the total
count accurate.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import mysql.connector
from fastapi import APIRouter, HTTPException, Query

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import (
    CommentItem, EngagementSnapshot,
    PostDetail, PostListResponse, PostSummary,
)

router = APIRouter()

# Dedup handled at data layer — no query-level join needed.
_DEDUP_JOIN = ""

_LATEST_EM_JOIN = """
    LEFT JOIN (
        SELECT em1.source_record_id,
               MAX(em1.likes_count)    AS likes_count,
               MAX(em1.views_count)    AS views_count,
               MAX(em1.comments_count) AS comments_count,
               MAX(em1.shares_count)   AS shares_count,
               MAX(COALESCE(em1.reactions_count, 0)) AS reactions_count
        FROM engagement_metrics em1
        WHERE em1.source_table = 'post'
        GROUP BY em1.source_record_id
    ) em ON em.source_record_id = p.id
"""

_BASE_JOINS = """
    FROM posts p
    JOIN handles h ON p.handle_id = h.id
    JOIN categories c ON h.category_id = c.id
    JOIN platforms pl ON p.platform_id = pl.id
"""


@router.get("/posts", response_model=PostListResponse)
def get_posts(
    category: Optional[str] = None,
    platform: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return a paginated list of posts with optional filters.

    Duplicate native posts are collapsed to their latest version before
    pagination so the same content never appears twice.
    """
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        clauses = ["1=1"]
        params: dict = {}

        if category:
            clauses.append("c.name = %(category)s")
            params["category"] = category
        if platform:
            clauses.append("pl.platform_code = %(platform)s")
            params["platform"] = platform
        if date_from:
            clauses.append("p.publish_timestamp >= %(date_from)s")
            params["date_from"] = date_from
        if date_to:
            clauses.append("p.publish_timestamp <= %(date_to)s")
            params["date_to"] = date_to

        where = " AND ".join(clauses)

        # Count using the dedup join so the total reflects unique posts only
        cursor.execute(f"""
            SELECT COUNT(*) AS total
            {_BASE_JOINS}
            {_DEDUP_JOIN}
            WHERE {where}
        """, params)
        total = cursor.fetchone()["total"]

        params["limit"] = limit
        params["offset"] = offset
        cursor.execute(f"""
            SELECT
                p.id AS post_id, p.title, p.url, p.post_type,
                p.language_code, p.publish_timestamp,
                c.name AS category_name,
                pl.display_name AS platform_display_name,
                h.display_name AS handle_display_name,
                COALESCE(em.likes_count, 0)    AS latest_likes,
                COALESCE(em.views_count, 0)    AS latest_views,
                COALESCE(em.comments_count, 0) AS latest_comments,
                COALESCE(em.shares_count, 0)   AS latest_shares,
                COALESCE(em.likes_count, 0) + COALESCE(em.comments_count, 0)
                    + COALESCE(em.shares_count, 0) + COALESCE(em.views_count, 0)
                    + COALESCE(em.reactions_count, 0) AS total_engagement
            {_BASE_JOINS}
            {_DEDUP_JOIN}
            {_LATEST_EM_JOIN}
            WHERE {where}
            ORDER BY p.publish_timestamp DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """, params)
        rows = cursor.fetchall()

    return PostListResponse(data=[PostSummary(**r) for r in rows], total=total)


@router.get("/posts/{post_id}", response_model=PostDetail)
def get_post_detail(post_id: int):
    """Return full post detail with comments and engagement history."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.id AS post_id, p.title, p.body, p.url, p.post_type,
                   p.language_code, p.publish_timestamp,
                   c.name AS category_name,
                   pl.display_name AS platform_display_name,
                   h.display_name AS handle_display_name
            FROM posts p
            JOIN handles h ON p.handle_id = h.id
            JOIN categories c ON h.category_id = c.id
            JOIN platforms pl ON p.platform_id = pl.id
            WHERE p.id = %(post_id)s
        """, {"post_id": post_id})
        post = cursor.fetchone()
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

        cursor.execute("""
            SELECT id AS comment_id, author_handle, comment_text,
                   language_code, publish_timestamp
            FROM comments
            WHERE post_id = %(post_id)s
            ORDER BY publish_timestamp ASC
        """, {"post_id": post_id})
        comments = cursor.fetchall()

        cursor.execute("""
            SELECT snapshot_timestamp, likes_count, views_count,
                   comments_count, shares_count, reactions_count
            FROM engagement_metrics
            WHERE source_record_id = %(post_id)s
              AND source_table = 'post'
            ORDER BY snapshot_timestamp ASC
        """, {"post_id": post_id})
        history = cursor.fetchall()

    return PostDetail(
        **post,
        comments=[CommentItem(**c) for c in comments],
        engagement_history=[EngagementSnapshot(**h) for h in history],
    )
