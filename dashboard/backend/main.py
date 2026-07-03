"""
dashboard/backend/main.py — FastAPI application entry point.

Start with:
    uvicorn dashboard.backend.main:app --port 8000 --reload

from the project root.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.backend.routers import (
    ai_analytics,
    analytics,
    overview,
    posts,
    reference,
    semantic_search,
    top_posts,
    scraper_status,
)

app = FastAPI(
    title="Choice Analytics API",
    version="1.0",
    description="REST API for the Choice Group Social Intelligence Dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(overview.router,      prefix="/api")
app.include_router(posts.router,         prefix="/api")
app.include_router(analytics.router,     prefix="/api")
app.include_router(top_posts.router,     prefix="/api")
app.include_router(reference.router,     prefix="/api")
app.include_router(ai_analytics.router,  prefix="/api")
app.include_router(semantic_search.router, prefix="/api")
app.include_router(scraper_status.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
