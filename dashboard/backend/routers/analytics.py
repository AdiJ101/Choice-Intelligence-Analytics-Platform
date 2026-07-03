"""
dashboard/backend/routers/analytics.py
GET /api/analytics/by-platform, /by-category, /engagement-trend

Issue fixes:
- by-platform: now LEFT JOINs from the platforms table so every platform
  appears in results even when it has zero posts (X and Instagram no longer
  missing from the platform summary).
- by-category: same treatment — every category appears even with zero posts.
- Both queries include a dedup sub-join that collapses posts sharing the same
  (platform_id, platform_native_post_id) into a single canonical row
  (MAX id), so duplicate scrapes don't inflate the counters.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import (
    CategoryAnalytics, CategoryAnalyticsResponse,
    ContentTypeCount, ContentTypeResponse,
    EngagementTrendPoint, EngagementTrendResponse,
    PlatformAnalytics, PlatformAnalyticsResponse,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared SQL fragments
# ---------------------------------------------------------------------------

# Inner body of the latest-engagement CTE (no WITH wrapper so it can be
# embedded inside a larger multi-CTE expression).
_LATEST_EM_BODY = """
    SELECT em1.source_record_id,
           MAX(em1.likes_count)    AS likes_count,
           MAX(em1.views_count)    AS views_count,
           MAX(em1.comments_count) AS comments_count,
           MAX(em1.shares_count)   AS shares_count,
           MAX(COALESCE(em1.reactions_count, 0)) AS reactions_count
    FROM engagement_metrics em1
    WHERE em1.source_table = 'post'
    GROUP BY em1.source_record_id
