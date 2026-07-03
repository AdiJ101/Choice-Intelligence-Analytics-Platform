"""
linkedin.py — LinkedIn adapter using linkedin-api (Voyager internal API).

Authenticates with a real LinkedIn account (email + password) and fetches
company updates (posts) directly from LinkedIn's Voyager API.  Returns
actual post text, timestamps, and post URLs.

Credentials (set in .env):
    LINKEDIN_USERNAME    LinkedIn login email
    LINKEDIN_PASSWORD    LinkedIn password

Falls back to FirecrawlScraper if credentials are not configured.

Install: pip install linkedin-api
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from ..base_adapter import AuthenticationError, BaseAdapter
from ..models import NormalisedComment, NormalisedEngagement, NormalisedPost

logger = logging.getLogger(__name__)


class LinkedInAdapter(BaseAdapter):
    """LinkedIn adapter — linkedin-api (Voyager) with email/password auth.

    Falls back to Firecrawl page scraping when credentials are absent.
    """

    platform_code = "linkedin"

    def __init__(self, handle_id: int = 0) -> None:
        super().__init__()
        self._handle_id = handle_id
        self._api = None
        self._scraper = None
        self._mode = "firecrawl"

    def authenticate(self) -> None:
        username = os.environ.get("LINKEDIN_USERNAME", "")
        password = os.environ.get("LINKEDIN_PASSWORD", "")

        if username and password:
            self._authenticate_linkedin_api(username, password)
        else:
            self._authenticate_firecrawl()

    def _authenticate_linkedin_api(self, username: str, password: str) -> None:
        try:
            from linkedin_api import Linkedin  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "linkedin-api is not installed. Run: pip install linkedin-api"
            ) from exc

        try:
            # authenticate=True forces a fresh login and caches cookies
            self._api = Linkedin(username, password, authenticate=True)
            self._mode = "linkedin_api"
            self._authenticated = True
            logger.info("LinkedInAdapter: logged in as %r", username)
        except Exception as exc:
            logger.error(
                "LinkedInAdapter: login failed for %r: %s", username, exc
            )
            raise AuthenticationError("linkedin", "LINKEDIN_PASSWORD") from exc

    def _authenticate_firecrawl(self) -> None:
        from .firecrawl_scraper import FirecrawlScraper
        self._scraper = FirecrawlScraper()
        self._mode = "firecrawl"
        self._authenticated = True
        logger.info(
            "LinkedInAdapter: no credentials — using Firecrawl fallback"
        )

    # ------------------------------------------------------------------

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        self._require_auth()
        if self._mode == "linkedin_api":
            return self._fetch_linkedin_api(handle, limit, since_timestamp)
        return self._fetch_firecrawl(handle, limit)

    def _fetch_linkedin_api(
        self, handle: str, limit: int, since_timestamp: datetime | None
    ) -> list[NormalisedPost]:
        assert self._api is not None
        try:
            updates = self._api.get_company_updates(handle, results=limit)
        except Exception as exc:
            logger.error(
                "LinkedInAdapter: get_company_updates failed for %r: %s",
                handle, exc,
            )
            return []

        posts: list[NormalisedPost] = []
        for update in (updates or []):
            text = _extract_update_text(update)
            if not text or len(text.strip()) < 20:
                continue

            pub_ts = _extract_update_timestamp(update)
            if since_timestamp is not None:
                st = since_timestamp
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                if pub_ts.tzinfo is None:
                    pub_ts = pub_ts.replace(tzinfo=timezone.utc)
                if pub_ts <= st:
                    continue

            # Prefer the URN-based key; fall back to content hash
            update_key = update.get("updateKey") or update.get("entityUrn", "")
            if update_key:
                native_id = update_key.replace(":", "_")[:255]
            else:
                native_id = f"li_{hashlib.sha1(text[:200].encode()).hexdigest()[:20]}"

            posts.append(
                NormalisedPost(
                    platform_native_post_id=native_id,
                    post_type="post",
                    title=None,
                    body=text[:10000],
                    url=f"https://www.linkedin.com/company/{handle}/posts/",
                    publish_timestamp=pub_ts,
                    handle_id=self._handle_id,
                )
            )

        logger.info(
            "LinkedInAdapter(api): %d posts for handle=%r", len(posts), handle
        )
        return posts[:limit]

    def _fetch_firecrawl(self, handle: str, limit: int) -> list[NormalisedPost]:
        assert self._scraper is not None
        page_url = (
            f"https://www.linkedin.com/company/{handle}/posts/?feedView=all"
        )
        markdown = self._scraper.scrape_markdown(page_url)
        raw = self._scraper.extract_posts(markdown, page_url, id_prefix="li")
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
        # linkedin-api does not expose per-post engagement counts
        return NormalisedEngagement()


# ---------------------------------------------------------------------------
# Helpers — LinkedIn update parsing
# The Voyager API returns deeply nested dicts that change structure over time.
# These helpers try several known paths before giving up.
# ---------------------------------------------------------------------------

def _extract_update_text(update: dict) -> str:
    """Extract the post body text from a LinkedIn Voyager update dict."""
    try:
        # Path 1: standard commentary (most common)
        v2 = (
            update.get("value", {})
                  .get("com.linkedin.voyager.feed.render.UpdateV2", {})
        )
        commentary = v2.get("commentary", {})
        if commentary:
            text = commentary.get("text", {})
            if isinstance(text, dict):
                return text.get("text", "")
            return str(text)

        # Path 2: subject (reshares)
        subject = v2.get("subject", {})
        if subject:
            inner = subject.get(
                "com.linkedin.voyager.feed.render.UpdateV2", {}
            )
            inner_text = (
                inner.get("commentary", {})
                     .get("text", {})
            )
            if isinstance(inner_text, dict):
                return inner_text.get("text", "")
            return str(inner_text) if inner_text else ""

        # Path 3: simpler flat structure (older API responses)
        if "text" in update:
            return str(update["text"])
    except Exception:
        pass
    return ""


def _extract_update_timestamp(update: dict) -> datetime:
    """Extract a UTC datetime from a LinkedIn update dict."""
    try:
        # createdAt or created.time are milliseconds since epoch
        for key in ("createdAt", "created"):
            val = update.get(key)
            if val is None:
                continue
            if isinstance(val, int):
                return datetime.fromtimestamp(val / 1000, tz=timezone.utc)
            if isinstance(val, dict) and "time" in val:
                return datetime.fromtimestamp(val["time"] / 1000, tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(tz=timezone.utc)
