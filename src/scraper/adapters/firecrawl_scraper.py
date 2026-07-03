"""
firecrawl_scraper.py — Shared Firecrawl-based page scraper.

Used by the LinkedIn, Facebook, Twitter/X, and Instagram adapters to render
JavaScript-heavy social media pages and extract post-like content blocks.

Firecrawl handles JS rendering, proxy rotation, and returns clean markdown,
which we then split into post-sized chunks.

Credentials: FIRECRAWL_API_KEY environment variable (required).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic constants
# ---------------------------------------------------------------------------

# Login-wall signals: if any of these appear AND the page is short, we have
# hit an authentication gate and should return no posts.
_LOGIN_SIGNALS = frozenset({
    "sign in to",
    "log in to",
    "create an account",
    "join linkedin",
    "join now to see",
    "log into facebook",
    "you must be signed",
    "sign up to see",
    "register to view",
})

# Chunk prefixes that indicate navigation, footers, or cookie banners.
_NAV_PREFIXES = (
    "home", "about", "search", "notifications", "messaging", "jobs",
    "try premium", "sign", "log in", "menu", "skip to", "© ",
    "copyright", "privacy", "terms of service", "terms of use",
    "cookie", "advertise", "help center", "accessibility",
)

_MIN_CHARS = 80    # minimum cleaned characters for a chunk to be a candidate
_MIN_WORDS = 12    # minimum word count


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class FirecrawlScraper:
    """Thin wrapper around the Firecrawl SDK for social media scraping.

    Supports both the v1 (params dict) and v2 (keyword args) SDK APIs by
    trying v2 first and falling back to v1 on TypeError.

    Parameters
    ----------
    None — reads FIRECRAWL_API_KEY from the environment at construction time.

    Raises
    ------
    RuntimeError
        If FIRECRAWL_API_KEY is absent or empty.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "FirecrawlScraper requires the FIRECRAWL_API_KEY "
                "environment variable to be set and non-empty."
            )
        # Lazy import so missing package only errors when actually used
        try:
            from firecrawl import FirecrawlApp  # type: ignore[import]
            self._client = FirecrawlApp(api_key=api_key)
        except ImportError as exc:
            raise ImportError(
                "firecrawl-py is not installed. Run: pip install firecrawl-py"
            ) from exc

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def scrape_markdown(self, url: str) -> str:
        """Scrape *url* with Firecrawl and return the page as markdown.

        Returns an empty string on any network or API error so the caller
        can gracefully return zero posts.
        """
        logger.info("FirecrawlScraper: scraping %r", url)
        try:
            # Try v2 SDK API first (keyword argument style)
            try:
                result = self._client.scrape_url(url, formats=["markdown"])
            except TypeError:
                # v1 SDK API uses a params dict
                result = self._client.scrape_url(
                    url, params={"formats": ["markdown"]}
                )

            # Result can be a dict (v1) or a response object (v2)
            if isinstance(result, dict):
                return result.get("markdown", "") or ""
            return getattr(result, "markdown", "") or ""

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "FirecrawlScraper.scrape_markdown failed for %r: %s", url, exc
            )
            return ""

    # ------------------------------------------------------------------
    # Post extraction
    # ------------------------------------------------------------------

    def extract_posts(
        self,
        markdown: str,
        page_url: str,
        id_prefix: str,
    ) -> list[dict[str, Any]]:
        """Extract post-like text chunks from page markdown.

        Parameters
        ----------
        markdown:
            The raw markdown returned by :meth:`scrape_markdown`.
        page_url:
            The canonical URL that was scraped — stored as the post URL.
        id_prefix:
            Short string prepended to each content-hash ID (e.g. ``"li"``,
            ``"fb"``, ``"tw"``).  Makes IDs platform-specific and avoids
            collisions when the same text appears on two platforms.

        Returns
        -------
        list[dict]
            Each dict has keys:
            - ``native_id`` (str) — stable content-hash-based identifier
            - ``body``      (str) — cleaned post text, ≤ 10 000 chars
            - ``url``       (str) — page_url
        """
        if not markdown or len(markdown) < 200:
            logger.warning(
                "FirecrawlScraper: too little content for %r (%d chars)",
                page_url,
                len(markdown),
            )
            return []

        # --- Login-wall detection -------------------------------------------
        lower_md = markdown.lower()
        if any(sig in lower_md for sig in _LOGIN_SIGNALS) and len(markdown) < 6000:
            logger.warning(
                "FirecrawlScraper: login wall detected at %r — 0 posts extracted.",
                page_url,
            )
            return []

        # --- Split into candidate chunks ------------------------------------
        # Prefer platform-style horizontal-rule separators; fall back to
        # multiple blank lines which most social pages use between post cards.
        if re.search(r"\n(?:---|===|\*\*\*)\n", markdown):
            raw_chunks = re.split(r"\n(?:---|===|\*\*\*)\n", markdown)
        else:
            raw_chunks = re.split(r"\n{3,}", markdown)

        # Break up any oversized chunks further on double newlines
        chunks: list[str] = []
        for chunk in raw_chunks:
            if len(chunk) > 2500:
                chunks.extend(re.split(r"\n{2,}", chunk))
            else:
                chunks.append(chunk)

        # --- Score and collect posts ----------------------------------------
        posts: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for raw_chunk in chunks:
            text = _clean_chunk(raw_chunk)

            if len(text) < _MIN_CHARS:
                continue
            if len(text.split()) < _MIN_WORDS:
                continue

            text_lower = text.lower()

            # Skip navigation / footer chunks
            if any(text_lower.startswith(p) for p in _NAV_PREFIXES):
                continue

            # Skip pure engagement-counter lines ("45 reactions • 12 comments")
            if re.match(
                r"^[\d\s,•·]+(?:reaction|like|comment|share|retweet|view|repost)s?",
                text_lower,
            ):
                continue

            # Stable, deterministic ID from the first 300 chars of content
            native_id = (
                f"{id_prefix}_{hashlib.sha1(text[:300].encode()).hexdigest()[:20]}"
            )
            if native_id in seen_ids:
                continue
            seen_ids.add(native_id)

            posts.append({
                "native_id": native_id,
                "body": text[:10000],
                "url": page_url,
            })

        logger.info(
            "FirecrawlScraper: extracted %d posts from %r",
            len(posts),
            page_url,
        )
        return posts


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clean_chunk(raw: str) -> str:
    """Strip markdown syntax and normalise whitespace from a text chunk."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", raw)            # remove images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links → text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"[*_`|>~]", "", text)                  # inline markup
    text = re.sub(r"https?://\S+", "", text)               # bare URLs
    text = re.sub(r"\s+", " ", text).strip()
    return text
