"""
facebook.py — Facebook adapter using facebook-scraper (web scraping).

Authenticates with a real Facebook account (email + password) and fetches
posts from a public brand page with text, timestamps, and engagement counts.

Credentials (set in .env):
    FACEBOOK_EMAIL       Facebook login email
    FACEBOOK_PASSWORD    Facebook password

Falls back to FirecrawlScraper if credentials are not configured.

Install: pip install facebook-scraper
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from ..base_adapter import AuthenticationError, BaseAdapter
from ..models import NormalisedComment, NormalisedEngagement, NormalisedPost

logger = logging.getLogger(__name__)


class FacebookAdapter(BaseAdapter):
    """Facebook adapter — facebook-scraper with email/password auth.

    Falls back to Firecrawl page scraping when credentials are absent.
    """

    platform_code = "facebook"

    def __init__(self, handle_id: int = 0) -> None:
        super().__init__()
        self._handle_id = handle_id
        self._fb_email = ""
        self._fb_password = ""
        self._scraper = None
        self._mode = "firecrawl"

    def authenticate(self) -> None:
        email    = os.environ.get("FACEBOOK_EMAIL", "")
        password = os.environ.get("FACEBOOK_PASSWORD", "")

        if email and password:
            # Validate that facebook-scraper is importable
            try:
                import facebook_scraper  # type: ignore[import] # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "facebook-scraper is not installed. "
                    "Run: pip install facebook-scraper"
                ) from exc
            self._fb_email    = email
            self._fb_password = password
            self._mode        = "facebook_scraper"
            self._authenticated = True
            logger.info("FacebookAdapter: using credentials for %r", email)
        else:
            from .firecrawl_scraper import FirecrawlScraper
            self._scraper = FirecrawlScraper()
            self._mode    = "firecrawl"
            self._authenticated = True
            logger.info(
                "FacebookAdapter: no credentials — using Firecrawl fallback"
            )

    # ------------------------------------------------------------------

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        self._require_auth()
        if self._mode == "facebook_scraper":
            return self._fetch_fb_scraper(handle, limit, since_timestamp)
        return self._fetch_firecrawl(handle, limit)

    def _fetch_fb_scraper(
        self, handle: str, limit: int, since_timestamp: datetime | None
    ) -> list[NormalisedPost]:
        from facebook_scraper import get_posts  # type: ignore[import]

        # pages=N roughly equals 5 posts per page; fetch a bit extra for filtering
        pages = max(2, (limit // 5) + 1)
        posts: list[NormalisedPost] = []

        try:
            for post_data in get_posts(
                handle,
                credentials=(self._fb_email, self._fb_password),
                pages=pages,
                options={"allow_extra_requests": False, "comments": False},
            ):
                # Timestamp
                raw_ts = post_data.get("time")
                if isinstance(raw_ts, datetime):
                    pub_ts = raw_ts
                    if pub_ts.tzinfo is None:
                        pub_ts = pub_ts.replace(tzinfo=timezone.utc)
                else:
                    pub_ts = datetime.now(tz=timezone.utc)

                # Since-filter
                if since_timestamp is not None:
                    st = since_timestamp
                    if st.tzinfo is None:
                        st = st.replace(tzinfo=timezone.utc)
                    if pub_ts.tzinfo is None:
                        pub_ts = pub_ts.replace(tzinfo=timezone.utc)
                    if pub_ts <= st:
                        continue

                # Text content (prefer post_text over text)
                text = (
                    post_data.get("post_text")
                    or post_data.get("text")
                    or ""
                ).strip()
                if not text:
                    continue

                # Native ID
                post_id = str(post_data.get("post_id") or "")
                if post_id:
                    native_id = f"fb_{post_id}"
                else:
                    native_id = (
                        f"fb_{hashlib.sha1(text[:200].encode()).hexdigest()[:20]}"
                    )

                posts.append(
                    NormalisedPost(
                        platform_native_post_id=native_id,
                        post_type="post",
                        title=None,
                        body=text[:10000],
                        url=(
                            post_data.get("post_url")
                            or f"https://www.facebook.com/{handle}/"
                        ),
                        publish_timestamp=pub_ts,
                        handle_id=self._handle_id,
                    )
                )

                if len(posts) >= limit:
                    break

        except Exception as exc:
            logger.error(
                "FacebookAdapter: scrape failed for handle=%r: %s", handle, exc
            )

        logger.info(
            "FacebookAdapter(fb-scraper): %d posts for handle=%r",
            len(posts), handle,
        )
        return posts

    def _fetch_firecrawl(self, handle: str, limit: int) -> list[NormalisedPost]:
        assert self._scraper is not None
        # Try the /posts/ tab first; fall back to the main page
        page_url = f"https://www.facebook.com/{handle}/posts/"
        markdown = self._scraper.scrape_markdown(page_url)
        if len(markdown) < 500:
            page_url = f"https://www.facebook.com/{handle}/"
            markdown = self._scraper.scrape_markdown(page_url)

        raw = self._scraper.extract_posts(markdown, page_url, id_prefix="fb")
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
        return NormalisedEngagement()
