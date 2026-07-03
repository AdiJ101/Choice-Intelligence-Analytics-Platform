"""
dashboard/backend/routers/reference.py — GET /api/categories and GET /api/platforms endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from dashboard.backend.db import get_conn
from dashboard.backend.schemas import (
    CategoryListResponse, CategoryRef,
    PlatformListResponse, PlatformRef,
)

router = APIRouter()


@router.get("/categories", response_model=CategoryListResponse)
def get_categories():
    """Return all categories ordered by name ascending."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id AS category_id, name AS category_name "
            "FROM categories ORDER BY name ASC"
        )
        rows = cursor.fetchall()
    return CategoryListResponse(data=[CategoryRef(**r) for r in rows])


@router.get("/platforms", response_model=PlatformListResponse)
def get_platforms():
    """Return all platforms ordered by display_name ascending."""
    with get_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id AS platform_id, platform_code, "
            "display_name AS platform_display_name "
            "FROM platforms ORDER BY display_name ASC"
        )
        rows = cursor.fetchall()
    return PlatformListResponse(data=[PlatformRef(**r) for r in rows])
