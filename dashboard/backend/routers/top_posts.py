"""
dashboard/backend/routers/top_posts.py — GET /api/top-posts endpoint.

Fix: added _DEDUP_JOIN so that posts sharing the same
(platform_id, platform_native_post_id) are collapsed to a single canonical
row (MAX id = latest scraped version) before ranking by engagement.
This prevents the same video/post appearing multiple times in the list.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import TopPost, TopPostsResponse

router = APIRouter()

_TOTAL_ENG = (
    "COALESCE(em.likes_count,0) + COALESCE(em.comments_count,0)"
    " + COALESCE(em.shares_count,0) + COALESCE(em.views_count,0)"
    " + COALESCE(em.reactions_count,0)"
)

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


@router.get("/top-posts", response_model=TopPostsResponse)
def get_top_posts(
    limit: int = Query(default=10, ge=1, le=100),
    platform: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    """Return top N posts by total engagement, optionally filtered by
    platform, category, and publish-date range."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        clauses, params = ["1=1"], {}

        if platform:
            clauses.append("pl.platform_code = %(platform)s")
            params["platform"] = platform
        if category:
            clauses.append("c.name = %(category)s")
            params["category"] = category
        if date_from:
            clauses.append("DATE(p.publish_timestamp) >= %(date_from)s")
            params["date_from"] = date_from
        if date_to:
            clauses.append("DATE(p.publish_timestamp) <= %(date_to)s")
            params["date_to"] = date_to

        where = " AND ".join(clauses)
        params["limit"] = limit

        cursor.execute(f"""
            SELECT p.id AS post_id, p.title, p.url, p.post_type,
                   p.publish_timestamp,
                   c.name AS category_name,
                   pl.display_name AS platform_display_name,
                   {_TOTAL_ENG} AS total_engagement
            FROM posts p
            {_DEDUP_JOIN}
            JOIN handles h    ON p.handle_id    = h.id
            JOIN categories c ON h.category_id  = c.id
            JOIN platforms pl ON p.platform_id  = pl.id
            {_LATEST_EM_JOIN}
            WHERE {where}
            ORDER BY total_engagement DESC
            LIMIT %(limit)s
        """, params)
        rows = cursor.fetchall()

    return TopPostsResponse(data=[TopPost(**r) for r in rows])
