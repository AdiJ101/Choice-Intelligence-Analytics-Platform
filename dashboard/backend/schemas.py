"""
dashboard/backend/schemas.py — Pydantic v2 response models for the Analytics Dashboard API.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    total_posts: int
    total_comments: int
    total_likes: int
    total_views: int


class PostSummary(BaseModel):
    post_id: int
    title: Optional[str] = None
    url: Optional[str] = None
    post_type: str
    language_code: Optional[str] = None
    publish_timestamp: datetime
    category_name: str
    platform_display_name: str
    handle_display_name: str
    latest_likes: int = 0
    latest_views: int = 0
    latest_comments: int = 0
    latest_shares: int = 0
    total_engagement: int = 0


class PostListResponse(BaseModel):
    data: list[PostSummary]
    total: int


class CommentItem(BaseModel):
    comment_id: int
    author_handle: str
    comment_text: str
    language_code: Optional[str] = None
    publish_timestamp: datetime


class EngagementSnapshot(BaseModel):
    snapshot_timestamp: datetime
    likes_count: int = 0
    views_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    reactions_count: Optional[int] = None


class PostDetail(BaseModel):
    post_id: int
    title: Optional[str] = None
    body: Optional[str] = None
    url: Optional[str] = None
    post_type: str
    language_code: Optional[str] = None
    publish_timestamp: datetime
    category_name: str
    platform_display_name: str
    handle_display_name: str
    comments: list[CommentItem] = []
    engagement_history: list[EngagementSnapshot] = []


class PlatformAnalytics(BaseModel):
    platform_display_name: str
    post_count: int = 0
    avg_likes: float = 0.0
    avg_views: float = 0.0
    avg_comments: float = 0.0
    total_engagement: int = 0


class PlatformAnalyticsResponse(BaseModel):
    data: list[PlatformAnalytics]


class CategoryAnalytics(BaseModel):
    category_name: str
    post_count: int = 0
    total_likes: int = 0
    total_views: int = 0
    total_comments: int = 0
    total_engagement: int = 0


class CategoryAnalyticsResponse(BaseModel):
    data: list[CategoryAnalytics]


class EngagementTrendPoint(BaseModel):
    date: date
    total_likes: int = 0
    total_views: int = 0
    total_comments: int = 0
    total_shares: int = 0


class EngagementTrendResponse(BaseModel):
    data: list[EngagementTrendPoint]


class TopPost(BaseModel):
    post_id: int
    title: Optional[str] = None
    url: Optional[str] = None
    post_type: str
    publish_timestamp: datetime
    category_name: str
    platform_display_name: str
    total_engagement: int = 0


class TopPostsResponse(BaseModel):
    data: list[TopPost]


class ContentTypeCount(BaseModel):
    post_type: str
    count: int


class ContentTypeResponse(BaseModel):
    data: list[ContentTypeCount]
    total: int = 0


class CategoryRef(BaseModel):
    category_id: int
    category_name: str


class CategoryListResponse(BaseModel):
    data: list[CategoryRef]


class PlatformRef(BaseModel):
    platform_id: int
    platform_code: str
    platform_display_name: str


class PlatformListResponse(BaseModel):
    data: list[PlatformRef]


class AIInsightsResponse(BaseModel):
    # Customer perspective (from comments + engagement signals)
    demands:             list[str] = []
    likes:               list[str] = []
    dislikes:            list[str] = []
    trends:              list[str] = []
    # Company perspective (from post titles, descriptions, bodies)
    launches:            list[str] = []
    announcements:       list[str] = []
    focus_areas:         list[str] = []
    campaigns:           list[str] = []
    # Metadata
    analyzed_comments:   int = 0
    analyzed_posts:      int = 0
    generated_at:        str = ""
    error:               Optional[str] = None
