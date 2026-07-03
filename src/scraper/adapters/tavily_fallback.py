"""
tavily_fallback.py — Search-based fallback adapter using the Tavily API.

Used by TwitterAdapter and LinkedInAdapter when the primary platform API
is rate-limited or unavailable.  Returns a list of plain dicts (not
NormalisedPost objects) so the caller can decide how to map them.

Requirements covered: 11.6, 12.5, 17.5
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class TavilyFallback:
    """Search-based fallback that queries ``<platform>.com <handle>`` via Tavily.

    The Tavily client is imported lazily so the module can be imported
    even when the ``tavily-python`` package is not installed (it will only
    fail when ``search_posts`` is actually called, which the orchestrator
    avoids if ``TAVILY_API_KEY`` is absent).

    Parameters
    ----------
    (none — credentials come exclusively from the environment)

    Raises
    ------
    RuntimeError
        If ``TAVILY_API_KEY`` is absent or empty at construction time.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "TavilyFallback requires the TAVILY_API_KEY environment variable "
                "to be set and non-empty."
            )

        # Lazy import — avoids hard dependency at module load time
        from tavily import TavilyClient  # type: ignore[import]

        self._client = TavilyClient(api_key=api_key)

    def search_posts(self, handle: str, platform: str) -> list[dict[str, Any]]:
        """Search for public posts about *handle* on *platform* via Tavily.

        Logs a WARNING before every call so operators know the fallback
        path is being exercised.

        Parameters
        ----------
        handle:
            The platform handle / username to search for (e.g. ``"elonmusk"``).
        platform:
            The platform name used to build the ``site:`` query (e.g.
            ``"twitter"`` → ``"site:twitter.com elonmusk"``).

        Returns
        -------
        list[dict]
            Each dict contains:
            - ``body``           (str | None) — ``content`` from the Tavily result
            - ``url``            (str | None) — direct URL of the result
            - ``likes_count``    (int)        — always 0 (Tavily has no engagement data)
            - ``comments_count`` (int)        — always 0
            - ``shares_count``   (int)        — always 0
            - ``views_count``    (int)        — always 0
            - ``reactions_count`` (None)      — always None

            Returns an empty list on any exception from the Tavily client.
        """
        logger.warning(
            "Using Tavily fallback for platform=%r handle=%r",
            platform,
            handle,
        )

        try:
            response = self._client.search(
                query=f"site:{platform}.com {handle}",
                max_results=10,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "TavilyFallback.search_posts failed for platform=%r handle=%r: %s",
                platform,
                handle,
                exc,
            )
            return []

        results: list[dict[str, Any]] = []
        for item in response.get("results", []):
            results.append(
                {
                    "body": item.get("content"),
                    "url": item.get("url"),
                    "likes_count": 0,
                    "comments_count": 0,
                    "shares_count": 0,
                    "views_count": 0,
                    "reactions_count": None,
                }
            )
        return results
