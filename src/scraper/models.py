"""
models.py — Canonical data transfer objects (DTOs) for the Scraper Service.

These dataclasses represent normalised, platform-agnostic records produced by
every platform Adapter. They are deliberately independent of any platform API
schema — adapters map raw API responses into these structures before passing
them to the upsert layer.

Three DTOs are defined:

  NormalisedPost       — A single post/video/text item from any platform.
  NormalisedComment    — A single comment on a post.
  NormalisedEngagement — Engagement counter snapshot for a post.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NormalisedPost:
    """A single post item returned by a platform Adapter.

    Fields
    ------
    platform_native_post_id : str
        The post's unique identifier on the originating platform.
        Must be non-empty and at most 255 characters.
    post_type : str
        Content type — one of ``'post'``, ``'video'``, or ``'text'``.
    title : str | None
        Post title (e.g. YouTube video title). None when not applicable.
    body : str | None
        Main text body of the post. None when not applicable.
    url : str | None
        Canonical URL to the post. None if unavailable.
    publish_timestamp : datetime
        When the post was published, as a UTC timezone-aware datetime.
    handle_id : int
        Foreign key referencing ``handles.id`` in the database.
    """

    platform_native_post_id: str        # non-empty, ≤255 chars
    post_type: str                      # 'post' | 'video' | 'text'
    title: str | None
    body: str | None
    url: str | None
    publish_timestamp: datetime         # UTC, timezone-aware
    handle_id: int                      # FK to handles.id


@dataclass
class NormalisedComment:
    """A single comment on a post, returned by a platform Adapter.

    Fields
    ------
    platform_native_comment_id : str
        The comment's unique identifier on the originating platform.
        Must be non-empty and at most 255 characters.
    author_handle : str
        The platform username or handle of the comment author.
        Must be non-empty and at most 255 characters.
    comment_text : str
        The full text of the comment.
        Must be non-empty and at most 10 000 characters.
    publish_timestamp : datetime
        When the comment was published, as a UTC timezone-aware datetime.
    """

    platform_native_comment_id: str    # non-empty, ≤255 chars
    author_handle: str                 # non-empty, ≤255 chars
    comment_text: str                  # non-empty, ≤10000 chars
    publish_timestamp: datetime        # UTC, timezone-aware


@dataclass
class NormalisedEngagement:
    """Engagement counter snapshot for a post at a point in time.

    All counts default to 0 so that adapters only need to set the fields
    their platform actually provides.

    Fields
    ------
    likes_count : int
        Number of likes / upvotes. Defaults to 0.
    comments_count : int
        Total number of comments. Defaults to 0.
    shares_count : int
        Number of shares / retweets / reposts. Defaults to 0.
    views_count : int
        Number of views / impressions. Defaults to 0.
    reactions_count : int | None
        Total reaction count (e.g. Facebook reactions beyond simple likes).
        ``None`` means the platform does not support reactions as a separate
        metric — this is distinct from a count of zero.
    """

    likes_count:     int       = 0
    comments_count:  int       = 0
    shares_count:    int       = 0
    views_count:     int       = 0
    reactions_count: int | None = None  # None = platform does not support
