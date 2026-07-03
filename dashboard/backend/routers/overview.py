"""
dashboard/backend/routers/overview.py — GET /api/overview endpoint.
"""

from __future__ import annotations

import mysql.connector
from fastapi import APIRouter, HTTPException

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import OverviewResponse

router = APIRouter()


@router.get("/overview", response_model=OverviewResponse)
def get_overview():
    """Return aggregate summary statistics for the Overview page."""
    try:
        with get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM posts) AS total_posts,
                    (SELECT COUNT(*) FROM comments) AS total_comments,
                    (SELECT COALESCE(SUM(max_likes), 0)
                     FROM (
                         SELECT MAX(likes_count) AS max_likes
                         FROM engagement_metrics
                         WHERE source_table = 'post'
                         GROUP BY source_record_id
                     ) sub
                    ) AS total_likes,
                    (SELECT COALESCE(SUM(max_views), 0)
                     FROM (
                         SELECT MAX(views_count) AS max_views
                         FROM engagement_metrics
                         WHERE source_table = 'post'
                         GROUP BY source_record_id
                     ) sub2
                    ) AS total_views
            """)
            row = cursor.fetchone()
            return OverviewResponse(**row)
    except mysql.connector.Error as exc:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}")
