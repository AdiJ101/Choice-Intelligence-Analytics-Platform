"""
instagram.py — Instagram adapter using instagrapi (private mobile API).

Authenticates with a real Instagram account (username + password) and
fetches posts directly from the user's media feed with full engagement
data (likes, comments, views).

Session is persisted to .instagram_session.json so login only happens
once; subsequent scrapes reuse the cached session token.

Credentials (set in .env):
    INSTAGRAM_USERNAME   Instagram username (not email)
    INSTAGRAM_PASSWORD   Instagram password

Falls back to FirecrawlScraper if credentials are not configured.

Install: pip install instagrapi
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..base_adapter import AuthenticationError, BaseAdapter
from ..models import NormalisedComment, NormalisedEngagement, NormalisedPost

logger = logging.getLogger(__name__)

_SESSION_FILE = Path(".instagram_session.json")

# Instagram media_type codes → our post_type
_MEDIA_TYPE_MAP = {1: "post", 2: "video", 8: "post"}  # photo, video, carousel


class InstagramAdapter(BaseAdapter):
    """Instagram adapter — instagrapi with username/password auth.

    Falls back to Firecrawl page scraping when credentials are absent.
    """

    platform_code = "instagram"

    def __init__(self, handle_id: int = 0) -> None:
        super().__init__()
        self._handle_id = handle_id
        self._cl = None          # instagrapi Client
        self._scraper = None     # FirecrawlScraper fallback
        self._mode = "firecrawl"

    def authenticate(self) -> None:
        username = os.environ.get("INSTAGRAM_USERNAME", "")
        password = os.environ.get("INSTAGRAM_PASSWORD", "")

        if username and password:
            self._authenticate_instagrapi(username, password)
        else:
            self._authenticate_firecrawl()

    def _authenticate_instagrapi(self, username: str, password: str) -> None:
        try:
            from instagrapi import Client  # type: ignore[import]
            from instagrapi.exceptions import (  # type: ignore[import]
                BadPassword, ChallengeRequired, LoginRequired,
            )
        except ImportError as exc:
            raise ImportError(
                "instagrapi is not installed. Run: pip install instagrapi"
            ) from exc

        cl = Client()
        cl.delay_range = [1, 3]   # polite delays between requests

        # Try to reuse an existing session
        if _SESSION_FILE.exists():
            try:
                cl.load_settings(_SESSION_FILE)
                cl.login(username, password)
                logger.info("InstagramAdapter: reused saved session for %r", username)
                self._cl = cl
                self._mode = "instagrapi"
                self._authenticated = True
                return
            except Exception as exc:
                logger.warning(
                    "InstagramAdapter: saved session invalid (%s) — re-logging in", exc
                )
                _SESSION_FILE.unlink(missing_ok=True)

        # Fresh login
        try:
            cl.login(username, password)
            cl.dump_settings(_SESSION_FILE)
            logger.info("InstagramAdapter: logged in as %r", username)
            self._cl = cl
            self._mode = "instagrapi"
            self._authenticated = True
        except Exception as exc:
            logger.error(
                "InstagramAdapter: login failed for %r: %s", username, exc
            )
            raise AuthenticationError("instagram", "INSTAGRAM_PASSWORD") from exc

    def _authenticate_firecrawl(self) -> None:
        from .firecrawl_scraper import FirecrawlScraper
        self._scraper = FirecrawlScraper()
        self._mode = "firecrawl"
        self._authenticated = True
        logger.info(
            "InstagramAdapter: no credentials — using Firecrawl fallback"
        )

    # ------------------------------------------------------------------

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        self._require_auth()
        if self._mode == "instagrapi":
            return self._fetch_instagrapi(handle, limit, since_timestamp)
        return self._fetch_firecrawl(handle, limit)

    def _fetch_instagrapi(
        self, handle: str, limit: int, since_timestamp: datetime | None
    ) -> list[NormalisedPost]:
        assert self._cl is not None
        try:
            user_id = self._cl.user_id_from_username(handle)
            medias = self._cl.user_medias(user_id, amount=limit)
        except Exception as exc:
            logger.error(
                "InstagramAdapter: failed to fetch medias for %r: %s", handle, exc
            )
            return []

        posts: list[NormalisedPost] = []
        for media in medias:
            pub_ts: datetime = media.taken_at
            if pub_ts.tzinfo is None:
                pub_ts = pub_ts.replace(tzinfo=timezone.utc)

            if since_timestamp is not None:
                st = since_timestamp
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                if pub_ts <= st:
                    continue

            posts.append(
                NormalisedPost(
                    platform_native_post_id=str(media.id),
                    post_type=_MEDIA_TYPE_MAP.get(media.media_type, "post"),
                    title=None,
                    body=media.caption_text or None,
                    url=f"https://www.instagram.com/p/{media.code}/",
                    publish_timestamp=pub_ts,
                    handle_id=self._handle_id,
                )
            )

        logger.info(
            "InstagramAdapter(instagrapi): %d posts for handle=%r", len(posts), handle
        )
        return posts[:limit]

    def _fetch_firecrawl(self, handle: str, limit: int) -> list[NormalisedPost]:
        assert self._scraper is not None
        page_url = f"https://www.instagram.com/{handle}/"
        markdown = self._scraper.scrape_markdown(page_url)
        raw = self._scraper.extract_posts(markdown, page_url, id_prefix="ig")
        today_utc = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return [
            NormalisedPost(
                platform_native_post_id=item["native_id"],
                post_type="post",
                title=None,
                body=item["body"],
                url=item["url"],
                publish_timestamp=today_utc,
                handle_id=self._handle_id,
            )
            for item in raw[:limit]
        ]

    def fetch_comments(self, post: NormalisedPost, limit: int) -> list[NormalisedComment]:
        return []

    def fetch_engagement(self, post: NormalisedPost) -> NormalisedEngagement:
        if self._mode != "instagrapi" or self._cl is None:
            return NormalisedEngagement()
        try:
            media = self._cl.media_info(post.platform_native_post_id)
            return NormalisedEngagement(
                likes_count=int(media.like_count or 0),
                comments_count=int(media.comment_count or 0),
                views_count=int(
                    getattr(media, "view_count", None)
                    or getattr(media, "play_count", None)
                    or 0
                ),
            )
        except Exception as exc:
            logger.debug(
                "InstagramAdapter.fetch_engagement failed for %s: %s",
                post.platform_native_post_id, exc,
            )
            return NormalisedEngagement()
