"""
dashboard/frontend/api_client.py — HTTP client for the Analytics Dashboard frontend.

Wraps all FastAPI backend calls with Streamlit caching (5-minute TTL).
Note: st.cache_data on instance methods requires _self (not self) as the first arg.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import requests
import streamlit as st

BASE_URL = "http://localhost:8000"
TIMEOUT = 10


class APIClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base = base_url

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = requests.get(f"{self.base}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    @st.cache_data(ttl=300)
    def get_overview(_self) -> dict:
        return _self._get("/api/overview")

    @st.cache_data(ttl=300)
    def get_posts(
        _self,
        category: Optional[str] = None,
        platform: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        params: dict = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category
        if platform:
            params["platform"] = platform
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        return _self._get("/api/posts", params)

    @st.cache_data(ttl=300)
    def get_post_detail(_self, post_id: int) -> dict:
        return _self._get(f"/api/posts/{post_id}")

    @st.cache_data(ttl=300)
    def get_by_platform(_self, category: Optional[str] = None) -> dict:
        params = {"category": category} if category else {}
        return _self._get("/api/analytics/by-platform", params)

    @st.cache_data(ttl=300)
    def get_by_category(_self, platform: Optional[str] = None) -> dict:
        params = {"platform": platform} if platform else {}
        return _self._get("/api/analytics/by-category", params)

    @st.cache_data(ttl=300)
    def get_content_types(_self, category: Optional[str] = None) -> dict:
        params = {"category": category} if category else {}
        return _self._get("/api/analytics/content-types", params)

    @st.cache_data(ttl=300)
    def get_engagement_trend(
        _self,
        platform: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        params: dict = {}
        if platform:
            params["platform"] = platform
        if category:
            params["category"] = category
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        return _self._get("/api/analytics/engagement-trend", params)

    @st.cache_data(ttl=300)
    def get_top_posts(
        _self,
        limit: int = 10,
        platform: Optional[str] = None,
        category: Optional[str] = None,
        date_from=None,
        date_to=None,
    ) -> dict:
        params: dict = {"limit": limit}
        if platform:
            params["platform"] = platform
        if category:
            params["category"] = category
        if date_from:
            params["date_from"] = date_from.isoformat() if hasattr(date_from, "isoformat") else date_from
        if date_to:
            params["date_to"] = date_to.isoformat() if hasattr(date_to, "isoformat") else date_to
        return _self._get("/api/top-posts", params)

    @st.cache_data(ttl=300)
    def get_categories(_self) -> list[dict]:
        return _self._get("/api/categories")["data"]

    @st.cache_data(ttl=300)
    def get_platforms(_self) -> list[dict]:
        return _self._get("/api/platforms")["data"]

    # AI analytics — no cache_data; results are stored in Streamlit session state
    # by the page itself so the user controls when to regenerate.
    def start_ai_analytics_job(
        _self,
        category:     Optional[str]  = None,
        platform:     Optional[str]  = None,
        date_from:    Optional[date] = None,
        date_to:      Optional[date] = None,
    ) -> dict:
        params: dict = {}
        if category:
            params["category"] = category
        if platform:
            params["platform"] = platform
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        resp = requests.post(
            f"{_self.base}/api/ai-analytics/job",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_ai_analytics_job_status(_self, job_id: str) -> dict:
        resp = requests.get(
            f"{_self.base}/api/ai-analytics/job/{job_id}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_last_ai_analytics(_self) -> dict:
        resp = requests.get(
            f"{_self.base}/api/ai-analytics/last",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_active_ai_job(_self) -> dict:
        resp = requests.get(
            f"{_self.base}/api/ai-analytics/active-job",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def clear_last_ai_analytics(_self) -> dict:
        resp = requests.post(
            f"{_self.base}/api/ai-analytics/clear",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_scraper_status(_self) -> dict:
        resp = requests.get(
            f"{_self.base}/api/scraper/status",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def send_scraper_command(_self, command: str) -> dict:
        resp = requests.post(
            f"{_self.base}/api/scraper/control",
            json={"command": command},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


client = APIClient()