"""

# Dedup is now handled at the data layer (migration 014 + cleanup scripts).
# No query-level dedup join needed.
_DEDUP_JOIN = ""

_TOTAL_ENG = (
    "COALESCE(lem.likes_count,0) + COALESCE(lem.comments_count,0)"
    " + COALESCE(lem.shares_count,0) + COALESCE(lem.views_count,0)"
    " + COALESCE(lem.reactions_count,0)"
)

# Kept for the engagement-trend query which still uses the original pattern.
_LATEST_EM_CTE = f"WITH latest_em AS ({_LATEST_EM_BODY})"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/analytics/by-platform", response_model=PlatformAnalyticsResponse)
def get_by_platform(category: Optional[str] = None):
    """Aggregated metrics grouped by platform.

    Every platform in the platforms table is returned, even if it has zero
    posts (e.g. X / Instagram when credentials haven't been scraped yet).
    Optionally filtered by category name.
    """
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)

        if category:
            cursor.execute(
                "SELECT id FROM categories WHERE name = %(n)s", {"n": category}
            )
            if not cursor.fetchone():
                raise HTTPException(404, detail=f"Category '{category}' not found")

        clauses, params = ["1=1"], {}
        if category:
            clauses.append("c.name = %(category)s")
            params["category"] = category
        where = " AND ".join(clauses)

        cursor.execute(f"""
            WITH latest_em AS ({_LATEST_EM_BODY}),
            platform_metrics AS (
                SELECT pl.id AS pid,
                       COUNT(p.id)                                     AS post_count,
                       ROUND(AVG(COALESCE(lem.likes_count,    0)), 2)  AS avg_likes,
                       ROUND(AVG(COALESCE(lem.views_count,    0)), 2)  AS avg_views,
                       ROUND(AVG(COALESCE(lem.comments_count, 0)), 2)  AS avg_comments,
                       COALESCE(SUM({_TOTAL_ENG}), 0)                  AS total_engagement
                FROM posts p
                {_DEDUP_JOIN}
                JOIN handles h    ON p.handle_id   = h.id
                JOIN categories c ON h.category_id = c.id
                JOIN platforms pl ON p.platform_id = pl.id
                LEFT JOIN latest_em lem ON lem.source_record_id = p.id
                WHERE {where}
                GROUP BY pl.id
            )
            SELECT pl.display_name                          AS platform_display_name,
                   COALESCE(pm.post_count,       0)         AS post_count,
                   COALESCE(pm.avg_likes,        0.0)       AS avg_likes,
                   COALESCE(pm.avg_views,        0.0)       AS avg_views,
                   COALESCE(pm.avg_comments,     0.0)       AS avg_comments,
                   COALESCE(pm.total_engagement, 0)         AS total_engagement
            FROM platforms pl
            LEFT JOIN platform_metrics pm ON pm.pid = pl.id
            ORDER BY pl.display_name
        """, params)
        rows = cursor.fetchall()

    return PlatformAnalyticsResponse(data=[PlatformAnalytics(**r) for r in rows])


@router.get("/analytics/by-category", response_model=CategoryAnalyticsResponse)
def get_by_category(platform: Optional[str] = None):
    """Aggregated metrics grouped by category / brand.

    Every category in the categories table is returned, even if it has zero
    posts for the given platform filter.
    Optionally filtered by platform code.
    """
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)

        if platform:
            cursor.execute(
                "SELECT id FROM platforms WHERE platform_code = %(p)s", {"p": platform}
            )
            if not cursor.fetchone():
                raise HTTPException(404, detail=f"Platform '{platform}' not found")

        clauses, params = ["1=1"], {}
        if platform:
            clauses.append("pl.platform_code = %(platform)s")
            params["platform"] = platform
        where = " AND ".join(clauses)

        cursor.execute(f"""
            WITH latest_em AS ({_LATEST_EM_BODY}),
            category_metrics AS (
                SELECT c.id AS cid,
                       COUNT(p.id)                                    AS post_count,
                       COALESCE(SUM(lem.likes_count),    0)           AS total_likes,
                       COALESCE(SUM(lem.views_count),    0)           AS total_views,
                       COALESCE(SUM(lem.comments_count), 0)           AS total_comments,
                       COALESCE(SUM({_TOTAL_ENG}),       0)           AS total_engagement
                FROM posts p
                {_DEDUP_JOIN}
                JOIN handles h    ON p.handle_id   = h.id
                JOIN categories c ON h.category_id = c.id
                JOIN platforms pl ON p.platform_id = pl.id
                LEFT JOIN latest_em lem ON lem.source_record_id = p.id
                WHERE {where}
                GROUP BY c.id
            )
            SELECT c.name                                   AS category_name,
                   COALESCE(cm.post_count,       0)         AS post_count,
                   COALESCE(cm.total_likes,      0)         AS total_likes,
                   COALESCE(cm.total_views,      0)         AS total_views,
                   COALESCE(cm.total_comments,   0)         AS total_comments,
                   COALESCE(cm.total_engagement, 0)         AS total_engagement
            FROM categories c
            LEFT JOIN category_metrics cm ON cm.cid = c.id
            ORDER BY c.name
        """, params)
        rows = cursor.fetchall()

    return CategoryAnalyticsResponse(data=[CategoryAnalytics(**r) for r in rows])


@router.get("/analytics/engagement-trend", response_model=EngagementTrendResponse)
def get_engagement_trend(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
):
    """Daily aggregate engagement trend with optional filters."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        clauses = ["em.source_table = 'post'"]
        params: dict = {}

        if platform:
            clauses.append("pl.platform_code = %(platform)s")
            params["platform"] = platform
        if category:
            clauses.append("c.name = %(category)s")
            params["category"] = category
        if date_from:
            clauses.append("DATE(em.snapshot_timestamp) >= %(date_from)s")
            params["date_from"] = date_from
        if date_to:
            clauses.append("DATE(em.snapshot_timestamp) <= %(date_to)s")
            params["date_to"] = date_to

        where = " AND ".join(clauses)
        cursor.execute(f"""
            SELECT DATE(em.snapshot_timestamp) AS date,
                   SUM(em.likes_count)          AS total_likes,
                   SUM(em.views_count)          AS total_views,
                   SUM(em.comments_count)       AS total_comments,
                   SUM(em.shares_count)         AS total_shares
            FROM engagement_metrics em
            JOIN posts p      ON p.id           = em.source_record_id
            JOIN handles h    ON p.handle_id    = h.id
            JOIN categories c ON h.category_id  = c.id
            JOIN platforms pl ON p.platform_id  = pl.id
            WHERE em.snapshot_timestamp = (
                SELECT MAX(em2.snapshot_timestamp)
                FROM engagement_metrics em2
                WHERE em2.source_record_id = em.source_record_id
                  AND em2.source_table = 'post'
                  AND DATE(em2.snapshot_timestamp) = DATE(em.snapshot_timestamp)
            )
              AND {where}
            GROUP BY DATE(em.snapshot_timestamp)
            ORDER BY date ASC
        """, params)
        rows = cursor.fetchall()

    return EngagementTrendResponse(data=[EngagementTrendPoint(**r) for r in rows])


@router.get("/analytics/content-types", response_model=ContentTypeResponse)
def get_content_types(category: Optional[str] = None):
    """Exact post_type distribution computed in SQL (no row limit).

    Counts every post grouped by post_type, optionally filtered by category.
    Used by the content-types donut so the chart is accurate regardless of
    how many posts exist.
    """
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)

        clauses, params = ["1=1"], {}
        if category:
            clauses.append("c.name = %(category)s")
            params["category"] = category
        where = " AND ".join(clauses)

        cursor.execute(f"""
            SELECT p.post_type AS post_type, COUNT(*) AS count
            FROM posts p
            JOIN handles h    ON p.handle_id   = h.id
            JOIN categories c ON h.category_id = c.id
            WHERE {where}
            GROUP BY p.post_type
            ORDER BY count DESC
        """, params)
        rows = cursor.fetchall()

    total = sum(int(r["count"]) for r in rows)
    return ContentTypeResponse(
        data=[ContentTypeCount(post_type=r["post_type"], count=int(r["count"])) for r in rows],
        total=total,
    )
